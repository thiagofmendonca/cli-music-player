import PyInstaller.__main__
import os
import shutil
import sys
from PyInstaller.utils.hooks import collect_submodules

# Ensure we are in the root
if not os.path.exists("musicplayer"):
    print("Error: Run this from the project root directory")
    sys.exit(1)

print("--- Starting Build Process ---")

# Clean previous builds
print("Cleaning build/dist...")
shutil.rmtree("build", ignore_errors=True)
shutil.rmtree("dist", ignore_errors=True)

# Collect all yt_dlp submodules (extractors, etc)
hidden_yt_dlp = collect_submodules('yt_dlp')

# Build command arguments
args = [
    'musicplayer/main.py',
    '--name=MusicPlayerCthulhu',
    '--onefile',
    '--clean',
    '--noconfirm',
    # Include the source package files as data just in case
    '--add-data=musicplayer;musicplayer', 
    # Hidden imports that dynamic analysis might miss
    '--hidden-import=musicplayer',
    '--hidden-import=musicplayer.mpv_setup',
    '--hidden-import=musicplayer.search',
    '--hidden-import=musicplayer.utils',
] + [f'--hidden-import={m}' for m in hidden_yt_dlp]

# Windows specific
if sys.platform == 'win32':
    args.append('--hidden-import=curses')
    # Icon? (Optional, if we had one)
    # args.append('--icon=icon.ico')

print(f"Running PyInstaller with args: {args}")

try:
    PyInstaller.__main__.run(args)
    print("\nSUCCESS! Build complete.")
    print(f"Executable should be in: {os.path.abspath('dist')}")
except Exception as e:
    print(f"\nFAILED! Build error: {e}")
    sys.exit(1)