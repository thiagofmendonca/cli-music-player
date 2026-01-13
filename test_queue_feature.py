import unittest
from unittest.mock import MagicMock, patch
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from musicplayer.main import MusicPlayer

class TestQueue(unittest.TestCase):
    @patch('musicplayer.main.curses')
    @patch('musicplayer.main.load_config')
    @patch('musicplayer.main.get_mpv_path')
    @patch('musicplayer.main.download_mpv')
    def setUp(self, mock_dl, mock_get_mpv, mock_conf, mock_curses):
        mock_conf.return_value = {}
        mock_get_mpv.return_value = '/usr/bin/mpv'
        
        self.stdscr = MagicMock()
        self.stdscr.getmaxyx.return_value = (24, 80)
        
        # Suppress the scan_directory call which touches FS
        with patch('musicplayer.main.MusicPlayer.scan_directory'):
            with patch('threading.Thread'): # suppress background threads
                self.player = MusicPlayer(self.stdscr)
            
        # Mock _start_mpv to avoid subprocess
        self.player._start_mpv = MagicMock()
        self.player.cleanup = MagicMock()
        self.player.stop_music = MagicMock()

    def test_queue_initialization(self):
        self.assertEqual(self.player.queue, [])

    def test_add_local_file_to_queue(self):
        # Setup fake file list
        self.player.current_dir = '/tmp'
        self.player.files = [{'name': 'song.mp3', 'type': 'file', 'path': 'song.mp3'}]
        self.player.selected_index = 0
        self.player.view_mode = 'browser'
        
        # Simulate 'a' key press
        self.player.process_key(ord('a'))
        
        self.assertEqual(len(self.player.queue), 1)
        item = self.player.queue[0]
        self.assertEqual(item['type'], 'file')
        self.assertEqual(item['name'], 'song.mp3')
        self.assertEqual(item['path'], '/tmp/song.mp3')

    def test_add_search_result_to_queue(self):
        # Setup fake search results
        self.player.view_mode = 'search_results'
        self.player.search_results = [{
            'title': 'Test Song',
            'artist': 'Test Artist',
            'id': 'videoid',
            'type': 'stream'
        }]
        self.player.selected_index = 0
        
        # Simulate 'a' key press
        self.player.process_key(ord('a'))
        
        self.assertEqual(len(self.player.queue), 1)
        item = self.player.queue[0]
        self.assertEqual(item['title'], 'Test Song')
        self.assertEqual(item['type'], 'stream')

    def test_play_queue_logic(self):
        # 1. Queue is empty, playing index -1 -> stop
        self.player.queue = []
        self.player.playing_index = -1
        self.player.handle_end_of_file()
        self.player.stop_music.assert_called()

        # 2. Queue has item
        item = {'type': 'stream', 'title': 'Q Song', 'artist': 'Q', 'id': '123'}
        self.player.queue = [item]
        self.player.stop_music.reset_mock()
        
        self.player.handle_end_of_file()
        
        self.assertEqual(len(self.player.queue), 0) # Item popped
        self.player._start_mpv.assert_called() # Player started
        args, _ = self.player._start_mpv.call_args
        self.assertTrue('123' in args[0] or 'youtube' in args[0])

if __name__ == '__main__':
    unittest.main()
