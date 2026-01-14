import sys
import os
import threading
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QSlider, QLabel, QListWidget, QListWidgetItem, 
                             QLineEdit, QTabWidget, QProgressBar, QStyle)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot, QSize
from PyQt6.QtGui import QFont, QColor, QPalette

from .engine import PlayerEngine
from .utils import format_time

class CthulhuPulse(QLabel):
    def __init__(self):
        super().__init__(" ( o . o ) \n (  |||  ) \n/||\\/||\\/||\\ ")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(QFont("Monospace", 20, QFont.Weight.Bold))
        self.setStyleSheet("color: #00ff00;")
        self.frame = 0
        self.frames = [
            r""" ( o . o ) 
 (  |||  ) 
/||\\/||\\/||\\ """,
            r""" ( O . O ) 
 ( /|||\ ) 
//||\\/||\\/||\\ """
        ]
        self.timer = QTimer()
        self.timer.timeout.connect(self.animate)
        self.timer.start(400)

    def animate(self):
        self.frame = (self.frame + 1) % 2
        self.setText(self.frames[self.frame])

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.engine = PlayerEngine()
        self.setWindowTitle("Cthulhu Music Player v0.9.1 (GUI)")
        self.setMinimumSize(900, 700)
        self.init_ui()
        self.setup_connections()
        
        # Initial scan
        self.engine.scan_directory()

    def init_ui(self):
        # Dark Theme
        self.set_dark_theme()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 1. Search Bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search YouTube (use sc: for SoundCloud)...")
        self.search_input.returnPressed.connect(self.start_search)
        self.btn_search = QPushButton("Search")
        self.btn_search.clicked.connect(self.start_search)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.btn_search)
        main_layout.addLayout(search_layout)

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
        self.lbl_path = QLabel(f"Path: {self.engine.current_dir}")
        self.file_list = QListWidget()
        self.file_list.itemDoubleClicked.connect(self.on_file_double_clicked)
        lib_layout.addWidget(self.lbl_path)
        lib_layout.addWidget(self.file_list)
        self.tabs.addTab(self.library_tab, "Library")

        # Tab: Search Results
        self.search_tab = QWidget()
        search_res_layout = QVBoxLayout(self.search_tab)
        self.search_list = QListWidget()
        self.search_list.itemDoubleClicked.connect(self.on_search_item_double_clicked)
        search_res_layout.addWidget(self.search_list)
        self.tabs.addTab(self.search_tab, "Search Results")

        main_layout.addWidget(self.tabs)

        # 3. Controls
        controls_panel = QWidget()
        controls_layout = QVBoxLayout(controls_panel)

        # Progress
        progress_layout = QHBoxLayout()
        self.lbl_current_time = QLabel("00:00")
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setEnabled(False)
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
        self.engine.directory_scanned.connect(self.populate_file_list)
        self.engine.message_emitted.connect(self.statusBar().showMessage)
        self.engine.lyrics_loaded.connect(self.populate_lyrics)

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
            self.progress_slider.setValue(int(current))

    @pyqtSlot(bool)
    def update_play_icon(self, paused):
        icon = QStyle.StandardPixmap.SP_MediaPause if not paused else QStyle.StandardPixmap.SP_MediaPlay
        self.btn_play.setIcon(self.style().standardIcon(icon))

    @pyqtSlot(list)
    def populate_file_list(self, files):
        self.file_list.clear()
        self.lbl_path.setText(f"Path: {self.engine.current_dir}")
        for f in files:
            icon = "📁 " if f['type'] == 'dir' else "🎵 "
            item = QListWidgetItem(f"{icon}{f['name']}")
            item.setData(Qt.ItemDataRole.UserRole, f)
            if self.engine.is_in_queue(f):
                item.setForeground(QColor(0, 255, 0))
            self.file_list.addItem(item)

    @pyqtSlot(list)
    def populate_lyrics(self, lyrics):
        self.lyrics_area.clear()
        for line in lyrics:
            self.lyrics_area.addItem(line['text'])

    def on_file_double_clicked(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data['type'] == 'dir':
            new_path = os.path.abspath(os.path.join(self.engine.current_dir, data['path']))
            self.engine.scan_directory(new_path)
        else:
            idx = self.file_list.row(item)
            self.engine.play_file(idx)

    def start_search(self):
        query = self.search_input.text()
        if not query: return
        self.statusBar().showMessage(f"Searching for: {query}...")
        
        def run_search():
            source = 'soundcloud' if query.startswith('sc:') else 'youtube'
            q = query[3:] if source == 'soundcloud' else query
            results = self.engine.searcher.search(q, source)
            QTimer.singleShot(0, lambda: self.show_search_results(results))
        
        threading.Thread(target=run_search, daemon=True).start()

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
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
