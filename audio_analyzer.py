"""
Профессиональный спектральный DAW-аудиоанализатор и FFT-фильтр (PyQt6 + PyQtGraph)
"""
import os
import sys
sys.dont_write_bytecode = True
import numpy as np
import sounddevice as sd
from PyQt6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from core.defaults import AUDIO_PROFILE
from core.audio_engine import AudioEngine, LIMIT_FREQ_MIN, LIMIT_FREQ_MAX
from ui.custom_axes import CleanLogFrequencyAxis
from ui.viewboxes import FFTFilterViewBox, SpectrogramTimelineViewBox
from ui.styles import (
    apply_pg_dark_theme, create_clean_region, create_clean_2d_rect_item, create_timeline_cursor,
    SPINBOX_CLEAN_QSS, BTN_CYAN_QSS, BTN_GREEN_QSS, BTN_RED_QSS
)

# =======================================================
#           ДИНАМИЧЕСКИЕ НАСТРОЙКИ ИЗ CONFIGS.PY
# =======================================================
LOGS_DIR = os.path.join("results", "sensors_logs")

LIMIT_DB_MIN = AUDIO_PROFILE["limit_db_min"]
LIMIT_DB_MAX = AUDIO_PROFILE["limit_db_max"]
DEFAULT_DB_MIN = AUDIO_PROFILE["default_db_min"]
DEFAULT_DB_MAX = AUDIO_PROFILE["default_db_max"]

ISOLATE_FFT_ON_FILTER = AUDIO_PROFILE.get("isolate_fft_on_filter", 0)
# =======================================================

apply_pg_dark_theme()


