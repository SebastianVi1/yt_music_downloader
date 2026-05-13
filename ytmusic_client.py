from __future__ import annotations

import re
from typing import Any

from ytmusicapi import YTMusic

from config import config


class YTMusicClient:
    def __init__(self) -> None:
        self._public: YTMusic | None = None
        self._auth: YTMusic | None = None

    @property
    def public(self) -> YTMusic:
        if self._public is None:
            self._public = YTMusic()
        return self._public

    @property
    def auth(self) -> YTMusic:
        if self._auth is None:
            oauth_path = str(config.oauth_file)
            if config.oauth_file.exists():
                self._auth = YTMusic(oauth_path)
            else:
                self._auth = YTMusic(oauth_path, open_browser=True)
        return self._auth

    def search(self, query: str) -> list[dict[str, Any]]:
        results = self.public.search(query, filter="songs", limit=20)
        return self._normalise_tracks(results)

    def get_playlist_tracks(self, playlist_id: str) -> dict[str, Any]:
        playlist = self.public.get_playlist(playlist_id, limit=None)
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
        album = self.public.get_album(album_id)
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

    def get_song_info(self, video_id: str) -> dict[str, Any]:
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

    def get_liked_songs(self, limit: int = 5000) -> dict[str, Any]:
        tracks = self._normalise_tracks(
            self.auth.get_liked_songs(limit=limit).get("tracks", [])
        )
        return {
            "title": "Liked Songs",
            "track_count": len(tracks),
            "tracks": tracks,
        }

    def parse_url(self, url: str) -> dict[str, str] | None:
        patterns = [
            ("playlist", r"music\.youtube\.com/playlist\?list=([\w-]+)"),
            ("album", r"music\.youtube\.com/browse/([\w-]+)"),
            ("track", r"music\.youtube\.com/watch\?v=([\w-]+)"),
        ]

        for kind, pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return {"type": kind, "id": match.group(1)}

        match = re.search(r"youtube\.com/watch\?v=([\w-]+)", url)
        if match:
            return {"type": "track", "id": match.group(1)}

        match = re.search(r"youtube\.com/playlist\?list=([\w-]+)", url)
        if match:
            return {"type": "playlist", "id": match.group(1)}

        return None

    @staticmethod
    def _normalise_tracks(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


client = YTMusicClient()
