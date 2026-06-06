#!/usr/bin/env python3
"""
Interactive CLI for searching, browsing, and downloading music from
YouTube Music.

Authentication uses **browser headers**: you copy the request headers
from a logged-in YouTube Music browser session and paste them once.
Credentials are saved to ``~/.config/ytmusic/browser.json`` and reused
on subsequent runs.
"""

from __future__ import annotations

import shutil
import signal
import sys
import time
from pathlib import Path
from typing import Any

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import config
from downloader import downloader
from ytmusic_client import client as ytm

console = Console()

BANNER = """
██╗   ██╗████████╗███╗   ███╗██╗   ██╗███████╗██╗ ██████╗
╚██╗ ██╔╝╚══██╔══╝████╗ ████║██║   ██║██╔════╝██║██╔════╝
 ╚████╔╝    ██║   ██╔████╔██║██║   ██║███████╗██║██║
  ╚██╔╝     ██║   ██║╚██╔╝██║██║   ██║╚════██║██║██║
   ██║      ██║   ██║ ╚═╝ ██║╚██████╔╝███████║██║╚██████╗
   ╚═╝      ╚═╝   ╚═╝     ╚═╝ ╚═════╝ ╚══════╝╚═╝ ╚═════╝
"""

_STYLE_RULES: list[tuple[str, str]] = [
    ("qmark", "fg:#FF0000 bold"),
    ("selected", "fg:#FF0000 bold"),
    ("pointer", "fg:#FF0000 bold"),
    ("instruction", ""),
]


# ======================================================================
# Main loop
# ======================================================================


def main() -> None:
    """Entry point – print banner, then run the interactive menu loop."""
    _setup_signal_handlers()
    console.print(BANNER, style="bold red")
    console.print(Panel.fit(
        f"Downloads will be saved to: [bold]{config.output_dir}[/]",
        border_style="red",
    ))
    _check_ffmpeg()

    while True:
        _show_auth_status()
        action = questionary.select(
            "What would you like to do?",
            choices=_build_main_menu(),
            style=_questionary_style(),
        ).unsafe_ask()

        if action is None or action == "exit":
            console.print("\n👋 Goodbye!", style="bold")
            break

        try:
            _handle_action(action)
        except KeyboardInterrupt:
            console.print("\n\n⚠️  Operation cancelled.", style="yellow")
        except Exception as exc:
            console.print(f"\n❌ Error: {exc}", style="bold red")

        console.print()


def _show_auth_status() -> None:
    """Display whether the user is logged in."""
    if ytm.is_authenticated:
        console.print(
            "🔐  [bold green]Logged in to YouTube Music[/] "
            "(browser headers)\n"
        )
    else:
        console.print(
            "🔓  [dim]Not logged in[/] — login to access your library\n"
        )


def _build_main_menu() -> list[Any]:
    """
    Build the main menu, adapting it based on whether the user is
    currently authenticated.
    """
    choices: list[Any] = [
        questionary.Separator("─" * 40),
        questionary.Choice("🎵  Search and download tracks", "search"),
        questionary.Choice("🔗  Download by URL", "url"),
    ]

    if ytm.is_authenticated:
        choices += [
            questionary.Choice("📂  My Library", "library"),
            questionary.Choice("📋  Download playlist by ID", "playlist_id"),
            questionary.Choice("⚙️   Settings", "settings"),
            questionary.Separator("─" * 40),
            questionary.Choice("🔓  Logout", "logout"),
        ]
    else:
        choices += [
            questionary.Choice("📋  Download playlist by ID", "playlist_id"),
            questionary.Choice("🔐  Login to YouTube Music", "login"),
            questionary.Choice("⚙️   Settings", "settings"),
            questionary.Separator("─" * 40),
        ]

    choices.append(questionary.Choice("🚪  Exit", "exit"))
    return choices


