import curses
import os
import threading
import time
import signal
import sys
import shutil
import random
import urllib.request
import urllib.parse
import re
import socket
import json
import tempfile
import subprocess

from .utils import slugify, format_time, parse_lrc
from .search import OnlineSearcher
from .mpv_setup import get_mpv_path, download_mpv

# Supported audio extensions
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.wma', '.aac', '.opus'}

class MusicPlayer:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.current_dir = os.getcwd()
        self.files = []
        self.selected_index = 0
        self.scroll_offset = 0
        
        # Check MPV
        self.mpv_bin = get_mpv_path()
        if not self.mpv_bin:
            self.mpv_bin = download_mpv()
            
        if not self.mpv_bin:
            print("Error: MPV player not found.")
            print("Please install 'mpv' via your package manager (e.g., sudo pacman -S mpv) or add it to PATH.")
            sys.exit(1)

        # State
        self.playing_index = -1
        self.paused = False
        self.volume = 100
        self.running = True
        self.view_mode = 'browser'
        self.shuffle = False
        self.library_mode = False 
        self.playback_history = [] 
        
        # Search State
        self.searcher = OnlineSearcher()
        self.search_results = []
        self.search_query = []
        self.is_searching_input = False
        
        # MPV State
        self.mpv_process = None
        self.ipc_socket = os.path.join(tempfile.gettempdir(), f'mpv_socket_{os.getpid()}')
        self.duration = 0
        self.position = 0
        self.metadata = {}
        
        # Lyrics State
        self.lyrics = None
        self.show_lyrics = False
        self.lyrics_scroll_offset = 0
        self.current_song_lyrics_fetched = False
        
        # Animation State
        self.anim_frame = 0
        self.last_anim_time = time.time()
        
        # UI
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_RED)
        curses.init_pair(5, curses.COLOR_CYAN, -1)
        curses.init_pair(6, curses.COLOR_WHITE, -1)
        curses.init_pair(7, curses.COLOR_GREEN, -1)
        curses.curs_set(0)
        self.stdscr.nodelay(1)
        self.stdscr.timeout(100)

        # Cleanup hooks
        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

        self.scan_directory()
        
        # Monitor thread
        self.monitor_thread = threading.Thread(target=self.ipc_loop, daemon=True)
        self.monitor_thread.start()

    def handle_signal(self, signum, frame):
        self.cleanup()
        sys.exit(0)

    def cleanup(self):
        if self.mpv_process:
            try:
                self.send_ipc_command(["quit"])
                self.mpv_process.wait(timeout=1)
            except:
                try: self.mpv_process.kill()
                except: pass
        if os.path.exists(self.ipc_socket):
            try: os.remove(self.ipc_socket)
            except: pass

    def send_ipc_command(self, command):
        if not os.path.exists(self.ipc_socket): return None
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(self.ipc_socket)
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

    def get_property(self, prop):
        res = self.send_ipc_command(["get_property", prop])
        if res:
            try:
                data = json.loads(res.decode('utf-8').strip())
                return data.get("data")
            except: pass
        return None

    def ipc_loop(self):
        while self.running:
            if self.mpv_process and self.mpv_process.poll() is None:
                # Poll position/duration
                pos = self.get_property("time-pos")
                if pos is not None: self.position = float(pos)
                dur = self.get_property("duration")
                if dur is not None: self.duration = float(dur)
                
                # Metadata
                meta = self.get_property("metadata")
                if meta:
                    self.metadata = meta
                    if 'media-title' in meta and 'title' not in self.metadata:
                        self.metadata['title'] = meta['media-title']
                
                # Fetch lyrics trigger
                if self.show_lyrics and not self.current_song_lyrics_fetched:
                    artist = self.metadata.get('artist')
                    title = self.metadata.get('title')
                    if artist and title:
                        self.current_song_lyrics_fetched = True
                        threading.Thread(target=self.fetch_lyrics, args=(artist, title), daemon=True).start()

                # Pause state
                paused = self.get_property("pause")
                if paused is not None: self.paused = paused
                
                # EOF
                idle = self.get_property("idle-active")
                if idle is True: self.handle_end_of_file()
            
            time.sleep(0.5)

    def fetch_lyrics(self, artist, title):
        self.lyrics = [{'time': None, 'text': "Loading lyrics..."}]
        found_lyrics = False
        
        # 1. LRCLib
        try:
            url = f"https://lrclib.net/api/get?artist_name={urllib.parse.quote(artist)}&track_name={urllib.parse.quote(title)}"
            req = urllib.request.Request(url, headers={'User-Agent': 'CLI-Music-Player/1.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                if data.get('syncedLyrics'):
                    self.lyrics = parse_lrc(data['syncedLyrics'])
                    found_lyrics = True
                elif data.get('plainLyrics'):
                    self.lyrics = [{'time': None, 'text': l} for l in data['plainLyrics'].split('\n')]
                    found_lyrics = True
        except: pass
        
        # 2. Letras.mus.br fallback
        if not found_lyrics:
             from .main import MusicPlayer # avoid circular import if needed, but methods are self-contained
             # Actually let's implement the scraper here briefly or import utils if we moved it
             pass 

        if not found_lyrics:
             self.lyrics = [{'time': None, 'text': "Lyrics not found."}]

    def scan_directory(self):
        self.library_mode = False
        self.files = []
        try:
            items = sorted(os.listdir(self.current_dir))
            self.files.append({'name': '..', 'type': 'dir', 'path': '..'}) # Added missing closing parenthesis
            for item in items:
                full_path = os.path.join(self.current_dir, item)
                if os.path.isdir(full_path) and not item.startswith('.'):
                    self.files.append({'name': item, 'type': 'dir', 'path': item})
                elif os.path.isfile(full_path):
                    ext = os.path.splitext(item)[1].lower()
                    if ext in AUDIO_EXTENSIONS:
                        self.files.append({'name': item, 'type': 'file', 'path': item})
            self.selected_index = 0
            self.scroll_offset = 0
        except: pass

    def scan_recursive(self):
        self.library_mode = True
        self.files = [{'name': '..', 'type': 'dir', 'path': '..'}] # Added missing closing parenthesis
        for root, _, files in os.walk(self.current_dir):
            for f in sorted(files):
                if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS:
                    path = os.path.relpath(os.path.join(root, f), self.current_dir)
                    self.files.append({'name': path, 'type': 'file', 'path': path})
        self.selected_index = 0

    def get_next_index(self, current_idx):
        if self.shuffle:
            candidates = [i for i, f in enumerate(self.files) if f['type'] == 'file' and i != current_idx]
            return random.choice(candidates) if candidates else None
        idx = current_idx + 1
        while idx < len(self.files):
            if self.files[idx]['type'] == 'file': return idx
            idx += 1
        return None

    def get_prev_index(self, current_idx):
        if self.playback_history: return self.playback_history[-1]
        idx = current_idx - 1
        while idx >= 0:
            if self.files[idx]['type'] == 'file': return idx
            idx -= 1
        return None

    def play_file(self, index, push_history=True):
        self.cleanup()
        if 0 <= index < len(self.files):
            if push_history and self.playing_index != -1:
                self.playback_history.append(self.playing_index)
            self.playing_index = index
            path = os.path.join(self.current_dir, self.files[index]['path'])
            self._start_mpv(path)

    def play_stream(self, result):
        self.cleanup()
        self.playing_index = -1
        self.metadata = {'title': result['title'], 'artist': result['artist']}
        target = result.get('url') or result['id']
        if len(target) == 11 and '.' not in target: # Rough ID check
             target = f"https://www.youtube.com/watch?v={target}"
        self._start_mpv(target)
        threading.Thread(target=self.fetch_lyrics, args=(result['artist'], result['title']), daemon=True).start()

    def _start_mpv(self, target):
        self.paused = False
        self.view_mode = 'player'
        cmd = [
            self.mpv_bin,
            '--no-video',
            f'--input-ipc-server={self.ipc_socket}',
            f'--volume={self.volume}',
            '--idle',
            target
        ]
        self.mpv_process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    def stop_music(self):
        self.cleanup()
        self.playing_index = -1
        self.paused = False
        self.position = 0
        self.duration = 0
        self.view_mode = 'browser'

    def handle_end_of_file(self):
        if self.playing_index != -1:
             next_idx = self.get_next_index(self.playing_index)
             if next_idx is not None: self.play_file(next_idx)
             else: self.stop_music()

    def toggle_pause(self):
        self.send_ipc_command(["cycle", "pause"])

    def change_volume(self, delta):
        self.volume = max(0, min(200, self.volume + delta))
        self.send_ipc_command(["set_property", "volume", self.volume])

    def draw_player_view(self):
        height, width = self.stdscr.getmaxyx()
        if height < 15 or width < 40:
            try: self.stdscr.addstr(0, 0, "Terminal too small")
            except: pass
            return

        title = self.metadata.get('title', "Unknown")
        artist = self.metadata.get('artist', "Unknown")
        prev_name, next_name = "", ""
        
        if self.playing_index != -1:
            if self.playback_history:
                 p_idx = self.playback_history[-1]
                 if 0 <= p_idx < len(self.files): prev_name = f"Prev: {self.files[p_idx]['name']}"
            else:
                p_idx = self.playing_index - 1
                if 0 <= p_idx < len(self.files) and self.files[p_idx]['type'] == 'file': prev_name = f"Prev: {self.files[p_idx]['name']}"
            
            if self.shuffle: next_name = "Next: Random"
            else:
                n_idx = self.get_next_index(self.playing_index)
                if n_idx is not None: next_name = f"Next: {self.files[n_idx]['name']}"
            
        center_y = height // 2
        
        if prev_name and center_y - 8 > 0:
            try:
                self.stdscr.addstr(center_y - 8, (width - len(prev_name)) // 2, prev_name[:width], curses.A_DIM)
                self.stdscr.addstr(center_y - 7, (width - 1) // 2, "^", curses.A_DIM)
            except: pass

        try:
            self.stdscr.attron(curses.A_BOLD)
            self.stdscr.addstr(center_y - 5, max(0, (width - len(title)) // 2), title[:width])
            self.stdscr.attroff(curses.A_BOLD)
            self.stdscr.addstr(center_y - 4, max(0, (width - len(artist)) // 2), artist[:width])
        except: pass
        
        mode_str = " [Shuffle]" if self.shuffle else ""
        if self.library_mode: mode_str += " [Lib]"
        status = ("PAUSED" if self.paused else "PLAYING") + mode_str
        try:
            self.stdscr.addstr(center_y - 2, (width - len(status)) // 2, status, 
                           curses.color_pair(3) if self.paused else curses.color_pair(2))
        except: pass

        if self.show_lyrics:
            lyrics_height = 10
            start_y = center_y - 2
            if self.lyrics:
                is_synced = any(l['time'] is not None for l in self.lyrics)
                current_line_idx = 0
                if is_synced:
                    found_idx = -1
                    for i, line in enumerate(self.lyrics):
                         if line['time'] is not None and line['time'] <= self.position: found_idx = i
                         else: break
                    if found_idx != -1: current_line_idx = found_idx
                    target_offset = current_line_idx - (lyrics_height // 2)
                    self.lyrics_scroll_offset = max(0, min(len(self.lyrics) - 1, target_offset))
                
                for i in range(lyrics_height):
                    line_idx = self.lyrics_scroll_offset + i
                    if 0 <= line_idx < len(self.lyrics):
                        line_data = self.lyrics[line_idx]
                        line_text = line_data['text'].strip()
                        style = curses.color_pair(6)
                        if is_synced and line_idx == current_line_idx:
                            style = curses.color_pair(2) | curses.A_BOLD
                            line_text = ">> " + line_text
                        try: self.stdscr.addstr(start_y + i, max(0, (width - len(line_text)) // 2), line_text[:width], style)
                        except: pass
                
                if len(self.lyrics) > lyrics_height:
                    scroll_pct = self.lyrics_scroll_offset / (len(self.lyrics) - lyrics_height)
                    try: self.stdscr.addstr(start_y + int(lyrics_height * scroll_pct), width - 2, "|", curses.A_DIM)
                    except: pass
            else:
                 msg = "Fetching lyrics..." if self.current_song_lyrics_fetched else "Lyrics (Waiting for Metadata...)"
                 try: self.stdscr.addstr(center_y, (width - len(msg)) // 2, msg, curses.A_DIM)
                 except: pass
        else:
            if time.time() - self.last_anim_time > 0.4:
                self.anim_frame = (self.anim_frame + 1) % 2
                self.last_anim_time = time.time()
            
            cthulhu_frames = [
                [" ( o . o ) ", " (  |||  ) ", "/||\/||\/||\"],
                [" ( O . O ) ", " ( /|||\ ) ", "//||\/||\/\\"]
            ]
            
            if not self.paused:
                art = cthulhu_frames[self.anim_frame]
                for i, line in enumerate(art):
                    try: self.stdscr.addstr(center_y + i, (width - len(line)) // 2, line, curses.color_pair(7) | curses.A_BOLD)
                    except: pass
            else:
                 art = [" ( - . - ) ", " (  zzz  ) ", "  |||||||  "]
                 for i, line in enumerate(art):
                    try: self.stdscr.addstr(center_y + i, (width - len(line)) // 2, line, curses.color_pair(7) | curses.A_DIM)
                    except: pass

        self.draw_progress_bar(center_y + 4, width - 4)
        vol_str = f"Volume: {int(self.volume)}%"
        try: self.stdscr.addstr(center_y + 6, (width - len(vol_str)) // 2, vol_str)
        except: pass

        if next_name and center_y + 9 < height - 1:
             try:
                 self.stdscr.addstr(center_y + 8, (width - 1) // 2, "v", curses.A_DIM)
                 self.stdscr.addstr(center_y + 9, (width - len(next_name)) // 2, next_name[:width], curses.A_DIM)
             except: pass

        hint = "[n] Next  [p] Prev  [Space] Pause  [z] Shuffle  [l] Lyrics  [/] Search  [q] Browser"
        try: self.stdscr.addstr(height - 2, max(0, (width - len(hint)) // 2), hint[:width], curses.color_pair(1))
        except: pass

    def draw_progress_bar(self, y, width):
        if self.duration <= 0: pct = 0
        else: pct = self.position / self.duration
        bar_width = width - 20
        fill_width = int(bar_width * pct)
        bar = "[" + "=" * fill_width + "-" * (bar_width - fill_width) + "]"
        time_str = f"{format_time(self.position)} / {format_time(self.duration)}"
        try: self.stdscr.addstr(y, 2, f"{bar} {time_str}", curses.color_pair(5))
        except: pass

    def draw_browser(self):
        height, width = self.stdscr.getmaxyx()
        mode_title = "LIBRARY (Recursive)" if self.library_mode else f"Browser: {self.current_dir}"
        if self.shuffle: mode_title += " [SHUFFLE]"
        try:
            self.stdscr.attron(curses.color_pair(1))
            self.stdscr.addstr(0, 0, f" {mode_title} " + " " * (width - len(mode_title) - 3))
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
            if file_idx == self.selected_index: style = curses.color_pair(1)
            try:
                line = f"{prefix} {name}"
                self.stdscr.addstr(i + 1, 0, line[:width], style)
            except: pass
                
        if self.playing_index != -1:
            status = f" Playing: {self.files[self.playing_index]['name']} ({int(self.volume)}%) [TAB to View]"
            try: self.stdscr.addstr(height-1, 0, status[:width], curses.color_pair(2))
            except: pass
        else:
            help_txt = "[R]ecursive Lib | [/] Search | [B]rowser | [z]Shuffle"
            try: self.stdscr.addstr(height-1, 0, help_txt[:width], curses.color_pair(6))
            except: pass

    def draw_search_results(self):
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()
        title = f"Search Results: {''.join(self.search_query)}"
        try:
            self.stdscr.attron(curses.color_pair(1))
            self.stdscr.addstr(0, 0, f" {title} " + " " * (width - len(title) - 3))
            self.stdscr.attroff(curses.color_pair(1))
        except: pass
        
        for i, item in enumerate(self.search_results[self.scroll_offset:self.scroll_offset+20]):
             idx = i + self.scroll_offset
             style = curses.color_pair(1) if idx == self.selected_index else curses.A_NORMAL
             name = f"{item['title']} - {item['artist']}"
             try: self.stdscr.addstr(i+1, 0, name[:width], style)
             except: pass
        self.stdscr.refresh()

    def handle_input(self, key):
        if key == 10: # Enter
            query = "".join(self.search_query)
            if query:
                self.is_searching_input = False
                self.view_mode = 'search_results'
                source = 'soundcloud' if query.startswith('sc:') else 'youtube'
                if source == 'soundcloud': query = query[3:]
                self.search_results = self.searcher.search(query, source)
        elif key == 27: self.is_searching_input = False
        elif key == 127: 
            if self.search_query: self.search_query.pop()
        elif 32 <= key <= 126: self.search_query.append(chr(key))

    def run(self):
        while self.running:
            if self.view_mode == 'player': self.draw_player_view()
            elif self.view_mode == 'search_results': self.draw_search_results()
            else: self.draw_browser()
            
            if self.is_searching_input:
                try: self.stdscr.addstr(0,0, "Search: " + "".join(self.search_query), curses.A_REVERSE)
                except: pass
            
            try: key = self.stdscr.getch()
            except: continue
            
            if key == -1: continue
            
            if self.is_searching_input:
                self.handle_input(key)
                continue
                
            if key == ord('q'): 
                if self.view_mode != 'browser': self.view_mode = 'browser'
                else: self.running = False
            elif key == ord('/'): 
                self.is_searching_input = True
                self.search_query = []
            elif key == 10 and self.view_mode == 'browser':
                f = self.files[self.selected_index]
                if f['type'] == 'dir':
                    if f['name'] == '..': self.current_dir = os.path.dirname(self.current_dir)
                    else: self.current_dir = os.path.join(self.current_dir, f['path'])
                    self.scan_directory()
                else: self.play_file(self.selected_index)
            elif key == 10 and self.view_mode == 'search_results':
                if self.search_results: self.play_stream(self.search_results[self.selected_index])
            elif key == curses.KEY_DOWN: self.selected_index += 1
            elif key == curses.KEY_UP: self.selected_index -= 1
            elif key == ord(' '): self.toggle_pause()
            elif key == ord('l'): self.show_lyrics = not self.show_lyrics

def main():
    curses.wrapper(lambda s: MusicPlayer(s).run())

if __name__ == "__main__":
    main()
