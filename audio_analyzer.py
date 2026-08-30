import os
import sys
import numpy as np
import scipy.signal as signal
import sounddevice as sd
import soundfile as sf
import threading

from PyQt6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

# =======================================================
#               GLOBAL CONFIGURATION & LIMITS
# =======================================================
LOGS_DIR = os.path.join("results", "sensors_logs")

# Бюджет колонок спектрограммы на экран
TARGET_SPEC_WIDTH = 10000

# Глобальные границы анализатора
LIMIT_FREQ_MIN = 20.0       # Hz
LIMIT_FREQ_MAX = 8000.0    # Hz (20 kHz)
LIMIT_DB_MIN   = -50.0      # dB
LIMIT_DB_MAX   = 200.0      # dB

DEFAULT_DB_MIN = -10.0      # dB
DEFAULT_DB_MAX = 50.0       # dB

# 1 = Скрывать на FFT-графике всё за пределами выделенных областей
# 0 = Показывать полный спектр FFT независимо от выделения
ISOLATE_FFT_ON_FILTER = 0
# =======================================================

pg.setConfigOptions(antialias=True, useOpenGL=True)
pg.setConfigOption('background', '#0E0E0E')
pg.setConfigOption('foreground', '#FFFFFF')

# Логарифмическая шкала частот
class CleanLogFrequencyAxis(pg.AxisItem):
    def __init__(self, analyzer_ref, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.analyzer = analyzer_ref

    def tickValues(self, minVal, maxVal, size):
        ticks_hz = [20, 50, 100, 200, 500, 1000, 2000, 3000, 5000, 8000, 10000, 15000, 20000]
        if hasattr(self, 'analyzer') and self.analyzer.freq_scale_mode == "Linear":
            vals = [float(hz) for hz in ticks_hz if minVal <= float(hz) <= maxVal]
            return [(1.0, vals)]
        else:
            log_vals = [float(np.log10(hz)) for hz in ticks_hz if minVal <= np.log10(hz) <= maxVal]
            return [(1.0, log_vals)]

    def tickStrings(self, values, scale, spacing):
        strings = []
        is_lin = hasattr(self, 'analyzer') and self.analyzer.freq_scale_mode == "Linear"
        for val in values:
            hz = float(val) if is_lin else (10.0 ** val)
            if hz >= 1000:
                k_val = hz / 1000.0
                strings.append(f"{k_val:.0f}k" if k_val.is_integer() else f"{k_val:.1f}k")
            else:
                strings.append(f"{hz:.0f}")
        return strings

# 1. Верхний ViewBox FFT
class FFTFilterViewBox(pg.ViewBox):
    def __init__(self, analyzer_ref, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.analyzer = analyzer_ref
        self.temp_region = None
        self.panning_data = None
        self.setMouseMode(pg.ViewBox.RectMode)

    def mouseClickEvent(self, ev):
        # Одиночный клик ПКМ -> удаление фильтра под курсором или сброс всех
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            pos = self.mapToView(ev.pos())
            x_val = pos.x()
            f_click = (10.0 ** x_val) if self.analyzer.freq_scale_mode == "Log" else x_val
            self.analyzer.remove_filter_at_pos(t_click=None, f_click=f_click, is_fft=True)
            ev.accept()
        else:
            ev.accept()

    def mousePressEvent(self, ev):
        # Нажатие СКМ (Колесико) -> начало панорамирования
        if ev.button() == QtCore.Qt.MouseButton.MiddleButton:
            ev.accept()
            self.panning_data = {
                'start_pos': ev.scenePos(),
                'start_x_range': self.viewRange()[0],
                'start_y_range': self.viewRange()[1]
            }
        else:
            super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == QtCore.Qt.MouseButton.MiddleButton:
            ev.accept()
            self.panning_data = None
        else:
            super().mouseReleaseEvent(ev)

    def mouseMoveEvent(self, ev):
        if self.panning_data is not None:
            ev.accept()
            delta = ev.scenePos() - self.panning_data['start_pos']
            
            # Pan по X (Частоты) с сохранением точного span_x
            vr_x = self.panning_data['start_x_range']
            span_x = vr_x[1] - vr_x[0]
            dx = -delta.x() / max(1, self.width()) * span_x
            new_min_x = vr_x[0] + dx
            self.setXRange(new_min_x, new_min_x + span_x, padding=0)

            # Pan по Y (dB) с сохранением точного span_y
            vr_y = self.panning_data['start_y_range']
            span_y = vr_y[1] - vr_y[0]
            dy = (delta.y() / max(1, self.height())) * span_y
            new_min_y = vr_y[0] + dy
            self.setYRange(new_min_y, new_min_y + span_y, padding=0)

            self.clamp_view()
        else:
            super().mouseMoveEvent(ev)

    def mouseDragEvent(self, ev, axis=None):
        # ПКМ + Drag -> Рисование частотной полосы
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            ev.accept()
            modifiers = QtWidgets.QApplication.keyboardModifiers()

            if ev.isStart():
                if not (modifiers & QtCore.Qt.KeyboardModifier.ControlModifier):
                    self.analyzer.clear_all_filters()

                p1 = self.mapToView(ev.buttonDownPos())
                self.temp_region = self.analyzer.create_clean_region(p1.x(), p1.x())
                self.addItem(self.temp_region, ignoreBounds=True)

            if self.temp_region is not None:
                p1 = self.mapToView(ev.buttonDownPos())
                p2 = self.mapToView(ev.pos())
                x_min = min(p1.x(), p2.x())
                x_max = max(p1.x(), p2.x())
                self.temp_region.setRegion([x_min, x_max])

            if ev.isFinish():
                if self.temp_region is not None:
                    r_min, r_max = self.temp_region.getRegion()
                    self.removeItem(self.temp_region)
                    self.temp_region = None

                    if (r_max - r_min) > 0.01:
                        if self.analyzer.freq_scale_mode == "Log":
                            f_min = 10.0 ** r_min
                            f_max = 10.0 ** r_max
                        else:
                            f_min = r_min
                            f_max = r_max
                        self.analyzer.add_filter_from_fft(f_min, f_max, r_min, r_max)
        else:
            ev.ignore()

    def wheelEvent(self, ev, axis=None):
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        delta = ev.delta()
        mouse_pos = self.mapToView(ev.pos())

        is_alt   = bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier)
        is_shift = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier)

        SCROLL_SPEED_X = 0.04

        # 1. ALT + Wheel -> Зум частот (X)
        if is_alt:
            scale = 0.82 if delta > 0 else 1.22
            self.scaleBy(x=scale, y=1.0, center=mouse_pos)
            self.clamp_view()
            ev.accept()

        # 2. SHIFT + Wheel -> Зум dB (Y)
        elif is_shift:
            scale = 0.82 if delta > 0 else 1.22
            self.scaleBy(x=1.0, y=scale, center=mouse_pos)
            self.clamp_view()
            ev.accept()

        # 3. Просто колесико -> Скролл Влево / Вправо (Частоты)
        else:
            x_range = self.viewRange()[0]
            span_x = x_range[1] - x_range[0]
            shift_x = span_x * SCROLL_SPEED_X * (-1 if delta > 0 else 1)
            if self.analyzer.freq_scale_mode == "Log":
                min_lim, max_lim = np.log10(LIMIT_FREQ_MIN), np.log10(LIMIT_FREQ_MAX)
            else:
                min_lim, max_lim = LIMIT_FREQ_MIN, LIMIT_FREQ_MAX
            new_xmin = max(min_lim, x_range[0] + shift_x)
            new_xmax = min(max_lim, new_xmin + span_x)
            if new_xmax >= max_lim:
                new_xmax = max_lim
                new_xmin = max(min_lim, max_lim - span_x)
            self.setXRange(new_xmin, new_xmax, padding=0)
            self.clamp_view()
            ev.accept()

    def clamp_view(self):
        x_range = self.viewRange()[0]
        y_range = self.viewRange()[1]
        span_x = x_range[1] - x_range[0]
        span_y = y_range[1] - y_range[0]

        # Лимиты X
        if self.analyzer.freq_scale_mode == "Log":
            min_x, max_x = np.log10(LIMIT_FREQ_MIN), np.log10(LIMIT_FREQ_MAX)
        else:
            min_x, max_x = LIMIT_FREQ_MIN, LIMIT_FREQ_MAX

        total_x = max_x - min_x
        if span_x >= total_x:
            clamped_xmin, clamped_xmax = min_x, max_x
        else:
            clamped_xmin = max(min_x, x_range[0])
            clamped_xmax = clamped_xmin + span_x
            if clamped_xmax >= max_x:
                clamped_xmax = max_x
                clamped_xmin = max(min_x, max_x - span_x)

        # Лимиты Y
        bound_ymin = float(self.analyzer.spin_ymin.value())
        bound_ymax = float(self.analyzer.spin_ymax.value())
        total_y = bound_ymax - bound_ymin

        if span_y >= total_y:
            clamped_ymin, clamped_ymax = bound_ymin, bound_ymax
        else:
            clamped_ymin = max(bound_ymin, y_range[0])
            clamped_ymax = clamped_ymin + span_y
            if clamped_ymax >= bound_ymax:
                clamped_ymax = bound_ymax
                clamped_ymin = max(bound_ymin, bound_ymax - span_y)

        self.setRange(xRange=[clamped_xmin, clamped_xmax], yRange=[clamped_ymin, clamped_ymax], padding=0)

