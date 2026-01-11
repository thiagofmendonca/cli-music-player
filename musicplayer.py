#!/usr/bin/env python3
import curses
import os
import threading
import time
import signal
import sys
import json
import shutil
import random
import urllib.request
import urllib.parse
import re
import unicodedata

# Suppress pygame welcome message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame
import mutagen

# Supported audio extensions (Pygame/SDL_mixer supports most of these)
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
        self.volume = 1.0 # 0.0 to 1.0 in pygame
        self.running = True
        self.view_mode = 'browser' # 'browser' or 'player'
        self.shuffle = False
        self.library_mode = False 
        self.playback_history = [] 
        
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
            # Initialize all of pygame (mixer, fonts, events)
            pygame.init()
            pygame.mixer.init() 
        except Exception as e:
            print(f"Audio Error: {e}")
            sys.exit(1)
            
        self.current_track_length = 0
        self.start_time = 0 # To track position
        self.pause_start = 0 # To track pause duration
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
        # atexit.register(self.cleanup) # Not strictly needed for pygame but good practice to stop
        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

        self.scan_directory()
        
        # Monitor thread (replaces IPC loop)
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

    def parse_lrc(self, lrc_text):
        parsed = []
        # Regex for [mm:ss.xx]Text
        pattern = re.compile(r'\[(\d+):(\d+(?:\.\d+)?)\](.*)')
        for line in lrc_text.splitlines():
            match = pattern.match(line)
            if match:
                minutes = float(match.group(1))
                seconds = float(match.group(2))
                text = match.group(3).strip()
                timestamp = minutes * 60 + seconds
                parsed.append({'time': timestamp, 'text': text})
        return parsed

    def slugify(self, text):
        """Convert text to letters-mus-br slug format"""
        # Normalize unicode characters (remove accents)
        text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
        text = text.lower()
        # Replace non-alphanumeric characters with hyphens (or remove them)
        # Letras.mus.br logic: spaces become hyphens, special chars are removed
        text = re.sub(r'[\s\-_]+', '-', text) # Spaces/underscores to hyphens
        text = re.sub(r'[^\w\-]', '', text)   # Remove other specials
        return text.strip('-')

    def fetch_from_letras_mus_br(self, artist, title):
        try:
            slug_artist = self.slugify(artist)
            slug_title = self.slugify(title)
            
            url = f"https://www.letras.mus.br/{slug_artist}/{slug_title}/"
            
            req = urllib.request.Request(url)
            # Browser User-Agent is required to avoid 403
            req.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36')
            
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8', errors='ignore')
                
                # Extract lyrics div: <div class="cnt-letra p402_premium">...</div>
                # Use DOTALL to match newlines
                match = re.search(r'<div class="cnt-letra[^"]*">(.*?)</div>', html, re.DOTALL)
                if match:
                    raw_html = match.group(1)
                    # Replace <br> tags with newlines
                    text = re.sub(r'<br\s*/?>', '\n', raw_html)
                    # Remove other tags like <p>
                    text = re.sub(r'<[^>]+>', '', text)
                    # Decode HTML entities if any (basic ones)
                    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('&quot;', '"')
                    
                    lines = [line.strip() for line in text.split('\n')]
                    # Remove empty lines from start/end
                    return [{'time': None, 'text': line} for line in lines]
        except Exception as e:
            # print(f"Letras.mus.br failed: {e}")
            pass
        return None

    def fetch_lyrics(self, artist, title, file_path=None):
        # Debug Logging
        debug_log = "/tmp/musicplayer_debug.log"
        with open(debug_log, "a") as f:
            f.write(f"Fetching: Artist='{artist}', Title='{title}', File='{file_path}'\n")

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
                        parsed = self.parse_lrc(content)
                        if parsed:
                            self.lyrics = parsed
                            found_lyrics = True
                except:
                    pass
        
        if found_lyrics:
            return

        # Prepare search terms
        search_terms = []
        if artist and title:
            search_terms.append(f"{artist} {title}")
        
        # Use filename as fallback or additional search term
        if file_path:
            filename = os.path.splitext(os.path.basename(file_path))[0]
            # Clean filename: replace underscores, remove common garbage like (Official Video), etc.
            clean_name = filename.replace('_', ' ').replace('-', ' ')
            clean_name = re.sub(r'\s+', ' ', clean_name).strip()
            if clean_name not in search_terms:
                search_terms.append(clean_name)
        
        with open(debug_log, "a") as f:
             f.write(f"Search candidates: {search_terms}\n")

        # 2. Try lrclib.net (Synced)
        try:
            # Check for internet connection first
            try:
                urllib.request.urlopen('https://www.google.com', timeout=1)
            except:
                self.lyrics = [{'time': None, 'text': "Offline mode: Cannot fetch lyrics."}]
                return

            # A. Try Exact Match (if we have clean Artist/Title)
            if artist and title:
                url = f"https://lrclib.net/api/get?artist_name={urllib.parse.quote(artist)}&track_name={urllib.parse.quote(title)}"
                try:
                    req = urllib.request.Request(url)
                    req.add_header('User-Agent', 'CLI-Music-Player/1.0')
                    with urllib.request.urlopen(req, timeout=10) as response:
                        data = json.loads(response.read().decode())
                        if data.get('syncedLyrics'):
                            parsed = self.parse_lrc(data['syncedLyrics'])
                            if parsed:
                                self.lyrics = parsed
                                found_lyrics = True
                                with open(debug_log, "a") as f: f.write("Found via Exact Match (Synced)\n")
                        elif data.get('plainLyrics'):
                            plain = data['plainLyrics'].strip().split('\n')
                            self.lyrics = [{'time': None, 'text': line} for line in plain]
                            found_lyrics = True
                            with open(debug_log, "a") as f: f.write("Found via Exact Match (Plain)\n")
                except urllib.error.HTTPError:
                    pass
                except Exception as e:
                     with open(debug_log, "a") as f: f.write(f"Exact match error: {e}\n")

            # B. Search Endpoint (Loop through candidates)
            if not found_lyrics:
                for q in search_terms:
                    if not q: continue
                    with open(debug_log, "a") as f: f.write(f"Searching query: '{q}'\n")
                    
                    try:
                        url = f"https://lrclib.net/api/search?q={urllib.parse.quote(q)}"
                        req = urllib.request.Request(url)
                        req.add_header('User-Agent', 'CLI-Music-Player/1.0')
                        
                        with urllib.request.urlopen(req, timeout=10) as response:
                            data = json.loads(response.read().decode())
                            # Look for first result with synced lyrics
                            best_match = None
                            for item in data:
                                if item.get('syncedLyrics'):
                                    best_match = item
                                    break
                            
                            # If no synced, take first plain
                            if not best_match and data:
                                best_match = data[0]
                                
                            if best_match:
                                if best_match.get('syncedLyrics'):
                                    parsed = self.parse_lrc(best_match['syncedLyrics'])
                                    if parsed:
                                        self.lyrics = parsed
                                        found_lyrics = True
                                        with open(debug_log, "a") as f: f.write(f"Found via Search '{q}' (Synced)\n")
                                elif best_match.get('plainLyrics'):
                                    plain = best_match['plainLyrics'].strip().split('\n')
                                    self.lyrics = [{'time': None, 'text': line} for line in plain]
                                    found_lyrics = True
                                    with open(debug_log, "a") as f: f.write(f"Found via Search '{q}' (Plain)\n")
                            
                            if found_lyrics: break
                    except Exception as e:
                        with open(debug_log, "a") as f: f.write(f"Search error for '{q}': {e}\n")

        except Exception as e:
            with open(debug_log, "a") as f: f.write(f"Global fetch error: {e}\n")

        # 3. Fallback to letras.mus.br (Scraping)
        if not found_lyrics and artist and title:
             with open(debug_log, "a") as f: f.write("Trying letras.mus.br fallback...\n")
             res = self.fetch_from_letras_mus_br(artist, title)
             if res:
                 self.lyrics = res
                 found_lyrics = True
                 with open(debug_log, "a") as f: f.write("Found via letras.mus.br\n")

        if not found_lyrics:
            # 4. Fallback to lyrics.ovh (Plain only)
            if artist and title:
                try:
                    url = f"https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}"
                    req = urllib.request.Request(url)
                    with urllib.request.urlopen(req, timeout=10) as response:
                        data = json.loads(response.read().decode())
                        raw = data.get('lyrics', '')
                        if raw:
                            self.lyrics = [{'time': None, 'text': line} for line in raw.replace('\r\n', '\n').split('\n')]
                            found_lyrics = True
                            with open(debug_log, "a") as f: f.write("Found via lyrics.ovh\n")
                except:
                    pass
            
        if not found_lyrics:
            self.lyrics = [{'time': None, 'text': "Lyrics not found."}]
            with open(debug_log, "a") as f: f.write("Gave up.\n")

    def scan_directory(self):
        """Standard Browser Mode: List current dir"""
        self.library_mode = False
        self.files = []
        try:
            items = sorted(os.listdir(self.current_dir))
            self.files.append({'name': '..', 'type': 'dir', 'path': '..'})
            for item in items:
                full_path = os.path.join(self.current_dir, item)
                if os.path.isdir(full_path) and not item.startswith('.'):
                    self.files.append({'name': item, 'type': 'dir', 'path': item})
                elif os.path.isfile(full_path):
                    ext = os.path.splitext(item)[1].lower()
                    if ext in AUDIO_EXTENSIONS:
                        self.files.append({'name': item, 'type': 'file', 'path': item})
            
            self._reset_selection()
        except PermissionError:
            pass

    def scan_recursive(self):
        """Library Mode: Flatten all subdirectories"""
        self.library_mode = True
        self.files = []
        # Option to go back to browser
        self.files.append({'name': '.. (Return to Browser Mode)', 'type': 'dir', 'path': '..'})
        
        try:
            # Show loading message (simple blocking since we are single threaded UI mostly)
            self.stdscr.addstr(0, 0, " Scanning Library... please wait ")
            self.stdscr.refresh()
            
            for root, dirs, files in os.walk(self.current_dir):
                # Sort to ensure consistent order
                dirs.sort()
                files.sort()
                
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in AUDIO_EXTENSIONS:
                        # Store relative path for display and access
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
        """Monitor playback status"""
        while self.running:
            if self.playing_index != -1:
                # Check for end of song
                if not pygame.mixer.music.get_busy() and not self.paused:
                    # Give a small buffer to ensure it really finished and wasn't just loading
                    time.sleep(0.1)
                    if not pygame.mixer.music.get_busy():
                        self.handle_end_of_file()
                
                # Trigger lyrics fetch if needed
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
            # Get all audio file indices
            candidates = [i for i, f in enumerate(self.files) if f['type'] == 'file' and i != current_idx]
            if candidates:
                return random.choice(candidates)
            return None
        else:
            idx = current_idx + 1
            while idx < len(self.files):
                if self.files[idx]['type'] == 'file':
                    return idx
                idx += 1
            return None

    def get_prev_index(self, current_idx):
        # If we have history, pop from it (Shuffle or Normal)
        if self.playback_history:
            # The last item is current song, so we need the one before
            # But we only push to history when changing.
            # Let's peek.
            return self.playback_history[-1]
            
        idx = current_idx - 1
        while idx >= 0:
            if self.files[idx]['type'] == 'file':
                return idx
            idx -= 1
        return None

    def get_position(self):
        if self.playing_index == -1: return 0
        if self.paused:
            # If paused, position is locked at pause_start relative to start_time and total_pause
            # Actually simplest way: track 'accumulated_time'
            return (self.pause_start - self.start_time - self.total_pause_time) 
        
        # Pygame get_pos returns ms played. It DOES NOT reset on pause usually, 
        # but docs say "time since the music was started".
        # Reliable way: pygame.mixer.music.get_pos() / 1000.0
        # However, get_pos() returns -1 if not playing.
        
        pos_ms = pygame.mixer.music.get_pos()
        if pos_ms == -1: return 0
        return pos_ms / 1000.0

    def play_file(self, index, push_history=True):
        if 0 <= index < len(self.files) and self.files[index]['type'] == 'file':
            # Add current song to history before switching
            if push_history and self.playing_index != -1:
                self.playback_history.append(self.playing_index)
                if len(self.playback_history) > 50:
                    self.playback_history.pop(0)

            self.playing_index = index
            file_path = os.path.join(self.current_dir, self.files[index]['path'])
            self.metadata = {}
            self.lyrics = None
            self.lyrics_scroll_offset = 0
            self.current_song_lyrics_fetched = False
            
            # Load Metadata with Mutagen
            try:
                audio = mutagen.File(file_path, easy=True)
                if audio:
                    self.metadata['title'] = audio.get('title', [None])[0] or os.path.basename(file_path)
                    self.metadata['artist'] = audio.get('artist', [None])[0] or "Unknown Artist"
                    # Mutagen length is in seconds (float)
                    if hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                        self.current_track_length = audio.info.length
                    else:
                        self.current_track_length = 0
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
                
                # Reset timing trackers if we were using custom logic, 
                # but get_pos() is usually sufficient for simple playback
            except Exception as e:
                # Show error somewhere?
                pass

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
        # Delta is +/- 5 (from original 0-100 scale)
        # Pygame volume is 0.0 to 1.0
        self.volume = max(0.0, min(1.0, self.volume + (delta / 100.0)))
        pygame.mixer.music.set_volume(self.volume)

    def format_time(self, seconds):
        if seconds is None: return "00:00"
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    def draw_progress_bar(self, y, width):
        duration = self.current_track_length
        position = self.get_position()
        
        if duration <= 0:
            pct = 0
        else:
            pct = min(1.0, position / duration)
        
        bar_width = width - 20 # Space for timestamps
        fill_width = int(bar_width * pct)
        
        bar = "[" + "=" * fill_width + "-" * (bar_width - fill_width) + "]"
        time_str = f"{self.format_time(position)} / {self.format_time(duration)}"
        
        try:
            self.stdscr.addstr(y, 2, f"{bar} {time_str}", curses.color_pair(5))
        except:
            pass

    def draw_player_view(self):
        height, width = self.stdscr.getmaxyx()
        
        # Check if terminal is too small
        if height < 15 or width < 40:
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
            title = self.metadata.get('title', self.files[self.playing_index]['name'])
            artist = self.metadata.get('artist', "Unknown Artist")
            
            # Prev info (Logical or History)
            if self.playback_history:
                 p_idx = self.playback_history[-1]
                 if 0 <= p_idx < len(self.files):
                    prev_name = f"Prev: {self.files[p_idx]['name']}"
            else:
                p_idx = self.playing_index - 1 # Simple lookback
                if 0 <= p_idx < len(self.files) and self.files[p_idx]['type'] == 'file':
                     prev_name = f"Prev: {self.files[p_idx]['name']}"
                
            # Next (Shuffle or Linear)
            if self.shuffle:
                next_name = "Next: Random"
            else:
                n_idx = self.get_next_index(self.playing_index)
                if n_idx is not None:
                    next_name = f"Next: {self.files[n_idx]['name']}"
            
        # Layout Calculations
        center_y = height // 2
        
        # 1. Previous Track (Dimmed) - Higher up
        if prev_name and center_y - 8 > 0:
            try:
                self.stdscr.addstr(center_y - 8, (width - len(prev_name)) // 2, prev_name[:width], curses.A_DIM)
                self.stdscr.addstr(center_y - 7, (width - 1) // 2, "^", curses.A_DIM)
            except: pass

        # 2. Current Track (Bold/Color)
        try:
            self.stdscr.attron(curses.A_BOLD)
            self.stdscr.addstr(center_y - 5, max(0, (width - len(title)) // 2), title[:width])
            self.stdscr.attroff(curses.A_BOLD)
            self.stdscr.addstr(center_y - 4, max(0, (width - len(artist)) // 2), artist[:width])
        except: pass
        
        # 3. Status
        mode_str = " [Shuffle]" if self.shuffle else ""
        if self.library_mode: mode_str += " [Lib]"
        status = ("PAUSED" if self.paused else "PLAYING") + mode_str
        try:
            self.stdscr.addstr(center_y - 2, (width - len(status)) // 2, status, 
                           curses.color_pair(3) if self.paused else curses.color_pair(2))
        except: pass

        # 4. PULSING CTHULHU (ASCII ART) or LYRICS
        if self.show_lyrics:
            # Display Lyrics
            lyrics_height = 10
            start_y = center_y - 2
            
            if self.lyrics:
                # Check if synced
                is_synced = any(l['time'] is not None for l in self.lyrics)
                
                current_line_idx = 0
                
                if is_synced:
                    # Find current line based on position
                    pos = self.get_position()
                    # We want the last line where time <= pos
                    found_idx = -1
                    for i, line in enumerate(self.lyrics):
                         if line['time'] is not None and line['time'] <= pos:
                             found_idx = i
                         else:
                             break
                    
                    if found_idx != -1:
                        current_line_idx = found_idx
                    
                    # Auto-scroll to keep current line in middle
                    # Target: current_line_idx should be at lyrics_height // 2
                    target_offset = current_line_idx - (lyrics_height // 2)
                    self.lyrics_scroll_offset = max(0, min(len(self.lyrics) - 1, target_offset))
                
                for i in range(lyrics_height):
                    line_idx = self.lyrics_scroll_offset + i
                    if 0 <= line_idx < len(self.lyrics):
                        line_data = self.lyrics[line_idx]
                        line_text = line_data['text'].strip()
                        
                        style = curses.color_pair(6)
                        if is_synced and line_idx == current_line_idx:
                            style = curses.color_pair(2) | curses.A_BOLD # Highlight current line
                            line_text = ">> " + line_text
                        
                        try:
                            self.stdscr.addstr(start_y + i, max(0, (width - len(line_text)) // 2), line_text[:width], style)
                        except: pass
                
                # Scroll bar/indicator if needed
                if len(self.lyrics) > lyrics_height:
                    scroll_pct = self.lyrics_scroll_offset / (len(self.lyrics) - lyrics_height)
                    try:
                        self.stdscr.addstr(start_y + int(lyrics_height * scroll_pct), width - 2, "|", curses.A_DIM)
                    except: pass

            else:
                 msg = "Fetching lyrics..." if self.current_song_lyrics_fetched else "Lyrics (Waiting for Metadata...)"
                 try:
                     self.stdscr.addstr(center_y, (width - len(msg)) // 2, msg, curses.A_DIM)
                 except: pass

        else:
            # Update animation frame
            if time.time() - self.last_anim_time > 0.4: # 400ms pulse
                self.anim_frame = (self.anim_frame + 1) % 2
                self.last_anim_time = time.time()
            
            cthulhu_frames = [
                [
                    " ( o . o ) ",
                    " (  |||  ) ",
                    "/||\/||\/|\\"
                ],
                [
                    " ( O . O ) ",
                    " ( /|||\ ) ",
                    "//||\/||\/\\\\"
                ]
            ]
            
            if not self.paused and self.playing_index != -1:
                art = cthulhu_frames[self.anim_frame]
                # Draw Art (3 lines) starting at center_y
                for i, line in enumerate(art):
                    try:
                        self.stdscr.addstr(center_y + i, (width - len(line)) // 2, line, 
                                           curses.color_pair(7) | curses.A_BOLD)
                    except: pass
            elif self.paused:
                 # Sleeping Cthulhu
                 art = [
                    " ( - . - ) ",
                    " (  zzz  ) ",
                    "  |||||||  "
                 ]
                 for i, line in enumerate(art):
                    try:
                        self.stdscr.addstr(center_y + i, (width - len(line)) // 2, line, 
                                           curses.color_pair(7) | curses.A_DIM)
                    except: pass


        # 5. Progress Bar
        self.draw_progress_bar(center_y + 4, width - 4)
        
        # 6. Volume
        vol_str = f"Volume: {int(self.volume * 100)}%"
        try:
            self.stdscr.addstr(center_y + 6, (width - len(vol_str)) // 2, vol_str)
        except: pass

        # 7. Next Track (Dimmed)
        if next_name and center_y + 9 < height - 1:
             try:
                 self.stdscr.addstr(center_y + 8, (width - 1) // 2, "v", curses.A_DIM)
                 self.stdscr.addstr(center_y + 9, (width - len(next_name)) // 2, next_name[:width], curses.A_DIM)
             except: pass

        # Controls Hint
        hint = "[n] Next  [p] Prev  [Space] Pause  [z] Shuffle  [l] Lyrics  [q] Browser"
        try:
            self.stdscr.addstr(height - 2, max(0, (width - len(hint)) // 2), hint[:width], curses.color_pair(1))
        except: pass

    def draw_browser(self):
        height, width = self.stdscr.getmaxyx()
        
        # Header
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
        else:
            # Help footer
            help_txt = "[R]ecursive Lib | [B]rowser | [z]Shuffle"
            try:
                self.stdscr.addstr(height-1, 0, help_txt[:width], curses.color_pair(6))
            except: pass

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
                elif key == ord('z'):
                    self.shuffle = not self.shuffle
                elif key == ord('l'):
                    self.show_lyrics = not self.show_lyrics
                    if self.show_lyrics and not self.current_song_lyrics_fetched and self.playing_index != -1:
                        artist = self.metadata.get('artist')
                        title = self.metadata.get('title')
                        file_path = os.path.join(self.current_dir, self.files[self.playing_index]['path'])
                        if (artist and title) or file_path:
                            self.current_song_lyrics_fetched = True
                            threading.Thread(target=self.fetch_lyrics, args=(artist or "", title or "", file_path), daemon=True).start()
                elif key == ord('R'):
                    self.scan_recursive()
                elif key == ord('B'):
                    self.scan_directory()
                
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
                            selected = self.files[self.selected_index]
                            if selected['type'] == 'dir':
                                if selected['path'] == '..':
                                    # If in Library mode, .. goes back to standard browser mode
                                    if self.library_mode:
                                        self.scan_directory()
                                    else:
                                        # Normal directory up
                                        new_path = os.path.abspath(os.path.join(self.current_dir, '..'))
                                        if os.path.isdir(new_path):
                                            self.current_dir = new_path
                                            self.selected_index = 0
                                            self.scroll_offset = 0
                                            self.scan_directory()
                                else:
                                    # Enter directory (only possible in Browser mode)
                                    new_path = os.path.abspath(os.path.join(self.current_dir, selected['path']))
                                    if os.path.isdir(new_path):
                                        self.current_dir = new_path
                                        self.selected_index = 0
                                        self.scroll_offset = 0
                                        self.scan_directory()
                            else:
                                self.play_file(self.selected_index)
                elif self.view_mode == 'player':
                    if key == curses.KEY_UP and self.show_lyrics:
                         self.lyrics_scroll_offset = max(0, self.lyrics_scroll_offset - 1)
                    elif key == curses.KEY_DOWN and self.show_lyrics:
                         if self.lyrics:
                             self.lyrics_scroll_offset = min(len(self.lyrics) - 1, self.lyrics_scroll_offset + 1)

            self.stdscr.refresh()

def main():
    try:
        curses.wrapper(lambda stdscr: MusicPlayer(stdscr).run())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()