def _handle_action(action: str) -> None:
    """Dispatch a main-menu selection to the appropriate handler."""
    handlers = {
        "search": _search_and_download,
        "url": _download_by_url,
        "library": _library_menu,
        "playlist_id": _download_playlist_by_id,
        "login": _login,
        "logout": _logout,
        "settings": _settings_menu,
    }
    handler = handlers.get(action)
    if handler:
        handler()


# ======================================================================
# Authentication
# ======================================================================


def _login() -> None:
    """
    Guide the user through the browser-header login flow.

    The user opens YouTube Music in their browser, uses F12 →
    Network tab to find a ``/browse`` POST request, copies the
    request headers, and pastes them here.  The headers are parsed
    and saved for future sessions.
    """
    instructions = (
        "\n[bold]Browser Header Authentication[/]\n\n"
        "1. Open [link=https://music.youtube.com]https://music.youtube.com[/] "
        "and sign in\n"
        "2. Press [bold]F12[/] → [bold]Network[/] tab\n"
        "3. In the filter bar type [bold]browse[/] to show only API requests\n"
        "4. Look for a [bold]POST[/] request (Status 200) at path "
        "[bold]/browse[/]\n"
        "5. Right-click it → [bold]Copy[/] → [bold]Copy request headers[/]\n"
        "   ([italic]Chrome:[/] click the request, scroll to "
        "'Request Headers',\n"
        "   select everything from [bold]accept: */*[/] through "
        "[bold]Cookie:[/])\n"
        "6. Paste the copied text below"
    )
    console.print(Panel(
        instructions,
        title="Setup Instructions",
        border_style="red",
    ))

    headers = questionary.text(
        "Paste browser request headers here:",
        style=_questionary_style(),
    ).unsafe_ask()

    if not headers or not headers.strip():
        console.print("Login cancelled.", style="yellow")
        return

    console.print("Saving credentials...", style="yellow")
    ytm.login(headers.strip())
    console.print(
        "✅ Successfully logged in with browser headers!",
        style="bold green",
    )


def _logout() -> None:
    """Delete stored credentials after confirmation."""
    confirmed = questionary.confirm(
        "Are you sure you want to log out?",
        default=True,
        style=_questionary_style(),
    ).unsafe_ask()
    if confirmed:
        ytm.logout()
        console.print("✅ Logged out.", style="green")


# ======================================================================
# Library menu (authenticated only)
# ======================================================================


def _library_menu() -> None:
    """Sub-menu for browsing the authenticated user's personal library."""
    while True:
        choice = questionary.select(
            "My Library",
            choices=[
                questionary.Separator("─" * 40),
                questionary.Choice("📋  My Playlists", "playlists"),
                questionary.Choice("💿  My Albums", "albums"),
                questionary.Choice("❤️   Liked Songs", "liked"),
                questionary.Choice("🎶  Library Songs", "songs"),
                questionary.Separator("─" * 40),
                questionary.Choice("↩   Back", "back"),
            ],
            style=_questionary_style(),
        ).unsafe_ask()

        if choice is None or choice == "back":
            break
        try:
            _handle_library_action(choice)
        except KeyboardInterrupt:
            console.print("\n\n⚠️  Operation cancelled.", style="yellow")
        except Exception as exc:
            console.print(f"\n❌ Error: {exc}", style="bold red")
        console.print()


def _handle_library_action(choice: str) -> None:
    """Dispatch a library sub-menu item."""
    dispatch = {
        "playlists": _download_library_playlists,
        "albums": _download_library_albums,
        "liked": _download_liked,
        "songs": _download_library_songs,
    }
    handler = dispatch.get(choice)
    if handler:
        handler()


