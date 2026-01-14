import os
import threading
import time
import socket
import json
import tempfile
import subprocess
import random
import urllib.request
import urllib.parse
import re
from PyQt6.QtCore import QObject, pyqtSignal

from .utils import slugify, format_time, parse_lrc
from .search import OnlineSearcher
from .mpv_setup import get_mpv_path, download_mpv
from .config import load_config, save_config

# Supported audio extensions
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.wma', '.aac', '.opus'}

class PlayerEngine(QObject):
    # Signals for the GUI
    track_changed = pyqtSignal(dict)
    position_changed = pyqtSignal(float, float) # current, total
    status_changed = pyqtSignal(bool) # paused
    queue_changed = pyqtSignal(list)
    lyrics_loaded = pyqtSignal(list)
    message_emitted = pyqtSignal(str)
    directory_scanned = pyqtSignal(list)

    def __init__(self, debug=False):
        super().__init__()
        self.debug_mode = debug
        self.config = load_config()
        self.current_dir = self.config.get('default_dir', os.getcwd())
        if not os.path.isdir(self.current_dir):
            self.current_dir = os.getcwd()

        self.mpv_bin = get_mpv_path() or download_mpv()
        if not self.mpv_bin:
            raise RuntimeError("MPV player not found.")

        self.files = []
        self.queue = []
        self.playing_index = -1
        self.paused = False
        self.volume = self.config.get('volume', 100)
        self.shuffle = False
        self.playback_history = []
        
        self.searcher = OnlineSearcher()
        self.mpv_process = None
        self.ipc_socket = os.path.join(tempfile.gettempdir(), f'mpv_socket_{os.getpid()}')
        self.duration = 0
        self.position = 0
        self.metadata = {}
        self.lyrics = None
        self.current_song_lyrics_fetched = False
        self.running = True

        # Monitor thread
        self.monitor_thread = threading.Thread(target=self.ipc_loop, daemon=True)
        self.monitor_thread.start()

    def log(self, message):
        if self.debug_mode:
            print(f"[DEBUG] {message}")

    def cleanup(self):
        self.running = False
        if self.mpv_process:
            try:
                self.send_ipc_command(["quit"])
                try: self.mpv_process.wait(timeout=0.5)
                except subprocess.TimeoutExpired: self.mpv_process.kill()
            except:
                try: self.mpv_process.kill()
                except: pass
            self.mpv_process = None
            
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
                pos = self.get_property("time-pos")
                if pos is not None: 
                    self.position = float(pos)
                
                dur = self.get_property("duration")
                if dur is not None: 
                    self.duration = float(dur)
                
                if pos is not None and dur is not None:
                    self.position_changed.emit(self.position, self.duration)
                
                meta = self.get_property("metadata")
                if meta:
                    new_title = meta.get('title') or meta.get('media-title')
                    new_artist = meta.get('artist')
                    changed = False
                    if new_title and self.metadata.get('title') != new_title:
                        self.metadata['title'] = new_title
                        changed = True
                    if new_artist and self.metadata.get('artist') != new_artist:
                        self.metadata['artist'] = new_artist
                        changed = True
                    
                    if changed:
                        self.log(f"Metadata changed: {self.metadata}")
                        self.track_changed.emit(self.metadata)
                        # Fetch lyrics if metadata changed
                        if self.metadata.get('artist') and self.metadata.get('title'):
                            threading.Thread(target=self.fetch_lyrics, 
                                            args=(self.metadata['artist'], self.metadata['title']),
                                            daemon=True).start()

                paused = self.get_property("pause")
                if paused is not None and self.paused != paused:
                    self.paused = paused
                    self.status_changed.emit(self.paused)
                
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
                match = re.search(r'<div class="cnt-letra[^"]*"> (.*?)</div>', html, re.DOTALL)
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
        self.log(f"Fetching lyrics for: {artist} - {title}")
        # Prevent double fetching
        if getattr(self, '_last_fetched_key', None) == (artist, title):
            self.log("Skipping duplicate fetch")
            return
        self._last_fetched_key = (artist, title)

        found_lyrics = False
        try:
            url = f"https://lrclib.net/api/get?artist_name={urllib.parse.quote(artist)}&track_name={urllib.parse.quote(title)}"
            self.log(f"Requesting LRCLIB: {url}")
            req = urllib.request.Request(url, headers={'User-Agent': 'CLI-Music-Player/1.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                if data.get('syncedLyrics'):
                    self.lyrics = parse_lrc(data['syncedLyrics'])
                    found_lyrics = True
                elif data.get('plainLyrics'):
                    self.lyrics = [{'time': None, 'text': l} for l in data['plainLyrics'].split('\n')]
                    found_lyrics = True
        except Exception as e: 
            self.log(f"LRCLIB Error: {e}")
        
        if not found_lyrics:
             self.log("Falling back to letras.mus.br")
             res = self.fetch_from_letras_mus_br(artist, title)
             if res:
                 self.lyrics = res
                 found_lyrics = True

        if not found_lyrics:
             self.log("Lyrics not found.")
             self.lyrics = [{'time': None, 'text': "Lyrics not found."}]
        
        self.lyrics_loaded.emit(self.lyrics)

    def scan_directory(self, path=None):
        if path: self.current_dir = path
        self.files = []
        try:
            items = sorted(os.listdir(self.current_dir))
            # Parent dir item
            self.files.append({'name': '..', 'type': 'dir', 'path': '..'}) # Corrected escaping for '..' string
            for item in items:
                full_path = os.path.join(self.current_dir, item)
                if os.path.isdir(full_path) and not item.startswith('.'):
                    self.files.append({'name': item, 'type': 'dir', 'path': item})
                elif os.path.isfile(full_path):
                    if os.path.splitext(item)[1].lower() in AUDIO_EXTENSIONS:
                        self.files.append({'name': item, 'type': 'file', 'path': item})
            self.directory_scanned.emit(self.files)
        except Exception as e:
            self.message_emitted.emit(f"Error scanning: {str(e)}")

    def scan_recursive(self, path=None):
        if path: self.current_dir = path
        self.files = [{'name': '..', 'type': 'dir', 'path': '..'}]
        for root, _, files in os.walk(self.current_dir):
            for f in sorted(files):
                if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS:
                    rel_path = os.path.relpath(os.path.join(root, f), self.current_dir)
                    self.files.append({'name': rel_path, 'type': 'file', 'path': rel_path})
        self.directory_scanned.emit(self.files)

    def search_local_files(self, query):
        if not query:
            self.scan_directory()
            return
            
        results = []
        try:
            for root, _, files in os.walk(self.current_dir):
                for f in sorted(files):
                    if query.lower() in f.lower() and os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS:
                        # Create a file object similar to scan_directory
                        full_path = os.path.join(root, f)
                        rel_path = os.path.relpath(full_path, self.current_dir)
                        results.append({'name': f, 'type': 'file', 'path': rel_path, 'full_path': full_path})
            
            # Update self.files so they can be played by index if needed, or just emit
            # For this feature, we likely want to show them in the list.
            # We replace self.files with search results for consistency in UI handling
            self.files = results
            self.directory_scanned.emit(self.files)
        except Exception as e:
            self.message_emitted.emit(f"Search error: {str(e)}")

    def get_next_index(self, current_idx):
        if self.shuffle:
            candidates = [i for i, f in enumerate(self.files) if f['type'] == 'file' and i != current_idx]
            return random.choice(candidates) if candidates else None
        idx = current_idx + 1
        while idx < len(self.files):
            if self.files[idx]['type'] == 'file': return idx
            idx += 1
        return None

    def play_file(self, index_or_path):
        if isinstance(index_or_path, int):
            index = index_or_path
            if 0 <= index < len(self.files):
                if self.playing_index != -1:
                    self.playback_history.append(self.playing_index)
                self.playing_index = index
                path = os.path.join(self.current_dir, self.files[index]['path'])
                self.metadata = {'title': self.files[index]['name'], 'artist': 'Local File'}
                self._start_mpv(path)
        else:
            path = index_or_path
            self.metadata = {'title': os.path.basename(path), 'artist': 'Local File'}
            self._start_mpv(path)

    def play_stream(self, result):
        self.playing_index = -1
        self.metadata = {'title': result['title'], 'artist': result['artist']}
        target = result.get('url') or result['id']
        if len(target) == 11 and '.' not in target:
             target = f"https://www.youtube.com/watch?v={target}"
        self._start_mpv(target)

    def play_queue_item(self, item):
        self.playing_index = -1
        self.metadata = {'title': item.get('title', item.get('name', 'Unknown')), 
                         'artist': item.get('artist', 'Unknown')}
        
        target = ""
        if item.get('type') == 'file':
            target = item['path']
        else:
            target = item.get('url') or item['id']
            if len(target) == 11 and '.' not in target:
                 target = f"https://www.youtube.com/watch?v={target}"
                 
        self._start_mpv(target)

    def play_queue_index(self, index):
        if 0 <= index < len(self.queue):
            # We play the selected item. 
            # Logic decision: Do we remove previous items? 
            # For a "Queue" (FIFO), usually yes. If we treat it as playlist, no.
            # User asked for "Playlist", but the backend is built as "Queue".
            # Compromise: Pop the item to play it.
            item = self.queue.pop(index)
            self.queue_changed.emit(self.queue)
            self.play_queue_item(item)

    def _start_mpv(self, target):
        self.log(f"Starting MPV: {target}")
        if self.mpv_process:
            self.send_ipc_command(["quit"])
            try: self.mpv_process.wait(timeout=0.2)
            except: self.mpv_process.kill()

        self.paused = False
        self.position = 0
        self.duration = 0
        # Reset last fetched key so re-playing the same song can refetch lyrics if needed (or not block if we improve logic)
        self._last_fetched_key = None 
        
        cmd = [
            self.mpv_bin,
            '--no-video',
            f'--input-ipc-server={self.ipc_socket}',
            f'--volume={self.volume}',
            '--idle',
            target
        ]
        self.mpv_process = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self.status_changed.emit(False)
        self.track_changed.emit(self.metadata)

    def stop_music(self):
        if self.mpv_process:
            self.send_ipc_command(["stop"])
        self.playing_index = -1
        self.paused = False
        self.status_changed.emit(False)

    def handle_end_of_file(self):
        if self.queue:
            item = self.queue.pop(0)
            self.queue_changed.emit(self.queue)
            self.play_queue_item(item)
            return

        if self.playing_index != -1:
             next_idx = self.get_next_index(self.playing_index)
             if next_idx is not None: self.play_file(next_idx)
             else: self.stop_music()
        else:
             self.stop_music()

    def toggle_pause(self):
        self.send_ipc_command(["cycle", "pause"])

    def set_volume(self, value):
        self.volume = max(0, min(200, value))
        self.send_ipc_command(["set_property", "volume", self.volume])
        save_config({'volume': self.volume})

    def seek(self, position):
        self.send_ipc_command(["seek", position, "absolute"])
        # Update position immediately to make UI responsive
        self.position = position
        self.position_changed.emit(self.position, self.duration)

    def is_in_queue(self, item):
        if item.get('type') == 'file':
            try:
                abs_path = os.path.abspath(os.path.join(self.current_dir, item['path']))
                for q_item in self.queue:
                    if q_item['type'] == 'file' and q_item['path'] == abs_path:
                        return True
            except: pass
        else:
            target_id = item.get('id')
            target_url = item.get('url')
            for q_item in self.queue:
                if q_item['type'] != 'file':
                     if (target_id and q_item.get('id') == target_id) or \
                        (target_url and q_item.get('url') == target_url):
                         return True
        return False

    def add_to_queue(self, items):
        if not isinstance(items, list):
            items = [items]
            
        added_count = 0
        for item in items:
            # Normalize item for queue
            if item.get('type') == 'file' and not os.path.isabs(item['path']):
                item['path'] = os.path.abspath(os.path.join(self.current_dir, item['path']))
            self.queue.append(item)
            added_count += 1
            
        self.queue_changed.emit(self.queue)
        self.message_emitted.emit(f"Added {added_count} items to queue")
        
        # Auto-play if idle
        if not self.mpv_process or self.get_property("idle-active"):
            self.handle_end_of_file()
