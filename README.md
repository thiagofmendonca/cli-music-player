# FreeThullu Music Player 🐙🎵

**Version 1.0.5**

A powerful, hybrid music player that summons your beats from the deep.
Featuring a modern **GUI** (PyQt6) for desktop comfort and a robust **CLI** mode for terminal dwellers.

## ✨ Features

- **Hybrid Interface:**
  - **GUI:** Modern Dark Theme, Tabbed Interface (Now Playing, Library, Search, Queue), and Animated Visuals.
  - **CLI:** Lightweight, keyboard-driven terminal interface.
- **Universal Playback:**
  - **Local Library:** Deep recursive scanning, instant filtering, and file management.
  - **Online Streaming:** Seamless **YouTube** and **SoundCloud** (prefix `sc:`) integration.
- **Immersive Experience:**
  - **Animated FreeThullu:** Watch the Great Old One pulse to the rhythm.
  - **Synced Lyrics:** Automatic fetching from LRCLib and Letras.mus.br.
- **Smart Queue:**
  - Manage your playlist with ease.
  - **Context Menus:** Right-click to add multiple items to the queue.
  - **Jump:** Double-click any item in the queue to play immediately.
- **Cross-Platform:** Native support for **Linux** and **Windows** (with auto-mpv setup).

## 🚀 Installation

### Via PIP

```bash
pip install cli-music-player-cthulhu
```

### System Requirements

- **Python 3.9+**
- **Linux:** Requires `mpv` (`sudo apt install mpv` / `sudo pacman -S mpv`).
- **Windows:** Auto-downloads `mpv` on first run.

## 🎮 Usage

### 🖥️ Graphical Interface (Recommended)

Launch the full experience:

```bash
musicplayer-gui
```

**Controls:**
- **Navigation:** Use tabs to switch views.
- **Library:** Type in the filter box. **Press Enter** to trigger a deep recursive search in subfolders.
- **Search:** Type queries for YouTube. Prefix with `sc:` for SoundCloud.
- **Queueing:** Select multiple items (Ctrl/Shift+Click) -> Right Click -> *Add to Queue*.
- **Debug Mode:** Run `musicplayer-gui --debug` to see backend logs.

### 📟 Terminal Interface

Launch the lightweight TUI:

```bash
musicplayer
```

*Controls: `Space` (Pause), `/` (Search), `a` (Queue), `q` (Quit).*

## 📦 Building from Source

To build standalone executables (Linux/Windows):

1. **Clone and Install Dependencies:**
   ```bash
   git clone https://github.com/thiagofmendonca/cli-music-player.git
   cd cli-music-player
   pip install .
   pip install pyinstaller
   ```

2. **Build:**
   ```bash
   # Linux
   pyinstaller --noconfirm --onefile --windowed --name "FreeThulluPlayer" --add-data "musicplayer/assets:musicplayer/assets" --icon "musicplayer/assets/frame1.png" --hidden-import "musicplayer" run_gui.py
   
   # Windows (PowerShell)
   pyinstaller --noconfirm --onefile --windowed --name "FreeThulluPlayer" --add-data "musicplayer/assets;musicplayer/assets" --icon "musicplayer/assets/frame1.png" --hidden-import "musicplayer" run_gui.py
   ```

## 📜 License

GNU Affero General Public License v3.0 (AGPLv3)