def _download_library_playlists() -> None:
    """Fetch user's playlists, let them pick which ones to download."""
    console.print("\n📦 Fetching your playlists...", style="yellow")
    playlists = ytm.get_library_playlists()
    if not playlists:
        console.print("No playlists found in your library.", style="yellow")
        return

    _show_playlist_table(playlists)
    selected = questionary.checkbox(
        "Select playlists to download. [Space] to select, [Enter] to confirm:",
        choices=[
            questionary.Choice(title=pl["title"], value=i)
            for i, pl in enumerate(playlists)
        ],
        style=_questionary_style(),
    ).unsafe_ask()

    if not selected:
        console.print("No playlists selected.", style="yellow")
        return

    for idx in selected:
        pl = playlists[idx]
        console.print(
            f"\n📦 Fetching [bold]'{pl['title']}'[/]...",
            style="yellow",
        )
        try:
            data = ytm.get_playlist_tracks(pl["playlist_id"])
            data["title"] = pl["title"]
            _confirm_and_download_batch(data)
        except Exception as exc:
            console.print(
                f"❌ Failed to fetch '{pl['title']}': {exc}",
                style="red",
            )


def _download_library_albums() -> None:
    """Fetch user's saved albums, let them pick which ones to download."""
    console.print("\n📦 Fetching your albums...", style="yellow")
    albums = ytm.get_library_albums()
    if not albums:
        console.print("No albums found in your library.", style="yellow")
        return

    _show_album_table(albums)
    selected = questionary.checkbox(
        "Select albums to download. [Space] to select, [Enter] to confirm:",
        choices=[
            questionary.Choice(
                title=f"{alb['artist']} — {alb['title']}",
                value=i,
            )
            for i, alb in enumerate(albums)
        ],
        style=_questionary_style(),
    ).unsafe_ask()

    if not selected:
        console.print("No albums selected.", style="yellow")
        return

    for idx in selected:
        alb = albums[idx]
        console.print(
            f"\n📦 Fetching album [bold]'{alb['title']}'[/]...",
            style="yellow",
        )
        try:
            data = ytm.get_album_tracks(alb["browse_id"])
            _confirm_and_download_batch(data)
        except Exception as exc:
            console.print(
                f"❌ Failed to fetch '{alb['title']}': {exc}",
                style="red",
            )


def _download_library_songs() -> None:
    """Fetch all uploaded / purchased songs from the user's library."""
    console.print("\n📦 Fetching your library songs...", style="yellow")
    data = ytm.get_library_songs()
    _confirm_and_download_batch(data)


# ======================================================================
# Search
# ======================================================================


def _search_and_download() -> None:
    """Search for tracks and let the user pick which ones to download."""
    query = questionary.text(
        "Search for a song, artist, or album:",
        style=_questionary_style(),
    ).unsafe_ask()

    if not query or not query.strip():
        return

    console.print(f"\n🔍 Searching for [bold]'{query}'[/]...", style="yellow")
    results = ytm.search(query.strip())

    if not results:
        console.print("❌ No results found.", style="red")
        return

    choices = [
        questionary.Choice(
            title=f"[{t['artist']}] {t['title']}",
            value=i,
        )
        for i, t in enumerate(results)
    ]

    selected = questionary.checkbox(
        f"Found {len(results)} tracks. Use [Space] to select, [Enter] to confirm:",
        choices=choices,
        style=_questionary_style(),
    ).unsafe_ask()

    if not selected:
        console.print("No tracks selected.", style="yellow")
        return

    tracks = [results[i] for i in selected]
    _download_tracks(tracks)


# ======================================================================
# URL-based download
# ======================================================================


