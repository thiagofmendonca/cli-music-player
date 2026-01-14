import sys
import os

# Fix SSL Certificate issues in PyInstaller (Linux/Windows)
if getattr(sys, 'frozen', False):
    try:
        import certifi
        # Force OpenSSL and Requests to use the bundled certifi PEM
        os.environ['SSL_CERT_FILE'] = certifi.where()
        os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
    except ImportError:
        pass

from musicplayer.gui import main

if __name__ == "__main__":
    main()