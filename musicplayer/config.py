import os
import json
import platform

def get_config_dir():
    """Get the OS-specific config directory"""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        path = os.path.join(base, "cli-music-player")
    else:
        # XDG Config Home compliant-ish
        base = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
        path = os.path.join(base, "cli-music-player")
    
    if not os.path.exists(path):
        try: os.makedirs(path)
        except: pass
    return path

def get_config_path():
    return os.path.join(get_config_dir(), "config.json")

def load_config():
    """Load config dictionary"""
    path = get_config_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_config(data):
    """Save config dictionary"""
    path = get_config_path()
    try:
        current = load_config()
        current.update(data)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(current, f, indent=4)
        return True
    except:
        return False