def _download_by_url() -> None:
    """Parse a YouTube Music URL and download the track / playlist / album."""
    url = questionary.text(
        "Paste YouTube Music URL (playlist, album, or track):",
        style=_questionary_style(),
    ).unsafe_ask()

    if not url or not url.strip():
        return

    parsed = ytm.parse_url(url.strip())
    if not parsed:
        console.print("❌ Could not parse URL. Supported formats:", style="red")
        console.print(
            "   • music.youtube.com/watch?v=...\n"
            "   • music.youtube.com/playlist?list=...\n"
            "   • music.youtube.com/browse/...\n"
            "   • youtube.com/watch?v=...\n"
            "   • youtube.com/playlist?list=...",
            style="dim",
        )
        return

    console.print(f"\n📦 Fetching [bold]{parsed['type']}[/]...", style="yellow")

    if parsed["type"] == "track":
        track = ytm.get_song_info(parsed["id"])
        _download_tracks([track])
    elif parsed["type"] == "playlist":
        data = ytm.get_playlist_tracks(parsed["id"])
        _confirm_and_download_batch(data)
    elif parsed["type"] == "album":
        data = ytm.get_album_tracks(parsed["id"])
        _confirm_and_download_batch(data)


# ======================================================================
# Other entry points
# ======================================================================


def _download_liked() -> None:
    """Fetch and download liked ("thumbs-up") songs."""
    console.print("\n📦 Fetching your liked songs...", style="yellow")
    data = ytm.get_liked_songs()
    _confirm_and_download_batch(data)


def _download_playlist_by_id() -> None:
    """Download a playlist by its raw ID string."""
    playlist_id = questionary.text(
        "Enter the playlist ID:",
        style=_questionary_style(),
    ).unsafe_ask()

    if not playlist_id or not playlist_id.strip():
        return

    console.print("\n📦 Fetching playlist...", style="yellow")
    data = ytm.get_playlist_tracks(playlist_id.strip())
    _confirm_and_download_batch(data)


# ======================================================================
# Settings
# ======================================================================


def _settings_menu() -> None:
    """Interactive menu to change output directory, format, quality, etc."""
    while True:
        choice = questionary.select(
            "Settings",
            choices=[
                questionary.Choice(
                    f"📁 Output directory: {config.output_dir}",
                    "output_dir",
                ),
                questionary.Choice(
                    f"🎵 Audio format: {config.audio_format} "
                    f"({config.audio_quality}k)",
                    "format",
                ),
                questionary.Choice(
                    f"⚡ Max concurrent downloads: "
                    f"{config.max_concurrent_downloads}",
                    "concurrent",
                ),
                questionary.Separator(),
                questionary.Choice("↩  Back", "back"),
            ],
            style=_questionary_style(),
        ).unsafe_ask()

        if choice is None or choice == "back":
            break

        if choice == "output_dir":
            new_dir = questionary.text(
                "Enter new output directory:",
                default=str(config.output_dir),
                style=_questionary_style(),
            ).unsafe_ask()
            if new_dir:
                config.output_dir = Path(new_dir.strip()).expanduser()
                config.output_dir.mkdir(parents=True, exist_ok=True)
                console.print(
                    f"✅ Output directory set to: {config.output_dir}",
                    style="green",
                )

        elif choice == "format":
            fmt = questionary.select(
                "Choose audio format:",
                choices=["mp3", "m4a", "opus", "flac"],
                default=config.audio_format,
                style=_questionary_style(),
            ).unsafe_ask()
            if fmt:
                config.audio_format = fmt
                qual = questionary.select(
                    "Choose quality (kbps):",
                    choices=["128", "192", "256", "320"],
                    default=config.audio_quality,
                    style=_questionary_style(),
                ).unsafe_ask()
                if qual:
                    config.audio_quality = qual
                console.print(
                    f"✅ Format set to: {config.audio_format} "
                    f"@ {config.audio_quality}kbps",
                    style="green",
                )

        elif choice == "concurrent":
            val = questionary.text(
                "Max concurrent downloads (1-10):",
                default=str(config.max_concurrent_downloads),
                validate=lambda v: v.isdigit() and 1 <= int(v) <= 10,
                style=_questionary_style(),
            ).unsafe_ask()
            if val:
                config.max_concurrent_downloads = int(val)
                console.print(
                    f"✅ Max concurrent downloads set to: "
                    f"{config.max_concurrent_downloads}",
                    style="green",
                )


# ======================================================================
# Download helpers
# ======================================================================


