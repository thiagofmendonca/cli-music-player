from .main import main

import os
import sys

def get_version():
    try:
        # If frozen by PyInstaller, look in sys._MEIPASS (temp folder)
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            # If running from source, look in project root (parent of this package)
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        version_file = os.path.join(base_path, 'VERSION')
        
        if os.path.exists(version_file):
            with open(version_file, 'r') as f:
                return f.read().strip()
    except Exception:
        pass
    return "0.0.0-dev"

__version__ = get_version()
