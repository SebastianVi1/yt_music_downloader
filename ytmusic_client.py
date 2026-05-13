"""
Wrapper around the `ytmusicapi <https://github.com/sigma67/ytmusicapi>`_
library that provides a single, high-level client for all YouTube Music
operations – searching, browsing library collections, fetching
playlist/album metadata, and managing authentication.
"""

from __future__ import annotations

import re
from typing import Any

from ytmusicapi import YTMusic, setup as ytm_setup

from config import config


class YTMusicClient:
    """
    High-level client that wraps *ytmusicapi*.

    Maintains two underlying sessions:

    * ``public`` – unauthenticated, used for searches and public playlists.
    * ``auth``  – authenticated via browser headers, used for library
      operations (liked songs, personal playlists, uploads).

    Authentication uses the **browser-header** method: the user copies
    the request headers from a logged-in YouTube Music browser session
    and the app parses and stores them for subsequent requests.
    """

    def __init__(self) -> None:
        self._public: YTMusic | None = None
        self._auth: YTMusic | None = None
        self._auth_type: str = ""

    # ------------------------------------------------------------------
    # Session properties
    # ------------------------------------------------------------------

    @property
    def public(self) -> YTMusic:
        """Unauthenticated session – always available."""
        if self._public is None:
            self._public = YTMusic()
        return self._public

    @property
    def auth(self) -> YTMusic:
        """
        Authenticated session built from the stored browser headers.

        Raises ``RuntimeError`` if the user has not logged in yet.
        """
        if self._auth is None:
            if config.browser_file.exists():
                self._auth = YTMusic(str(config.browser_file))
                self._auth_type = "browser"
            else:
                raise RuntimeError(
                    "Not authenticated. Use login() first."
                )
        return self._auth

    @property
    def is_authenticated(self) -> bool:
        """``True`` when a valid browser credential file exists."""
        return config.browser_file.exists()

    @property
    def auth_method(self) -> str:
        """Human-readable name of the active authentication method."""
        return "Browser headers" if self.is_authenticated else ""

    # ------------------------------------------------------------------
    # Authentication management
    # ------------------------------------------------------------------

    def login(self, headers_raw: str) -> None:
        """
        Parse raw browser request headers and save them as
        the credential file used for all authenticated requests.

        *headers_raw* should be the full text copied from the browser's
        developer-tools Network tab (right-click → "Copy request headers"
        on a ``/browse`` POST request).
        """
        config.browser_file.parent.mkdir(parents=True, exist_ok=True)
        ytm_setup(filepath=str(config.browser_file), headers_raw=headers_raw)
        self._auth = YTMusic(str(config.browser_file))
        self._auth_type = "browser"

    def logout(self) -> None:
        """Delete the stored credential file, effectively logging out."""
        if config.browser_file.exists():
            config.browser_file.unlink()
        self._auth = None
        self._auth_type = ""

    # ------------------------------------------------------------------
    # Search & discovery
    # ------------------------------------------------------------------

    def search(self, query: str) -> list[dict[str, Any]]:
        """
        Search for songs on YouTube Music.

        Returns up to 20 normalised track dicts, each with keys
        ``title``, ``artist``, ``album``, ``video_id``, and ``duration``.
        """
        results = self.public.search(query, filter="songs", limit=20)
        return self._normalise_tracks(results)

    def get_song_info(self, video_id: str) -> dict[str, Any]:
        """
        Fetch metadata for a single track by its YouTube ``video_id``.

        Returns a dict with ``title``, ``artist``, ``video_id``, etc.
        """
        try:
            info = self.public.get_song(video_id)
            video_details = info.get("videoDetails", {})
            return {
                "title": video_details.get("title", "Unknown"),
                "artist": video_details.get("author", "Unknown Artist"),
                "album": "",
                "video_id": video_id,
                "duration": "",
            }
        except Exception as exc:
            raise ValueError(
                f"Could not retrieve song info for ID '{video_id}'. "
                f"{exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Playlists & albums (public or authenticated)
    # ------------------------------------------------------------------

    def get_playlist_tracks(self, playlist_id: str) -> dict[str, Any]:
        """
        Fetch all tracks from a YouTube Music playlist.

        Tries the authenticated session first (for private playlists),
        falling back to the public session on failure.

        Returns a dict with ``title``, ``track_count``, and ``tracks``.
        """
        client = self._auth if self.is_authenticated else self.public
        try:
            playlist = client.get_playlist(playlist_id, limit=None)
        except Exception:
            if self.is_authenticated:
                playlist = self.public.get_playlist(playlist_id, limit=None)
            else:
                raise
        tracks = self._normalise_tracks(playlist.get("tracks", []))
        if not tracks:
            raise ValueError(
                "Could not retrieve tracks from this playlist. "
                "It may be private, region-locked, or the ID is invalid."
            )
        return {
            "title": playlist.get("title", "Unknown Playlist"),
            "track_count": len(tracks),
            "tracks": tracks,
        }

    def get_album_tracks(self, album_id: str) -> dict[str, Any]:
        """
        Fetch all tracks from a YouTube Music album by its ``browse_id``.

        Returns a dict with ``title``, ``artist``, ``track_count``, and
        ``tracks``.
        """
        client = self._auth if self.is_authenticated else self.public
        album = client.get_album(album_id)
        tracks = self._normalise_tracks(album.get("tracks", []))
        if not tracks:
            raise ValueError(
                "Could not retrieve tracks from this album. "
                "It may be region-locked or the ID is invalid."
            )
        return {
            "title": album.get("title", "Unknown Album"),
            "artist": ", ".join(a["name"] for a in album.get("artists", [])),
            "track_count": len(tracks),
            "tracks": tracks,
        }

    # ------------------------------------------------------------------
    # Personal library (requires authentication)
    # ------------------------------------------------------------------

    def get_liked_songs(self, limit: int = 5000) -> dict[str, Any]:
        """
        Fetch the user's liked ("thumbs-up") songs.

        Returns a dict with ``title``, ``track_count``, and ``tracks``.
        """
        tracks = self._normalise_tracks(
            self.auth.get_liked_songs(limit=limit).get("tracks", [])
        )
        return {
            "title": "Liked Songs",
            "track_count": len(tracks),
            "tracks": tracks,
        }

    def get_library_playlists(self) -> list[dict[str, Any]]:
        """
        Fetch all playlists in the user's library.

        Each playlist dict has ``title``, ``playlist_id``, and
        ``track_count``.
        """
        playlists = self.auth.get_library_playlists(limit=None)
        result: list[dict[str, Any]] = []
        for pl in playlists:
            result.append({
                "title": pl.get("title", "Unknown Playlist"),
                "playlist_id": pl.get("playlistId", ""),
                "track_count": pl.get("count", ""),
                "description": pl.get("description", ""),
            })
        return result

    def get_library_albums(self) -> list[dict[str, Any]]:
        """
        Fetch all saved albums in the user's library.

        Each album dict has ``title``, ``artist``, ``browse_id``, and
        ``year``.
        """
        albums = self.auth.get_library_albums(limit=None)
        result: list[dict[str, Any]] = []
        for alb in albums:
            artists = ", ".join(
                a["name"] for a in alb.get("artists", []) if a and "name" in a
            )
            result.append({
                "title": alb.get("title", "Unknown Album"),
                "artist": artists or "Unknown Artist",
                "browse_id": alb.get("browseId", ""),
                "year": alb.get("year", ""),
            })
        return result

    def get_library_songs(self, limit: int = 5000) -> dict[str, Any]:
        """
        Fetch all uploaded / purchased songs in the user's library
        (distinct from liked songs).

        Returns a dict with ``title``, ``track_count``, and ``tracks``.
        """
        tracks = self._normalise_tracks(
            self.auth.get_library_songs(limit=limit)
        )
        return {
            "title": "Library Songs",
            "track_count": len(tracks),
            "tracks": tracks,
        }

    # ------------------------------------------------------------------
    # URL parsing
    # ------------------------------------------------------------------

    def parse_url(self, url: str) -> dict[str, str] | None:
        """
        Parse a YouTube / YouTube Music URL into ``{"type": ..., "id": ...}``.

        Supported types: ``track``, ``playlist``, ``album``.
        Returns ``None`` if the URL cannot be parsed.
        """
        patterns = [
            ("playlist", r"music\.youtube\.com/playlist\?list=([\w-]+)"),
            ("album",    r"music\.youtube\.com/browse/([\w-]+)"),
            ("track",    r"music\.youtube\.com/watch\?v=([\w-]+)"),
        ]

        for kind, pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return {"type": kind, "id": match.group(1)}

        # also support plain youtube.com URLs
        match = re.search(r"youtube\.com/watch\?v=([\w-]+)", url)
        if match:
            return {"type": "track", "id": match.group(1)}

        match = re.search(r"youtube\.com/playlist\?list=([\w-]+)", url)
        if match:
            return {"type": "playlist", "id": match.group(1)}

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_tracks(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Convert ytmusicapi track dicts (which vary slightly across
        search / playlist / album endpoints) into a uniform shape::

            {
                "title": str,
                "artist": str,
                "album": str,
                "video_id": str,
                "duration": str,
            }

        Entries without a ``video_id`` are silently dropped.
        """
        normalised: list[dict[str, Any]] = []
        for item in raw:
            try:
                artists = ", ".join(
                    a["name"] for a in item.get("artists", []) if a and "name" in a
                )
                normalised.append({
                    "title": item.get("title", "Unknown"),
                    "artist": artists or "Unknown Artist",
                    "album": (
                        item.get("album", {}).get("name", "")
                        if isinstance(item.get("album"), dict)
                        else ""
                    ),
                    "video_id": item.get("videoId") or item.get("video_id") or "",
                    "duration": item.get("duration", ""),
                })
            except Exception:
                continue
        return [t for t in normalised if t["video_id"]]


#: Module-level singleton – import ``client`` wherever YTMusic access is needed.
client = YTMusicClient()
