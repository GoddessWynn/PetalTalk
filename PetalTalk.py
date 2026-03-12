import sys
import numpy as np
import sounddevice as sd
import json
import os
import webbrowser
from PyQt5.QtWidgets import (QApplication, QLabel, QMainWindow, QWidget, 
                             QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, 
                             QComboBox, QCheckBox, QFileDialog, QProgressBar, QMessageBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QPixmap, QIcon, QFont

CONFIG_FILE = "presets.json"
VERSION = "v1.0.0"

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class PNGTuberOverlay(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PetalTalk_Overlay_Window")
        self.setObjectName("PetalTalkOverlay")
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        icon_path = resource_path("icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self.container = QWidget(self)
        self.setCentralWidget(self.container)
        
        self.character_label = QLabel(self.container)
        self.character_label.setAlignment(Qt.AlignCenter)

        self.idle_raw = QPixmap(resource_path("idle.png"))
        self.talking_raw = QPixmap(resource_path("talking.png"))
        self.current_size = 300
        self.is_talking = False
        self.manual_test = False
        self.threshold = 0.1
        self.current_volume = 0
        self.stream = None
        
        self.update_appearance()
        self.start_audio_stream(None)
        self.show()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_appearance)
        self.timer.start(50)

    def set_images(self, idle_path, talking_path):
        if idle_path and os.path.exists(idle_path):
            self.idle_raw = QPixmap(idle_path)
        if talking_path and os.path.exists(talking_path):
            self.talking_raw = QPixmap(talking_path)
        self.update_appearance()

    def set_overlay_flags(self, stay_on_top, obs_mode=False):
        self.hide()
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setWindowFlags(Qt.Window) 
        
        QApplication.processEvents()
        self.repaint()

        def apply_new_state():
            if obs_mode:
                flags = Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint
                self.setAttribute(Qt.WA_TranslucentBackground, False)
                self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
                self.setStyleSheet("background-color: #00ff00;")
            else:
                flags = Qt.FramelessWindowHint | Qt.Tool
                if stay_on_top:
                    flags |= Qt.WindowStaysOnTopHint
                    self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                else:
                    self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
                
                self.setAttribute(Qt.WA_TranslucentBackground, True)
                self.setStyleSheet("background-color: transparent;")
            
            self.setWindowFlags(flags)
            self.setWindowTitle("PetalTalk_Overlay_Window")
            QTimer.singleShot(100, self.show)

        QTimer.singleShot(300, apply_new_state)

    def start_audio_stream(self, device_id):
        if self.stream:
            self.stream.stop()
            self.stream.close()
        try:
            self.stream = sd.InputStream(device=device_id, channels=1, samplerate=16000, callback=self.audio_callback)
            self.stream.start()
        except Exception as e:
            print(f"Audio Stream Error: {e}")

    def audio_callback(self, indata, frames, time, status):
        self.current_volume = np.linalg.norm(indata) * 10
        if not self.manual_test:
            self.is_talking = self.current_volume > self.threshold

    def update_appearance(self):
        img = self.talking_raw if self.is_talking else self.idle_raw
        if img and not img.isNull():
            scaled = img.scaled(self.current_size, self.current_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.character_label.setPixmap(scaled)
            self.character_label.resize(scaled.size())
            self.character_label.move(0, 0)
            
        self.container.setFixedSize(self.current_size, self.current_size)
        self.resize(self.current_size, self.current_size)

class ControlPanel(QWidget):
    def __init__(self, overlay):
        super().__init__()
        self.overlay = overlay
        self.setWindowTitle("PetalTalk Controls")
        self.setMinimumWidth(450)
        
        icon_path = resource_path("icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self.presets = self.load_all_presets()
        self.main_layout = QVBoxLayout()

        # Audio Section
        header_audio = QLabel("<b>Audio Input</b>")
        header_audio.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(header_audio)
        
        self.mic_dropdown = QComboBox()
        self.populate_mics()
        self.mic_dropdown.currentIndexChanged.connect(self.change_mic)
        self.main_layout.addWidget(self.mic_dropdown)

        self.sens_in = QLineEdit(str(self.overlay.threshold))
        self.sens_in.setPlaceholderText("Sensitivity (0.1 - 1.0)")
        self.main_layout.addWidget(self.sens_in)

        self.vol_bar = QProgressBar()
        self.vol_bar.setRange(0, 100)
        self.vol_bar.setTextVisible(False)
        self.main_layout.addWidget(self.vol_bar)

        self.test_btn = QPushButton("Hold to Test Talk State")
        self.test_btn.pressed.connect(self.start_test)
        self.test_btn.released.connect(self.stop_test)
        self.main_layout.addWidget(self.test_btn)

        # Image Section
        header_img = QLabel("<b>Character Images (Preset Saved)</b>")
        header_img.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(header_img)
        
        self.idle_path_display = QLineEdit(resource_path("idle.png"))
        self.idle_path_display.setReadOnly(True)
        self.btn_browse_idle = QPushButton("Browse Idle")
        self.btn_browse_idle.clicked.connect(lambda: self.browse_image("idle"))
        h1 = QHBoxLayout(); h1.addWidget(self.idle_path_display); h1.addWidget(self.btn_browse_idle)
        self.main_layout.addLayout(h1)

        self.talk_path_display = QLineEdit(resource_path("talking.png"))
        self.talk_path_display.setReadOnly(True)
        self.btn_browse_talk = QPushButton("Browse Talking")
        self.btn_browse_talk.clicked.connect(lambda: self.browse_image("talking"))
        h2 = QHBoxLayout(); h2.addWidget(self.talk_path_display); h2.addWidget(self.btn_browse_talk)
        self.main_layout.addLayout(h2)

        # Layout Section
        header_pos = QLabel("<b>Overlay Window Position (Preset Saved)</b>")
        header_pos.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(header_pos)
        
        size_layout = QHBoxLayout()
        self.size_in = QLineEdit(str(self.overlay.current_size))
        size_layout.addWidget(QLabel("Character Size:"))
        size_layout.addWidget(self.size_in)
        self.main_layout.addLayout(size_layout)
        
        pos_layout = QHBoxLayout()
        self.x_in = QLineEdit(str(self.overlay.x()))
        self.y_in = QLineEdit(str(self.overlay.y()))
        pos_layout.addWidget(QLabel("Win X:")); pos_layout.addWidget(self.x_in)
        pos_layout.addWidget(QLabel("Win Y:")); pos_layout.addWidget(self.y_in)
        self.main_layout.addLayout(pos_layout)

        # Centered Checkboxes
        check_layout = QHBoxLayout()
        self.ontop_check = QCheckBox("Always on Top")
        self.ontop_check.setChecked(True)
        self.obs_check = QCheckBox("OBS Mode (Green Screen)")
        self.obs_check.setChecked(False)
        
        self.ontop_check.toggled.connect(self.toggle_ontop_logic)
        self.obs_check.toggled.connect(self.toggle_obs_logic)
        
        check_layout.addStretch()
        check_layout.addWidget(self.ontop_check)
        check_layout.addWidget(self.obs_check)
        check_layout.addStretch()
        self.main_layout.addLayout(check_layout)

        self.apply_btn = QPushButton("Apply All Settings")
        self.apply_btn.clicked.connect(self.apply)
        self.main_layout.addWidget(self.apply_btn)

        # Presets Section
        header_presets = QLabel("<b>Saved Presets</b>")
        header_presets.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(header_presets)
        
        self.preset_dropdown = QComboBox()
        self.update_preset_list()
        self.main_layout.addWidget(self.preset_dropdown)

        p_btns = QHBoxLayout()
        self.load_btn = QPushButton("Load"); self.load_btn.clicked.connect(self.load_selected_preset)
        self.del_btn = QPushButton("Delete"); self.del_btn.clicked.connect(self.delete_preset)
        p_btns.addWidget(self.load_btn); p_btns.addWidget(self.del_btn)
        self.main_layout.addLayout(p_btns)

        self.new_preset_name = QLineEdit(); self.new_preset_name.setPlaceholderText("New Name...")
        self.main_layout.addWidget(self.new_preset_name)
        self.save_btn = QPushButton("Save Current State"); self.save_btn.clicked.connect(self.save_preset)
        self.main_layout.addWidget(self.save_btn)

        # Footer Area with Links
        self.main_layout.addSpacing(10)
        footer_layout = QHBoxLayout()
        
        # Version
        self.version_label = QLabel(VERSION)
        self.version_label.setStyleSheet("color: gray; font-size: 10px;")
        footer_layout.addWidget(self.version_label, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        
        footer_layout.addStretch()
        
        # Discord & GitHub Buttons (Middle)
        self.discord_btn = QPushButton("Discord")
        self.discord_btn.setFixedWidth(80)
        self.discord_btn.setStyleSheet("background-color: #5865F2; color: white; font-weight: bold; font-size: 10px; border-radius: 4px;")
        self.discord_btn.clicked.connect(lambda: webbrowser.open("https://discord.voidremnants.com/"))
        
        self.github_btn = QPushButton("GitHub")
        self.github_btn.setFixedWidth(80)
        self.github_btn.setStyleSheet("background-color: #333; color: white; font-weight: bold; font-size: 10px; border-radius: 4px;")
        self.github_btn.clicked.connect(lambda: webbrowser.open("https://github.com/")) 
        
        footer_layout.addWidget(self.discord_btn)
        footer_layout.addWidget(self.github_btn)
        
        footer_layout.addStretch()
        
        # Help Button
        self.help_btn = QPushButton("?")
        self.help_btn.setFixedSize(22, 22)
        self.help_btn.setToolTip("Help / Info")
        self.help_btn.clicked.connect(self.show_help)
        footer_layout.addWidget(self.help_btn, alignment=Qt.AlignRight | Qt.AlignVCenter)
        
        self.main_layout.addLayout(footer_layout)

        self.setLayout(self.main_layout)
        
        self.v_timer = QTimer()
        self.v_timer.timeout.connect(self.update_ui_volume)
        self.v_timer.start(30)
        
        self.auto_load_last()
        self.show()

    def toggle_ontop_logic(self, checked):
        if checked and self.obs_check.isChecked():
            self.obs_check.blockSignals(True)
            self.obs_check.setChecked(False)
            self.obs_check.blockSignals(False)

    def toggle_obs_logic(self, checked):
        if checked and self.ontop_check.isChecked():
            self.ontop_check.blockSignals(True)
            self.ontop_check.setChecked(False)
            self.ontop_check.blockSignals(False)

    def show_help(self):
        help_topics = {
            "Audio Input": "Select your microphone. Use the progress bar to calibrate your voice level.",
            "OBS Mode Setup": "1. Enable OBS Mode.<br>2. Add 'Window Capture' in OBS.<br>3. Target 'PetalTalk_Overlay_Window'.<br>4. Add a Chroma Key filter to remove the green background.",
            "Sensitivity": "The volume threshold required to trigger the 'Talking' state.",
            "Always on Top": "Stays visible over games. Incompatible with OBS Mode."
        }
        message = "<b>PetalTalk Guide</b><br><br>"
        for topic, description in help_topics.items():
            message += f"<b>{topic}:</b><br>{description}<br><br>"
        QMessageBox.information(self, "Help Information", message)

    def update_ui_volume(self):
        val = int(min(self.overlay.current_volume * 10, 100))
        self.vol_bar.setValue(val)
        color = "#2ecc71" if self.overlay.is_talking else "#e74c3c"
        self.vol_bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color}; }}")

    def browse_image(self, img_type):
        path, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            if img_type == "idle": self.idle_path_display.setText(path)
            else: self.talk_path_display.setText(path)
            self.apply()

    def start_test(self): self.overlay.manual_test = True; self.overlay.is_talking = True
    def stop_test(self): self.overlay.manual_test = False; self.overlay.is_talking = False

    def populate_mics(self):
        self.mic_dropdown.addItem("System Default", None)
        try:
            for i, dev in enumerate(sd.query_devices()):
                if dev['max_input_channels'] > 0: self.mic_dropdown.addItem(dev['name'], i)
        except Exception: pass

    def change_mic(self): self.overlay.start_audio_stream(self.mic_dropdown.currentData())

    def apply(self):
        try:
            self.overlay.current_size = int(self.size_in.text())
            self.overlay.threshold = float(self.sens_in.text())
            self.overlay.move(int(self.x_in.text()), int(self.y_in.text()))
            self.overlay.set_overlay_flags(self.ontop_check.isChecked(), self.obs_check.isChecked())
            self.overlay.set_images(self.idle_path_display.text(), self.talk_path_display.text())
        except Exception as e:
            print(f"Apply error: {e}")

    def load_all_presets(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f: return json.load(f)
            except: pass
        return {"presets": {}, "last_used": None}

    def update_preset_list(self):
        self.preset_dropdown.clear()
        self.preset_dropdown.addItems(self.presets["presets"].keys())

    def save_preset(self):
        name = self.new_preset_name.text().strip()
        if not name: return
        self.presets["presets"][name] = {
            "size": int(self.size_in.text()), "x": int(self.x_in.text()), "y": int(self.y_in.text()), 
            "sens": float(self.sens_in.text()), "ontop": self.ontop_check.isChecked(), "obs_mode": self.obs_check.isChecked(),
            "idle": self.idle_path_display.text(), "talk": self.talk_path_display.text()
        }
        self.presets["last_used"] = name
        with open(CONFIG_FILE, 'w') as f: json.dump(self.presets, f)
        self.update_preset_list()

    def delete_preset(self):
        name = self.preset_dropdown.currentText()
        if name in self.presets["presets"]:
            del self.presets["presets"][name]
            with open(CONFIG_FILE, 'w') as f: json.dump(self.presets, f)
            self.update_preset_list()

    def load_selected_preset(self):
        name = self.preset_dropdown.currentText()
        if name in self.presets["presets"]:
            p = self.presets["presets"][name]
            self.size_in.setText(str(p.get("size", 300)))
            self.x_in.setText(str(p.get("x", 0)))
            self.y_in.setText(str(p.get("y", 0)))
            self.sens_in.setText(str(p.get("sens", 0.1)))
            self.ontop_check.setChecked(p.get("ontop", True))
            self.obs_check.setChecked(p.get("obs_mode", False))
            self.idle_path_display.setText(p.get("idle", resource_path("idle.png")))
            self.talk_path_display.setText(p.get("talk", resource_path("talking.png")))
            self.apply()

    def auto_load_last(self):
        last = self.presets.get("last_used")
        if last and last in self.presets["presets"]:
            self.preset_dropdown.setCurrentText(last)
            self.load_selected_preset()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    overlay = PNGTuberOverlay()
    controls = ControlPanel(overlay)
    sys.exit(app.exec_())