def _confirm_and_download_batch(data: dict[str, Any]) -> None:
    """Show a preview table and ask for confirmation before downloading."""
    tracks = data["tracks"]
    title = data["title"]
    total = data["track_count"]

    if not tracks:
        console.print(f"❌ No tracks found in '{title}'.", style="red")
        return

    table = Table(title=f"\n{title}", border_style="red")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title")
    table.add_column("Artist")
    for i, t in enumerate(tracks[:15], 1):
        table.add_row(str(i), t["title"], t["artist"])
    if total > 15:
        table.add_row("...", f"... and {total - 15} more", "")
    console.print(table)

    confirmed = questionary.confirm(
        f"Download {total} tracks to {config.output_dir}?",
        default=True,
        style=_questionary_style(),
    ).unsafe_ask()

    if not confirmed:
        console.print("Cancelled.", style="yellow")
        return

    _download_tracks(tracks, album_title=title)


def _download_tracks(
    tracks: list[dict[str, Any]],
    album_title: str = "",
) -> None:
    """Download a list of tracks concurrently and display a summary."""
    total = len(tracks)
    console.print(f"\n⬇️  Downloading {total} track(s)...\n", style="bold")

    start_time = time.time()
    completed, skipped, failed = downloader.download(
        tracks,
        album_title=album_title,
    )
    elapsed = time.time() - start_time

    console.print(f"\n{'━' * 50}")
    console.print(
        f"✅ Completed: {completed}  ⏭️  Skipped: {skipped}  "
        f"❌ Failed: {len(failed)}",
        style="bold",
    )
    console.print(f"⏱️  Time: {elapsed:.1f}s", style="dim")

    if failed:
        console.print("\n❌ Failed downloads:", style="red")
        for name in failed[:10]:
            console.print(f"   • {name}", style="red")
        if len(failed) > 10:
            console.print(f"   ... and {len(failed) - 10} more", style="red")


def _show_playlist_table(playlists: list[dict[str, Any]]) -> None:
    """Render a rich table listing the user's playlists."""
    table = Table(title="\nYour Playlists", border_style="red")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title")
    table.add_column("Tracks", justify="right")
    for i, pl in enumerate(playlists, 1):
        table.add_row(str(i), pl["title"], str(pl.get("track_count", "?")))
    console.print(table)


def _show_album_table(albums: list[dict[str, Any]]) -> None:
    """Render a rich table listing the user's saved albums."""
    table = Table(title="\nYour Albums", border_style="red")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title")
    table.add_column("Artist")
    table.add_column("Year", justify="right")
    for i, alb in enumerate(albums, 1):
        table.add_row(
            str(i), alb["title"], alb["artist"], str(alb.get("year", ""))
        )
    console.print(table)


# ======================================================================
# Utility
# ======================================================================


def _questionary_style() -> questionary.Style:
    """Return the shared red-themed questionary style."""
    return questionary.Style(_STYLE_RULES)


def _setup_signal_handlers() -> None:
    """Catch Ctrl-C to exit cleanly."""

    def _handle_interrupt(signum: int, frame: Any) -> None:
        console.print("\n\n👋 Goodbye!", style="bold")
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_interrupt)


def _check_ffmpeg() -> None:
    """
    Warn if ``ffmpeg`` is missing (downloads will fall back to native
    M4A without post-processing or embedded metadata).
    """
    if shutil.which("ffmpeg") is None:
        if sys.platform == "win32":
            hint = "winget install Gyan.FFmpeg"
        else:
            hint = "sudo apt install ffmpeg"
        console.print(Panel.fit(
            "[bold yellow]ffmpeg not found[/] -- downloading in "
            "[bold]M4A[/] format (no MP3 conversion, no metadata).\n"
            f"[dim]Install ffmpeg:  {hint}[/]",
            border_style="yellow",
            title="Notice",
        ))


if __name__ == "__main__":
    main()
