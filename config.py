from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    output_dir: Path = field(
        default_factory=lambda: Path.home() / "Music" / "YTMusic"
    )
    audio_format: str = "mp3"
    audio_quality: str = "192"
    max_concurrent_downloads: int = 3
    oauth_file: Path = field(
        default_factory=lambda: Path.home() / ".config" / "ytmusic" / "oauth.json"
    )
    filename_template: str = "{artist} - {title}"

    def __post_init__(self) -> None:
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.oauth_file.parent, exist_ok=True)


config = Config()
