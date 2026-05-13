from __future__ import annotations

import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from config import config


class Downloader:
    def __init__(self) -> None:
        self._completed: int = 0
        self._failed: list[str] = []
        self._skipped: int = 0
        self._url_prefix = "https://music.youtube.com/watch?v="
        self._has_ffmpeg: bool = shutil.which("ffmpeg") is not None

    def download(
        self,
        tracks: list[dict[str, Any]],
        output_dir: Path | None = None,
        album_title: str = "",
    ) -> tuple[int, int, list[str]]:
        self._completed = 0
        self._failed = []
        self._skipped = 0

        output = output_dir or config.output_dir
        total = len(tracks)
        max_workers = min(config.max_concurrent_downloads, total) if total > 0 else 1

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self._download_one,
                    track,
                    output,
                    album_title,
                    idx,
                    total,
                ): track
                for idx, track in enumerate(tracks, 1)
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    pass

        return self._completed, self._skipped, self._failed

    @property
    def actual_ext(self) -> str:
        return config.audio_format if self._has_ffmpeg else "m4a"

    def _download_one(
        self,
        track: dict[str, Any],
        output_dir: Path,
        album_title: str,
        idx: int,
        total: int,
    ) -> None:
        video_id = track["video_id"]
        url = f"{self._url_prefix}{video_id}"

        safe_artist = self._sanitise(track["artist"])
        safe_title = self._sanitise(track["title"])

        template = config.filename_template
        filename = template.format(
            artist=safe_artist,
            title=safe_title,
            album=self._sanitise(album_title or track.get("album", "")),
            track_num=idx,
        )

        ext = self.actual_ext
        output_template = output_dir / f"{filename}.%(ext)s"
        final_path = output_dir / f"{filename}.{ext}"

        if final_path.exists():
            self._skipped += 1
            return

        ydl_opts = self._build_options(str(output_template))

        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            self._completed += 1
        except DownloadError:
            self._failed.append(f"{track['artist']} - {track['title']}")

    def _build_options(self, outtmpl: str) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "retries": 5,
            "fragment_retries": 5,
            "socket_timeout": 30,
        }

        if self._has_ffmpeg:
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": config.audio_format,
                    "preferredquality": config.audio_quality,
                },
                {"key": "FFmpegMetadata"},
                {"key": "EmbedThumbnail"},
            ]
            opts["writethumbnail"] = True
        else:
            opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"

        return opts

    @staticmethod
    def _sanitise(value: str) -> str:
        return re.sub(r'[\\/*?:"<>|]', "_", value).strip()


downloader = Downloader()