# 2. Нижний ViewBox Спектрограммы
class SpectrogramTimelineViewBox(pg.ViewBox):
    def __init__(self, analyzer_ref, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.analyzer = analyzer_ref
        self.setMouseMode(pg.ViewBox.RectMode)
        self.drag_start = None
        self.temp_box_item = None
        self.panning_data = None

    def mouseClickEvent(self, ev):
        # Клик ПКМ -> Точечное удаление фильтра или полный сброс
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            pos = self.mapToView(ev.pos())
            self.analyzer.remove_filter_at_pos(t_click=pos.x(), f_click=pos.y(), is_fft=False)
            ev.accept()
        # Клик ЛКМ -> Перемещение курсора времени
        elif ev.button() == QtCore.Qt.MouseButton.LeftButton:
            mouse_pos = self.mapToView(ev.pos())
            target_sec = max(0.0, min(self.analyzer.total_duration, mouse_pos.x()))
            self.analyzer.seek_to_time(target_sec)
            ev.accept()
        else:
            ev.accept()

    def mousePressEvent(self, ev):
        # Нажатие СКМ (Колесико) -> начало панорамирования
        if ev.button() == QtCore.Qt.MouseButton.MiddleButton:
            ev.accept()
            self.panning_data = {
                'start_pos': ev.scenePos(),
                'start_x_range': self.viewRange()[0],
                'start_y_range': self.viewRange()[1]
            }
        else:
            super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == QtCore.Qt.MouseButton.MiddleButton:
            ev.accept()
            self.panning_data = None
        else:
            super().mouseReleaseEvent(ev)

    def mouseMoveEvent(self, ev):
        if self.panning_data is not None:
            ev.accept()
            delta = ev.scenePos() - self.panning_data['start_pos']
            
            # Pan по X (Время) с сохранением точного span_x
            vr_x = self.panning_data['start_x_range']
            span_x = vr_x[1] - vr_x[0]
            dx = -delta.x() / max(1, self.width()) * span_x
            new_min_x = vr_x[0] + dx
            self.setXRange(new_min_x, new_min_x + span_x, padding=0)

            # Pan по Y (Частоты) с сохранением точного span_y
            vr_y = self.panning_data['start_y_range']
            span_y = vr_y[1] - vr_y[0]
            dy = (delta.y() / max(1, self.height())) * span_y
            new_min_y = vr_y[0] + dy
            self.setYRange(new_min_y, new_min_y + span_y, padding=0)

            self.clamp_view()
        else:
            super().mouseMoveEvent(ev)

    def mouseDragEvent(self, ev, axis=None):
        # 1. ЛКМ -> Скраббинг курсора времени
        if ev.button() == QtCore.Qt.MouseButton.LeftButton:
            ev.accept()
            mouse_pos = self.mapToView(ev.pos())
            target_sec = max(0.0, min(self.analyzer.total_duration, mouse_pos.x()))
            self.analyzer.seek_to_time(target_sec)

        # 2. ПКМ -> Рисование 2D области выделения Time x Freq
        elif ev.button() == QtCore.Qt.MouseButton.RightButton:
            ev.accept()
            modifiers = QtWidgets.QApplication.keyboardModifiers()

            # Начало рисования
            if ev.isStart():
                self.drag_start = self.mapToView(ev.buttonDownPos())
                if not (modifiers & QtCore.Qt.KeyboardModifier.ControlModifier):
                    self.analyzer.clear_all_filters()

                self.temp_box_item = QtWidgets.QGraphicsRectItem()
                self.temp_box_item.setPen(QtGui.QPen(QtCore.Qt.PenStyle.NoPen))
                self.temp_box_item.setBrush(pg.mkBrush(255, 255, 255, 120))
                self.temp_box_item.setZValue(15)
                self.addItem(self.temp_box_item, ignoreBounds=True)

            p1 = self.mapToView(ev.buttonDownPos())
            p2 = self.mapToView(ev.pos())
            t_min = min(p1.x(), p2.x())
            t_max = max(p1.x(), p2.x())
            f_min = min(p1.y(), p2.y())
            f_max = max(p1.y(), p2.y())

            if self.temp_box_item is not None:
                self.temp_box_item.setRect(QtCore.QRectF(t_min, f_min, t_max - t_min, f_max - f_min))

            # Конец рисования
            if ev.isFinish():
                if self.temp_box_item is not None:
                    self.removeItem(self.temp_box_item)
                    self.temp_box_item = None

                if (t_max - t_min) > 0.05 and (f_max - f_min) > 20:
                    self.analyzer.add_2d_spectrogram_filter(t_min, t_max, f_min, f_max)
                self.drag_start = None
        else:
            ev.ignore()

    def wheelEvent(self, ev, axis=None):
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        delta = ev.delta()
        mouse_pos = self.mapToView(ev.pos())

        is_alt   = bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier)
        is_shift = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier)

        SCROLL_SPEED_X = 0.04

        # 1. ALT + Wheel -> Зум времени X
        if is_alt:
            scale = 0.82 if delta > 0 else 1.22
            self.scaleBy(x=scale, y=1.0, center=mouse_pos)
            self.clamp_view()
            ev.accept()

        # 2. SHIFT + Wheel -> Зум частот Y
        elif is_shift:
            scale = 0.82 if delta > 0 else 1.22
            self.scaleBy(x=1.0, y=scale, center=mouse_pos)
            self.clamp_view()
            ev.accept()

        # 3. Просто Колесико -> Скролл Влево / Вправо по времени (X)
        else:
            x_range = self.viewRange()[0]
            span_x = x_range[1] - x_range[0]

            if span_x < (self.analyzer.total_duration - 0.05):
                shift_x = span_x * SCROLL_SPEED_X * (-1 if delta > 0 else 1)
                new_min = x_range[0] + shift_x
                new_max = x_range[1] + shift_x

                if new_min < 0.0:
                    new_min = 0.0
                    new_max = span_x
                elif new_max > self.analyzer.total_duration:
                    new_max = self.analyzer.total_duration
                    new_min = max(0.0, self.analyzer.total_duration - span_x)

                self.setXRange(new_min, new_max, padding=0)
                self.clamp_view()
            ev.accept()

    def clamp_view(self):
        x_range = self.viewRange()[0]
        y_range = self.viewRange()[1]
        span_x = x_range[1] - x_range[0]
        span_y = y_range[1] - y_range[0]

        # Лимиты X (Время)
        t_max = self.analyzer.total_duration
        if span_x >= t_max:
            clamped_xmin, clamped_xmax = 0.0, t_max
        else:
            clamped_xmin = max(0.0, x_range[0])
            clamped_xmax = clamped_xmin + span_x
            if clamped_xmax >= t_max:
                clamped_xmax = t_max
                clamped_xmin = max(0.0, t_max - span_x)

        # Лимиты Y (Частоты)
        total_freq = LIMIT_FREQ_MAX - LIMIT_FREQ_MIN
        if span_y >= total_freq:
            clamped_ymin, clamped_ymax = LIMIT_FREQ_MIN, LIMIT_FREQ_MAX
        else:
            clamped_ymin = max(LIMIT_FREQ_MIN, y_range[0])
            clamped_ymax = clamped_ymin + span_y
            if clamped_ymax >= LIMIT_FREQ_MAX:
                clamped_ymax = LIMIT_FREQ_MAX
                clamped_ymin = max(LIMIT_FREQ_MIN, LIMIT_FREQ_MAX - span_y)

        self.setRange(xRange=[clamped_xmin, clamped_xmax], yRange=[clamped_ymin, clamped_ymax], padding=0)
        
