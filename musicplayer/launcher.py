import sys
import os
import argparse

def launch():
    # Fix SSL Certificate issues in PyInstaller (Linux/Windows)
    if getattr(sys, 'frozen', False):
        try:
            import certifi
            # Force OpenSSL and Requests to use the bundled certifi PEM
            os.environ['SSL_CERT_FILE'] = certifi.where()
            os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
        except ImportError:
            pass

    parser = argparse.ArgumentParser(description="FreeThullu Music Player")
    parser.add_argument('--cli', action='store_true', help="Start in CLI mode (default is GUI)")
    parser.add_argument('-d', '--debug', action='store_true', help="Enable debug logging/verbose mode")
    
    # Keep compatibility with positional arg for directory in CLI mode
    parser.add_argument('directory', nargs='?', default=None, help="Optional: Start directory for local files")
    
    # Use parse_known_args to ignore flags that might be specific to sub-modules
    args, unknown = parser.parse_known_args()

    if args.cli:
        from .main import main as cli_main
        cli_main(debug=args.debug)
    else:
        from .gui import main as gui_main
        gui_main(debug=args.debug)

if __name__ == "__main__":
    launch()
