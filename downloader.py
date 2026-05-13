"""
Audio downloader built on `yt-dlp <https://github.com/yt-dlp/yt-dlp>`_.

Downloads run in parallel via `ThreadPoolExecutor`.  If ``ffmpeg`` is
present on the system, tracks are converted to the configured audio
format (default MP3) with embedded metadata and cover art.  Without
``ffmpeg`` it falls back to native M4A.
"""

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
    """
    Downloads audio from YouTube Music tracks using the best available
    audio stream, with optional post-processing via ffmpeg.

    Each :meth:`download` call resets the internal counters
    (completed / skipped / failed).
    """

    def __init__(self) -> None:
        self._completed: int = 0
        self._failed: list[str] = []
        self._skipped: int = 0
        self._url_prefix = "https://music.youtube.com/watch?v="
        self._has_ffmpeg: bool = shutil.which("ffmpeg") is not None

    # ----------------------------------------------------------------
    # Public interface
    # ----------------------------------------------------------------

    def download(
        self,
        tracks: list[dict[str, Any]],
        output_dir: Path | None = None,
        album_title: str = "",
    ) -> tuple[int, int, list[str]]:
        """
        Download a batch of *tracks* concurrently.

        Each track dict must have ``video_id``, ``artist``, and ``title``.

        Returns a tuple of ``(completed_count, skipped_count, failed_list)``.
        """
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
        """
        The file extension used for downloads — matches config if
        ffmpeg is available, otherwise ``"m4a"``.
        """
        return config.audio_format if self._has_ffmpeg else "m4a"

    # ----------------------------------------------------------------
    # Internal
    # ----------------------------------------------------------------

    def _download_one(
        self,
        track: dict[str, Any],
        output_dir: Path,
        album_title: str,
        idx: int,
        total: int,
    ) -> None:
        """
        Download a single track.

        Skips if the output file already exists (case-insensitive
        extension match).
        """
        video_id = track["video_id"]
        url = f"{self._url_prefix}{video_id}"

        safe_artist = self._sanitise(track["artist"])
        safe_title = self._sanitise(track["title"])

        filename = config.filename_template.format(
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
        """
        Build the ``yt_dlp.YoutubeDL`` options dict.

        With ffmpeg: extracts audio to the configured codec/bitrate,
        embeds metadata and thumbnail as cover art.

        Without ffmpeg: downloads the best M4A stream directly.
        """
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
            # Without ffmpeg, grab the native M4A container directly.
            opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"

        return opts

    @staticmethod
    def _sanitise(value: str) -> str:
        """Remove characters that are illegal in filenames."""
        return re.sub(r'[\\/*?:"<>|]', "_", value).strip()


#: Module-level singleton – import ``downloader`` wherever downloads are needed.
downloader = Downloader()