class AudioAnalyzerPro(QtWidgets.QMainWindow):
    def __init__(self, audio_path):
        super().__init__()
        self.audio_path = audio_path
        self.setWindowTitle(f"Audition Spectral DAW & Frequency Filter — {os.path.basename(audio_path)}")
        self.resize(1400, 880)

        # Чтение аудио
        data, self.sample_rate = sf.read(audio_path, dtype='float32')
        self.audio_samples = data[:, 0] if data.ndim > 1 else data
        self.total_duration = len(self.audio_samples) / self.sample_rate
        print(f"[AUDIO INFO] Sample Rate: {self.sample_rate} Hz | Max Physical Freq: {self.sample_rate / 2:.0f} Hz | Duration: {self.total_duration:.2f}s")

        # Состояние
        self.is_playing = False
        self.current_sample_idx = 0
        self.boost_db = 30.0
        self.fft_size = 4096

        self.current_ymin = DEFAULT_DB_MIN
        self.current_ymax = DEFAULT_DB_MAX
        self.freq_scale_mode = "Log"

        # Список активных фильтров и Lock для потокобезопасности
        self.active_filters = []
        self.filter_lock = threading.Lock()

        self.init_audio_stream()
        self.init_ui()
        self.calculate_and_render_spectrogram()

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_playhead)
        self.timer.start(16)

    def create_clean_region(self, min_val, max_val):
        """Создает вертикальную полосу без желтых краев с альфой ~0.35"""
        region = pg.LinearRegionItem(
            values=[min_val, max_val],
            orientation='vertical',
            brush=pg.mkBrush(255, 255, 255, 90),  # Белый полупрозрачный (~0.35)
            pen=pg.mkPen(None),
            hoverPen=pg.mkPen(None),
            movable=False
        )
        # Отключаем линии по краям, которые PyQtGraph красит в желтый цвет
        for line in region.lines:
            line.setPen(pg.mkPen(None))
            line.setHoverPen(pg.mkPen(None))
        return region

    def init_audio_stream(self):
        self._block_size = 1024
        # Состояния IIR-фильтров для бесшовной склейки блоков без треска
        self._filter_states = {}

        def get_bandpass_sos(f_low, f_high):
            """Создает стабильный Bandpass фильтр Баттерворта 4-го порядка"""
            nyq = self.sample_rate / 2.0
            low = max(20.0, float(f_low))
            high = min(nyq - 50.0, float(f_high))
            
            # Защита от вырожденных границ
            if low >= high:
                low = max(20.0, high - 50.0)

            w_low = low / nyq
            w_high = min(0.999, high / nyq)
            
            if w_low >= w_high:
                w_low = max(0.001, w_high - 0.01)

            return signal.butter(4, [w_low, w_high], btype='bandpass', output='sos')

        def audio_callback(outdata, frames, time_info, status):
            if not self.is_playing:
                outdata.fill(0)
                self._filter_states.clear()
                return

            try:
                start_idx = self.current_sample_idx
                end_idx = start_idx + frames
                total_len = len(self.audio_samples)

                if start_idx >= total_len:
                    outdata.fill(0)
                    self.is_playing = False
                    self.current_sample_idx = 0
                    self._filter_states.clear()
                    return

                if end_idx > total_len:
                    actual_chunk = self.audio_samples[start_idx:total_len]
                    chunk_raw = np.zeros(frames, dtype=np.float32)
                    chunk_raw[:len(actual_chunk)] = actual_chunk
                    self.current_sample_idx = 0
                    self.is_playing = False
                else:
                    chunk_raw = self.audio_samples[start_idx:end_idx].copy()
                    self.current_sample_idx = end_idx

                gain = float(10.0 ** (self.boost_db / 20.0))

                # Проверяем активные фильтры
                with self.filter_lock:
                    num_filters = len(self.active_filters)
                    active_bands = []
                    if num_filters > 0:
                        cur_t = start_idx / self.sample_rate
                        for filt in self.active_filters:
                            t_min, t_max = filt['t_min'], filt['t_max']
                            if t_min is None or (t_min <= cur_t <= t_max):
                                active_bands.append((int(filt['f_min']), int(filt['f_max'])))

                # 1. Режим оригинала без фильтров
                if num_filters == 0:
                    self._filter_states.clear()
                    outdata[:, 0] = np.clip(chunk_raw * gain, -1.0, 1.0)
                    return

                # 2. Фильтры есть, но курсор вне зоны времени -> тишина
                if not active_bands:
                    outdata.fill(0)
                    self._filter_states.clear()
                    return

                # 3. Фильтрация через гладкий IIR (SOS) без треска и кликов
                accumulated = np.zeros(frames, dtype=np.float32)

                # Удаляем устаревшие состояния фильтров
                active_keys = set(active_bands)
                dead_keys = [k for k in self._filter_states if k not in active_keys]
                for k in dead_keys:
                    del self._filter_states[k]

                for f_min, f_max in active_bands:
                    band_key = (f_min, f_max)
                    if band_key not in self._filter_states:
                        try:
                            sos = get_bandpass_sos(f_min, f_max)
                            zi = signal.sosfilt_zi(sos) * chunk_raw[0]
                            self._filter_states[band_key] = {'sos': sos, 'zi': zi}
                        except Exception:
                            continue

                    filt_data = self._filter_states[band_key]
                    filtered_band, filt_data['zi'] = signal.sosfilt(filt_data['sos'], chunk_raw, zi=filt_data['zi'])
                    accumulated += filtered_band.astype(np.float32)

                outdata[:, 0] = np.clip(accumulated * gain, -1.0, 1.0)

            except Exception:
                outdata.fill(0)

        self.stream = sd.OutputStream(
            channels=1,
            samplerate=self.sample_rate,
            blocksize=self._block_size,
            dtype='float32',
            callback=audio_callback
        )
        self.stream.start()

    def init_ui(self):
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 10, 15, 10)
        main_layout.setSpacing(10)

        # 1. Верхний график FFT
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
        for _ in range(16): # Пул до 16 одновременных зон
            txt = pg.TextItem("", color='#FF3366', anchor=(0.5, 1.2))
            txt.setFont(QtGui.QFont("Segoe UI", 9, QtGui.QFont.Weight.Bold))
            self.plot_fft.addItem(txt)
            self.peak_text_items.append(txt)
        self.plot_fft.setXRange(np.log10(LIMIT_FREQ_MIN), np.log10(LIMIT_FREQ_MAX), padding=0)

        main_layout.addWidget(self.plot_fft, stretch=5)

        # 2. Нижний график Спектрограммы
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

        # Яркий, поверх всех слоев курсор времени
        self.cursor_line = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            movable=False,
            pen=pg.mkPen(color='#00FFFF', width=2.5, style=QtCore.Qt.PenStyle.SolidLine)
        )
        self.cursor_line.setZValue(100) # Максимальный ZValue, поверх спектрограммы и выделений
        self.plot_spec.addItem(self.cursor_line, ignoreBounds=True)
        main_layout.addWidget(self.plot_spec, stretch=5)

        # 3. Нижняя панель управления
        controls_layout = QtWidgets.QHBoxLayout()
        controls_layout.setSpacing(12)

        self.btn_play = QtWidgets.QPushButton("▶ Play")
        self.btn_play.setFixedSize(90, 36)
        self.btn_play.setStyleSheet("background-color: #1E1E1E; color: #33FF57; font-size: 12pt; font-weight: bold; border-radius: 4px; border: 1px solid #333;")
        self.btn_play.clicked.connect(self.toggle_play)
        controls_layout.addWidget(self.btn_play)

        self.btn_render = QtWidgets.QPushButton("Render View")
        self.btn_render.setFixedSize(110, 36)
        self.btn_render.setStyleSheet("background-color: #1E1E1E; color: #33FF57; font-size: 10pt; font-weight: bold; border-radius: 4px; border: 1px solid #333;")
        self.btn_render.clicked.connect(self.render_current_view)
        controls_layout.addWidget(self.btn_render)

        self.btn_scale = QtWidgets.QPushButton("Scale: Log")
        self.btn_scale.setFixedSize(100, 36)
        self.btn_scale.setStyleSheet("background-color: #1E1E1E; color: #00E5FF; font-size: 10pt; font-weight: bold; border-radius: 4px; border: 1px solid #333;")
        self.btn_scale.clicked.connect(self.toggle_freq_scale)
        controls_layout.addWidget(self.btn_scale)

        lbl_boost = QtWidgets.QLabel("Boost:")
        lbl_boost.setStyleSheet("color: white; font-weight: bold;")
        controls_layout.addWidget(lbl_boost)

        self.spin_boost = QtWidgets.QDoubleSpinBox()
        self.spin_boost.setRange(0, 100)
        self.spin_boost.setValue(self.boost_db)
        self.spin_boost.setSingleStep(5)
        self.spin_boost.setSuffix(" dB")
        self.spin_boost.setStyleSheet("background-color: #1E1E1E; color: #00E5FF; font-weight: bold; padding: 4px; border: 1px solid #333;")
        self.spin_boost.valueChanged.connect(self.on_boost_changed)
        controls_layout.addWidget(self.spin_boost)

        controls_layout.addSpacing(10)

        lbl_ymin = QtWidgets.QLabel("Y Min:")
        lbl_ymin.setStyleSheet("color: white;")
        controls_layout.addWidget(lbl_ymin)

        self.spin_ymin = QtWidgets.QSpinBox()
        self.spin_ymin.setRange(int(LIMIT_DB_MIN), int(LIMIT_DB_MAX))
        self.spin_ymin.setValue(int(DEFAULT_DB_MIN))
        self.spin_ymin.setStyleSheet("background-color: #1E1E1E; color: #00E5FF; padding: 4px; border: 1px solid #333;")
        self.spin_ymin.valueChanged.connect(self.on_yrange_changed)
        controls_layout.addWidget(self.spin_ymin)

        lbl_ymax = QtWidgets.QLabel("Y Max:")
        lbl_ymax.setStyleSheet("color: white;")
        controls_layout.addWidget(lbl_ymax)

        self.spin_ymax = QtWidgets.QSpinBox()
        self.spin_ymax.setRange(int(LIMIT_DB_MIN), int(LIMIT_DB_MAX))
        self.spin_ymax.setValue(int(DEFAULT_DB_MAX))
        self.spin_ymax.setStyleSheet("background-color: #1E1E1E; color: #00E5FF; padding: 4px; border: 1px solid #333;")
        self.spin_ymax.valueChanged.connect(self.on_yrange_changed)
        controls_layout.addWidget(self.spin_ymax)

        controls_layout.addStretch()

        lbl_hint = QtWidgets.QLabel("Controls: [Left Click] Seek | [Middle Drag] Pan | [Alt+Wheel] Zoom X | [Shift+Wheel] Zoom Y | [Right Drag] Select | [Ctrl+Right Drag] Multi | [Right Click / Esc] Clear | [Space] Play")
        lbl_hint.setStyleSheet("color: #888888; font-style: italic;")
        controls_layout.addWidget(lbl_hint)

        main_layout.addLayout(controls_layout)

    def render_slice(self, t_start, t_end):
        s_idx = int(max(0.0, t_start) * self.sample_rate)
        e_idx = int(min(self.total_duration, t_end) * self.sample_rate)
        slice_audio = self.audio_samples[s_idx:e_idx]

        if len(slice_audio) < 128:
            return None, 0.0, LIMIT_FREQ_MAX

        span = max(0.05, t_end - t_start)
        nper = 1024 if span < 15 else 2048
        hop = max(16, len(slice_audio) // TARGET_SPEC_WIDTH)
        nov = max(0, nper - hop) if nper > hop else 0

        f_spec, t_spec, Sxx = signal.spectrogram(
            slice_audio,
            fs=self.sample_rate,
            nperseg=nper,
            noverlap=nov
        )
        # Фильтруем частоты в заданный диапазон [LIMIT_FREQ_MIN .. LIMIT_FREQ_MAX]
        mask = (f_spec >= LIMIT_FREQ_MIN) & (f_spec <= LIMIT_FREQ_MAX)
        if not np.any(mask):
            return None, LIMIT_FREQ_MIN, LIMIT_FREQ_MAX

        f_min_actual = float(f_spec[mask][0])
        f_max_actual = float(f_spec[mask][-1])

        Sxx_db = 10 * np.log10(Sxx[mask, :] + 1e-12)
        return Sxx_db, f_min_actual, f_max_actual

    def calculate_and_render_spectrogram(self):
        Sxx_db, f_min, f_max = self.render_slice(0.0, self.total_duration)
        if Sxx_db is not None:
            colormap = pg.colormap.get('inferno')
            self._spec_lut = colormap.getLookupTable(0.0, 1.0, 256)
            self.img_overview.setLookupTable(self._spec_lut)
            self.img_highres.setLookupTable(self._spec_lut)

            self.spec_min_v, self.spec_max_v = np.percentile(Sxx_db, [5, 99.5])
            self.img_overview.setImage(Sxx_db.T, levels=[self.spec_min_v, self.spec_max_v])
            self.img_overview.setRect(QtCore.QRectF(0, f_min, self.total_duration, f_max - f_min))
            self.plot_spec.setRange(xRange=[0, self.total_duration], yRange=[LIMIT_FREQ_MIN, LIMIT_FREQ_MAX], padding=0)
            
            # Принудительно ставим курсор на старт и строим начальный FFT
            self.cursor_line.setPos(0.0)
            self.compute_and_draw_fft_at(0)

    def render_current_view(self):
        x_range = self.plot_spec.plotItem.vb.viewRange()[0]
        t_start = max(0.0, x_range[0])
        t_end = min(self.total_duration, x_range[1])
        span = t_end - t_start

        Sxx_db, f_min, f_max = self.render_slice(t_start, t_end)
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
        
        # Обновляем позиции верхних рамок
        for filt in self.active_filters:
            x_min = np.log10(filt['f_min']) if self.freq_scale_mode == "Log" else filt['f_min']
            x_max = np.log10(filt['f_max']) if self.freq_scale_mode == "Log" else filt['f_max']
            filt['top_item'].setRegion([x_min, x_max])

        self.compute_and_draw_fft_at(self.current_sample_idx)

    # 1. Добавление фильтра сверху (с FFT графика через ПКМ)
    def add_filter_from_fft(self, f_min, f_max, x_min, x_max):
        top_region = self.create_clean_region(x_min, x_max)
        self.plot_fft.addItem(top_region, ignoreBounds=True)

        bot_rect = QtWidgets.QGraphicsRectItem(QtCore.QRectF(0, f_min, self.total_duration, f_max - f_min))
        bot_rect.setPen(QtGui.QPen(QtCore.Qt.PenStyle.NoPen))
        bot_rect.setBrush(pg.mkBrush(255, 255, 255, 90)) # ~0.35 прозрачность
        bot_rect.setZValue(15)
        self.plot_spec.addItem(bot_rect, ignoreBounds=True)

        filter_entry = {
            't_min': None,
            't_max': None,
            'f_min': f_min,
            'f_max': f_max,
            'top_item': top_region,
            'bottom_item': bot_rect
        }

        with self.filter_lock:
            self.active_filters.append(filter_entry)

        self.compute_and_draw_fft_at(self.current_sample_idx)
        print(f"[FILTER ACTIVE] Frequency Band: {f_min:.0f} Hz - {f_max:.0f} Hz (All Time)")

    # 2. Добавление 2D фильтра снизу (со Спектрограммы через ПКМ)
    def add_2d_spectrogram_filter(self, t_min, t_max, f_min, f_max):
        bot_rect = QtWidgets.QGraphicsRectItem(QtCore.QRectF(t_min, f_min, t_max - t_min, f_max - f_min))
        bot_rect.setPen(QtGui.QPen(QtCore.Qt.PenStyle.NoPen))
        bot_rect.setBrush(pg.mkBrush(255, 255, 255, 90)) # ~0.35 прозрачность
        bot_rect.setZValue(15)
        self.plot_spec.addItem(bot_rect, ignoreBounds=True)

        x_min = np.log10(f_min) if self.freq_scale_mode == "Log" else f_min
        x_max = np.log10(f_max) if self.freq_scale_mode == "Log" else f_max
        top_region = self.create_clean_region(x_min, x_max)
        self.plot_fft.addItem(top_region, ignoreBounds=True)

        filter_entry = {
            't_min': t_min,
            't_max': t_max,
            'f_min': f_min,
            'f_max': f_max,
            'top_item': top_region,
            'bottom_item': bot_rect
        }

        with self.filter_lock:
            self.active_filters.append(filter_entry)

        self.compute_and_draw_fft_at(self.current_sample_idx)
        print(f"[FILTER ACTIVE] 2D Box: {t_min:.1f}s - {t_max:.1f}s | Freq: {f_min:.0f} Hz - {f_max:.0f} Hz")

    def remove_filter_at_pos(self, t_click, f_click, is_fft=False):
        """Удаляет конкретный фильтр под курсором СКМ, либо все, если клик в пустоту"""
        target_idx = None

        with self.filter_lock:
            # Ищем, в какую область попал клик
            for idx, filt in enumerate(self.active_filters):
                f_min, f_max = filt['f_min'], filt['f_max']
                freq_match = (f_min <= f_click <= f_max)

                if is_fft:
                    # На верхнем графике FFT проверяем только диапазон частот
                    if freq_match:
                        target_idx = idx
                        break
                else:
                    # На нижней спектрограмме проверяем и время, и частоту
                    t_min = 0.0 if filt['t_min'] is None else filt['t_min']
                    t_max = self.total_duration if filt['t_max'] is None else filt['t_max']
                    time_match = (t_min <= t_click <= t_max)

                    if freq_match and time_match:
                        target_idx = idx
                        break

        # Если попали в конкретный фильтр -> удаляем только его
        if target_idx is not None:
            with self.filter_lock:
                removed_filt = self.active_filters.pop(target_idx)
            self.plot_fft.removeItem(removed_filt['top_item'])
            self.plot_spec.removeItem(removed_filt['bottom_item'])
            self.compute_and_draw_fft_at(self.current_sample_idx)
            print(f"[FILTER REMOVED] Area {removed_filt['f_min']:.0f} Hz - {removed_filt['f_max']:.0f} Hz deleted.")
        else:
            # Если кликнули в пустоту -> удаляем все
            self.clear_all_filters()
            
    def clear_all_filters(self):
        """Мгновенно и безопасно очищает все фильтры на обоих графиках"""
        with self.filter_lock:
            filters_to_remove = list(self.active_filters)
            self.active_filters.clear()

        for filt in filters_to_remove:
            self.plot_fft.removeItem(filt['top_item'])
            self.plot_spec.removeItem(filt['bottom_item'])

        self.compute_and_draw_fft_at(self.current_sample_idx)
        print("[FILTER] All filters cleared.")

    def seek_to_time(self, target_sec):
        self.current_sample_idx = int(target_sec * self.sample_rate)
        self.cursor_line.setPos(target_sec)
        self.compute_and_draw_fft_at(self.current_sample_idx)

    def scrub_adaptive(self, direction):
        x_range = self.plot_spec.plotItem.vb.viewRange()[0]
        visible_span = max(0.05, x_range[1] - x_range[0])
        step_sec = visible_span * 0.018 * direction

        cur_sec = self.current_sample_idx / self.sample_rate
        target_sec = max(0.0, min(self.total_duration, cur_sec + step_sec))
        self.current_sample_idx = int(target_sec * self.sample_rate)
        self.cursor_line.setPos(target_sec)

        self.compute_and_draw_fft_at(self.current_sample_idx)

        scrub_samples = int(min(0.08, visible_span * 0.1) * self.sample_rate)
        scrub_samples = max(1024, scrub_samples)
        start_s = self.current_sample_idx
        end_s = min(len(self.audio_samples), start_s + scrub_samples)
        snippet = self.audio_samples[start_s:end_s]
        
        if len(snippet) > 0:
            gain = 10.0 ** (self.boost_db / 20.0)
            preview = np.clip(snippet * gain, -1.0, 1.0)
            try:
                sd.play(preview, self.sample_rate)
            except Exception:
                pass

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

    def toggle_play(self):
        self.is_playing = not self.is_playing
        if self.is_playing:
            self.btn_play.setText("❚❚ Pause")
            self.btn_play.setStyleSheet("background-color: #1E1E1E; color: #FF3366; font-size: 12pt; font-weight: bold; border-radius: 4px; border: 1px solid #333;")
        else:
            self.btn_play.setText("▶ Play")
            self.btn_play.setStyleSheet("background-color: #1E1E1E; color: #33FF57; font-size: 12pt; font-weight: bold; border-radius: 4px; border: 1px solid #333;")

    def on_boost_changed(self, val):
        self.boost_db = float(val)

    def on_yrange_changed(self):
        self.plot_fft.setYRange(self.spin_ymin.value(), self.spin_ymax.value())

    def compute_and_draw_fft_at(self, sample_idx):
        start_s = max(0, sample_idx - self.fft_size // 2)
        end_s = start_s + self.fft_size

        # Скрываем все текстовые плашки перед пересчетом
        for txt in self.peak_text_items:
            txt.setText("")

        if end_s <= len(self.audio_samples):
            slice_data = self.audio_samples[start_s:end_s]
            window = np.hanning(len(slice_data))
            fft_vals = np.abs(np.fft.rfft(slice_data * window))
            freqs = np.fft.rfftfreq(len(slice_data), 1.0 / self.sample_rate)

            fft_db = 20 * np.log10((fft_vals / (len(slice_data) / 2)) + 1e-6) + 90.0

            valid_mask = freqs >= LIMIT_FREQ_MIN

            cur_t = sample_idx / self.sample_rate
            active_bands = []
            with self.filter_lock:
                if self.active_filters:
                    for filt in self.active_filters:
                        t_min, t_max = filt['t_min'], filt['t_max']
                        if t_min is None or (t_min <= cur_t <= t_max):
                            active_bands.append((filt['f_min'], filt['f_max']))

            # Изоляция FFT частот по активным фильтрам
            if ISOLATE_FFT_ON_FILTER:
                if self.active_filters:
                    if active_bands:
                        band_mask = np.zeros_like(freqs, dtype=bool)
                        for f_min, f_max in active_bands:
                            band_mask |= (freqs >= f_min) & (freqs <= f_max)
                        valid_mask = valid_mask & band_mask
                    else:
                        valid_mask = np.zeros_like(freqs, dtype=bool)

            x_coords = np.log10(freqs[valid_mask]) if self.freq_scale_mode == "Log" else freqs[valid_mask]
            valid_db = fft_db[valid_mask]
            self.fft_curve.setData(x_coords, valid_db)

            # Поиск пиков
            peak_xs = []
            peak_ys = []

            # Вариант 1: Есть выделенные активные зоны -> ищем локальный максимум в КАЖДОЙ зоне
            if active_bands:
                for idx, (f_min, f_max) in enumerate(active_bands):
                    if idx >= len(self.peak_text_items):
                        break
                    local_mask = (freqs >= f_min) & (freqs <= f_max)
                    if np.any(local_mask):
                        sub_f = freqs[local_mask]
                        sub_db = fft_db[local_mask]
                        max_i = np.argmax(sub_db)
                        peak_f = sub_f[max_i]
                        peak_p = sub_db[max_i]

                        peak_x = np.log10(peak_f) if self.freq_scale_mode == "Log" else peak_f
                        peak_xs.append(peak_x)
                        peak_ys.append(peak_p)

                        txt_item = self.peak_text_items[idx]
                        txt_item.setText(f"Peak: {peak_f:.0f} Hz ({peak_p:.1f} dB)")
                        txt_item.setPos(peak_x, min(self.spin_ymax.value() - 1, peak_p + 3))

            # Вариант 2: Нет выделений -> один глобальный пик по всему спектру
            elif not self.active_filters:
                global_mask = (freqs >= 50) & (freqs <= LIMIT_FREQ_MAX)
                if np.any(global_mask):
                    sub_f = freqs[global_mask]
                    sub_db = fft_db[global_mask]
                    max_i = np.argmax(sub_db)
                    peak_f = sub_f[max_i]
                    peak_p = sub_db[max_i]

                    peak_x = np.log10(peak_f) if self.freq_scale_mode == "Log" else peak_f
                    peak_xs.append(peak_x)
                    peak_ys.append(peak_p)

                    txt_item = self.peak_text_items[0]
                    txt_item.setText(f"Peak: {peak_f:.0f} Hz ({peak_p:.1f} dB)")
                    txt_item.setPos(peak_x, min(self.spin_ymax.value() - 1, peak_p + 3))

            self.peak_scatter.setData(peak_xs, peak_ys)
            
    def update_playhead(self):
        if self.is_playing:
            cur_sec = self.current_sample_idx / self.sample_rate
            self.cursor_line.setPos(cur_sec)
            self.compute_and_draw_fft_at(self.current_sample_idx)

            # Если трек закончился во время воспроизведения, синхронизируем кнопку Play
            if not self.is_playing:
                self.btn_play.setText("▶ Play")
                self.btn_play.setStyleSheet("background-color: #1E1E1E; color: #33FF57; font-size: 12pt; font-weight: bold; border-radius: 4px; border: 1px solid #333;")

    def closeEvent(self, event):
        self.stream.stop()
        self.stream.close()
        event.accept()

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