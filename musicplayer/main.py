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
import tempfile

# Suppress pygame welcome message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame
import mutagen

from .utils import slugify, format_time, parse_lrc
from .search import OnlineSearcher

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
        self.volume = 1.0
        self.running = True
        self.view_mode = 'browser' # 'browser', 'player', 'search'
        self.shuffle = False
        self.library_mode = False 
        self.playback_history = [] 
        
        # Search State
        self.searcher = OnlineSearcher()
        self.search_results = []
        self.search_query = []
        self.is_searching_input = False
        
        # Animation State
        self.anim_frame = 0
        self.last_anim_time = time.time()

        # Lyrics State
        self.lyrics = None
        self.show_lyrics = False
        self.lyrics_scroll_offset = 0
        self.current_song_lyrics_fetched = False
        
        # Pygame State
        try:
            pygame.init()
            pygame.mixer.init()
        except Exception as e:
            # print(f"Audio Error: {e}")
            sys.exit(1)
            
        self.current_track_length = 0
        self.start_time = 0
        self.pause_start = 0
        self.total_pause_time = 0
        
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
        curses.init_pair(7, curses.COLOR_GREEN, -1)     # Cthulhu
        curses.curs_set(0)
        self.stdscr.nodelay(1)
        self.stdscr.timeout(100)

        # Cleanup hooks
        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

        self.scan_directory()
        
        # Monitor thread
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()

    def handle_signal(self, signum, frame):
        self.cleanup()
        sys.exit(0)

    def cleanup(self):
        try:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        except:
            pass

    def fetch_from_letras_mus_br(self, artist, title):
        try:
            slug_artist = slugify(artist)
            slug_title = slugify(title)
            
            url = f"https://www.letras.mus.br/{slug_artist}/{slug_title}/"
            
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36')
            
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8', errors='ignore')
                match = re.search(r'<div class="cnt-letra[^\"]*">((?:.|\n)*?)</div>', html, re.DOTALL)
                if match:
                    raw_html = match.group(1)
                    text = re.sub(r'<br\s*/?>', '\n', raw_html)
                    text = re.sub(r'<[^>]+>', '', text)
                    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('&quot;', '"')
                    lines = [line.strip() for line in text.split('\n')]
                    return [{'time': None, 'text': line} for line in lines]
        except Exception as e:
            pass
        return None

    def fetch_lyrics(self, artist, title, file_path=None):
        self.lyrics = [{'time': None, 'text': "Loading lyrics..."}]
        found_lyrics = False
        
        # 1. Try local .lrc file
        if file_path:
            base_path = os.path.splitext(file_path)[0]
            lrc_path = base_path + ".lrc"
            if os.path.exists(lrc_path):
                try:
                    with open(lrc_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        parsed = parse_lrc(content)
                        if parsed:
                            self.lyrics = parsed
                            found_lyrics = True
                except:
                    pass
        
        if found_lyrics: return

        # Search terms
        search_terms = []
        if artist and title: search_terms.append(f"{artist} {title}")
        if file_path:
            filename = os.path.splitext(os.path.basename(file_path))[0]
            clean_name = filename.replace('_', ' ').replace('-', ' ')
            clean_name = re.sub(r'\s+', ' ', clean_name).strip()
            if clean_name not in search_terms: search_terms.append(clean_name)

        # 2. Try lrclib.net (Synced)
        try:
            # Check connection
            try: urllib.request.urlopen('https://www.google.com', timeout=1)
            except: 
                self.lyrics = [{'time': None, 'text': "Offline mode: Cannot fetch lyrics."}]
                return

            # A. Exact Match
            if artist and title:
                url = f"https://lrclib.net/api/get?artist_name={urllib.parse.quote(artist)}&track_name={urllib.parse.quote(title)}"
                try:
                    req = urllib.request.Request(url)
                    req.add_header('User-Agent', 'CLI-Music-Player/1.0')
                    with urllib.request.urlopen(req, timeout=10) as response:
                        data = json.loads(response.read().decode())
                        if data.get('syncedLyrics'):
                            self.lyrics = parse_lrc(data['syncedLyrics'])
                            found_lyrics = True
                        elif data.get('plainLyrics'):
                            plain = data['plainLyrics'].strip().split('\n')
                            self.lyrics = [{'time': None, 'text': line} for line in plain]
                            found_lyrics = True
                except: pass

            # B. Search
            if not found_lyrics:
                for q in search_terms:
                    if not q: continue
                    try:
                        url = f"https://lrclib.net/api/search?q={urllib.parse.quote(q)}"
                        req = urllib.request.Request(url)
                        req.add_header('User-Agent', 'CLI-Music-Player/1.0')
                        with urllib.request.urlopen(req, timeout=10) as response:
                            data = json.loads(response.read().decode())
                            best_match = None
                            for item in data:
                                if item.get('syncedLyrics'):
                                    best_match = item
                                    break
                            if not best_match and data: best_match = data[0]
                            if best_match:
                                if best_match.get('syncedLyrics'):
                                    self.lyrics = parse_lrc(best_match['syncedLyrics'])
                                    found_lyrics = True
                                elif best_match.get('plainLyrics'):
                                    plain = best_match['plainLyrics'].strip().split('\n')
                                    self.lyrics = [{'time': None, 'text': line} for line in plain]
                                    found_lyrics = True
                            if found_lyrics: break
                    except: pass
        except: pass

        # 3. Fallback: letras.mus.br
        if not found_lyrics and artist and title:
             res = self.fetch_from_letras_mus_br(artist, title)
             if res:
                 self.lyrics = res
                 found_lyrics = True

        # 4. Fallback: lyrics.ovh
        if not found_lyrics and artist and title:
            try:
                url = f"https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode())
                    raw = data.get('lyrics', '')
                    if raw:
                        self.lyrics = [{'time': None, 'text': line} for line in raw.replace('\r\n', '\n').split('\n')]
                        found_lyrics = True
            except: pass
            
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
            self._reset_selection()
        except PermissionError: pass

    def scan_recursive(self):
        self.library_mode = True
        self.files = []
        self.files.append({'name': '.. (Return to Browser Mode)', 'type': 'dir', 'path': '..'}) # Added missing closing parenthesis
        try:
            self.stdscr.addstr(0, 0, " Scanning Library... please wait ")
            self.stdscr.refresh()
            for root, dirs, files in os.walk(self.current_dir):
                dirs.sort()
                files.sort()
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in AUDIO_EXTENSIONS:
                        full_path = os.path.join(root, f)
                        rel_path = os.path.relpath(full_path, self.current_dir)
                        self.files.append({'name': rel_path, 'type': 'file', 'path': rel_path})
            self._reset_selection()
        except Exception:
            self.library_mode = False
            self.scan_directory()

    def _reset_selection(self):
        if self.selected_index >= len(self.files):
            self.selected_index = 0
            self.scroll_offset = 0

    def monitor_loop(self):
        while self.running:
            if self.playing_index != -1:
                if not pygame.mixer.music.get_busy() and not self.paused:
                    time.sleep(0.1)
                    if not pygame.mixer.music.get_busy():
                        self.handle_end_of_file()
                
                if self.show_lyrics and not self.current_song_lyrics_fetched:
                     artist = self.metadata.get('artist')
                     title = self.metadata.get('title')
                     file_path = None
                     if self.playing_index != -1 and self.playing_index < len(self.files):
                          file_path = os.path.join(self.current_dir, self.files[self.playing_index]['path'])
                     if (artist and title) or file_path:
                         self.current_song_lyrics_fetched = True
                         threading.Thread(target=self.fetch_lyrics, args=(artist or "", title or "", file_path), daemon=True).start()
            time.sleep(0.5)

    def get_next_index(self, current_idx):
        if self.shuffle:
            candidates = [i for i, f in enumerate(self.files) if f['type'] == 'file' and i != current_idx]
            if candidates: return random.choice(candidates)
            return None
        else:
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

    def handle_end_of_file(self):
        if self.playing_index != -1:
             next_idx = self.get_next_index(self.playing_index)
             if next_idx is not None:
                 self.play_file(next_idx)
             else:
                 self.stop_music()

    def get_position(self):
        if self.playing_index == -1: return 0
        if self.paused: return (self.pause_start - self.start_time - self.total_pause_time)
        pos_ms = pygame.mixer.music.get_pos()
        if pos_ms == -1: return 0
        return pos_ms / 1000.0

    def play_file(self, index, push_history=True):
        if 0 <= index < len(self.files) and self.files[index]['type'] == 'file':
            if push_history and self.playing_index != -1:
                self.playback_history.append(self.playing_index)
                if len(self.playback_history) > 50: self.playback_history.pop(0)

            self.playing_index = index
            file_path = os.path.join(self.current_dir, self.files[index]['path'])
            self.metadata = {}
            self.lyrics = None
            self.lyrics_scroll_offset = 0
            self.current_song_lyrics_fetched = False
            
            try:
                audio = mutagen.File(file_path, easy=True)
                if audio:
                    self.metadata['title'] = audio.get('title', [None])[0] or os.path.basename(file_path)
                    self.metadata['artist'] = audio.get('artist', [None])[0] or "Unknown Artist"
                    if hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                        self.current_track_length = audio.info.length
                    else: self.current_track_length = 0
                else:
                    self.metadata['title'] = os.path.basename(file_path)
                    self.metadata['artist'] = "Unknown"
                    self.current_track_length = 0
            except:
                self.metadata['title'] = os.path.basename(file_path)
                self.metadata['artist'] = "Unknown"
                self.current_track_length = 0
            
            try:
                pygame.mixer.music.load(file_path)
                pygame.mixer.music.play()
                pygame.mixer.music.set_volume(self.volume)
                self.paused = False
                self.view_mode = 'player'
            except Exception as e: pass

    def stop_music(self):
        pygame.mixer.music.stop()
        self.playing_index = -1
        self.paused = False
        self.view_mode = 'browser'

    def toggle_pause(self):
        if self.playing_index != -1:
            if self.paused:
                pygame.mixer.music.unpause()
                self.paused = False
            else:
                pygame.mixer.music.pause()
                self.paused = True

    def change_volume(self, delta):
        self.volume = max(0.0, min(1.0, self.volume + (delta / 100.0)))
        pygame.mixer.music.set_volume(self.volume)

    def draw_progress_bar(self, y, width):
        duration = self.current_track_length
        position = self.get_position()
        if duration <= 0: pct = 0
        else: pct = min(1.0, position / duration)
        bar_width = width - 20
        fill_width = int(bar_width * pct)
        bar = "[" + "=" * fill_width + "-" * (bar_width - fill_width) + "]"
        time_str = f"{format_time(position)} / {format_time(duration)}"
        try: self.stdscr.addstr(y, 2, f"{bar} {time_str}", curses.color_pair(5))
        except: pass

    def draw_player_view(self):
        height, width = self.stdscr.getmaxyx()
        if height < 15 or width < 40:
            try: self.stdscr.addstr(0, 0, "Terminal too small")
            except: pass
            return

        title = "No Media"
        artist = "Unknown Artist"
        prev_name = ""
        next_name = ""
        
        if self.playing_index != -1:
            title = self.metadata.get('title', self.files[self.playing_index]['name'])
            artist = self.metadata.get('artist', "Unknown Artist")
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
                    pos = self.get_position()
                    found_idx = -1
                    for i, line in enumerate(self.lyrics):
                         if line['time'] is not None and line['time'] <= pos: found_idx = i
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
                [" ( o . o ) ", " (  |||  ) ", "/|||\/||" + "/||"],
                [" ( O . O ) ", " ( /|||\ ) ", "//|||\/||" + "/|\\"]
            ]
            
            if not self.paused and self.playing_index != -1:
                art = cthulhu_frames[self.anim_frame]
                for i, line in enumerate(art):
                    try: self.stdscr.addstr(center_y + i, (width - len(line)) // 2, line, curses.color_pair(7) | curses.A_BOLD)
                    except: pass
            elif self.paused:
                 art = [" ( - . - ) ", " (  zzz  ) ", "  |||||||  "]
                 for i, line in enumerate(art):
                    try: self.stdscr.addstr(center_y + i, (width - len(line)) // 2, line, curses.color_pair(7) | curses.A_DIM)
                    except: pass

        self.draw_progress_bar(center_y + 4, width - 4)
        vol_str = f"Volume: {int(self.volume * 100)}%"
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

    def play_stream(self, result):
        """Play an online stream by downloading to cache"""
        self.cleanup()
        self.paused = False
        self.view_mode = 'player'
        self.metadata = {
            'title': result['title'],
            'artist': result['artist'],
            'duration': result['duration']
        }
        self.current_track_length = result['duration']
        self.playing_index = -1 # Special index for stream?
        self.lyrics = None
        self.lyrics_scroll_offset = 0
        self.current_song_lyrics_fetched = False
        
        # Show loading
        try:
            self.stdscr.erase()
            h, w = self.stdscr.getmaxyx()
            msg = f"Buffering {result['title']}..."
            self.stdscr.addstr(h//2, (w-len(msg))//2, msg)
            self.stdscr.refresh()
        except: pass

        def buffer_and_play():
            try:
                # Download directly using yt-dlp
                # This is more robust than extracting URL because yt-dlp handles the complex deciphering/throttling
                import yt_dlp
                
                cache_dir = tempfile.gettempdir()
                cache_base = os.path.join(cache_dir, f"gemini_music_cache_{os.getpid()}")
                # Add template for ext
                out_tmpl = cache_base + ".%(ext)s"
                
                # Cleanup previous cache
                for f in os.listdir(cache_dir):
                    if f.startswith(f"gemini_music_cache_{os.getpid()}"):
                        try: os.remove(os.path.join(cache_dir, f))
                        except: pass

                # Try different clients strategies
                clients_to_try = [
                    ['ios', 'web'],       # Often works for audio
                    ['android', 'web'],   # Fallback
                    ['web'],              # Standard
                    ['mweb']              # Mobile web
                ]
                
                downloaded_path = None
                last_error = None
                
                for clients in clients_to_try:
                    try:
                        ydl_opts = {
                            'format': 'bestaudio/best', 
                            'quiet': True,
                            'outtmpl': out_tmpl,
                            'overwrites': True,
                            'extractor_args': {'youtube': {'player_client': clients}},
                            'nocheckcertificate': True,
                            'ignoreerrors': True,
                            'no_warnings': True,
                        }
                        
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(result['id'], download=True)
                            if not info: raise Exception("No info extracted")
                            ext = info.get('ext', 'mp3')
                            path = cache_base + "." + ext
                            if os.path.exists(path) and os.path.getsize(path) > 0:
                                downloaded_path = path
                                break
                    except Exception as e:
                        last_error = e
                        continue

                if downloaded_path and os.path.exists(downloaded_path):
                    # Play
                    pygame.mixer.music.load(downloaded_path)
                    pygame.mixer.music.play()
                    pygame.mixer.music.set_volume(self.volume)
                    
                    # Fetch lyrics
                    threading.Thread(target=self.fetch_lyrics, args=(result['artist'], result['title']), daemon=True).start()
                else:
                    # Failed all attempts
                    self.metadata['title'] = "Playback Error"
                    self.metadata['artist'] = "Try: 'sudo pacman -S nodejs' or use 'sc:Query'"
                
            except Exception as e:
                # print(f"Stream Error: {e}")
                pass
                    # Play
                    pygame.mixer.music.load(downloaded_path)
                    pygame.mixer.music.play()
                    pygame.mixer.music.set_volume(self.volume)
                    
                    # Fetch lyrics
                    threading.Thread(target=self.fetch_lyrics, args=(result['artist'], result['title']), daemon=True).start()
                
            except Exception as e:
                # print(f"Stream Error: {e}")
                pass

        threading.Thread(target=buffer_and_play, daemon=True).start()

    def handle_input(self, key):
        if key == 10 or key == 13: # Enter
            query = "".join(self.search_query)
            if query:
                self.is_searching_input = False
                self.view_mode = 'search_results'
                self.selected_index = 0
                self.scroll_offset = 0
                
                # Run search
                try:
                    self.stdscr.erase()
                    self.stdscr.addstr(0, 0, f"Searching for '{query}'...")
                    self.stdscr.refresh()
                    # Determine source (simple heuristic or default)
                    source = 'youtube'
                    if query.startswith('sc:'):
                        source = 'soundcloud'
                        query = query[3:]
                    self.search_results = self.searcher.search(query, source)
                except: pass
        elif key == 27: # Esc
            self.is_searching_input = False
            self.search_query = []
        elif key == 8 or key == 127 or key == curses.KEY_BACKSPACE:
            if self.search_query: self.search_query.pop()
        elif 32 <= key <= 126:
            self.search_query.append(chr(key))

    def draw_search_results(self):
        height, width = self.stdscr.getmaxyx()
        
        # Header
        title = f"Search Results: {''.join(self.search_query)}"
        try:
            self.stdscr.attron(curses.color_pair(1))
            self.stdscr.addstr(0, 0, f" {title} " + " " * (width - len(title) - 3))
            self.stdscr.attroff(curses.color_pair(1))
        except: pass
        
        if not self.search_results:
            try: self.stdscr.addstr(2, 2, "No results found.")
            except: pass
            return

        list_height = height - 2
        for i in range(list_height):
            idx = i + self.scroll_offset
            if idx >= len(self.search_results): break
            
            item = self.search_results[idx]
            name = f"{item['title']} - {item['artist']} ({format_time(item['duration'])})"
            
            style = curses.A_NORMAL
            prefix = "  "
            if idx == self.selected_index: style = curses.color_pair(1)
            
            try:
                line = f"{prefix} {name}"
                self.stdscr.addstr(i + 1, 0, line[:width], style)
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
            status = f" Playing: {self.files[self.playing_index]['name']} ({int(self.volume*100)}%) [TAB to View]"
            try: self.stdscr.addstr(height-1, 0, status[:width], curses.color_pair(2))
            except: pass
        else:
            help_txt = "[R]ecursive Lib | [/] Search | [B]rowser | [z]Shuffle"
            try: self.stdscr.addstr(height-1, 0, help_txt[:width], curses.color_pair(6))
            except: pass

    def run(self):
        while self.running:
            self.stdscr.erase()
            
            # Draw background view first
            if self.view_mode == 'player': self.draw_player_view()
            elif self.view_mode == 'search_results': self.draw_search_results()
            else: self.draw_browser()

            # Draw search prompt on top if active
            if self.is_searching_input:
                h, w = self.stdscr.getmaxyx()
                try:
                    # Clear line first
                    self.stdscr.move(h-1, 0)
                    self.stdscr.clrtoeol()
                    prompt = "Search (yt/sc): " + "".join(self.search_query)
                    self.stdscr.addstr(h-1, 0, prompt, curses.color_pair(1))
                except: pass
            
            try: key = self.stdscr.getch()
            except: continue
            
            if key != -1:
                if key == curses.KEY_RESIZE:
                    curses.update_lines_cols()
                    self.stdscr.clear()
                    self.stdscr.refresh()
                    continue
                
                if self.is_searching_input:
                    self.handle_input(key)
                    continue

                if key == ord('q'):
                    if self.view_mode == 'player' or self.view_mode == 'search_results':
                        self.view_mode = 'browser'
                    else: self.running = False
                elif key == 9: self.view_mode = 'player' if self.view_mode == 'browser' and self.playing_index != -1 else 'browser'
                elif key == ord(' '): self.toggle_pause()
                elif key == ord('s'): self.stop_music()
                elif key == ord('+') or key == ord('='): self.change_volume(5)
                elif key == ord('-') or key == ord('_'): self.change_volume(-5)
                elif key == ord('n'): self.play_next()
                elif key == ord('p'): self.play_prev()
                elif key == ord('z'): self.shuffle = not self.shuffle
                elif key == ord('/'): 
                    self.is_searching_input = True
                    self.search_query = []
                elif key == ord('l'):
                    self.show_lyrics = not self.show_lyrics
                    if self.show_lyrics and not self.current_song_lyrics_fetched and self.playing_index != -1:
                        artist = self.metadata.get('artist')
                        title = self.metadata.get('title')
                        file_path = None
                        if self.playing_index != -1 and self.playing_index < len(self.files):
                             file_path = os.path.join(self.current_dir, self.files[self.playing_index]['path'])
                        if (artist and title) or file_path:
                            self.current_song_lyrics_fetched = True
                            threading.Thread(target=self.fetch_lyrics, args=(artist or "", title or "", file_path), daemon=True).start()
                elif key == ord('R'): self.scan_recursive()
                elif key == ord('B'): self.scan_directory()
                
                if self.view_mode == 'browser':
                    if key == curses.KEY_UP:
                        self.selected_index = max(0, self.selected_index - 1)
                        if self.selected_index < self.scroll_offset: self.scroll_offset = self.selected_index
                    elif key == curses.KEY_DOWN:
                        self.selected_index = min(len(self.files) - 1, self.selected_index + 1)
                        height, _ = self.stdscr.getmaxyx()
                        if self.selected_index >= self.scroll_offset + (height - 2):
                            self.scroll_offset = self.selected_index - (height - 2) + 1
                    elif key == curses.KEY_ENTER or key == 10 or key == 13:
                        if self.files:
                            selected = self.files[self.selected_index]
                            if selected['type'] == 'dir':
                                if selected['path'] == '..':
                                    if self.library_mode: self.scan_directory()
                                    else:
                                        new_path = os.path.abspath(os.path.join(self.current_dir, '..'))
                                        if os.path.isdir(new_path):
                                            self.current_dir = new_path
                                            self.selected_index = 0
                                            self.scroll_offset = 0
                                            self.scan_directory()
                                else:
                                    new_path = os.path.abspath(os.path.join(self.current_dir, selected['path']))
                                    if os.path.isdir(new_path):
                                        self.current_dir = new_path
                                        self.selected_index = 0
                                        self.scroll_offset = 0
                                        self.scan_directory()
                            else: self.play_file(self.selected_index)
                elif self.view_mode == 'search_results':
                    if key == curses.KEY_UP:
                        self.selected_index = max(0, self.selected_index - 1)
                        if self.selected_index < self.scroll_offset: self.scroll_offset = self.selected_index
                    elif key == curses.KEY_DOWN:
                        self.selected_index = min(len(self.search_results) - 1, self.selected_index + 1)
                        height, _ = self.stdscr.getmaxyx()
                        if self.selected_index >= self.scroll_offset + (height - 2):
                            self.scroll_offset = self.selected_index - (height - 2) + 1
                    elif key == curses.KEY_ENTER or key == 10 or key == 13:
                        if self.search_results:
                            self.play_stream(self.search_results[self.selected_index])
                elif self.view_mode == 'player':
                    if key == curses.KEY_UP and self.show_lyrics: self.lyrics_scroll_offset = max(0, self.lyrics_scroll_offset - 1)
                    elif key == curses.KEY_DOWN and self.show_lyrics:
                         if self.lyrics: self.lyrics_scroll_offset = min(len(self.lyrics) - 1, self.lyrics_scroll_offset + 1)
            self.stdscr.refresh()

def main():
    try: curses.wrapper(lambda stdscr: MusicPlayer(stdscr).run())
    except KeyboardInterrupt: pass

if __name__ == "__main__":
    main()
