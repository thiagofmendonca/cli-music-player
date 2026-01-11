import PyInstaller.__main__
import os
import shutil

# Ensure we are in the root
if not os.path.exists("musicplayer"):
    print("Run this from the project root")
    exit(1)

# Clean previous builds
shutil.rmtree("build", ignore_errors=True)
shutil.rmtree("dist", ignore_errors=True)

# Build command
PyInstaller.__main__.run([
    'musicplayer/main.py',
    '--name=MusicPlayerCthulhu',
    '--onefile',
    '--clean',
    '--add-data=musicplayer:musicplayer', # Include the package files
    '--hidden-import=musicplayer.mpv_setup',
    '--hidden-import=musicplayer.search',
    '--hidden-import=musicplayer.utils',
    # Note: On Windows, we don't bundle mpv.exe inside the onefile because it's huge 
    # and harder to extract at runtime. 
    # Our code already handles downloading it to AppData if missing.
])

print("Build complete. Check dist/MusicPlayerCthulhu")
