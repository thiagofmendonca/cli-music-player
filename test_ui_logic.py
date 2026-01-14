import unittest
import os
from unittest.mock import MagicMock
from musicplayer.main import MusicPlayer

class TestMusicPlayerLogic(unittest.TestCase):
    def setUp(self):
        self.stdscr = MagicMock()
        # Mocking curses methods
        self.stdscr.getmaxyx.return_value = (24, 80)
        
        # We need to mock get_mpv_path to avoid sys.exit()
        with unittest.mock.patch('musicplayer.main.get_mpv_path', return_value='/usr/bin/mpv'):
            with unittest.mock.patch('musicplayer.main.load_config', return_value={}):
                with unittest.mock.patch('curses.start_color'):
                     with unittest.mock.patch('curses.use_default_colors'):
                         with unittest.mock.patch('curses.init_pair'):
                             with unittest.mock.patch('curses.curs_set'):
                                 self.player = MusicPlayer(self.stdscr)

    def test_initial_view_mode(self):
        self.assertEqual(self.player.view_mode, 'player')

    def test_is_in_queue_local_file(self):
        # Setup
        abs_path = os.path.abspath("test_song.mp3")
        queue_item = {'type': 'file', 'path': abs_path, 'name': 'test_song.mp3'}
        self.player.queue.append(queue_item)
        
        # Test Browser Item (relative path)
        browser_item = {'type': 'file', 'path': 'test_song.mp3', 'name': 'test_song.mp3'}
        
        # We need to make sure self.current_dir matches where "test_song.mp3" would be
        self.player.current_dir = os.getcwd()
        
        self.assertTrue(self.player.is_in_queue(browser_item))
        
        # Test not in queue
        browser_item_2 = {'type': 'file', 'path': 'other_song.mp3', 'name': 'other_song.mp3'}
        self.assertFalse(self.player.is_in_queue(browser_item_2))

    def test_is_in_queue_stream(self):
        # Setup
        queue_item = {'type': 'stream', 'id': '12345', 'title': 'Stream Song'}
        self.player.queue.append(queue_item)
        
        # Test Search Result Item
        search_item = {'type': 'stream', 'id': '12345', 'title': 'Stream Song'}
        self.assertTrue(self.player.is_in_queue(search_item))
        
        # Test not in queue
        search_item_2 = {'type': 'stream', 'id': '67890', 'title': 'Other Song'}
        self.assertFalse(self.player.is_in_queue(search_item_2))

if __name__ == '__main__':
    unittest.main()
