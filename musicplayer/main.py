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
import atexit

from .utils import slugify, format_time, parse_lrc
from .search import OnlineSearcher
from .mpv_setup import get_mpv_path, download_mpv
from .config import load_config, save_config
from .ipc import MpvIpcClient

# Supported audio extensions
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.wma', '.aac', '.opus'}

class MusicPlayer:
    def __init__(self, stdscr, debug=False):
        self.stdscr = stdscr
        self.debug = debug
        
        # Determine start directory
        self.config = load_config()
        start_dir = os.getcwd()
        
        if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
            start_dir = os.path.abspath(sys.argv[1])
        elif 'default_dir' in self.config and os.path.isdir(self.config['default_dir']):
            start_dir = self.config['default_dir']
            
        self.current_dir = start_dir
        self.files = []
        self.selected_index = 0
        self.scroll_offset = 0
        self.message = "" 
        self.message_time = 0
        
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
        self.view_mode = 'player'
        self.shuffle = False
        self.library_mode = False 
        self.playback_history = [] 
        
        # Search State
        self.searcher = OnlineSearcher()
        self.search_results = []
        self.search_query = []
        self.is_searching_input = False
        self.queue = []
        
        # MPV State
        self.mpv_process = None
        self.ipc = MpvIpcClient()
        self.duration = 0
        self.position = 0
        self.metadata = {'title': 'No Music Playing', 'artist': 'Press [b] for Library'}
        
        # Lyrics State
        self.lyrics = None
        self.show_lyrics = False
        self.lyrics_scroll_offset = 0
        self.current_song_lyrics_fetched = False
        
        # Animation State
        self.anim_frame = 0
        self.last_anim_time = time.time()
        
        # UI Colors
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
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

        self.scan_directory()
        
        # Monitor thread
        self.monitor_thread = threading.Thread(target=self.ipc_loop, daemon=True)
        self.monitor_thread.start()

    def is_in_queue(self, item):
        # item can be from self.files (local) or self.search_results (stream)
        # Check local file
        if item.get('type') == 'file':
            # Resolve absolute path for the item to check against queue
            # Note: item from browser is relative or just name
            try:
                abs_path = os.path.abspath(os.path.join(self.current_dir, item['path']))
                for q_item in self.queue:
                    if q_item['type'] == 'file' and q_item['path'] == abs_path:
                        return True
            except: pass
        else:
            # Check stream by ID or URL
            target_id = item.get('id')
            target_url = item.get('url')
            for q_item in self.queue:
                if q_item['type'] != 'file':
                     if (target_id and q_item.get('id') == target_id) or \
                        (target_url and q_item.get('url') == target_url):
                         return True
        return False

    def handle_signal(self, signum, frame):
        self.cleanup()
        sys.exit(0)

    def cleanup(self):
        if self.mpv_process:
            try:
                self.ipc.send_command(["quit"])
                try: self.mpv_process.wait(timeout=0.5)
                except subprocess.TimeoutExpired: self.mpv_process.kill()
            except:
                try: self.mpv_process.kill()
                except: pass
            self.mpv_process = None
            
        self.ipc.cleanup()
        
        # Cleanup Cache
        try:
            cache_dir = os.path.join(tempfile.gettempdir(), "musicplayer_cthulhu_cache")
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir)
        except: pass

    def get_property(self, prop):
        res = self.ipc.send_command(["get_property", prop])
        if res:
            try:
                data = json.loads(res.decode('utf-8').strip())
                return data.get("data")
            except: pass
        return None

    def ipc_loop(self):
        while self.running:
            if self.mpv_process and self.mpv_process.poll() is None:
                pos = self.get_property("time-pos")
                if pos is not None: self.position = float(pos)
                dur = self.get_property("duration")
                if dur is not None: self.duration = float(dur)
                
                meta = self.get_property("metadata")
                if meta:
                    new_title = meta.get('title') or meta.get('media-title')
                    new_artist = meta.get('artist')
                    if new_title: self.metadata['title'] = new_title
                    if new_artist: self.metadata['artist'] = new_artist
                
                if self.show_lyrics and not self.current_song_lyrics_fetched:
                    artist = self.metadata.get('artist')
                    title = self.metadata.get('title')
                    if artist and title and artist != "Unknown" and title != "Unknown":
                        self.current_song_lyrics_fetched = True
                        threading.Thread(target=self.fetch_lyrics, args=(artist, title), daemon=True).start()

                paused = self.get_property("pause")
                if paused is not None: self.paused = paused
                
                idle = self.get_property("idle-active")
                if idle is True: self.handle_end_of_file()
            
            time.sleep(0.5)

    def fetch_from_letras_mus_br(self, artist, title):
        try:
            slug_artist = slugify(artist)
            slug_title = slugify(title)
            url = f"https://www.letras.mus.br/{slug_artist}/{slug_title}/"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8', errors='ignore')
                match = re.search(r'<div class="cnt-letra[^\"]*"> (.*?)</div>', html, re.DOTALL)
                if match:
                    raw_html = match.group(1)
                    text = re.sub(r'<br\s*/?>', '\n', raw_html)
                    text = re.sub(r'<[^>]+>', '', text)
                    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('&quot;', '"')
                    lines = [line.strip() for line in text.split('\n')]
                    return [{'time': None, 'text': line} for line in lines]
        except: pass
        return None

    def fetch_lyrics(self, artist, title):
        self.lyrics = [{'time': None, 'text': "Loading lyrics..."}]
        found_lyrics = False
        try:
            url = f"https://lrclib.net/api/get?artist_name={urllib.parse.quote(artist)}&track_name={urllib.parse.quote(title)}"
            req = urllib.request.Request(url, headers={'User-Agent': 'CLI-Music-Player/1.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                if data.get('syncedLyrics'):
                    self.lyrics = parse_lrc(data['syncedLyrics'])
                    found_lyrics = True
                elif data.get('plainLyrics'):
                    self.lyrics = [{'time': None, 'text': l} for l in data['plainLyrics'].split('\n')]
                    found_lyrics = True
        except: pass
        
        if not found_lyrics:
             res = self.fetch_from_letras_mus_br(artist, title)
             if res:
                 self.lyrics = res
                 found_lyrics = True

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
                    if os.path.splitext(item)[1].lower() in AUDIO_EXTENSIONS:
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
            self.metadata = {'title': self.files[index]['name'], 'artist': 'Local File'}
            self._start_mpv(path)

    def play_stream(self, result):
        self.cleanup()
        self.playing_index = -1
        self.metadata = {'title': result['title'], 'artist': result['artist']}
        self.current_song_lyrics_fetched = False
        target = result.get('url') or result['id']
        if len(target) == 11 and '.' not in target:
             target = f"https://www.youtube.com/watch?v={target}"
        self._start_mpv(target)
        if self.show_lyrics:
            threading.Thread(target=self.fetch_lyrics, args=(result['artist'], result['title']), daemon=True).start()

    def play_queue_item(self, item):
        self.cleanup()
        self.playing_index = -1
        self.metadata = {'title': item.get('title', item.get('name', 'Unknown')), 
                         'artist': item.get('artist', 'Unknown')}
        self.current_song_lyrics_fetched = False
        
        target = ""
        if item['type'] == 'file':
            target = item['path']
        else:
            target = item.get('url') or item['id']
            if len(target) == 11 and '.' not in target:
                 target = f"https://www.youtube.com/watch?v={target}"
                 
        self._start_mpv(target)
        if self.show_lyrics and item['type'] != 'file':
            threading.Thread(target=self.fetch_lyrics, args=(self.metadata['artist'], self.metadata['title']), daemon=True).start()

    def _start_mpv(self, target):
        self.paused = False
        self.view_mode = 'player'
        self.position = 0
        self.duration = 0
        cmd = [
            self.mpv_bin,
            '--no-video',
            self.ipc.get_mpv_flag(),
            f'--volume={self.volume}',
            '--idle',
            target
        ]
        self.mpv_process = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    def stop_music(self):
        self.cleanup()
        self.playing_index = -1
        self.paused = False
        self.view_mode = 'browser'

    def handle_end_of_file(self):
        if self.queue:
            item = self.queue.pop(0)
            self.play_queue_item(item)
            return

        if self.playing_index != -1:
             next_idx = self.get_next_index(self.playing_index)
             if next_idx is not None: self.play_file(next_idx)
             else: self.stop_music()
        else:
             self.stop_music()

    def toggle_pause(self):
        self.ipc.send_command(["cycle", "pause"])

    def change_volume(self, delta):
        self.volume = max(0, min(200, self.volume + delta))
        self.ipc.send_command(["set_property", "volume", self.volume])

    def draw_player_view(self):
        height, width = self.stdscr.getmaxyx()
        if height < 15 or width < 40:
            try: self.stdscr.addstr(0, 0, "Terminal too small")
            except: pass
            return

        title = self.metadata.get('title', "Unknown")
        artist = self.metadata.get('artist', "Unknown")
        center_y = height // 2
        
        # 1. Current Track
        try:
            self.stdscr.attron(curses.A_BOLD)
            self.stdscr.addstr(center_y - 5, max(0, (width - len(title)) // 2), title[:width])
            self.stdscr.attroff(curses.A_BOLD)
            self.stdscr.addstr(center_y - 4, max(0, (width - len(artist)) // 2), artist[:width])
        except: pass
        
        # 2. Status
        status = ("PAUSED" if self.paused else "PLAYING") + (" [Shuffle]" if self.shuffle else "")
        try:
            self.stdscr.addstr(center_y - 2, (width - len(status)) // 2, status, 
                           curses.color_pair(3) if self.paused else curses.color_pair(2))
        except: pass

        # 3. Cthulhu or Lyrics
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
                        line_text = self.lyrics[line_idx]['text'].strip()
                        style = curses.color_pair(6)
                        if is_synced and line_idx == current_line_idx:
                            style = curses.color_pair(2) | curses.A_BOLD
                            line_text = ">> " + line_text
                        try: self.stdscr.addstr(start_y + i, max(0, (width - len(line_text)) // 2), line_text[:width], style)
                        except: pass
            else:
                 msg = "Fetching lyrics..." if self.current_song_lyrics_fetched else "Lyrics (Waiting...)"
                 try: self.stdscr.addstr(center_y, (width - len(msg)) // 2, msg, curses.A_DIM)
                 except: pass
        else:
            if time.time() - self.last_anim_time > 0.4:
                self.anim_frame = (self.anim_frame + 1) % 2
                self.last_anim_time = time.time()
            cthulhu_frames = [
                [" ( o . o ) ", " (  |||  ) ", "/||\\/||\\/||\\"],
                [" ( O . O ) ", " ( /|||\\ ) ", "//||\\/||\\/||\\\\"]
            ]
            art = cthulhu_frames[self.anim_frame] if not self.paused else [" ( - . - ) ", " (  zzz  ) ", "  |||||||  "]
            for i, line in enumerate(art):
                try: self.stdscr.addstr(center_y + i, (width - len(line)) // 2, line, curses.color_pair(7) | (curses.A_BOLD if not self.paused else curses.A_DIM))
                except: pass

        self.draw_progress_bar(center_y + 4, width - 4)
        vol_str = f"Volume: {int(self.volume)}%"
        try: self.stdscr.addstr(center_y + 6, (width - len(vol_str)) // 2, vol_str)
        except: pass

        # 4. Queue Preview
        queue_y = center_y + 8
        remaining_lines = height - 2 - queue_y
        # Debugging: write to file
        # with open('debug_view.log', 'a') as f: f.write(f"H:{height} QY:{queue_y} Rem:{remaining_lines} QLen:{len(self.queue)}\n")
        if remaining_lines >= 3 and self.queue:
             try:
                 self.stdscr.addstr(queue_y, (width - 10) // 2, "--- Queue ---", curses.A_DIM)
                 count = min(remaining_lines - 1, 5, len(self.queue))
                 for i in range(count):
                     item = self.queue[i]
                     name = item.get('title', item.get('name', 'Unknown'))
                     display = f"{i+1}. {name}"
                     self.stdscr.addstr(queue_y + 1 + i, max(0, (width - len(display)) // 2), display[:width], curses.color_pair(6))
             except Exception as e:
                 with open("error_log.txt", "a") as f: f.write(str(e) + "\n")

        hint = "[n] Next  [p] Prev  [Space] Pause  [z] Shuffle  [l] Lyrics  [/] Search  [b] Library  [q] Quit"
        try: self.stdscr.addstr(height - 2, max(0, (width - len(hint)) // 2), hint[:width], curses.color_pair(1))
        except: pass

    def draw_progress_bar(self, y, width):
        if self.duration <= 0: pct = 0
        else: pct = min(1.0, self.position / self.duration)
        bar_width = width - 20
        fill_width = int(bar_width * pct)
        bar = "[" + "=" * fill_width + "-" * (bar_width - fill_width) + "]"
        time_str = f"{format_time(self.position)} / {format_time(self.duration)}"
        try: self.stdscr.addstr(y, 2, f"{bar} {time_str}", curses.color_pair(5))
        except: pass

    def draw_browser(self):
        height, width = self.stdscr.getmaxyx()
        try:
            self.stdscr.attron(curses.color_pair(1))
            self.stdscr.addstr(0, 0, f" Browser: {self.current_dir} ".ljust(width))
            self.stdscr.attroff(curses.color_pair(1))
        except: pass
        for i in range(height - 2):
            file_idx = i + self.scroll_offset
            if file_idx >= len(self.files): break
            
            item = self.files[file_idx]
            is_selected = (file_idx == self.selected_index)
            is_queued = self.is_in_queue(item)
            
            style = curses.A_NORMAL
            if is_selected:
                style = curses.color_pair(1)
            elif is_queued:
                style = curses.color_pair(2) # Green for queued

            try: self.stdscr.addstr(i + 1, 0, f"  {item['name']}"[:width], style)
            except: pass
        help_txt = "[R]ecursive | [/] Search | [D]efault Dir | [z]Shuffle | [a] Queue | [m] Player"
        try: self.stdscr.addstr(height-1, 0, help_txt[:width], curses.color_pair(6))
        except: pass
        if time.time() - self.message_time < 2 and self.message:
            try: self.stdscr.addstr(0, width - len(self.message) - 2, self.message, curses.color_pair(2) | curses.A_BOLD)
            except: pass

    def draw_search_results(self):
        height, width = self.stdscr.getmaxyx()
        try:
            self.stdscr.attron(curses.color_pair(1))
            self.stdscr.addstr(0, 0, f" Search Results ".ljust(width))
            self.stdscr.attroff(curses.color_pair(1))
        except: pass
        for i in range(height - 2):
            idx = i + self.scroll_offset
            if idx >= len(self.search_results): break
            
            item = self.search_results[idx]
            is_selected = (idx == self.selected_index)
            is_queued = self.is_in_queue(item)
            
            style = curses.A_NORMAL
            if is_selected:
                style = curses.color_pair(1)
            elif is_queued:
                style = curses.color_pair(2) # Green

            name = f"{item['title']} - {item['artist']}"
            try: self.stdscr.addstr(i+1, 0, f"  {name}"[:width], style)
            except: pass
        
        hint = "[Enter] Play | [a] Add One | [A] Add All | [q] Back | [m] Player"
        try: self.stdscr.addstr(height-1, 0, hint[:width], curses.color_pair(6))
        except: pass

    def handle_input(self, key):
        if key == 10:
            query = "".join(self.search_query)
            if query:
                self.is_searching_input = False
                self.view_mode = 'search_results'
                source = 'soundcloud' if query.startswith('sc:') else 'youtube'
                if source == 'soundcloud': query = query[3:]
                self.search_results = self.searcher.search(query, source)
                self.selected_index = 0
                self.scroll_offset = 0
        elif key == 27: self.is_searching_input = False
        elif key in (127, curses.KEY_BACKSPACE, 8): 
            if self.search_query: self.search_query.pop()
        elif 32 <= key <= 126: self.search_query.append(chr(key))

    def process_key(self, key):
        if key == ord('q'): 
            if self.view_mode != 'browser' and self.view_mode != 'player': self.view_mode = 'browser'
            elif self.view_mode == 'player': self.running = False
            else: self.running = False # Quit from browser
        elif key == ord('m'):
            self.view_mode = 'player'
        elif key == ord('b'):
            self.view_mode = 'browser'
        elif key == ord('D'):
            if save_config({'default_dir': self.current_dir}):
                self.message = " Default Dir Saved "
                self.message_time = time.time()
        elif key == ord('/'): 
            self.is_searching_input = True
            self.search_query = []
        elif key == 10:
            if self.view_mode == 'browser':
                f = self.files[self.selected_index]
                if f['type'] == 'dir':
                    self.current_dir = os.path.abspath(os.path.join(self.current_dir, f['path']))
                    self.scan_directory()
                else: self.play_file(self.selected_index)
            elif self.view_mode == 'search_results':
                if self.search_results: self.play_stream(self.search_results[self.selected_index])
        elif key == curses.KEY_DOWN:
            limit = len(self.files) if self.view_mode == 'browser' else len(self.search_results)
            self.selected_index = min(limit - 1, self.selected_index + 1)
        elif key == curses.KEY_UP:
            self.selected_index = max(0, self.selected_index - 1)
        elif key == ord('a'):
            if self.view_mode == 'search_results' and self.search_results:
                item = self.search_results[self.selected_index]
                self.queue.append(item)
                self.message = f" Added to queue: {item['title'][:20]}... "
                self.message_time = time.time()
            elif self.view_mode == 'browser' and self.files:
                f = self.files[self.selected_index]
                if f['type'] == 'file':
                    abs_path = os.path.abspath(os.path.join(self.current_dir, f['path']))
                    item = {'type': 'file', 'path': abs_path, 'name': f['name'], 'artist': 'Local File'}
                    self.queue.append(item)
                    self.message = f" Added to queue: {f['name'][:20]}... "
                    self.message_time = time.time()
        elif key == ord('A'):
             if self.view_mode == 'search_results' and self.search_results:
                 for item in self.search_results:
                     self.queue.append(item)
                 self.message = f" Added {len(self.search_results)} items to queue "
                 self.message_time = time.time()
                 if not self.mpv_process:
                     self.handle_end_of_file()
        elif key == ord(' '): self.toggle_pause()
        elif key == ord('l'): self.show_lyrics = not self.show_lyrics
        elif key == ord('n'): self.handle_end_of_file()
        elif key == ord('p'):
            if self.playback_history:
                idx = self.playback_history.pop()
                self.play_file(idx, push_history=False)

    def run(self):
        while self.running:
            self.stdscr.clear()
            if self.view_mode == 'player': self.draw_player_view()
            elif self.view_mode == 'search_results': self.draw_search_results()
            else: self.draw_browser()
            if self.is_searching_input:
                try: self.stdscr.addstr(0,0, "Search: " + "".join(self.search_query), curses.A_REVERSE)
                except: pass
            self.stdscr.refresh()
            try: key = self.stdscr.getch()
            except: continue
            if key == -1: continue
            if self.is_searching_input:
                self.handle_input(key)
                continue
            self.process_key(key)

def main(debug=False):
    curses.wrapper(lambda s: MusicPlayer(s, debug=debug).run())

if __name__ == "__main__":
    main()
