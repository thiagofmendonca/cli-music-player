import sys
import os
import threading
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QSlider, QLabel, QListWidget, QListWidgetItem, 
                             QLineEdit, QTabWidget, QProgressBar, QStyle, QAbstractItemView,
                             QMenu, QMessageBox)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot, QSize, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette, QAction, QPixmap, QIcon, QKeySequence, QShortcut

from .engine import PlayerEngine
from .utils import format_time
from . import __version__

class CthulhuPulse(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setScaledContents(False) # Keep aspect ratio if possible, or True to fill
        
        # Load images
        base_path = os.path.dirname(__file__)
        self.pixmaps = [
            QPixmap(os.path.join(base_path, "assets", "frame1.png")),
            QPixmap(os.path.join(base_path, "assets", "frame2.png"))
        ]
        
        # Scale images if needed (optional, keeping original size for now unless too huge)
        self.pixmaps = [p.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio) for p in self.pixmaps]

        self.frame = 0
        if self.pixmaps[0].isNull():
             self.setText("Cthulhu Image Missing")
        else:
             self.setPixmap(self.pixmaps[0])

        self.timer = QTimer()
        self.timer.timeout.connect(self.animate)
        self.timer.start(400)
        self.is_playing = False

    def animate(self):
        if not self.is_playing:
            # Show static frame (e.g., frame 0) when paused
            if not self.pixmaps[0].isNull():
                self.setPixmap(self.pixmaps[0])
            return
            
        if self.pixmaps[0].isNull(): return
        self.frame = (self.frame + 1) % 2
        self.setPixmap(self.pixmaps[self.frame])

    def set_playing(self, playing):
        self.is_playing = playing
        if not playing:
            # Force update to static frame immediately
            self.animate()

