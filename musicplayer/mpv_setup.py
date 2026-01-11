import os
import sys
import platform
import shutil
import urllib.request
import zipfile
import tempfile

def get_mpv_path():
    # 1. Check global PATH
    mpv_cmd = shutil.which("mpv")
    if mpv_cmd:
        return mpv_cmd

    # 2. Check local user data path
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
    Uses ZIP for Windows to ensure native Python extraction.
    """
    system = platform.system()
    if system != "Windows":
        return None # On Linux/Mac user should use package manager

    print("MPV not found. Attempting to download a portable version...")
    
    # Using a reliable direct ZIP link for Windows x64
    # This is a static build that includes everything needed
    url = "https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/v20240107/mpv-x86_64-20240107-git-1741765.zip"
    
    install_dir = os.path.join(os.environ.get("APPDATA", ""), "cli-music-player", "bin")
    if not os.path.exists(install_dir):
        os.makedirs(install_dir)

    download_path = os.path.join(tempfile.gettempdir(), "mpv_archive.zip")

    try:
        # Download
        print(f"Downloading MPV...")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response, open(download_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        
        print("Extracting (this may take a minute)...")
        with zipfile.ZipFile(download_path, 'r') as zip_ref:
            # We only need mpv.exe and its immediate dependencies
            # But extracting all is safer
            zip_ref.extractall(install_dir)
            
        print(f"MPV installed successfully.")
        
        # Check if mpv.exe is in a subdirectory (sometimes zips have them)
        expected_exe = os.path.join(install_dir, "mpv.exe")
        if not os.path.exists(expected_exe):
            # Scan for mpv.exe in subdirs
            for root, dirs, files in os.walk(install_dir):
                if "mpv.exe" in files:
                    # Move it to the main bin dir
                    shutil.move(os.path.join(root, "mpv.exe"), expected_exe)
                    break
        
        return expected_exe

    except Exception as e:
        print(f"Failed to auto-setup MPV: {e}")
        return None