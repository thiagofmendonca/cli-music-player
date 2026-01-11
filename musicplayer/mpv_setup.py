import os
import sys
import platform
import shutil
import urllib.request
import zipfile
import tarfile
import tempfile
import subprocess

def get_mpv_path():
    # 1. Check global PATH
    mpv_cmd = shutil.which("mpv")
    if mpv_cmd:
        return mpv_cmd

    # 2. Check local user data path (for auto-downloaded binary)
    if platform.system() == "Windows":
        local_bin = os.path.join(os.environ.get("APPDATA", ""), "cli-music-player", "bin", "mpv.exe")
    else:
        local_bin = os.path.join(os.path.expanduser("~"), ".local", "share", "cli-music-player", "bin", "mpv")

    if os.path.exists(local_bin):
        return local_bin

    return None

def download_mpv():
    """
    Downloads MPV static build for the current platform.
    """
    system = platform.system()
    machine = platform.machine().lower()
    
    print("MPV not found. Attempting to download a portable version...")
    
    # Define URLs for static builds
    url = None
    if system == "Windows":
        # Sourceforge usually has reliable windows builds or direct github releases
        # Using a reliable recent build from shinchiro (widely used)
        url = "https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/v20240107/mpv-x86_64-20240107-git-1741765.7z" 
        # Note: 7z extraction in python requires py7zr, let's look for a zip if possible, 
        # or assume user has tar/7z. Actually, Python 3.13 supports more formats, but let's be safe.
        # Fallback to a source that provides ZIP for windows if possible, or use tar command which windows 10+ has.
        url = "https://sourceforge.net/projects/mpv-player-windows/files/64bit/mpv-x86_64-20231210-git-7067f56.7z/download"
        
    elif system == "Linux":
        print("On Linux, it is highly recommended to install mpv via your package manager.")
        print("Arch: sudo pacman -S mpv")
        print("Debian/Ubuntu: sudo apt install mpv")
        # We generally don't download binaries for Linux due to glibc versioning hell.
        return None

    if not url:
        return None

    # Setup paths
    if system == "Windows":
        install_dir = os.path.join(os.environ.get("APPDATA", ""), "cli-music-player", "bin")
    else:
        install_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "cli-music-player", "bin")
        
    if not os.path.exists(install_dir):
        os.makedirs(install_dir)

    download_path = os.path.join(tempfile.gettempdir(), "mpv_archive.7z")

    try:
        # Download
        print(f"Downloading MPV from {url}...")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response, open(download_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        
        print("Extracting...")
        # Python's tarfile/zipfile don't handle 7z well standardly without deps.
        # We rely on system 'tar' (Win10+ has it) or '7z'.
        
        # Try native tar (works on Win10+ for many formats now, but 7z is tricky)
        # Actually, for Windows, let's suggest the user install it or assume we can use a simpler zip source.
        # Bootstrapping 7z is hard.
        
        # Alternative: Mid-2024, most simple way:
        # If we can't extract, we fail.
        
        # Let's try calling '7z' or 'tar' subprocess
        try:
            subprocess.run(["tar", "-xf", download_path, "-C", install_dir], check=True)
        except:
            print("Failed to extract MPV. Please install MPV manually and add to PATH.")
            return None
            
        print(f"MPV installed to {install_dir}")
        
        if system == "Windows":
            return os.path.join(install_dir, "mpv.exe")
        else:
            return os.path.join(install_dir, "mpv")

    except Exception as e:
        print(f"Failed to auto-setup MPV: {e}")
        return None