class MainWindow(QMainWindow):
    search_finished = pyqtSignal(list)

    def __init__(self, debug=False):
        super().__init__()
        self.debug = debug
        self.engine = PlayerEngine(debug=debug)
        self.setWindowTitle(f"FreeThullu Music Player v{__version__} (GUI)")
        self.setMinimumSize(900, 700)
        
        # Set Window Icon
        base_path = os.path.dirname(__file__)
        icon_path = os.path.join(base_path, "assets", "frame1.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.init_ui()
        self.setup_shortcuts()
        self.setup_connections()
        
        # Connect custom signal
        self.search_finished.connect(self.show_search_results)
        
        # Initial scan
        self.engine.scan_directory()
        
        # Check for MPV
        if not self.engine.mpv_bin:
            QMessageBox.critical(self, "MPV Missing", 
                                "The 'mpv' player was not found on your system.\n\n"
                                "Please install it to enable playback:\n"
                                "- Linux: sudo apt install mpv (or your manager)\n"
                                "- Windows: It should have downloaded automatically, check your internet.")

    def setup_shortcuts(self):
        # Space for Play/Pause
        self.shortcut_space = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self.shortcut_space.activated.connect(self.engine.toggle_pause)
        
        # Media Keys
        self.shortcut_play = QShortcut(QKeySequence(Qt.Key.Key_MediaPlay), self)
        self.shortcut_play.activated.connect(self.engine.toggle_pause)
        
        self.shortcut_stop = QShortcut(QKeySequence(Qt.Key.Key_MediaStop), self)
        self.shortcut_stop.activated.connect(self.engine.stop_music)
        
        self.shortcut_next = QShortcut(QKeySequence(Qt.Key.Key_MediaNext), self)
        self.shortcut_next.activated.connect(self.engine.handle_end_of_file)

    def init_ui(self):
        # Dark Theme
        self.set_dark_theme()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 2. Tabs
        self.tabs = QTabWidget()
        
        # Tab: Now Playing
        self.player_tab = QWidget()
        player_layout = QVBoxLayout(self.player_tab)
        self.cthulhu = CthulhuPulse()
        self.lbl_title = QLabel("No Music Playing")
        self.lbl_title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_artist = QLabel("-")
        self.lbl_artist.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lyrics_area = QListWidget()
        self.lyrics_area.setStyleSheet("background: transparent; border: none;")
        
        player_layout.addWidget(self.lbl_title)
        player_layout.addWidget(self.lbl_artist)
        player_layout.addStretch()
        player_layout.addWidget(self.cthulhu)
        player_layout.addStretch()
        player_layout.addWidget(QLabel("Lyrics:"))
        player_layout.addWidget(self.lyrics_area)
        
        self.tabs.addTab(self.player_tab, "Now Playing")

        # Tab: Library
        self.library_tab = QWidget()
        lib_layout = QVBoxLayout(self.library_tab)
        
        # Filter Bar
        self.lib_filter = QLineEdit()
        self.lib_filter.setPlaceholderText("Filter files (Press Enter for deep recursive search)...")
        self.lib_filter.textChanged.connect(self.filter_library)
        self.lib_filter.returnPressed.connect(self.trigger_recursive_search)
        lib_layout.addWidget(self.lib_filter)
        
        # Navigation Bar (Path)
        nav_layout = QHBoxLayout()
        self.btn_up = QPushButton("⬆")
        self.btn_up.setFixedWidth(30)
        self.btn_up.clicked.connect(self.go_up_dir)
        
        self.path_input = QLineEdit()
        self.path_input.setText(self.engine.current_dir)
        self.path_input.returnPressed.connect(self.navigate_to_path)
        
        nav_layout.addWidget(self.btn_up)
        nav_layout.addWidget(self.path_input)
        lib_layout.addLayout(nav_layout)
        
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.itemDoubleClicked.connect(self.on_file_double_clicked)
        self.file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self.show_library_context_menu)
        
        lib_layout.addWidget(self.file_list)
        self.tabs.addTab(self.library_tab, "Library")

        # Tab: Search Results
        self.search_tab = QWidget()
        search_res_layout = QVBoxLayout(self.search_tab)
        
        # Search Bar moved here
        search_bar_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search YouTube (use sc: for SoundCloud)...")
        self.search_input.returnPressed.connect(self.start_search)
        self.btn_search = QPushButton("Search")
        self.btn_search.clicked.connect(self.start_search)
        search_bar_layout.addWidget(self.search_input)
        search_bar_layout.addWidget(self.btn_search)
        search_res_layout.addLayout(search_bar_layout)
        
        self.search_list = QListWidget()
        self.search_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.search_list.itemDoubleClicked.connect(self.on_search_item_double_clicked)
        self.search_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.search_list.customContextMenuRequested.connect(self.show_search_context_menu)
        search_res_layout.addWidget(self.search_list)
        self.tabs.addTab(self.search_tab, "Online Search")

        # Tab: Queue
        self.queue_tab = QWidget()
        queue_layout = QVBoxLayout(self.queue_tab)
        self.queue_list = QListWidget()
        self.queue_list.itemDoubleClicked.connect(self.on_queue_item_double_clicked)
        queue_layout.addWidget(self.queue_list)
        self.tabs.addTab(self.queue_tab, "Queue")

        # Tab: Sobre
        self.about_tab = QWidget()
        about_layout = QVBoxLayout(self.about_tab)
        about_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_about = QLabel("<h2>FreeThullu Music Player</h2>")
        lbl_about.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_repo = QLabel('<a href="https://github.com/thiagofmendonca/cli-music-player" style="color: #2a82da;">GitHub Repository</a>')
        lbl_repo.setOpenExternalLinks(True)
        lbl_repo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_insta = QLabel('Instagram: <a href="https://instagram.com/tfaria1991" style="color: #2a82da;">@tfaria1991</a>')
        lbl_insta.setOpenExternalLinks(True)
        lbl_insta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_v = QLabel(f"Version {__version__}")
        lbl_v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        about_layout.addStretch()
        about_layout.addWidget(lbl_about)
        about_layout.addWidget(lbl_v)
        about_layout.addSpacing(20)
        about_layout.addWidget(lbl_repo)
        about_layout.addWidget(lbl_insta)
        about_layout.addStretch()
        
        self.tabs.addTab(self.about_tab, "Sobre")

        main_layout.addWidget(self.tabs)

        # 3. Controls
        controls_panel = QWidget()
        controls_layout = QVBoxLayout(controls_panel)

        # Progress
        progress_layout = QHBoxLayout()
        self.lbl_current_time = QLabel("00:00")
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setEnabled(True) # Enabled for seeking
        self.progress_slider.sliderReleased.connect(self.on_seek_released)
        self.progress_slider.sliderPressed.connect(self.on_seek_pressed)
        self.is_seeking = False
        
        self.lbl_total_time = QLabel("00:00")
        progress_layout.addWidget(self.lbl_current_time)
        progress_layout.addWidget(self.progress_slider)
        progress_layout.addWidget(self.lbl_total_time)
        controls_layout.addLayout(progress_layout)

        # Buttons
        btns_layout = QHBoxLayout()
        self.btn_prev = QPushButton()
        self.btn_prev.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward))
        
        self.btn_play = QPushButton()
        self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.btn_play.clicked.connect(self.engine.toggle_pause)

        self.btn_next = QPushButton()
        self.btn_next.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward))
        self.btn_next.clicked.connect(self.engine.handle_end_of_file)

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 150)
        self.vol_slider.setValue(self.engine.volume)
        self.vol_slider.setFixedWidth(150)
        self.vol_slider.valueChanged.connect(self.engine.set_volume)

        btns_layout.addWidget(self.btn_prev)
        btns_layout.addWidget(self.btn_play)
        btns_layout.addWidget(self.btn_next)
        btns_layout.addStretch()
        btns_layout.addWidget(QLabel("Vol:"))
        btns_layout.addWidget(self.vol_slider)
        
        controls_layout.addLayout(btns_layout)
        main_layout.addWidget(controls_panel)

        # Status Bar
        self.statusBar().showMessage("Ready")

    def set_dark_theme(self):
        palette = QPalette()
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Base, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.AlternateBase, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Text, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Button, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        self.setPalette(palette)
        self.setStyleSheet("QToolTip { color: #ffffff; background-color: #2a82da; border: 1px solid white; }")

    def setup_connections(self):
        self.engine.track_changed.connect(self.update_track_info)
        self.engine.position_changed.connect(self.update_progress)
        self.engine.status_changed.connect(self.update_play_icon)
        # Fix animation state
        self.engine.status_changed.connect(lambda paused: self.cthulhu.set_playing(not paused))
        
        self.engine.directory_scanned.connect(self.populate_file_list)
        self.engine.message_emitted.connect(self.statusBar().showMessage)
        self.engine.lyrics_loaded.connect(self.populate_lyrics)
        self.engine.queue_changed.connect(self.populate_queue)

    def trigger_recursive_search(self):
        query = self.lib_filter.text()
        if query:
            self.statusBar().showMessage(f"Deep searching for: {query}...")
            # We run this in a thread ideally, but for now direct call (it uses os.walk which is blocking but fast enough for local)
            # Or better, let the engine handle threading if needed. Engine.search_local_files is synchronous now.
            threading.Thread(target=self.engine.search_local_files, args=(query,), daemon=True).start()

    def show_library_context_menu(self, pos):
        menu = QMenu()
        add_action = QAction("Add to Queue", self)
        add_action.triggered.connect(lambda: self.add_selected_to_queue(self.file_list))
        menu.addAction(add_action)
        menu.exec(self.file_list.mapToGlobal(pos))

    def show_search_context_menu(self, pos):
        menu = QMenu()
        add_action = QAction("Add to Queue", self)
        add_action.triggered.connect(lambda: self.add_selected_to_queue(self.search_list))
        menu.addAction(add_action)
        menu.exec(self.search_list.mapToGlobal(pos))

    def add_selected_to_queue(self, list_widget):
        items = list_widget.selectedItems()
        data_list = []
        for item in items:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data['type'] != 'dir':
                data_list.append(data)
        
        if data_list:
            self.engine.add_to_queue(data_list)

    @pyqtSlot(list)
    def populate_queue(self, queue):
        self.queue_list.clear()
        for i, item in enumerate(queue):
            name = item.get('title', item.get('name', 'Unknown'))
            artist = item.get('artist', 'Unknown')
            list_item = QListWidgetItem(f"{i+1}. {name} - {artist}")
            list_item.setData(Qt.ItemDataRole.UserRole, i) # Store index
            self.queue_list.addItem(list_item)
        
        # Refresh highlights in other lists
        self.refresh_list_highlights(self.file_list)
        self.refresh_list_highlights(self.search_list)

    def refresh_list_highlights(self, list_widget):
        count = list_widget.count()
        for i in range(count):
            item = list_widget.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if self.engine.is_in_queue(data):
                item.setForeground(QColor(0, 255, 0))
            else:
                # Reset color (assuming default is white/theme dependent, or explicitly set white)
                # Ideally we should use the theme's text color, but here we forced white/grey in theme
                item.setForeground(QColor(255, 255, 255))

    def on_queue_item_double_clicked(self, item):
        idx = item.data(Qt.ItemDataRole.UserRole)
        self.engine.play_queue_index(idx)

    @pyqtSlot(dict)
    def update_track_info(self, meta):
        self.lbl_title.setText(meta.get('title', 'Unknown'))
        self.lbl_artist.setText(meta.get('artist', 'Unknown'))
        self.tabs.setCurrentIndex(0)

    @pyqtSlot(float, float)
    def update_progress(self, current, total):
        self.lbl_current_time.setText(format_time(current))
        self.lbl_total_time.setText(format_time(total))
        if total > 0:
            self.progress_slider.setMaximum(int(total))
            if not self.is_seeking:
                self.progress_slider.setValue(int(current))

    def on_seek_pressed(self):
        self.is_seeking = True

    def on_seek_released(self):
        pos = self.progress_slider.value()
        self.engine.seek(pos)
        self.is_seeking = False

    @pyqtSlot(bool)
    def update_play_icon(self, paused):
        icon = QStyle.StandardPixmap.SP_MediaPause if not paused else QStyle.StandardPixmap.SP_MediaPlay
        self.btn_play.setIcon(self.style().standardIcon(icon))
        self.cthulhu.set_playing(not paused)

    @pyqtSlot(list)
    def populate_file_list(self, files):
        self.file_list.clear()
        self.path_input.setText(self.engine.current_dir)
        for f in files:
            icon = "📁 " if f['type'] == 'dir' else "🎵 "
            item = QListWidgetItem(f"{icon}{f['name']}")
            item.setData(Qt.ItemDataRole.UserRole, f)
            if self.engine.is_in_queue(f):
                item.setForeground(QColor(0, 255, 0))
            self.file_list.addItem(item)
        self.refresh_list_highlights(self.file_list)

    def go_up_dir(self):
        parent_dir = os.path.dirname(self.engine.current_dir)
        if os.path.isdir(parent_dir):
            self.engine.scan_directory(parent_dir)

    def navigate_to_path(self):
        path = self.path_input.text()
        if os.path.isdir(path):
            self.engine.scan_directory(path)
        else:
            self.path_input.setText(self.engine.current_dir) # Revert if invalid

    @pyqtSlot(list)
    def populate_lyrics(self, lyrics):
        self.lyrics_area.clear()
        for line in lyrics:
            self.lyrics_area.addItem(line['text'])

    def on_file_double_clicked(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data['type'] == 'dir':
            new_path = os.path.abspath(os.path.join(self.engine.current_dir, data['path']))
            self.lib_filter.clear() # Clear filter on navigation
            self.engine.scan_directory(new_path)
        else:
            idx = self.file_list.row(item)
            self.engine.play_file(idx)

    def filter_library(self, text):
        count = self.file_list.count()
        for i in range(count):
            item = self.file_list.item(i)
            item_text = item.text().lower()
            # Keep parent dir visible always or filter it too? Let's keep it visible if it matches or is '..'
            if '..' in item_text or text.lower() in item_text:
                item.setHidden(False)
            else:
                item.setHidden(True)

    def start_search(self):
        query = self.search_input.text()
        if not query: return
        self.statusBar().showMessage(f"Searching for: {query}...")
        if self.debug: print(f"[DEBUG] GUI Start Search: {query}")
        
        def run_search():
            try:
                source = 'soundcloud' if query.startswith('sc:') else 'youtube'
                q = query[3:] if source == 'soundcloud' else query
                if self.debug: print(f"[DEBUG] Executing search backend: {q} ({source})")
                results = self.engine.searcher.search(q, source)
                if self.debug: print(f"[DEBUG] Search results count: {len(results)}")
                # Emit signal to update UI from main thread
                self.search_finished.emit(results)
            except Exception as e:
                if self.debug: print(f"[DEBUG] Search Thread Error: {e}")
        
        threading.Thread(target=run_search, daemon=True).start()

    @pyqtSlot(list)
    def show_search_results(self, results):
        self.search_list.clear()
        for res in results:
            item = QListWidgetItem(f"🌐 {res['title']} - {res['artist']}")
            item.setData(Qt.ItemDataRole.UserRole, res)
            if self.engine.is_in_queue(res):
                item.setForeground(QColor(0, 255, 0))
            self.search_list.addItem(item)
        self.tabs.setCurrentIndex(2)
        self.statusBar().showMessage(f"Found {len(results)} results")

    def on_search_item_double_clicked(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        self.engine.play_stream(data)

    def closeEvent(self, event):
        self.engine.cleanup()
        event.accept()

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Cthulhu Music Player (GUI)")
    parser.add_argument('-d', '--debug', action='store_true', help="Enable debug logging")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    window = MainWindow(debug=args.debug)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
