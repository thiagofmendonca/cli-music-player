#!/usr/bin/env python3
import curses
import os
import subprocess
import threading
import time
import signal
import sys
import socket
import json
import shutil
import atexit
import tempfile

# Supported audio extensions
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.wma', '.aac', '.opus'}

class MusicPlayer:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.current_dir = os.getcwd()
        self.files = []
        self.selected_index = 0
        self.scroll_offset = 0
        
        # State
        self.playing_index = -1
        self.paused = False
        self.volume = 100
        self.running = True
        self.view_mode = 'browser' # 'browser' or 'player'
        
        # MPV State
        self.mpv_process = None
        self.ipc_socket = os.path.join(tempfile.gettempdir(), f'mpv_socket_{os.getpid()}')
        self.duration = 0
        self.position = 0
        self.metadata = {}
        
        # UI
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)  # Selected
        curses.init_pair(2, curses.COLOR_GREEN, -1)     # Playing
        curses.init_pair(3, curses.COLOR_YELLOW, -1)    # Directory
        curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_RED)   # Error
        curses.init_pair(5, curses.COLOR_CYAN, -1)      # Progress Bar
        curses.init_pair(6, curses.COLOR_WHITE, -1)     # Dimmed/Normal text
        curses.curs_set(0)
        self.stdscr.nodelay(1)
        self.stdscr.timeout(100)

        # Cleanup hooks
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

        self.scan_directory()
        
        # Start IPC poller
        self.ipc_thread = threading.Thread(target=self.ipc_loop, daemon=True)
        self.ipc_thread.start()

    def handle_signal(self, signum, frame):
        self.cleanup()
        sys.exit(0)

    def cleanup(self):
        """Robust cleanup to ensure no zombie mpv processes"""
        if self.mpv_process:
            try:
                # Send quit command via IPC first if possible
                self.send_ipc_command(["quit"])
                time.sleep(0.1)
                
                # Force kill if still alive
                if self.mpv_process.poll() is None:
                    os.killpg(os.getpgid(self.mpv_process.pid), signal.SIGTERM)
                    self.mpv_process.wait(timeout=1)
            except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(os.getpgid(self.mpv_process.pid), signal.SIGKILL)
                except:
                    pass
            self.mpv_process = None
            
        if os.path.exists(self.ipc_socket):
            try:
                os.remove(self.ipc_socket)
            except:
                pass

    def scan_directory(self):
        self.files = []
        try:
            items = sorted(os.listdir(self.current_dir))
            self.files.append({'name': '..', 'type': 'dir'})
            for item in items:
                full_path = os.path.join(self.current_dir, item)
                if os.path.isdir(full_path) and not item.startswith('.'):
                    self.files.append({'name': item, 'type': 'dir'})
                elif os.path.isfile(full_path):
                    ext = os.path.splitext(item)[1].lower()
                    if ext in AUDIO_EXTENSIONS:
                        self.files.append({'name': item, 'type': 'file'})
            
            if self.selected_index >= len(self.files):
                self.selected_index = 0
                self.scroll_offset = 0
        except PermissionError:
            pass

    def send_ipc_command(self, command):
        """Send raw JSON command to MPV socket"""
        if not os.path.exists(self.ipc_socket):
            return None
        
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(self.ipc_socket)
            message = json.dumps({"command": command}) + '\n'
            client.sendall(message.encode('utf-8'))
            
            # Read response (simple)
            client.settimeout(0.1)
            response = b""
            try:
                while True:
                    chunk = client.recv(4096)
                    if not chunk: break
                    response += chunk
                    if b'\n' in chunk: break
            except socket.timeout:
                pass
            
            client.close()
            return response
        except Exception:
            return None

    def get_property(self, prop):
        res = self.send_ipc_command(["get_property", prop])
        if res:
            try:
                data = json.loads(res.decode('utf-8').strip())
                return data.get("data")
            except:
                pass
        return None

    def ipc_loop(self):
        """Poll MPV for status"""
        while self.running:
            if self.mpv_process and self.mpv_process.poll() is None:
                # Poll position
                pos = self.get_property("time-pos")
                if pos is not None:
                    self.position = float(pos)
                
                # Poll duration
                dur = self.get_property("duration")
                if dur is not None:
                    self.duration = float(dur)
                    
                # Poll metadata
                meta = self.get_property("metadata")
                if meta:
                    self.metadata = meta
                
                # Poll pause state
                paused = self.get_property("pause")
                if paused is not None:
                    self.paused = paused
                
                # Check end of file
                idle = self.get_property("idle-active")
                if idle is True:
                     # Song finished
                     self.handle_end_of_file()

            time.sleep(0.5)

    def get_next_index(self, current_idx):
        idx = current_idx + 1
        while idx < len(self.files):
            if self.files[idx]['type'] == 'file':
                return idx
            idx += 1
        return None

    def get_prev_index(self, current_idx):
        idx = current_idx - 1
        while idx >= 0:
            if self.files[idx]['type'] == 'file':
                return idx
            idx -= 1
        return None

    def handle_end_of_file(self):
        if self.playing_index != -1:
             next_idx = self.get_next_index(self.playing_index)
             if next_idx is not None:
                 self.play_file(next_idx)
             else:
                 self.stop_music()

    def play_next(self):
        if self.playing_index != -1:
            next_idx = self.get_next_index(self.playing_index)
            if next_idx is not None:
                self.play_file(next_idx)

    def play_prev(self):
        if self.playing_index != -1:
            prev_idx = self.get_prev_index(self.playing_index)
            if prev_idx is not None:
                self.play_file(prev_idx)

    def _preexec_fn(self):
        # Ensure the child process receives SIGTERM if the parent dies
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        PR_SET_PDEATHSIG = 1
        libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
        # Still create a new session
        os.setsid()

    def play_file(self, index):
        self.cleanup() # Stop current
        
        if 0 <= index < len(self.files) and self.files[index]['type'] == 'file':
            self.playing_index = index
            file_path = os.path.join(self.current_dir, self.files[index]['name'])
            self.metadata = {} # Reset metadata
            
            try:
                # Start MPV with IPC
                cmd = [
                    'mpv',
                    '--no-video',
                    f'--input-ipc-server={self.ipc_socket}',
                    f'--volume={self.volume}',
                    '--volume-max=200',
                    '--idle', # Keep mpv running even after file ends
                    file_path
                ]
                
                self.mpv_process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=self._preexec_fn
                )
                self.paused = False
                self.view_mode = 'player' # Switch to player view
            except Exception as e:
                pass

    def stop_music(self):
        self.cleanup()
        self.playing_index = -1
        self.paused = False
        self.position = 0
        self.duration = 0
        self.view_mode = 'browser'

    def toggle_pause(self):
        if self.mpv_process:
            self.send_ipc_command(["cycle", "pause"])

    def change_volume(self, delta):
        self.volume = max(0, min(200, self.volume + delta))
        if self.mpv_process:
            self.send_ipc_command(["set_property", "volume", self.volume])

    def format_time(self, seconds):
        if seconds is None: return "00:00"
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    def draw_progress_bar(self, y, width):
        if self.duration <= 0:
            pct = 0
        else:
            pct = self.position / self.duration
        
        bar_width = width - 20 # Space for timestamps
        fill_width = int(bar_width * pct)
        
        bar = "[" + "=" * fill_width + "-" * (bar_width - fill_width) + "]"
        time_str = f"{self.format_time(self.position)} / {self.format_time(self.duration)}"
        
        try:
            self.stdscr.addstr(y, 2, f"{bar} {time_str}", curses.color_pair(5))
        except:
            pass

        def draw_player_view(self):

            height, width = self.stdscr.getmaxyx()

            

            # Check if terminal is too small

            if height < 10 or width < 40:

                try:

                    self.stdscr.addstr(0, 0, "Terminal too small")

                except: pass

                return

    

            # Determine current, prev, next

            title = "No Media"

            artist = "Unknown Artist"

            prev_name = ""

            next_name = ""

            

            if self.playing_index != -1:

                # Current

                title = self.files[self.playing_index]['name']

                if 'title' in self.metadata: title = self.metadata['title']

                if 'artist' in self.metadata: artist = self.metadata['artist']

                

                # Prev

                p_idx = self.get_prev_index(self.playing_index)

                if p_idx is not None:

                    prev_name = f"Prev: {self.files[p_idx]['name']}"

                    

                # Next

                n_idx = self.get_next_index(self.playing_index)

                if n_idx is not None:

                    next_name = f"Next: {self.files[n_idx]['name']}"

                

            # Layout

            center_y = height // 2

            

            # Previous Track (Dimmed)

            if prev_name and center_y - 5 > 0:

                try:

                    self.stdscr.addstr(center_y - 5, (width - len(prev_name)) // 2, prev_name[:width], curses.A_DIM)

                    self.stdscr.addstr(center_y - 4, (width - 1) // 2, "^", curses.A_DIM)

                except: pass

    

            # Current Track (Bold/Color)

            try:

                self.stdscr.attron(curses.A_BOLD)

                self.stdscr.addstr(center_y - 2, max(0, (width - len(title)) // 2), title[:width])

                self.stdscr.attroff(curses.A_BOLD)

                self.stdscr.addstr(center_y - 1, max(0, (width - len(artist)) // 2), artist[:width])

            except: pass

            

            # Status

            status = "PAUSED" if self.paused else "PLAYING"

            try:

                self.stdscr.addstr(center_y + 1, (width - len(status)) // 2, status, 

                               curses.color_pair(3) if self.paused else curses.color_pair(2))

            except: pass

    

            # Progress

            self.draw_progress_bar(center_y + 3, width - 4)

            

            # Volume

            vol_str = f"Volume: {self.volume}%"

            try:

                self.stdscr.addstr(center_y + 5, (width - len(vol_str)) // 2, vol_str)

            except: pass

    

            # Next Track (Dimmed)

            if next_name and center_y + 8 < height - 1:

                 try:

                     self.stdscr.addstr(center_y + 7, (width - 1) // 2, "v", curses.A_DIM)

                     self.stdscr.addstr(center_y + 8, (width - len(next_name)) // 2, next_name[:width], curses.A_DIM)

                 except: pass

    

            # Controls Hint

            hint = "[n] Next  [p] Prev  [Space] Pause  [q] Browser  [+/-] Vol"

            try:

                self.stdscr.addstr(height - 2, max(0, (width - len(hint)) // 2), hint[:width], curses.color_pair(1))

            except: pass

    

        def draw_browser(self):

            height, width = self.stdscr.getmaxyx()

            

            # Header

            header = f" Browser: {self.current_dir} "

            try:

                self.stdscr.attron(curses.color_pair(1))

                self.stdscr.addstr(0, 0, header + " " * (width - len(header) - 1))

                self.stdscr.attroff(curses.color_pair(1))

            except: pass

            

            list_height = height - 2

            for i in range(list_height):

                file_idx = i + self.scroll_offset

                if file_idx >= len(self.files): break

                

                item = self.files[file_idx]

                name = item['name']

                if item['type'] == 'dir': name += "/"

                

                style = curses.A_NORMAL

                prefix = "  "

                

                if item['type'] == 'dir': style = curses.color_pair(3)

                if self.playing_index != -1 and self.files[self.playing_index] == item:

                    style = curses.color_pair(2) | curses.A_BOLD

                    prefix = ">>"

                if file_idx == self.selected_index:

                    style = curses.color_pair(1)

                    

                try:

                    line = f"{prefix} {name}"

                    self.stdscr.addstr(i + 1, 0, line[:width], style)

                except:

                    pass

                    

            # Mini Player Status at bottom if playing

            if self.playing_index != -1:

                status = f" Playing: {self.files[self.playing_index]['name']} ({self.volume}%) [TAB to View]"

                try:

                    self.stdscr.addstr(height-1, 0, status[:width], curses.color_pair(2))

                except:

                    pass

    

        def run(self):

            while self.running:

                self.stdscr.erase()

                

                if self.view_mode == 'player':

                    self.draw_player_view()

                else:

                    self.draw_browser()

                    

                try:

                    key = self.stdscr.getch()

                except:

                    continue

                    

                if key != -1:

                    if key == curses.KEY_RESIZE:

                        curses.update_lines_cols()

                        self.stdscr.clear()

                        self.stdscr.refresh()

                        continue

                    

                    if key == ord('q'):

                        if self.view_mode == 'player':

                            self.view_mode = 'browser'

                        else:

                            self.running = False

                    elif key == 9: # TAB

                        self.view_mode = 'player' if self.view_mode == 'browser' and self.playing_index != -1 else 'browser'

                    elif key == ord(' '):

                        self.toggle_pause()

                    elif key == ord('s'):

                        self.stop_music()

                    elif key == ord('+') or key == ord('='):

                        self.change_volume(5)

                    elif key == ord('-') or key == ord('_'):

                        self.change_volume(-5)

                    elif key == ord('n'):

                        self.play_next()

                    elif key == ord('p'):

                        self.play_prev()

                    

                    # Browser navigation
                if self.view_mode == 'browser':
                    if key == curses.KEY_UP:
                        self.selected_index = max(0, self.selected_index - 1)
                        if self.selected_index < self.scroll_offset:
                            self.scroll_offset = self.selected_index
                    elif key == curses.KEY_DOWN:
                        self.selected_index = min(len(self.files) - 1, self.selected_index + 1)
                        height, _ = self.stdscr.getmaxyx()
                        if self.selected_index >= self.scroll_offset + (height - 2):
                            self.scroll_offset = self.selected_index - (height - 2) + 1
                    elif key == curses.KEY_ENTER or key == 10 or key == 13:
                        if self.files:
                            if self.files[self.selected_index]['type'] == 'dir':
                                new_path = os.path.abspath(os.path.join(self.current_dir, self.files[self.selected_index]['name']))
                                if os.path.isdir(new_path):
                                    self.current_dir = new_path
                                    self.selected_index = 0
                                    self.scroll_offset = 0
                                    self.scan_directory()
                            else:
                                self.play_file(self.selected_index)

            self.stdscr.refresh()

def check_dependencies():
    if shutil.which('mpv'): return True
    print("MPV player not found. Attempting to install...")
    distro_id = "unknown"
    try:
        if os.path.exists("/etc/os-release"):
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("ID="):
                        distro_id = line.strip().split("=")[1].strip('"')
                        break
    except: pass

    cmd = []
    if distro_id in ["ubuntu", "debian", "linuxmint", "pop", "kali"]:
        cmd = ["sudo", "apt-get", "install", "-y", "mpv"]
    elif distro_id in ["fedora", "centos", "rhel"]:
        cmd = ["sudo", "dnf", "install", "-y", "mpv"]
    elif distro_id in ["arch", "manjaro"]:
        cmd = ["sudo", "pacman", "-S", "--noconfirm", "mpv"]
    elif distro_id in ["opensuse", "suse"]:
        cmd = ["sudo", "zypper", "install", "-y", "mpv"]
    elif distro_id in ["alpine"]:
        cmd = ["sudo", "apk", "add", "mpv"]
    else:
        print(f"Manual installation required for distro: {distro_id}")
        return False

    try:
        subprocess.check_call(cmd)
        return True
    except:
        return False

def main():
    if not check_dependencies():
        sys.exit(1)
    try:
        curses.wrapper(lambda stdscr: MusicPlayer(stdscr).run())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
