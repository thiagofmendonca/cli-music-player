import sys
import os
import socket
import time
import json
import tempfile

class MpvIpcClient:
    def __init__(self):
        self.socket_path = self._get_socket_path()
        self.is_windows = sys.platform == 'win32'

    def _get_socket_path(self):
        pid = os.getpid()
        if sys.platform == 'win32':
            return fr'\\.\pipe\mpv-socket-{pid}'
        else:
            return os.path.join(tempfile.gettempdir(), f'mpv_socket_{pid}')

    def get_mpv_flag(self):
        return f'--input-ipc-server={self.socket_path}'

    def send_command(self, command):
        if self.is_windows:
            return self._send_windows(command)
        else:
            return self._send_unix(command)

    def _send_unix(self, command):
        if not os.path.exists(self.socket_path): return None
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(self.socket_path)
            message = json.dumps({"command": command}) + '\n'
            client.sendall(message.encode('utf-8'))
            client.settimeout(0.1)
            response = b""
            try:
                while True:
                    chunk = client.recv(4096)
                    if not chunk: break
                    response += chunk
                    if b'\n' in chunk: break
            except socket.timeout: pass
            client.close()
            return response
        except: return None

    def _send_windows(self, command):
        # Named pipe client implementation for Windows
        # MPV creates the pipe server, we connect as client
        try:
            # We use standard file IO for named pipes in Python
            # However, blocking/transactional nature can be tricky.
            # Using wait_for_pipe logic is safer but let's try direct open first.
            
            message = json.dumps({"command": command}) + '\n'
            
            # Open for read/write
            with open(self.socket_path, 'r+b', buffering=0) as f:
                f.write(message.encode('utf-8'))
                f.flush()
                # Read response (naive)
                # MPV sends one line per response usually
                response = f.readline()
                return response
        except FileNotFoundError:
            return None # MPV likely not running or pipe not ready
        except Exception:
            return None

    def cleanup(self):
        if not self.is_windows and os.path.exists(self.socket_path):
            try: os.remove(self.socket_path)
            except: pass
