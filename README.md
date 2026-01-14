# CLI Music Player (Cthulhu Edition)

A powerful, lightweight terminal-based music player written in Python. It combines a robust local file browser with online streaming capabilities (YouTube, SoundCloud) and a unique visual style featuring a pulsing Cthulhu and synced lyrics.

![Demo](demo.gif)

## Features

- **Hybrid Playback:**
  - **Local:** Plays MP3, FLAC, OGG, WAV, M4A, and more.
  - **Online:** Search and stream directly from **YouTube** and **SoundCloud**.
- **Robust Engine:** Uses `mpv` as the core backend for best-in-class format support and stability.
- **Visuals:**
  - Pulsing Cthulhu animation.
  - **Synced Lyrics:** Automatic fetching from LRCLib with fallback to Letras.mus.br and Lyrics.ovh.
- **Queue System:**
  - Build a custom playback queue from mixed sources (Local files + YouTube).
  - **YouTube Playlists:** Paste a playlist URL to load all videos as search results.
  - **Bulk Add:** Add all search results to the queue instantly.
  - **Queue Preview:** See upcoming tracks directly in the player view.
- **Smart Interface:**
  - **Recursive Library:** Scan entire folder trees.
  - **Search Mode:** Press `/` to find online tracks instantly.
  - **Persistence:** Save your default music directory.
- **Cross-Platform:**
  - **Linux:** Works with system `mpv`.
  - **Windows:** Automatically downloads a portable `mpv` if missing.

## Installation

### Via PIP (Recommended)

```bash
pip install cli-music-player-cthulhu
```

### Requirements

- **Python 3.8+**
- **Linux:** You must install `mpv` (e.g., `sudo pacman -S mpv` or `sudo apt install mpv`).
- **Windows:** No extra steps! The player downloads a standalone `mpv` on first run if needed.

## Usage

Run the player:

```bash
musicplayer
# OR open a specific folder:
musicplayer /path/to/music
```

### Controls

| Key | Action |
| :--- | :--- |
| **Arrow Up/Down** | Navigate files / Scroll Lyrics |
| **Enter** | Play file / Open directory / Select Search Result |
| **Space** | Play / Pause |
| **a** | **Add to Queue** (File or Search Result) |
| **A** (Shift+a) | **Bulk Add** (All Search Results to Queue) |
| **/** | **Search Online** (YouTube default, use `sc:` for SoundCloud) |
| **l** | Toggle Lyrics / Cthulhu View |
| **D** (Shift+d) | **Set current directory as Default** (Persistent) |
| **n** | Next Track |
| **p** | Previous Track (History-aware) |
| **z** | Toggle Shuffle Mode |
| **R** (Shift+r) | Load Recursive Library (all subfolders) |
| **b** | **Open Library/Browser** (from Player view) |
| **m** | **Back to Player** (from Library or Search views) |
| **+ / -** | Volume Up / Down |
| **s** | Stop |
| **q** | Quit (from Player/Browser) or Back to Browser (from Search) |

*Queued items are highlighted in **green** in the browser and search results.*

## Advanced Search

- **YouTube:** Just type your query (e.g., `Coldplay Yellow`).
- **YouTube Playlists:** Paste a full YouTube Playlist URL to browse and import items.
- **SoundCloud:** Prefix with `sc:` (e.g., `sc:Synthwave mix`).
- **Queue Management:** Use `a` to enqueue individual items or `A` (Shift+a) to enqueue the entire search result list. The player will auto-start if idle.

## License

MIT