class AudioAnalyzerPro(QtWidgets.QMainWindow):
    def __init__(self, audio_path: str):
        super().__init__()
        self.audio_path = audio_path
        self.setWindowTitle(f"Audition Spectral DAW & Frequency Filter — {os.path.basename(audio_path)}")
        self.resize(1400, 880)

        # Подключаем звуковой движок из core/
        self.engine = AudioEngine(audio_path)
        self.total_duration = self.engine.total_duration

        # Состояние графиков
        self.current_ymin = DEFAULT_DB_MIN
        self.current_ymax = DEFAULT_DB_MAX
        self.freq_scale_mode = "Log"

        # Матрица спектрограммы
        self.spec_db_matrix = None
        self.spec_f_min = LIMIT_FREQ_MIN
        self.spec_f_max = LIMIT_FREQ_MAX

        self.init_ui()
        self.calculate_and_render_spectrogram()

        # Таймер плейхеда (60 FPS)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_playhead)
        self.timer.start(16)

    def init_ui(self):
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 10, 15, 10)
        main_layout.setSpacing(10)

        # 1. Верхний график: Live FFT
        self.freq_axis = CleanLogFrequencyAxis(self, orientation='bottom')
        self.freq_axis.setLabel('Frequency', units='Hz')
        self.fft_vb = FFTFilterViewBox(self)
        self.plot_fft = pg.PlotWidget(viewBox=self.fft_vb, axisItems={'bottom': self.freq_axis})
        self.plot_fft.showGrid(x=True, y=True, alpha=0.3)
        self.plot_fft.setYRange(self.current_ymin, self.current_ymax)
        self.plot_fft.setLabel('left', 'Sound Pressure Level', units='dB')
        self.plot_fft.setLabel('bottom', 'Frequency', units='Hz')
        self.plot_fft.setTitle("<span style='color: #FFFFFF; font-size: 11pt;'><b>1. Real-time Acoustic Spectrum (Live FFT)</b></span>")

        self.fft_curve = self.plot_fft.plot(pen=pg.mkPen(color='#00E5FF', width=2))
        self.peak_scatter = self.plot_fft.plot(pen=None, symbol='x', symbolSize=12, symbolPen=pg.mkPen('#FF3366', width=2.5))
        self.peak_text_items = []
        for _ in range(16):
            txt = pg.TextItem("", color='#FF3366', anchor=(0.5, 1.2))
            txt.setFont(QtGui.QFont("Segoe UI", 9, QtGui.QFont.Weight.Bold))
            self.plot_fft.addItem(txt)
            self.peak_text_items.append(txt)

        self.plot_fft.setXRange(np.log10(LIMIT_FREQ_MIN), np.log10(LIMIT_FREQ_MAX), padding=0)
        main_layout.addWidget(self.plot_fft, stretch=5)

        # 2. Нижний график: 2D-Спектрограмма (на всю ширину)
        self.spec_vb = SpectrogramTimelineViewBox(self)
        self.plot_spec = pg.PlotWidget(viewBox=self.spec_vb)
        self.plot_spec.showGrid(x=True, y=True, alpha=0.3)
        self.plot_spec.setLabel('left', 'Frequency', units='Hz')
        self.plot_spec.setLabel('bottom', 'Time', units='s')
        self.plot_spec.setTitle("<span style='color: #FFFFFF; font-size: 11pt;'><b>2. 2D Spectrogram Timeline</b></span>")
        
        self.img_overview = pg.ImageItem()
        self.img_overview.setZValue(1)
        self.plot_spec.addItem(self.img_overview)

        self.img_highres = pg.ImageItem()
        self.img_highres.setZValue(2)
        self.plot_spec.addItem(self.img_highres)

        self.cursor_line = create_timeline_cursor()
        self.plot_spec.addItem(self.cursor_line, ignoreBounds=True)
        main_layout.addWidget(self.plot_spec, stretch=5)

        # 3. Нижняя панель управления
        controls_layout = QtWidgets.QHBoxLayout()
        controls_layout.setSpacing(12)

        self.btn_play = QtWidgets.QPushButton("▶ Play")
        self.btn_play.setFixedSize(90, 36)
        self.btn_play.setStyleSheet(BTN_GREEN_QSS)
        self.btn_play.clicked.connect(self.toggle_play)
        controls_layout.addWidget(self.btn_play)

        self.btn_render = QtWidgets.QPushButton("Render View")
        self.btn_render.setFixedSize(110, 36)
        self.btn_render.setStyleSheet(BTN_GREEN_QSS)
        self.btn_render.clicked.connect(self.render_current_view)
        controls_layout.addWidget(self.btn_render)

        self.btn_scale = QtWidgets.QPushButton("Scale: Log")
        self.btn_scale.setFixedSize(100, 36)
        self.btn_scale.setStyleSheet(BTN_CYAN_QSS)
        self.btn_scale.clicked.connect(self.toggle_freq_scale)
        controls_layout.addWidget(self.btn_scale)

        lbl_boost = QtWidgets.QLabel("Boost:")
        lbl_boost.setStyleSheet("color: white; font-weight: bold;")
        controls_layout.addWidget(lbl_boost)

        self.spin_boost = QtWidgets.QDoubleSpinBox()
        self.spin_boost.setRange(0, 100)
        self.spin_boost.setValue(self.engine.boost_db)
        self.spin_boost.setSingleStep(5)
        self.spin_boost.setSuffix(" dB")
        self.spin_boost.setStyleSheet(SPINBOX_CLEAN_QSS)
        self.spin_boost.valueChanged.connect(self.on_boost_changed)
        controls_layout.addWidget(self.spin_boost)

        controls_layout.addSpacing(10)

        lbl_ymin = QtWidgets.QLabel("Y Min:")
        lbl_ymin.setStyleSheet("color: white;")
        controls_layout.addWidget(lbl_ymin)

        self.spin_ymin = QtWidgets.QSpinBox()
        self.spin_ymin.setRange(int(LIMIT_DB_MIN), int(LIMIT_DB_MAX))
        self.spin_ymin.setValue(int(DEFAULT_DB_MIN))
        self.spin_ymin.setStyleSheet(SPINBOX_CLEAN_QSS)
        self.spin_ymin.valueChanged.connect(self.on_yrange_changed)
        controls_layout.addWidget(self.spin_ymin)

        lbl_ymax = QtWidgets.QLabel("Y Max:")
        lbl_ymax.setStyleSheet("color: white;")
        controls_layout.addWidget(lbl_ymax)

        self.spin_ymax = QtWidgets.QSpinBox()
        self.spin_ymax.setRange(int(LIMIT_DB_MIN), int(LIMIT_DB_MAX))
        self.spin_ymax.setValue(int(DEFAULT_DB_MAX))
        self.spin_ymax.setStyleSheet(SPINBOX_CLEAN_QSS)
        self.spin_ymax.valueChanged.connect(self.on_yrange_changed)
        controls_layout.addWidget(self.spin_ymax)

        controls_layout.addStretch()

        self.lbl_telemetry_status = QtWidgets.QLabel("Hover over charts to inspect coordinates...")
        self.lbl_telemetry_status.setStyleSheet("color: #888888; font-style: italic; font-size: 8.5pt;")
        controls_layout.addWidget(self.lbl_telemetry_status)

        main_layout.addLayout(controls_layout)

    def calculate_and_render_spectrogram(self):
        Sxx_db, f_min, f_max = self.engine.render_spectrogram_slice(0.0, self.total_duration)
        if Sxx_db is not None:
            self.spec_db_matrix = Sxx_db
            self.spec_f_min = f_min
            self.spec_f_max = f_max

            colormap = pg.colormap.get('inferno')
            self._spec_lut = colormap.getLookupTable(0.0, 1.0, 256)
            self.img_overview.setLookupTable(self._spec_lut)
            self.img_highres.setLookupTable(self._spec_lut)

            self.spec_min_v, self.spec_max_v = np.percentile(Sxx_db, [5, 99.5])
            self.img_overview.setImage(Sxx_db.T, levels=[self.spec_min_v, self.spec_max_v])
            self.img_overview.setRect(QtCore.QRectF(0, f_min, self.total_duration, f_max - f_min))
            self.plot_spec.setRange(xRange=[0, self.total_duration], yRange=[LIMIT_FREQ_MIN, LIMIT_FREQ_MAX], padding=0)
            
            self.cursor_line.setPos(0.0)
            self.compute_and_draw_fft_at(0)

    def get_spec_db_at(self, t_sec: float, f_hz: float) -> float:
        """Делегирует расчет dB в точку (t, f) единому движку AudioEngine"""
        return self.engine.get_db_at_time_and_freq(t_sec, f_hz)

    def render_current_view(self):
        x_range = self.plot_spec.plotItem.vb.viewRange()[0]
        t_start, t_end = max(0.0, x_range[0]), min(self.total_duration, x_range[1])
        span = t_end - t_start

        Sxx_db, f_min, f_max = self.engine.render_spectrogram_slice(t_start, t_end)
        if Sxx_db is not None:
            self.img_highres.setImage(Sxx_db.T, levels=[self.spec_min_v, self.spec_max_v])
            self.img_highres.setRect(QtCore.QRectF(t_start, f_min, span, f_max - f_min))
            print(f"[OK] High-Res view rendered for: {t_start:.2f}s - {t_end:.2f}s (Span: {span:.2f}s)")

    def toggle_freq_scale(self):
        if self.freq_scale_mode == "Log":
            self.freq_scale_mode = "Linear"
            self.btn_scale.setText("Scale: Linear")
            self.plot_fft.setXRange(LIMIT_FREQ_MIN, LIMIT_FREQ_MAX, padding=0)
        else:
            self.freq_scale_mode = "Log"
            self.btn_scale.setText("Scale: Log")
            self.plot_fft.setXRange(np.log10(LIMIT_FREQ_MIN), np.log10(LIMIT_FREQ_MAX), padding=0)
        
        with self.engine.filter_lock:
            for filt in self.engine.active_filters:
                x_min = np.log10(filt['f_min']) if self.freq_scale_mode == "Log" else filt['f_min']
                x_max = np.log10(filt['f_max']) if self.freq_scale_mode == "Log" else filt['f_max']
                filt['top_item'].setRegion([x_min, x_max])

        self.compute_and_draw_fft_at(self.engine.current_sample_idx)

    def add_filter_from_fft(self, f_min, f_max, x_min, x_max):
        top_region = create_clean_region(x_min, x_max)
        self.plot_fft.addItem(top_region, ignoreBounds=True)

        bot_rect = create_clean_2d_rect_item(QtCore.QRectF(0, f_min, self.total_duration, f_max - f_min))
        self.plot_spec.addItem(bot_rect, ignoreBounds=True)

        filter_entry = {
            't_min': None, 't_max': None,
            'f_min': f_min, 'f_max': f_max,
            'top_item': top_region, 'bottom_item': bot_rect
        }

        with self.engine.filter_lock:
            self.engine.active_filters.append(filter_entry)

        self.compute_and_draw_fft_at(self.engine.current_sample_idx)
        print(f"[FILTER ACTIVE] Frequency Band: {f_min:.0f} Hz - {f_max:.0f} Hz (All Time)")

    def add_2d_spectrogram_filter(self, t_min, t_max, f_min, f_max):
        bot_rect = create_clean_2d_rect_item(QtCore.QRectF(t_min, f_min, t_max - t_min, f_max - f_min))
        self.plot_spec.addItem(bot_rect, ignoreBounds=True)

        x_min = np.log10(f_min) if self.freq_scale_mode == "Log" else f_min
        x_max = np.log10(f_max) if self.freq_scale_mode == "Log" else f_max
        top_region = create_clean_region(x_min, x_max)
        self.plot_fft.addItem(top_region, ignoreBounds=True)

        filter_entry = {
            't_min': t_min, 't_max': t_max,
            'f_min': f_min, 'f_max': f_max,
            'top_item': top_region, 'bottom_item': bot_rect
        }

        with self.engine.filter_lock:
            self.engine.active_filters.append(filter_entry)

        self.compute_and_draw_fft_at(self.engine.current_sample_idx)
        print(f"[FILTER ACTIVE] 2D Box: {t_min:.1f}s - {t_max:.1f}s | Freq: {f_min:.0f} Hz - {f_max:.0f} Hz")

    def remove_filter_at_pos(self, t_click, f_click, is_fft=False):
        target_idx = None
        with self.engine.filter_lock:
            for idx, filt in enumerate(self.engine.active_filters):
                f_match = (filt['f_min'] <= f_click <= filt['f_max'])
                if is_fft:
                    if f_match: target_idx = idx; break
                else:
                    t_min = 0.0 if filt['t_min'] is None else filt['t_min']
                    t_max = self.total_duration if filt['t_max'] is None else filt['t_max']
                    if f_match and (t_min <= t_click <= t_max):
                        target_idx = idx; break

        if target_idx is not None:
            with self.engine.filter_lock:
                removed_filt = self.engine.active_filters.pop(target_idx)
            self.plot_fft.removeItem(removed_filt['top_item'])
            self.plot_spec.removeItem(removed_filt['bottom_item'])
            self.compute_and_draw_fft_at(self.engine.current_sample_idx)
            print(f"[FILTER REMOVED] Area {removed_filt['f_min']:.0f} Hz - {removed_filt['f_max']:.0f} Hz deleted.")
        else:
            self.clear_all_filters()

    def clear_all_filters(self):
        with self.engine.filter_lock:
            filters_to_remove = list(self.engine.active_filters)
            self.engine.active_filters.clear()

        for filt in filters_to_remove:
            self.plot_fft.removeItem(filt['top_item'])
            self.plot_spec.removeItem(filt['bottom_item'])

        self.compute_and_draw_fft_at(self.engine.current_sample_idx)
        print("[FILTER] All filters cleared.")

    def seek_to_time(self, target_sec):
        self.engine.current_sample_idx = int(target_sec * self.engine.sample_rate)
        self.cursor_line.setPos(target_sec)
        self.compute_and_draw_fft_at(self.engine.current_sample_idx)

    def scrub_adaptive(self, direction):
        x_range = self.plot_spec.plotItem.vb.viewRange()[0]
        visible_span = max(0.05, x_range[1] - x_range[0])
        step_sec = visible_span * 0.018 * direction

        cur_sec = self.engine.current_sample_idx / self.engine.sample_rate
        target_sec = max(0.0, min(self.total_duration, cur_sec + step_sec))
        self.engine.current_sample_idx = int(target_sec * self.engine.sample_rate)
        self.cursor_line.setPos(target_sec)
        self.compute_and_draw_fft_at(self.engine.current_sample_idx)

        scrub_samples = int(min(0.08, visible_span * 0.1) * self.engine.sample_rate)
        scrub_samples = max(1024, scrub_samples)
        start_s = self.engine.current_sample_idx
        end_s = min(len(self.engine.audio_samples), start_s + scrub_samples)
        snippet = self.audio_samples[start_s:end_s]
        
        if len(snippet) > 0:
            gain = 10.0 ** (self.engine.boost_db / 20.0)
            preview = np.clip(snippet * gain, -1.0, 1.0)
            try:
                sd.play(preview, self.engine.sample_rate)
            except Exception:
                pass

    def compute_and_draw_fft_at(self, sample_idx):
        for txt in self.peak_text_items:
            txt.setText("")

        x_coords, valid_db, peak_xs, peak_ys, peak_labels = self.engine.compute_fft_at(
            sample_idx, self.freq_scale_mode, ISOLATE_FFT_ON_FILTER
        )

        if x_coords is not None:
            self.fft_curve.setData(x_coords, valid_db)
            self.peak_scatter.setData(peak_xs, peak_ys)

            for idx, (px, py, label) in enumerate(zip(peak_xs, peak_ys, peak_labels)):
                if idx < len(self.peak_text_items):
                    txt_item = self.peak_text_items[idx]
                    txt_item.setText(label)
                    txt_item.setPos(px, min(self.spin_ymax.value() - 1, py + 3))

    def update_playhead(self):
        if self.engine.is_playing:
            cur_sec = self.engine.current_sample_idx / self.engine.sample_rate
            self.cursor_line.setPos(cur_sec)
            self.compute_and_draw_fft_at(self.engine.current_sample_idx)

            if not self.engine.is_playing:
                self.btn_play.setText("▶ Play")
                self.btn_play.setStyleSheet(BTN_GREEN_QSS)

    def toggle_play(self):
        self.engine.is_playing = not self.engine.is_playing
        if self.engine.is_playing:
            self.btn_play.setText("❚❚ Pause")
            self.btn_play.setStyleSheet(BTN_RED_QSS)
        else:
            self.btn_play.setText("▶ Play")
            self.btn_play.setStyleSheet(BTN_GREEN_QSS)

    def on_boost_changed(self, val):
        self.engine.boost_db = float(val)

    def on_yrange_changed(self):
        self.plot_fft.setYRange(self.spin_ymin.value(), self.spin_ymax.value())

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_Space:
            self.toggle_play()
        elif event.key() == QtCore.Qt.Key.Key_Escape:
            self.clear_all_filters()
        elif event.key() == QtCore.Qt.Key.Key_Left:
            self.scrub_adaptive(-1)
        elif event.key() == QtCore.Qt.Key.Key_Right:
            self.scrub_adaptive(1)
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.engine.close()
        event.accept()


# =======================================================
#                      MAIN ENTRY
# =======================================================
if __name__ == '__main__':
    audio_files = [f for f in os.listdir(LOGS_DIR) if (f.endswith(".mp3") or f.endswith(".wav")) and f.startswith("audio_raw_")]
    if not audio_files:
        print(f"[ERROR] No audio recordings found in '{LOGS_DIR}'!")
        sys.exit(1)

    print("="*65)
    print("      AUDITION-STYLE SPECTRAL DAW & FILTER SUITE      ")
    print("="*65)
    for idx, f in enumerate(audio_files):
        print(f" [{idx + 1}] {f}")
    print("="*65)

    choice = input("Select audio recording to analyze (default 1): ").strip()
    file_idx = int(choice) - 1 if choice.isdigit() and 1 <= int(choice) <= len(audio_files) else 0

    selected_audio = audio_files[file_idx]
    audio_path = os.path.join(LOGS_DIR, selected_audio)

    app = QtWidgets.QApplication(sys.argv)
    window = AudioAnalyzerPro(audio_path)
    window.show()
    sys.exit(app.exec())