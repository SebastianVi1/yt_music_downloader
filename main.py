#!/usr/bin/env python3
from __future__ import annotations

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


def main() -> None:
    _setup_signal_handlers()
    console.print(BANNER, style="bold red")
    console.print(Panel.fit(
        f"Downloads will be saved to: [bold]{config.output_dir}[/]",
        border_style="red",
    ))

    _check_ffmpeg()

    while True:
        action = questionary.select(
            "What would you like to do?",
            choices=[
                questionary.Separator("─" * 40),
                questionary.Choice("🎵  Search and download tracks", "search"),
                questionary.Choice("🔗  Download by URL", "url"),
                questionary.Choice("❤️   Download liked songs", "liked"),
                questionary.Choice("📋  Download playlist by ID", "playlist_id"),
                questionary.Choice("⚙️   Settings", "settings"),
                questionary.Separator("─" * 40),
                questionary.Choice("🚪  Exit", "exit"),
            ],
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


def _handle_action(action: str) -> None:
    if action == "search":
        _search_and_download()
    elif action == "url":
        _download_by_url()
    elif action == "liked":
        _download_liked()
    elif action == "playlist_id":
        _download_playlist_by_id()
    elif action == "settings":
        _settings_menu()


def _search_and_download() -> None:
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


def _download_by_url() -> None:
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
            "   • youtube.com/watch?v=...",
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


def _download_liked() -> None:
    console.print("\n🔐 Authenticating...", style="yellow")
    console.print(
        "A browser window will open for you to log in to YouTube Music.",
        style="dim",
    )

    data = ytm.get_liked_songs()
    _confirm_and_download_batch(data)


def _download_playlist_by_id() -> None:
    playlist_id = questionary.text(
        "Enter the playlist ID:",
        style=_questionary_style(),
    ).unsafe_ask()

    if not playlist_id or not playlist_id.strip():
        return

    console.print("\n📦 Fetching playlist...", style="yellow")
    data = ytm.get_playlist_tracks(playlist_id.strip())
    _confirm_and_download_batch(data)


def _settings_menu() -> None:
    while True:
        choice = questionary.select(
            "Settings",
            choices=[
                questionary.Choice(
                    f"📁 Output directory: {config.output_dir}", "output_dir"
                ),
                questionary.Choice(
                    f"🎵 Audio format: {config.audio_format} ({config.audio_quality}k)",
                    "format",
                ),
                questionary.Choice(
                    f"⚡ Max concurrent downloads: {config.max_concurrent_downloads}",
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
                console.print(f"✅ Output directory set to: {config.output_dir}", style="green")

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
                    f"✅ Format set to: {config.audio_format} @ {config.audio_quality}kbps",
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
                    f"✅ Max concurrent downloads set to: {config.max_concurrent_downloads}",
                    style="green",
                )


def _confirm_and_download_batch(data: dict[str, Any]) -> None:
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
    total = len(tracks)
    console.print(f"\n⬇️  Downloading {total} track(s)...\n", style="bold")

    start_time = time.time()
    completed, skipped, failed = downloader.download(tracks, album_title=album_title)
    elapsed = time.time() - start_time

    console.print(f"\n{'━' * 50}")
    console.print(
        f"✅ Completed: {completed}  ⏭️  Skipped: {skipped}  ❌ Failed: {len(failed)}",
        style="bold",
    )
    console.print(f"⏱️  Time: {elapsed:.1f}s", style="dim")

    if failed:
        console.print("\n❌ Failed downloads:", style="red")
        for name in failed[:10]:
            console.print(f"   • {name}", style="red")
        if len(failed) > 10:
            console.print(f"   ... and {len(failed) - 10} more", style="red")


def _questionary_style() -> questionary.Style:
    return questionary.Style(_STYLE_RULES)


def _setup_signal_handlers() -> None:
    def _handle_interrupt(signum: int, frame: Any) -> None:
        console.print("\n\n👋 Goodbye!", style="bold")
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_interrupt)


def _check_ffmpeg() -> None:
    import shutil
    if shutil.which("ffmpeg") is None:
        console.print(Panel.fit(
            "[bold yellow]ffmpeg not found[/] -- downloading in [bold]M4A[/] format "
            "(no MP3 conversion, no metadata).\n"
            "[dim]Install ffmpeg for MP3:  sudo apt install ffmpeg[/]",
            border_style="yellow",
            title="Notice",
        ))


if __name__ == "__main__":
    main()
