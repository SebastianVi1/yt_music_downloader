# YT Music Downloader

A Python CLI tool to search, browse, and download music from YouTube Music.

## Features

- **Search** — find tracks by keyword and pick which ones to download
- **URL download** — paste a YouTube Music URL (track, playlist, or album)
- **My Library** — browse and download your playlists, albums, liked songs, and library uploads
- **Parallel downloads** — configurable concurrent downloads (default 3)
- **Duplicate skip** — tracks already in the output directory are skipped
- **FFmpeg-aware** — with ffmpeg: MP3 + embedded metadata + cover art. Without it: native M4A

## Requirements

- Python 3.10+
- ffmpeg (optional, for MP3 output and metadata)

## Setup

```bash
cd yt_music_downloader
./run.sh
```

Or manually:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

Install ffmpeg for MP3 output with embedded metadata:

```bash
sudo apt install ffmpeg
```

## Usage

Launch the app:

```
🔓  Not logged in — login to access your library
────────────────────────────────────────
🎵  Search and download tracks
🔗  Download by URL
📋  Download playlist by ID
🔐  Login to YouTube Music
⚙️   Settings
────────────────────────────────────────
🚪  Exit
```

After logging in, a **My Library** section appears with your personal content.

### Authentication

The app uses **browser headers** — it acts as your browser by reusing its YouTube Music session cookies.

1. Select **"Login to YouTube Music"** from the menu
2. Open `https://music.youtube.com` in your browser and sign in
3. Press **F12** → **Network** tab
4. In the filter bar, type `browse` to find a POST request to `/browse`
5. Right-click the request → **Copy** → **Copy request headers**
   *(Chrome: click the request, scroll to "Request Headers", select from `accept: */*` through the `Cookie` line)*
6. Paste the headers into the app

Credentials are saved to `~/.config/ytmusic/browser.json` and remain valid for ~2 years (as long as you don't log out of YouTube Music in the browser).

### Search and download

Type a query, pick tracks with Space, press Enter to download.

### Download by URL

| Type | Example |
|------|---------|
| Track | `https://music.youtube.com/watch?v=...` |
| Playlist | `https://music.youtube.com/playlist?list=...` |
| Album | `https://music.youtube.com/browse/...` |

### My Library (requires login)

- **My Playlists** — browse and download your playlists
- **My Albums** — browse and download your saved albums
- **Liked Songs** — download all liked songs
- **Library Songs** — download uploaded/purchased songs

### Settings

- **Output directory** — default: `~/Music/YTMusic`
- **Audio format** — MP3, M4A, Opus, or FLAC
- **Quality** — 128, 192, 256, or 320 kbps
- **Max concurrent downloads** — 1 to 10

## Project structure

```
yt_music_downloader/
├── main.py           Interactive CLI entry point
├── downloader.py     Audio download logic (yt-dlp + ThreadPoolExecutor)
├── ytmusic_client.py YouTube Music API wrapper (ytmusicapi)
├── config.py         Centralized settings
├── requirements.txt  Python dependencies
├── run.sh            Convenience launcher
└── downloads/        Default output directory
```

## How it works

1. **Search / browse** — `ytmusic_client.py` wraps [ytmusicapi](https://github.com/sigma67/ytmusicapi) to query the YouTube Music web API.

2. **Authentication** — copies your browser's request headers (cookie + authorization token) and reuses them for authenticated API calls. The `ytmusicapi.setup()` function parses the raw headers and stores them as `~/.config/ytmusic/browser.json`.

3. **Download** — `downloader.py` wraps [yt-dlp](https://github.com/yt-dlp/yt-dlp) to download each track's best audio stream. Downloads run in parallel via `ThreadPoolExecutor`.

4. **Post-processing** — if ffmpeg is available, converts to MP3 (configurable), embeds metadata, and attaches cover art. Without ffmpeg, falls back to native M4A.

## Dependencies

| Library | Purpose |
|---------|---------|
| [ytmusicapi](https://github.com/sigma67/ytmusicapi) | YouTube Music API client |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Audio extraction and download |
| [questionary](https://github.com/tmbo/questionary) | Interactive CLI prompts |
| [rich](https://github.com/Textualize/rich) | Terminal formatting and panels |
| ffmpeg (system) | Audio conversion and metadata embedding |
