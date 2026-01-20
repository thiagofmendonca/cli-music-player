import os
import sys
import platform
import shutil
import urllib.request
import tempfile
import json

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

def get_latest_mpv_url():
    try:
        api_url = "https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases/latest"
        req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            for asset in data.get('assets', []):
                # Prefer v3 x86_64 build
                if 'mpv-x86_64-v3' in asset['name'] and asset['name'].endswith('.7z'):
                    return asset['browser_download_url']
                # Fallback to standard x86_64
                if 'mpv-x86_64' in asset['name'] and asset['name'].endswith('.7z') and 'v3' not in asset['name']:
                    fallback = asset['browser_download_url']
            
            return fallback if 'fallback' in locals() else None
    except:
        return None

def download_mpv():
    """
    Downloads MPV static build for the current platform.
    Uses 7z for Windows and extracts using py7zr.
    """
    system = platform.system()
    if system != "Windows":
        return None

    print("MPV not found. Attempting to download a portable version...")
    
    url = get_latest_mpv_url()
    if not url:
        # Hardcoded fallback if API fails
        url = "https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/20260120/mpv-dev-x86_64-20260120-git-b7e8fe9.7z"
    
    install_dir = os.path.join(os.environ.get("APPDATA", ""), "cli-music-player", "bin")
    if not os.path.exists(install_dir):
        os.makedirs(install_dir)

    download_path = os.path.join(tempfile.gettempdir(), "mpv_archive.7z")

    try:
        # Import py7zr here to ensure it's only needed on Windows during download
        import py7zr
        
        # Download
        print(f"Downloading MPV (20260111)...")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as response, open(download_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        
        print("Extracting 7z archive (this may take a minute)...")
        with py7zr.SevenZipFile(download_path, mode='r') as z:
            z.extractall(path=install_dir)
            
        print(f"MPV extracted to {install_dir}")
        
        # Check if mpv.exe is in a subdirectory
        expected_exe = os.path.join(install_dir, "mpv.exe")
        if not os.path.exists(expected_exe):
            # Scan for mpv.exe in subdirs
            for root, dirs, files in os.walk(install_dir):
                if "mpv.exe" in files:
                    # Move it to the main bin dir
                    src = os.path.join(root, "mpv.exe")
                    shutil.move(src, expected_exe)
                    break
        
        if os.path.exists(expected_exe):
            print("MPV setup complete.")
            return expected_exe
        else:
            print("Could not find mpv.exe after extraction.")
            return None

    except ImportError:
        print("Error: 'py7zr' library is missing. Please run: pip install py7zr")
        return None
    except Exception as e:
        print(f"Failed to auto-setup MPV: {e}")
        return None
