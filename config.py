"""
Centralized application configuration using dataclasses.

All user-facing settings (output directory, audio format, concurrent
downloads, and authentication) live here.  Values can be changed at
runtime through the interactive Settings menu.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Application-wide configuration with sensible defaults."""

    # ---- download settings ----
    output_dir: Path = field(
        default_factory=lambda: Path.home() / "Music" / "YTMusic"
    )
    """Directory where downloaded audio files are saved."""

    audio_format: str = "mp3"
    """Target audio codec (``mp3``, ``m4a``, ``opus``, ``flac``)."""

    audio_quality: str = "192"
    """Bitrate in kbps (``128``, ``192``, ``256``, ``320``)."""

    max_concurrent_downloads: int = 3
    """How many tracks to download in parallel (1-10)."""

    filename_template: str = "{artist} - {title}"
    """Template for output filenames.
    Available placeholders: ``{artist}``, ``{title}``, ``{album}``, ``{track_num}``.
    """

    # ---- authentication ----
    auth_dir: Path = field(
        default_factory=lambda: Path.home() / ".config" / "ytmusic"
    )
    """Directory that stores authentication credentials."""

    browser_file: Path = field(
        default_factory=lambda: Path.home() / ".config" / "ytmusic" / "browser.json"
    )
    """Path to the browser-header credential file used by ytmusicapi."""

    def __post_init__(self) -> None:
        """Ensure required directories exist after initialisation."""
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.auth_dir, exist_ok=True)


#: Module-level singleton – import ``config`` wherever settings are needed.
config = Config()
