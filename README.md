# CLI Music Player

A lightweight, terminal-based music player written in Python, using `mpv` as the playback engine.

## Features

- **Terminal User Interface (TUI):** Clean interface built with `curses`.
- **File Browser:** Navigate directories to find your music.
- **Recursive Library Mode:** Scan all subdirectories and play your entire collection at once.
- **Shuffle Mode:** Randomized playback with a history-aware "Previous" function.
- **Audio Formats:** Supports mp3, wav, flac, ogg, m4a, wma, aac, opus.
- **Playback Controls:**
  - Play / Pause / Stop
  - Next / Previous Track
  - Volume Control (up to 200%)
  - Seek / Progress Bar
- **Now Playing View:** Dedicated screen showing track info and progress.
- **Dependency Check:** Automatically detects and attempts to install `mpv` if missing (Linux).

## Requirements

- Python 3
- `mpv` (The script attempts to install it automatically on Linux, but you can install it manually via your package manager).

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/thiagofmendonca/cli-music-player.git
   cd cli-music-player
   ```

2. Make the script executable:
   ```bash
   chmod +x musicplayer.py
   ```

3. (Optional) Install globally:
   ```bash
   sudo cp musicplayer.py /usr/local/bin/musicplayer
   ```

## Usage

Run the script from your terminal:

```bash
./musicplayer.py
# OR if installed globally:
musicplayer
```

### Controls

| Key | Action |
| :--- | :--- |
| **Arrow Up/Down** | Navigate files |
| **Enter** | Play file / Open directory |
| **Space** | Play / Pause |
| **n** | Next Track |
| **p** | Previous Track (History-aware in Shuffle) |
| **z** | Toggle Shuffle Mode |
| **R** (Shift+r) | Load Recursive Library (all subfolders) |
| **B** (Shift+b) | Return to Browser Mode |
| **+ / -** | Volume Up / Down |
| **Tab** | Toggle "Now Playing" View |
| **s** | Stop |
| **q** | Quit (or go back from Player View) |

## License

MIT
