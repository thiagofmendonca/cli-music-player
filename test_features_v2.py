import unittest
from unittest.mock import MagicMock, patch
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from musicplayer.main import MusicPlayer
from musicplayer.search import OnlineSearcher

class TestQueueFeatures(unittest.TestCase):
    def setUp(self):
        # Setup Patches
        self.patcher_curses = patch('musicplayer.main.curses')
        self.patcher_config = patch('musicplayer.main.load_config')
        self.patcher_get_mpv = patch('musicplayer.main.get_mpv_path')
        self.patcher_dl_mpv = patch('musicplayer.main.download_mpv')
        
        self.mock_curses = self.patcher_curses.start()
        self.mock_config = self.patcher_config.start()
        self.mock_get_mpv = self.patcher_get_mpv.start()
        self.mock_dl_mpv = self.patcher_dl_mpv.start()
        
        self.mock_config.return_value = {}
        self.mock_get_mpv.return_value = '/usr/bin/mpv'
        
        self.stdscr = MagicMock()
        self.stdscr.getmaxyx.return_value = (40, 100) # Large screen
        
        # Suppress scan_directory
        with patch('musicplayer.main.MusicPlayer.scan_directory'):
            with patch('threading.Thread'): 
                self.player = MusicPlayer(self.stdscr)
        
        self.player._start_mpv = MagicMock()
        self.player.cleanup = MagicMock()
        self.player.stop_music = MagicMock()

    def tearDown(self):
        self.patcher_curses.stop()
        self.patcher_config.stop()
        self.patcher_get_mpv.stop()
        self.patcher_dl_mpv.stop()

    def test_add_all_search_results(self):
        self.player.view_mode = 'search_results'
        self.player.search_results = [
            {'title': 'T1', 'artist': 'A1', 'id': '1', 'type': 'stream'},
            {'title': 'T2', 'artist': 'A2', 'id': '2', 'type': 'stream'}
        ]
        
        # Simulate 'A' (shift+a)
        self.player.process_key(ord('A'))
        
        self.assertEqual(len(self.player.queue), 2)
        self.assertEqual(self.player.queue[0]['title'], 'T1')
        self.assertEqual(self.player.queue[1]['title'], 'T2')

    def test_queue_display_logic(self):
        # Setup queue
        self.player.queue = [
            {'title': 'Song A'},
            {'title': 'Song B'},
            {'title': 'Song C'},
            {'title': 'Song D'},
            {'title': 'Song E'},
            {'title': 'Song F'} # Should not show (max 5)
        ]
        self.player.duration = 100
        self.player.position = 10
        self.player.metadata = {'title': 'Now Playing', 'artist': 'Me'}
        
        self.player.draw_player_view()
        
        # Verify calls to addstr
        found_header = False
        found_song_a = False
        found_song_f = False
        
        for call in self.stdscr.addstr.call_args_list:
            args = call[0]
            for arg in args:
                if isinstance(arg, str):
                    if "--- Queue ---" in arg: found_header = True
                    if "Song A" in arg: found_song_a = True 
                    if "Song F" in arg: found_song_f = True
            
        self.assertTrue(found_header, "Header not found")
        self.assertTrue(found_song_a, "Song A not found. Args were: " + str([c[0] for c in self.stdscr.addstr.call_args_list]))
        self.assertFalse(found_song_f, "Song F should not be found")

class TestSearcher(unittest.TestCase):
    @patch('yt_dlp.YoutubeDL')
    def test_search_url_handling(self, mock_ydl_cls):
        searcher = OnlineSearcher()
        mock_ydl = mock_ydl_cls.return_value.__enter__.return_value
        
        # 1. Normal query
        mock_ydl.extract_info.return_value = {'entries': []}
        searcher.search("hello world")
        mock_ydl.extract_info.assert_called_with("ytsearch20:hello world", download=False)
        
        # 2. URL query
        searcher.search("https://youtube.com/playlist?list=123")
        mock_ydl.extract_info.assert_called_with("https://youtube.com/playlist?list=123", download=False)

if __name__ == '__main__':
    unittest.main()