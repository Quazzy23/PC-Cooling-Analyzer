import os
import sys
import json
import numpy as np
import pandas as pd

from PyQt6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

# Import profiles from utils/configs.py
from utils.configs import CPU_PROFILE, GPU_PROFILE

# =======================================================
#               MODE & DIRECTORY CONFIGURATION
# =======================================================
ANALYSIS_MODE = "CPU"  # "CPU" or "GPU"

PROFILE = CPU_PROFILE if ANALYSIS_MODE.upper() == "CPU" else GPU_PROFILE

RESULTS_DIR = "results"
LOGS_DIR = os.path.join(RESULTS_DIR, "sensors_logs")
SUMMARY_DIR = os.path.join(RESULTS_DIR, "summary_reports", PROFILE["summary_dir_name"])
HW_INFO_FILE = os.path.join("system_info", "hardware_info.json")

# Default Interactive Parameters
DEFAULT_SMOOTHING = 4  # Сделаем по умолчанию 1 (без сглаживания, чтобы графики и таблица сразу соотносились 1 в 1)
DEFAULT_DOWNSAMPLE_STEP = 1
DEFAULT_RAW_ALPHA = 1.0
DEFAULT_TREND_ALPHA = 0.0

TIME_START = 0       # Start time in seconds (0 = log start)
TIME_END   = "last"  # End time in seconds ("last" = log end)

ID_TIME = "TIME_SEC"
# =======================================================

pg.setConfigOptions(antialias=True, useOpenGL=True)
pg.setConfigOption('background', '#0E0E0E')
pg.setConfigOption('foreground', '#FFFFFF')


class CleanTimeViewBox(pg.ViewBox):
    """ViewBox с поддержкой Alt+Wheel (Zoom X), Shift+Wheel (Zoom Y), Middle Click (Pan) и ПКМ (Выделение областей)"""
    def __init__(self, analyzer_ref, plot_widget_ref, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.analyzer = analyzer_ref
        self.plot_widget = plot_widget_ref
        self.setMouseEnabled(x=False, y=False)
        self.setMenuEnabled(False)
        self.temp_region_p1 = None
        self.temp_region_p2 = None

    def mouseClickEvent(self, ev):
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            ev.accept()
            pos = self.mapToView(ev.pos())
            t_click = pos.x()
            self.analyzer.handle_right_click_on_timeline(t_click)
        else:
            ev.ignore()

    def mousePressEvent(self, ev):
        if ev.button() == QtCore.Qt.MouseButton.MiddleButton:
            ev.accept()
            self.analyzer.panning_data = {
                'start_pos': ev.scenePos(),
                'start_x_range': self.viewRange()[0],
                'vb_ranges': {k: vb.viewRange()[1] for k, vb in self.analyzer.viewboxes_map.items() if self.analyzer.sensor_move_active.get(k, False)}
            }
        else:
            super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == QtCore.Qt.MouseButton.MiddleButton:
            ev.accept()
            self.analyzer.panning_data = None
        else:
            super().mouseReleaseEvent(ev)

    def mouseMoveEvent(self, ev):
        if self.analyzer.panning_data is not None:
            ev.accept()
            delta = ev.scenePos() - self.analyzer.panning_data['start_pos']
            
            # Pan по оси X (Время)
            vr_x = self.analyzer.panning_data['start_x_range']
            span_x = vr_x[1] - vr_x[0]
            dx = -delta.x() / self.width() * span_x
            
            t_max = self.analyzer.total_duration
            new_min_x = max(0.0, vr_x[0] + dx)
            new_max_x = min(t_max, new_min_x + span_x)
            if new_max_x >= t_max:
                new_max_x = t_max
                new_min_x = max(0.0, t_max - span_x)
            self.setXRange(new_min_x, new_max_x, padding=0)
            self.clamp_x()

            # Pan по оси Y для датчиков с активной кнопкой M
            rect_h = self.height()
            for k, start_vr_y in self.analyzer.panning_data['vb_ranges'].items():
                if k in self.analyzer.viewboxes_map:
                    vb = self.analyzer.viewboxes_map[k]
                    span_y = start_vr_y[1] - start_vr_y[0]
                    dy = (delta.y() / rect_h) * span_y
                    
                    new_min_y = start_vr_y[0] + dy
                    new_max_y = start_vr_y[1] + dy

                    # Строгие лимиты Y (не даем уйти за рамки исходного рендеринга)
                    if k in self.analyzer.sensor_y_limits:
                        orig_min, orig_max = self.analyzer.sensor_y_limits[k]
                        if new_min_y < orig_min:
                            new_min_y = orig_min
                            new_max_y = orig_min + span_y
                        if new_max_y > orig_max:
                            new_max_y = orig_max
                            new_min_y = orig_max - span_y

                    vb.setYRange(new_min_y, new_max_y, padding=0)
                    cur_side = self.analyzer.sensor_sides.get(k, "left")
                    if k in self.analyzer.axes_map:
                        ax = self.analyzer.axes_map[k][cur_side]
                        ax.picture = None
                        ax.setRange(new_min_y, new_max_y)
                        ax.update()
        else:
            super().mouseMoveEvent(ev)

    def mouseDragEvent(self, ev, axis=None):
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            ev.accept()
            modifiers = QtWidgets.QApplication.keyboardModifiers()
            is_ctrl = bool(modifiers & QtCore.Qt.KeyboardModifier.ControlModifier)

            p1 = self.mapToView(ev.buttonDownPos())
            p2 = self.mapToView(ev.pos())
            t_min = min(p1.x(), p2.x())
            t_max = max(p1.x(), p2.x())

            if ev.isStart():
                if not is_ctrl:
                    self.analyzer.clear_all_time_regions()

                self.temp_region_p1 = self.analyzer.create_clean_region(t_min, t_min)
                self.temp_region_p2 = self.analyzer.create_clean_region(t_min, t_min)
                self.analyzer.p1_plot.addItem(self.temp_region_p1, ignoreBounds=True)
                self.analyzer.p2_plot.addItem(self.temp_region_p2, ignoreBounds=True)

            if self.temp_region_p1 is not None:
                self.temp_region_p1.setRegion([t_min, t_max])
                self.temp_region_p2.setRegion([t_min, t_max])

            if ev.isFinish():
                if self.temp_region_p1 is not None:
                    self.analyzer.p1_plot.removeItem(self.temp_region_p1)
                    self.analyzer.p2_plot.removeItem(self.temp_region_p2)
                    self.temp_region_p1 = None
                    self.temp_region_p2 = None

                if (t_max - t_min) > 0.1:
                    self.analyzer.add_time_region(t_min, t_max)
        else:
            ev.ignore()

    def wheelEvent(self, ev, axis=None):
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        is_alt = bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier)
        is_shift = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier)
        delta = ev.delta()

        if is_alt:
            mouse_pos = self.mapToView(ev.pos())
            scale = 0.82 if delta > 0 else 1.22
            self.scaleBy(x=scale, y=1.0, center=mouse_pos)
            self.clamp_x()
            ev.accept()
        elif is_shift:
            # Зумирование по оси Y ТОЛЬКО для датчиков с активной кнопкой M
            scale = 0.82 if delta > 0 else 1.22
            
            target_sensors = self.analyzer.p1_sensors if self.plot_widget == self.analyzer.p1_plot else self.analyzer.p2_sensors
            target_keys = {s["key"] for s in target_sensors}

            for k, vb in self.analyzer.viewboxes_map.items():
                if k in target_keys and self.analyzer.sensor_move_active.get(k, False):
                    vr_y = vb.viewRange()[1]
                    span_y = vr_y[1] - vr_y[0]
                    center_y = (vr_y[0] + vr_y[1]) / 2  # Зум относительно центра шкалы датчика
                    
                    new_span_y = span_y * scale
                    new_min_y = center_y - new_span_y / 2
                    new_max_y = center_y + new_span_y / 2

                    # Проверка лимитов: нельзя отдалить шире исходного авто-фита
                    if k in self.analyzer.sensor_y_limits:
                        orig_min, orig_max = self.analyzer.sensor_y_limits[k]
                        if new_min_y < orig_min: new_min_y = orig_min
                        if new_max_y > orig_max: new_max_y = orig_max
                        # Если попытались сжать в точку
                        if new_min_y >= new_max_y:
                            continue

                    vb.setYRange(new_min_y, new_max_y, padding=0)
                    
                    cur_side = self.analyzer.sensor_sides.get(k, "left")
                    if k in self.analyzer.axes_map:
                        ax = self.analyzer.axes_map[k][cur_side]
                        ax.picture = None
                        ax.setRange(new_min_y, new_max_y)
                        ax.update()

            ev.accept()
        else:
            vr = self.viewRange()[0]
            span = vr[1] - vr[0]
            shift = span * 0.04 * (-1 if delta > 0 else 1)
            t_max = self.analyzer.total_duration
            new_min = max(0.0, vr[0] + shift)
            new_max = min(t_max, new_min + span)
            if new_max >= t_max:
                new_max = t_max
                new_min = max(0.0, t_max - span)
            self.setXRange(new_min, new_max, padding=0)
            self.clamp_x()
            ev.accept()

    def clamp_x(self):
        vr = self.viewRange()[0]
        span = vr[1] - vr[0]
        t_max = self.analyzer.total_duration

        if span >= t_max:
            self.setXRange(0.0, t_max, padding=0)
        else:
            xmin = max(0.0, vr[0])
            xmax = min(t_max, xmin + span)
            if xmax >= t_max:
                xmax = t_max
                xmin = max(0.0, t_max - span)
            self.setXRange(xmin, xmax, padding=0)


class OverlayViewBox(pg.ViewBox):
    """Оверлейный ViewBox для наложенных осей"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseEnabled(x=False, y=False)
        self.setMenuEnabled(False)

    def mouseDragEvent(self, ev, axis=None):
        ev.ignore()

    def mouseClickEvent(self, ev):
        ev.ignore()

    def wheelEvent(self, ev, axis=None):
        ev.ignore()


class CoolingAnalyzerPro(QtWidgets.QMainWindow):
    def __init__(self, df, selected_file, hw_model_name):
        super().__init__()
        self.df = df
        self.selected_file = selected_file
        self.hw_model_name = hw_model_name

        self.clean_file_name = selected_file.replace("table_raw_", "")
        self.chart_filename = f"graph_{self.clean_file_name.replace('.csv', '.jpg')}"
        self.chart_filepath = os.path.join(SUMMARY_DIR, self.chart_filename)
        self.summary_filename = f"table_{self.clean_file_name}"
        self.summary_filepath = os.path.join(SUMMARY_DIR, self.summary_filename)

        self.setWindowTitle(f"{PROFILE['mode_name']} Cooling Analysis — {self.clean_file_name} ({hw_model_name})")
        self.resize(1580, 930)

        # Состояние
        self.current_step = 1
        self.current_raw_alpha = DEFAULT_RAW_ALPHA
        self.current_trend_alpha = DEFAULT_TREND_ALPHA
        self.y_fit_mode = "Raw"

        # Реестры управления
        self.sensor_sides = {}       # key -> "left" / "right"
        self.sensor_move_active = {} # key -> bool (активирована ли кнопка M для зума/перемещения)
        self.sensor_y_limits = {}    # key -> [min_y, max_y] (жесткие базовые лимиты Y)
        self.panning_data = None     # Для перетаскивания средней кнопкой мыши (Pan)
        self.curves = {}             # f"{key}_raw" / f"{key}_trend" -> PlotCurveItem
        self._persistent_curves = [] # Постоянное удержание объектов в памяти
        self._all_curve_items = []   # Защита от сборщика мусора Python GC
        self.time_regions = []       # Список активных выделений: [{t_min, t_max, item_p1, item_p2}, ...]
        self.axes_map = {}           # key -> {'left': AxisItem, 'right': AxisItem}
        self.viewboxes_map = {}      # key -> OverlayViewBox
        self.plot_map = {}           # key -> PlotWidget
        self.sensor_checkboxes = {}  # key -> QCheckBox
        self.side_buttons = {}       # key -> QPushButton

        self.resolve_sensors()
        self.init_ui()
        self.populate_summary_table()
        self.apply_initial_visibility()
        self.update_plots_data()
        self.update_y_limits()

    def resolve_sensors(self):
        def get_col(sensor_id):
            if not sensor_id:
                return None
            for col in self.df.columns:
                col_id = col[1] if isinstance(col, tuple) else str(col)
                if col_id == sensor_id:
                    return col
            return None

        self.col_time = get_col(ID_TIME) or self.df.columns[0]
        raw_t = self.df[self.col_time].to_numpy().astype(float)
        self.time_data = raw_t - raw_t[0]
        self.total_duration = float(self.time_data[-1])

        # Привязка сенсоров P1 и P2
        self.p1_sensors = []
        for s in PROFILE.get("panel1_sensors", []):
            col = get_col(s["id"])
            if col is not None:
                self.p1_sensors.append({**s, "col": col})

        self.p2_sensors = []
        for s in PROFILE.get("panel2_sensors", []):
            col = get_col(s["id"])
            if col is not None:
                self.p2_sensors.append({**s, "col": col})

        self.col_clock = get_col(PROFILE.get("clock_id"))
        self.col_volt  = get_col(PROFILE.get("voltage_id"))
        self.get_col_fn = get_col

    def smooth_series(self, series):
        if series is not None:
            return series.rolling(window=DEFAULT_SMOOTHING, min_periods=1).mean().to_numpy()
        return None

    def resample_series(self, series, step):
        if series is not None and step > 1:
            return series.rolling(window=step, min_periods=1).mean().iloc[::step].to_numpy()
        elif series is not None:
            return series.to_numpy()
        return None

    def get_resampled_time(self, step):
        if step > 1:
            return self.time_data[::step]
        return self.time_data

    def create_pen(self, color_hex, width, alpha):
        c = QtGui.QColor(color_hex)
        c.setAlphaF(max(0.0, min(1.0, alpha)))
        return pg.mkPen(color=c, width=width)

    def attach_overlay_view(self, plot_widget, color_hex, default_side):
        """Создает оверлейный ViewBox и пару осей без двойного добавления в сцену"""
        vb = OverlayViewBox()
        plot_widget.plotItem.scene().addItem(vb)

        ax_left = pg.AxisItem('left')
        ax_left.setPen(pg.mkPen('#444444', width=1))
        ax_left.setTextPen(pg.mkPen(color_hex))
        ax_left.setWidth(50)
        ax_left.linkToView(vb)
        plot_widget.plotItem.scene().addItem(ax_left)

        ax_right = pg.AxisItem('right')
        ax_right.setPen(pg.mkPen('#444444', width=1))
        ax_right.setTextPen(pg.mkPen(color_hex))
        ax_right.setWidth(50)
        ax_right.linkToView(vb)
        plot_widget.plotItem.scene().addItem(ax_right)

        if default_side == 'left':
            ax_left.setVisible(True)
            ax_right.setVisible(False)
        else:
            ax_left.setVisible(False)
            ax_right.setVisible(True)

        def sync_views():
            rect = plot_widget.plotItem.vb.sceneBoundingRect()
            vb.setGeometry(rect)
            vb.setXRange(*plot_widget.plotItem.vb.viewRange()[0], padding=0)
            ax_left.setGeometry(QtCore.QRectF(rect.left() - 50, rect.top(), 50, rect.height()))
            ax_right.setGeometry(QtCore.QRectF(rect.right(), rect.top(), 50, rect.height()))

        plot_widget.plotItem.vb.sigResized.connect(sync_views)
        plot_widget.plotItem.vb.sigRangeChanged.connect(sync_views)
        return vb, ax_left, ax_right

    def init_ui(self):
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QtWidgets.QHBoxLayout(central_widget)
        self.main_layout.setContentsMargins(15, 10, 15, 10)
        self.main_layout.setSpacing(14)

        # Левая колонка: Графики
        graphs_container = QtWidgets.QWidget()
        graphs_layout = QtWidgets.QVBoxLayout(graphs_container)
        graphs_layout.setContentsMargins(0, 0, 0, 0)
        graphs_layout.setSpacing(10)

        # =========================================================================
        # 1. Верхний график: Теплофизика (P1)
        # =========================================================================
        self.vb1 = CleanTimeViewBox(self, None) # Временно, назначим ниже
        self.p1_plot = pg.PlotWidget(viewBox=self.vb1)
        self.vb1.plot_widget = self.p1_plot     # Привязываем ссылку
        self.p1_plot.showGrid(x=True, y=True, alpha=0.18)
        self.p1_plot.setTitle(f"<span style='color: #FFFFFF; font-size: 11pt;'><b>1. {PROFILE['chart_title_prefix']} ({self.hw_model_name} — {self.clean_file_name})</b></span>", justify='left')
        
        self.p1_plot.hideAxis('left')
        self.p1_plot.hideAxis('right')
        self.p1_plot.getAxis('bottom').enableAutoSIPrefix(False)
        self.p1_plot.getAxis('bottom').setPen(pg.mkPen('#444444', width=1))
        self.p1_plot.getAxis('bottom').setTextPen(pg.mkPen('#AAAAAA'))
        self.p1_plot.plotItem.layout.setContentsMargins(55, 0, 55, 0)

        for s in self.p1_sensors:
            k = s["key"]
            self.sensor_sides[k] = s.get("axis", "left")
            self.plot_map[k] = self.p1_plot

            vb, ax_l, ax_r = self.attach_overlay_view(self.p1_plot, s['color'], s.get("axis", "left"))
            self.axes_map[k] = {'left': ax_l, 'right': ax_r}
            self.viewboxes_map[k] = vb

            pen_raw = self.create_pen(s['color'], 1.2, self.current_raw_alpha)
            pen_trend = self.create_pen(s['color'], 2.4, self.current_trend_alpha)

            c_raw = pg.PlotCurveItem(self.time_data, self.smooth_series(self.df[s["col"]]), pen=pen_raw)
            c_trend = pg.PlotCurveItem(self.time_data, self.smooth_series(self.df[s["col"]]), pen=pen_trend)

            self.curves[f"{k}_raw"] = c_raw
            self.curves[f"{k}_trend"] = c_trend
            self._persistent_curves.extend([c_raw, c_trend])

            vb.addItem(c_raw)
            vb.addItem(c_trend)

        graphs_layout.addWidget(self.p1_plot, stretch=5)

        # =========================================================================
        # 2. Нижний график: Обороты и Шум (P2)
        # =========================================================================
        self.vb2 = CleanTimeViewBox(self, None) # Временно, назначим ниже
        self.p2_plot = pg.PlotWidget(viewBox=self.vb2)
        self.vb2.plot_widget = self.p2_plot     # Привязываем ссылку
        self.p2_plot.showGrid(x=True, y=True, alpha=0.18)
        self.p2_plot.setTitle(f"<span style='color: #FFFFFF; font-size: 10pt;'><b>2. {PROFILE['panel2_title']}</b></span>", justify='left')
        self.p2_plot.setLabel('bottom', 'Time (Seconds)')
        
        self.p2_plot.hideAxis('left')
        self.p2_plot.hideAxis('right')
        self.p2_plot.getAxis('bottom').enableAutoSIPrefix(False)
        self.p2_plot.getAxis('bottom').setPen(pg.mkPen('#444444', width=1))
        self.p2_plot.getAxis('bottom').setTextPen(pg.mkPen('#AAAAAA'))
        self.p2_plot.plotItem.layout.setContentsMargins(55, 0, 55, 0)
        self.vb2.setXLink(self.vb1)

        for s in self.p2_sensors:
            k = s["key"]
            self.sensor_sides[k] = s.get("axis", "left")
            self.plot_map[k] = self.p2_plot

            vb, ax_l, ax_r = self.attach_overlay_view(self.p2_plot, s['color'], s.get("axis", "left"))
            self.axes_map[k] = {'left': ax_l, 'right': ax_r}
            self.viewboxes_map[k] = vb

            pen_raw = self.create_pen(s['color'], 1.2, self.current_raw_alpha)
            pen_trend = self.create_pen(s['color'], 2.4, self.current_trend_alpha)

            c_raw = pg.PlotCurveItem(self.time_data, self.smooth_series(self.df[s["col"]]), pen=pen_raw)
            c_trend = pg.PlotCurveItem(self.time_data, self.smooth_series(self.df[s["col"]]), pen=pen_trend)

            self.curves[f"{k}_raw"] = c_raw
            self.curves[f"{k}_trend"] = c_trend
            self._persistent_curves.extend([c_raw, c_trend])

            vb.addItem(c_raw)
            vb.addItem(c_trend)

        graphs_layout.addWidget(self.p2_plot, stretch=3)

        # Вертикальная линия перекрестия (Crosshair)
        self.crosshair_line = pg.InfiniteLine(
            pos=0, 
            angle=90, 
            pen=pg.mkPen(color='#00E5FF', width=1, style=QtCore.Qt.PenStyle.DashLine)
        )
        self.crosshair_line.setZValue(1000)
        self.p1_plot.addItem(self.crosshair_line)

        self.crosshair_line2 = pg.InfiniteLine(
            pos=0, 
            angle=90, 
            pen=pg.mkPen(color='#00E5FF', width=1, style=QtCore.Qt.PenStyle.DashLine)
        )
        self.crosshair_line2.setZValue(1000)
        self.p2_plot.addItem(self.crosshair_line2)

        # Раздельная подписка на движение мыши для P1 и P2
        self.p1_proxy = pg.SignalProxy(self.p1_plot.scene().sigMouseMoved, rateLimit=60, slot=lambda evt: self.on_mouse_moved(evt, "P1"))
        self.p2_proxy = pg.SignalProxy(self.p2_plot.scene().sigMouseMoved, rateLimit=60, slot=lambda evt: self.on_mouse_moved(evt, "P2"))

        # =========================================================================
        # 3. Нижняя панель управления
        # =========================================================================
        controls_layout = QtWidgets.QHBoxLayout()
        controls_layout.setSpacing(12)

        # Единый стиль чистых полей ввода без стрелочек и кнопок
        spin_qss = """
            QAbstractSpinBox {
                background-color: #1A1A1A;
                color: #00E5FF;
                font-weight: bold;
                font-size: 9pt;
                border: 1px solid #333333;
                border-radius: 4px;
                padding-left: 6px;
                padding-right: 6px;
                min-height: 28px;
            }
            QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
                width: 0px;
                border: none;
                background: transparent;
            }
        """

        # Поле Smooth
        lbl_smooth = QtWidgets.QLabel("Smooth:")
        lbl_smooth.setStyleSheet("color: white; font-size: 9pt;")
        controls_layout.addWidget(lbl_smooth)

        self.spin_smooth = QtWidgets.QSpinBox()
        self.spin_smooth.setRange(1, 30)
        self.spin_smooth.setValue(DEFAULT_SMOOTHING)
        self.spin_smooth.setFixedWidth(65)
        self.spin_smooth.setStyleSheet(spin_qss)
        self.spin_smooth.valueChanged.connect(self.on_smooth_changed)
        controls_layout.addWidget(self.spin_smooth)

        controls_layout.addSpacing(6)

        # Поле Step
        lbl_step = QtWidgets.QLabel("Step:")
        lbl_step.setStyleSheet("color: white; font-weight: bold; font-size: 9pt;")
        controls_layout.addWidget(lbl_step)

        self.spin_step = QtWidgets.QSpinBox()
        self.spin_step.setRange(1, 200)
        self.spin_step.setSingleStep(5)   # Шаг равен 5
        self.spin_step.setValue(self.current_step)
        self.spin_step.setFixedWidth(65)
        self.spin_step.setStyleSheet(spin_qss)
        self.spin_step.valueChanged.connect(self.on_step_changed)
        controls_layout.addWidget(self.spin_step)

        # Поле Raw Fog
        lbl_raw = QtWidgets.QLabel("Raw Fog:")
        lbl_raw.setStyleSheet("color: white; font-size: 9pt;")
        controls_layout.addWidget(lbl_raw)

        self.spin_raw = QtWidgets.QDoubleSpinBox()
        self.spin_raw.setRange(0.0, 1.0)
        self.spin_raw.setSingleStep(0.05)
        self.spin_raw.setValue(self.current_raw_alpha)
        self.spin_raw.setFixedWidth(65)
        self.spin_raw.setStyleSheet(spin_qss)
        self.spin_raw.valueChanged.connect(self.on_raw_alpha_changed)
        controls_layout.addWidget(self.spin_raw)

        # Поле Trend A
        lbl_trend = QtWidgets.QLabel("Trend A:")
        lbl_trend.setStyleSheet("color: white; font-size: 9pt;")
        controls_layout.addWidget(lbl_trend)

        self.spin_trend = QtWidgets.QDoubleSpinBox()
        self.spin_trend.setRange(0.0, 1.0)
        self.spin_trend.setSingleStep(0.05)
        self.spin_trend.setValue(self.current_trend_alpha)
        self.spin_trend.setFixedWidth(65)
        self.spin_trend.setStyleSheet(spin_qss)
        self.spin_trend.valueChanged.connect(self.on_trend_alpha_changed)
        controls_layout.addWidget(self.spin_trend)

        controls_layout.addSpacing(6)

        # Кнопка Fit: Raw / Trend
        self.btn_fit = QtWidgets.QPushButton("Fit: Raw")
        self.btn_fit.setFixedSize(95, 32)
        self.btn_fit.setStyleSheet("""
            QPushButton {
                background-color: #1A1A1A;
                color: #00E5FF;
                font-weight: bold;
                font-size: 9pt;
                border-radius: 4px;
                border: 1px solid #333333;
            }
            QPushButton:hover {
                background-color: #2A2A2A;
                border: 1px solid #00E5FF;
            }
        """)
        self.btn_fit.clicked.connect(self.toggle_y_fit)
        controls_layout.addWidget(self.btn_fit)

        # Кнопка Save Result
        self.btn_save = QtWidgets.QPushButton("Save Result")
        self.btn_save.setFixedSize(115, 32)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #1A1A1A;
                color: #33FF57;
                font-weight: bold;
                font-size: 9pt;
                border-radius: 4px;
                border: 1px solid #333333;
            }
            QPushButton:hover {
                background-color: #2A2A2A;
                border: 1px solid #33FF57;
            }
        """)
        self.btn_save.clicked.connect(self.save_result_action)
        controls_layout.addWidget(self.btn_save)

        controls_layout.addStretch()
        
        # Интерактивная строка статуса телеметрии под курсором
        self.lbl_telemetry_status = QtWidgets.QLabel("Hover over charts to inspect telemetry...")
        self.lbl_telemetry_status.setStyleSheet("color: #888888; font-style: italic; font-size: 8.5pt;")
        controls_layout.addWidget(self.lbl_telemetry_status)

        graphs_layout.addLayout(controls_layout)

        # =========================================================================
        # 4. Правая боковая панель: SUMMARY METRICS + SENSOR PASSPORT
        # =========================================================================
        sidebar = QtWidgets.QFrame()
        sidebar.setFixedWidth(380)
        sidebar.setStyleSheet("background-color: #121212; border: 1px solid #2A2A2A; border-radius: 6px; padding: 6px;")
        sb_layout = QtWidgets.QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(6, 6, 6, 6)
        sb_layout.setSpacing(8)

        self.lbl_summary_title = QtWidgets.QLabel(f"<b>SUMMARY METRICS</b> <span style='color:#888; font-size:8pt;'>({PROFILE['mode_name']})</span>")
        self.lbl_summary_title.setStyleSheet("color: #FFFFFF; font-size: 9pt;")
        sb_layout.addWidget(self.lbl_summary_title)

        self.table_summary = QtWidgets.QTableWidget()
        self.table_summary.setColumnCount(4)
        self.table_summary.setHorizontalHeaderLabels(["Metric", "Min", "Max", "Avg"])
        
        header = self.table_summary.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        
        self.table_summary.verticalHeader().setVisible(False)
        self.table_summary.verticalHeader().setDefaultSectionSize(20)
        self.table_summary.setShowGrid(False)

        self.table_summary.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_summary.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.table_summary.setStyleSheet("""
            QTableWidget {
                background-color: #0E0E0E;
                color: #FFFFFF;
                border: 1px solid #222222;
                border-radius: 4px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 8pt;
            }
            QTableWidget::item {
                padding-top: 1px;
                padding-bottom: 1px;
                padding-left: 2px;
                padding-right: 2px;
            }
            QHeaderView::section {
                background-color: #181818;
                color: #00E5FF;
                font-weight: bold;
                font-size: 8.5pt;
                height: 32px;
                padding-top: 1px;
                padding-bottom: 4px;
                border: 1px solid #222222;
            }
        """)
        sb_layout.addWidget(self.table_summary, stretch=5)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2A2A2A;")
        sb_layout.addWidget(sep)

        lbl_passport_title = QtWidgets.QLabel("<b>SENSOR PASSPORT & VISIBILITY</b>")
        lbl_passport_title.setStyleSheet("color: #FFFFFF; font-size: 9pt;")
        sb_layout.addWidget(lbl_passport_title)

        passport_scroll = QtWidgets.QScrollArea()
        passport_scroll.setWidgetResizable(True)
        passport_scroll.setStyleSheet("background: transparent; border: none;")
        
        passport_widget = QtWidgets.QWidget()
        self.passport_layout = QtWidgets.QVBoxLayout(passport_widget)
        self.passport_layout.setContentsMargins(0, 0, 0, 0)
        self.passport_layout.setSpacing(3)

        for s in self.p1_sensors + self.p2_sensors:
            self.add_passport_row(s)

        self.passport_layout.addStretch()
        passport_scroll.setWidget(passport_widget)
        sb_layout.addWidget(passport_scroll, stretch=5)

        # Сборка главного контейнера: Графики (лево) + Сайдбар (право)
        self.main_layout.addWidget(graphs_container, stretch=7)
        self.main_layout.addWidget(sidebar, stretch=3)

    def add_passport_row(self, s):
        k = s["key"]
        row_widget = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(2, 0, 2, 0)
        row_layout.setSpacing(4)
        row_widget.setFixedHeight(24)

        is_default_vis = s.get("visible", True)
        cb = QtWidgets.QCheckBox(s['label'])
        cb.blockSignals(True)
        cb.setChecked(is_default_vis)
        cb.blockSignals(False)
        cb.setStyleSheet(f"""
            QCheckBox {{
                color: {s['color']};
                font-weight: bold;
                font-size: 8pt;
                font-family: 'Segoe UI', Arial, sans-serif;
                spacing: 5px;
            }}
            QCheckBox::indicator {{
                width: 12px;
                height: 12px;
                background-color: #1A1A1A;
                border: 1px solid {s['color']};
                border-radius: 2px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {s['color']};
            }}
        """)
        cb.toggled.connect(lambda checked, key=k: self.toggle_curve_visibility(key, checked))
        row_layout.addWidget(cb, stretch=1)
        self.sensor_checkboxes[k] = cb

        cur_side = self.sensor_sides.get(k, "left")
        side_text = "L" if cur_side == "left" else "R"
        btn_side = QtWidgets.QPushButton(side_text)
        btn_side.setFixedSize(20, 17)
        btn_side.setToolTip("Toggle Axis Side (Left / Right)")
        btn_side.setStyleSheet(f"""
            QPushButton {{
                background-color: #1A1A1A;
                color: #00E5FF;
                font-weight: bold;
                font-size: 7.5pt;
                font-family: 'Segoe UI', Arial, sans-serif;
                border: 1px solid #333333;
                border-radius: 2px;
                padding: 0px;
                margin: 0px;
            }}
            QPushButton:hover {{
                background-color: #2A2A2A;
                border: 1px solid #00E5FF;
            }}
        """)
        btn_side.clicked.connect(lambda _, key=k, btn=btn_side: self.toggle_axis_side(key, btn))
        row_layout.addWidget(btn_side)
        self.side_buttons[k] = btn_side

        # Кнопка M (Move / Zoom Active)
        self.sensor_move_active[k] = False
        btn_move = QtWidgets.QPushButton("M")
        btn_move.setFixedSize(20, 17)
        btn_move.setToolTip("Enable/Disable Zoom & Pan for this sensor")
        btn_move.setStyleSheet("""
            QPushButton {
                background-color: #1A1A1A;
                color: #888888;
                font-weight: bold;
                font-size: 7.5pt;
                font-family: 'Segoe UI', Arial, sans-serif;
                border: 1px solid #333333;
                border-radius: 2px;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #2A2A2A;
                border: 1px solid #AAAAAA;
            }
        """)
        btn_move.clicked.connect(lambda _, key=k, btn=btn_move: self.toggle_sensor_move(key, btn))
        row_layout.addWidget(btn_move)

        self.passport_layout.addWidget(row_widget)

    def toggle_axis_side(self, key, btn):
        if key not in self.axes_map:
            return

        current_side = self.sensor_sides.get(key, "left")
        new_side = "right" if current_side == "left" else "left"
        self.sensor_sides[key] = new_side

        btn.setText("L" if new_side == "left" else "R")

        is_visible = self.sensor_checkboxes[key].isChecked()
        axes = self.axes_map[key]
        plot_widget = self.plot_map[key]
        vb = self.viewboxes_map[key]

        rect = plot_widget.plotItem.vb.sceneBoundingRect()
        target_axis = axes[new_side]
        hidden_axis = axes['right' if new_side == 'left' else 'left']

        hidden_axis.setVisible(False)

        if is_visible:
            if new_side == 'left':
                target_axis.setGeometry(QtCore.QRectF(rect.left() - 50, rect.top(), 50, rect.height()))
            else:
                target_axis.setGeometry(QtCore.QRectF(rect.right(), rect.top(), 50, rect.height()))

            target_axis.setVisible(True)
            target_axis.picture = None
            target_axis.setRange(*vb.viewRange()[1])
            target_axis.update()

        plot_widget.plotItem.scene().update()

    def toggle_sensor_move(self, key, btn):
        """Включает/выключает режим зума и перемещения для конкретного датчика"""
        current_state = self.sensor_move_active.get(key, False)
        new_state = not current_state
        self.sensor_move_active[key] = new_state

        if new_state:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #00E5FF;
                    color: #000000;
                    font-weight: bold;
                    font-size: 7.5pt;
                    font-family: 'Segoe UI', Arial, sans-serif;
                    border: 1px solid #00E5FF;
                    border-radius: 2px;
                    padding: 0px;
                    margin: 0px;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1A1A1A;
                    color: #888888;
                    font-weight: bold;
                    font-size: 7.5pt;
                    font-family: 'Segoe UI', Arial, sans-serif;
                    border: 1px solid #333333;
                    border-radius: 2px;
                    padding: 0px;
                    margin: 0px;
                }
            """)

    def toggle_curve_visibility(self, key, is_visible):
        raw_key = f"{key}_raw"
        trend_key = f"{key}_trend"
        
        if raw_key in self.curves:
            self.curves[raw_key].setVisible(is_visible)
            self.curves[trend_key].setVisible(is_visible)

        if key in self.axes_map:
            cur_side = self.sensor_sides.get(key, "left")
            axes = self.axes_map[key]
            plot_widget = self.plot_map[key]
            vb = self.viewboxes_map[key]
            
            target_axis = axes[cur_side]
            hidden_axis = axes['right' if cur_side == 'left' else 'left']

            hidden_axis.setVisible(False)

            if is_visible:
                rect = plot_widget.plotItem.vb.sceneBoundingRect()
                if cur_side == 'left':
                    target_axis.setGeometry(QtCore.QRectF(rect.left() - 50, rect.top(), 50, rect.height()))
                else:
                    target_axis.setGeometry(QtCore.QRectF(rect.right(), rect.top(), 50, rect.height()))
                
                target_axis.setVisible(True)
                target_axis.picture = None
                target_axis.setRange(*vb.viewRange()[1])
                target_axis.update()
            else:
                target_axis.setVisible(False)

            plot_widget.plotItem.scene().update()

    def create_clean_region(self, t_min, t_max):
        """Создает красивую полупрозрачную полосу времени без границ"""
        region = pg.LinearRegionItem(
            values=[t_min, t_max],
            orientation='vertical',
            brush=pg.mkBrush(255, 255, 255, 80),  # Белый полупрозрачный (~0.3)
            pen=pg.mkPen(None),
            hoverPen=pg.mkPen(None),
            movable=False
        )
        for line in region.lines:
            line.setPen(pg.mkPen(None))
            line.setHoverPen(pg.mkPen(None))
        region.setZValue(50)
        return region

    def add_time_region(self, t_min, t_max):
        """Добавляет синхронную область времени на верхний и нижний графики"""
        reg_p1 = self.create_clean_region(t_min, t_max)
        reg_p2 = self.create_clean_region(t_min, t_max)

        self.p1_plot.addItem(reg_p1, ignoreBounds=True)
        self.p2_plot.addItem(reg_p2, ignoreBounds=True)

        self.time_regions.append({
            't_min': t_min,
            't_max': t_max,
            'item_p1': reg_p1,
            'item_p2': reg_p2
        })
        self.populate_summary_table()
        print(f"[REGION ADDED] Time Range: {t_min:.1f}s - {t_max:.1f}s (Total regions: {len(self.time_regions)})")

    def handle_right_click_on_timeline(self, t_click):
        """ПКМ-клик: удаляет конкретную область под курсором или сбрасывает все, если клик в пустоту"""
        target_idx = None
        for idx, reg in enumerate(self.time_regions):
            if reg['t_min'] <= t_click <= reg['t_max']:
                target_idx = idx
                break

        if target_idx is not None:
            removed = self.time_regions.pop(target_idx)
            self.p1_plot.removeItem(removed['item_p1'])
            self.p2_plot.removeItem(removed['item_p2'])
            print(f"[REGION REMOVED] Region {removed['t_min']:.1f}s - {removed['t_max']:.1f}s deleted.")
        else:
            self.clear_all_time_regions()

        self.populate_summary_table()

    def clear_all_time_regions(self):
        """Очищает все активные области времени на обоих графиках"""
        for reg in self.time_regions:
            self.p1_plot.removeItem(reg['item_p1'])
            self.p2_plot.removeItem(reg['item_p2'])
        self.time_regions.clear()
        self.populate_summary_table()
        print("[REGIONS CLEARED] All time selections cleared.")

    def populate_summary_table(self):
        """Динамически пересчитывает таблицу по всей длительности или по выделенным областям времени"""
        t_col_name = self.col_time
        time_arr = self.df[t_col_name].to_numpy()

        if self.time_regions:
            mask = np.zeros(len(self.df), dtype=bool)
            ranges_str_list = []
            
            for reg in self.time_regions:
                t_min = min(reg['t_min'], reg['t_max'])
                t_max = max(reg['t_min'], reg['t_max'])
                
                # Создаем булеву маску напрямую по значениям времени лога
                region_mask = (time_arr >= t_min) & (time_arr <= t_max)
                mask |= region_mask
                
                # Находим реальные граничные значения времени для заголовка
                valid_t = time_arr[region_mask]
                if len(valid_t) > 0:
                    ranges_str_list.append(f"{valid_t[0]:.1f}s - {valid_t[-1]:.1f}s")
                else:
                    ranges_str_list.append(f"{t_min:.1f}s - {t_max:.1f}s")
            
            target_df = self.df[mask]
            
            ranges_title = ", ".join(ranges_str_list)
            self.lbl_summary_title.setText(f"<b>SUMMARY METRICS</b> <span style='color:#00E5FF; font-size:7.5pt;'>({ranges_title})</span>")
        else:
            target_df = self.df
            self.lbl_summary_title.setText(f"<b>SUMMARY METRICS</b> <span style='color:#888; font-size:8pt;'>({PROFILE['mode_name']} Total)</span>")

        # 2. Пересчитываем строки
        rows = []
        def add_row(label, col_data, fmt="%.1f"):
            if col_data is not None and not target_df.empty:
                series_full = self.df[col_data]
                # Используем актуальное значение сглаживания из поля ввода (или переменной DEFAULT_SMOOTHING)
                current_window = max(1, int(getattr(self, 'spin_smooth', None) and self.spin_smooth.value() or DEFAULT_SMOOTHING))
                
                smoothed_full = series_full.rolling(window=current_window, min_periods=1).mean()
                
                # Применяем маску выделенного времени по индексам target_df
                s_valid = smoothed_full[target_df.index].dropna()
                
                if not s_valid.empty:
                    mn = fmt % s_valid.min()
                    mx = fmt % s_valid.max()
                    av = fmt % s_valid.mean()
                else:
                    mn, mx, av = "—", "—", "—"
                rows.append((label, mn, mx, av))

        # Сенсоры P1
        for s in self.p1_sensors:
            fmt = "%.3f" if "volt" in s["key"].lower() else "%.1f"
            add_row(s["label"], s["col"], fmt=fmt)

        if self.col_clock: 
            add_row("Clock (MHz)", self.col_clock, fmt="%.0f")

        # Сенсоры P2
        for s in self.p2_sensors:
            fmt = "%.0f" if "RPM" in s["label"] else "%.1f"
            add_row(s["label"], s["col"], fmt=fmt)

        # 3. Заполняем таблицу
        self.table_summary.setRowCount(len(rows))
        for r_idx, (m, mn, mx, av) in enumerate(rows):
            item_m = QtWidgets.QTableWidgetItem(m)
            item_mn = QtWidgets.QTableWidgetItem(mn)
            item_mx = QtWidgets.QTableWidgetItem(mx)
            item_av = QtWidgets.QTableWidgetItem(av)

            item_mn.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            item_mx.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            item_av.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

            self.table_summary.setItem(r_idx, 0, item_m)
            self.table_summary.setItem(r_idx, 1, item_mn)
            self.table_summary.setItem(r_idx, 2, item_mx)
            self.table_summary.setItem(r_idx, 3, item_av)

    def apply_initial_visibility(self):
        """Применяет стартовую видимость графиков и осей из configs.py после полной загрузки данных"""
        for s in self.p1_sensors + self.p2_sensors:
            k = s["key"]
            is_vis = s.get("visible", True)
            self.toggle_curve_visibility(k, is_vis)

    def update_plots_data(self):
        """Обновляет только линии тренда при смене шага Step (сырые данные raw не перезаписываются)"""
        t_res = self.get_resampled_time(self.current_step)

        for s in self.p1_sensors + self.p2_sensors:
            k = s["key"]
            trend_data = self.resample_series(self.df[s["col"]], self.current_step)
            self.curves[f"{k}_trend"].setData(t_res, trend_data)

    def on_mouse_moved(self, evt, panel_label):
        pos = evt[0]  # Ссылка на позицию мыши в сцене
        
        active_plot = self.p1_plot if panel_label == "P1" else self.p2_plot
        target_sensors = self.p1_sensors if panel_label == "P1" else self.p2_sensors

        # Проверяем, находится ли курсор в пределах этого графика
        if not active_plot.sceneBoundingRect().contains(pos):
            return

        # Получаем реальное время (координату X) под курсором мыши
        mouse_point = active_plot.plotItem.vb.mapSceneToView(pos)
        x_time = mouse_point.x()

        values_list = []
        for s in target_sensors:
            k = s["key"]
            if k in self.sensor_checkboxes and self.sensor_checkboxes[k].isChecked():
                if k in self.viewboxes_map:
                    vb = self.viewboxes_map[k]
                    # Точная проекция Y курсора в шкалу конкретного датчика
                    scene_pos = active_plot.plotItem.vb.mapFromScene(pos)
                    view_point = vb.mapSceneToView(active_plot.plotItem.vb.mapToScene(scene_pos))
                    val = view_point.y()

                    # Форматирование под тип датчика
                    if "volt" in k.lower():
                        val_str = f"{val:.3f}"
                    elif "RPM" in s["label"]:
                        val_str = f"{val:.0f}"  # Обороты вентиляторов без десятых
                    elif "load" in k.lower():
                        val_str = f"{val:.1f}"  # Нагрузка (%) с десятыми
                    elif "power" in k.lower() or "pwr" in k.lower():
                        val_str = f"{val:.1f}"  # Мощность (W) с десятыми
                    else:
                        val_str = f"{val:.1f}"  # Температуры и остальное с десятыми
                    
                    values_list.append(val_str)

        # 1-я строка: Чистое время (X) под курсором с выравниванием по правому краю
        time_str = f"<div style='text-align: right;'>{x_time:.1f}</div>"

        # 2-я строка: Значения датчиков активного окна (P1 или P2)
        if values_list:
            chunks = [values_list[i:i + 6] for i in range(0, len(values_list), 6)]
            joined_vals = " | ".join([" | ".join(c) for c in chunks])
            sensors_str = f"{panel_label}: {joined_vals}"
        else:
            sensors_str = f"{panel_label}: —"

        # Собираем через компактную HTML-таблицу (время справа сверху, датчики слева снизу)
        formatted_text = f"""
            <table width='100%' cellspacing='0' cellpadding='0' style='color: #AAAAAA; font-size: 8.5pt;'>
                <tr>
                    <td align='right'><b>{x_time:.1f}</b></td>
                </tr>
                <tr>
                    <td align='left'>{sensors_str}</td>
                </tr>
            </table>
        """
        self.lbl_telemetry_status.setText(formatted_text)

    def update_y_limits(self):
        def compute_limits(col):
            if col is None: 
                return None, None
            
            if self.y_fit_mode == "Raw":
                s_data = self.smooth_series(self.df[col])
            else:
                s_data = self.resample_series(self.df[col], self.current_step)

            valid = s_data[~np.isnan(s_data)]
            if len(valid) == 0:
                return 0.0, 1.0

            mn, mx = float(np.min(valid)), float(np.max(valid))
            pad = (mx - mn) * 0.08 if mx != mn else 1.0
            return mn - pad, mx + pad

        self.vb1.setXRange(0.0, self.total_duration, padding=0)

        # P1 диапазоны
        for s in self.p1_sensors:
            k = s["key"]
            mn, mx = compute_limits(s["col"])
            if k not in self.sensor_y_limits:
                self.sensor_y_limits[k] = [mn, mx]  # Сохраняем исходные жесткие лимиты
            if k in self.viewboxes_map:
                self.viewboxes_map[k].setYRange(mn, mx, padding=0)
                cur_side = self.sensor_sides.get(k, "left")
                target_axis = self.axes_map[k][cur_side]
                target_axis.picture = None
                target_axis.setRange(mn, mx)
                target_axis.update()

        # P2 диапазоны
        for s in self.p2_sensors:
            k = s["key"]
            mn, mx = compute_limits(s["col"])
            if k not in self.sensor_y_limits:
                self.sensor_y_limits[k] = [mn, mx]
            if k in self.viewboxes_map:
                self.viewboxes_map[k].setYRange(mn, mx, padding=0)
                cur_side = self.sensor_sides.get(k, "left")
                target_axis = self.axes_map[k][cur_side]
                target_axis.picture = None
                target_axis.setRange(mn, mx)
                target_axis.update()

    def on_smooth_changed(self, val):
        """Динамически меняет окно сглаживания графиков"""
        global DEFAULT_SMOOTHING
        DEFAULT_SMOOTHING = max(1, val)
        
        # Пересчитываем кривые на графиках с новым сглаживанием
        t_full = self.time_data  # Полный массив времени для сырых данных
        t_res = self.get_resampled_time(self.current_step)  # Рессемплированный для тренда
        
        for s in self.p1_sensors + self.p2_sensors:
            k = s["key"]
            raw_series = self.smooth_series(self.df[s["col"]])
            trend_data = self.resample_series(self.df[s["col"]], self.current_step)
            
            # Обновляем кривые с соответствующими массивами времени
            self.curves[f"{k}_raw"].setData(t_full, raw_series)
            self.curves[f"{k}_trend"].setData(t_res, trend_data)
        
        # Автоматически пересчитываем таблицу Summary по сглаженным данным
        self.populate_summary_table()

    def on_step_changed(self, val):
        self.current_step = max(1, val)
        if self.current_step > 1:
            self.spin_raw.setValue(0.25)
            self.spin_trend.setValue(1.00)
        else:
            self.spin_raw.setValue(1.00)
            self.spin_trend.setValue(0.00)

        self.update_plots_data()
        self.update_y_limits()

    def on_raw_alpha_changed(self, val):
        self.current_raw_alpha = float(val)
        for s in self.p1_sensors + self.p2_sensors:
            k = s["key"]
            self.curves[f"{k}_raw"].setPen(self.create_pen(s['color'], 1.2, self.current_raw_alpha))

    def on_trend_alpha_changed(self, val):
        self.current_trend_alpha = float(val)
        for s in self.p1_sensors + self.p2_sensors:
            k = s["key"]
            self.curves[f"{k}_trend"].setPen(self.create_pen(s['color'], 2.4, self.current_trend_alpha))

    def toggle_y_fit(self):
        if self.y_fit_mode == "Raw":
            self.y_fit_mode = "Trend"
            self.btn_fit.setText("Fit: Trend")
        else:
            self.y_fit_mode = "Raw"
            self.btn_fit.setText("Fit: Raw")
        self.update_y_limits()

    def save_result_action(self):
        QtWidgets.QApplication.processEvents()

        # Гарантируем, что папка для сохранения существует
        os.makedirs(SUMMARY_DIR, exist_ok=True)

        # Сохранение изображения графиков через встроенный векторный экспорт PyQtGraph (обходит OpenGL)
        try:
            import pyqtgraph.exporters as pg_exporters

            # Экспортируем верхний график (P1) во временный файл
            tmp_p1 = self.chart_filepath.replace('.jpg', '_tmp_p1.jpg')
            exporter_p1 = pg_exporters.ImageExporter(self.p1_plot.plotItem)
            exporter_p1.parameters()['width'] = 1200  # Ширина в пикселях для отличного качества
            exporter_p1.export(tmp_p1)

            # Экспортируем нижний график (P2) во временный файл
            tmp_p2 = self.chart_filepath.replace('.jpg', '_tmp_p2.jpg')
            exporter_p2 = pg_exporters.ImageExporter(self.p2_plot.plotItem)
            exporter_p2.parameters()['width'] = 1200
            exporter_p2.export(tmp_p2)

            # Аккуратно склеиваем оба графика вертикально с помощью QImage
            img1 = QtGui.QImage(tmp_p1)
            img2 = QtGui.QImage(tmp_p2)

            w = max(img1.width(), img2.width())
            h1 = img1.height()
            h2 = img2.height()

            combined_image = QtGui.QImage(w, h1 + h2, QtGui.QImage.Format.Format_ARGB32)
            combined_image.fill(QtGui.QColor("#0E0E0E")) # Цвет фона графиков

            painter = QtGui.QPainter(combined_image)
            painter.drawImage(0, 0, img1)
            painter.drawImage(0, h1, img2)
            painter.end()

            # Сохраняем итоговый скриншот графиков
            combined_image.save(self.chart_filepath, "JPG", 92)

            # Удаляем временные файлы
            if os.path.exists(tmp_p1): os.remove(tmp_p1)
            if os.path.exists(tmp_p2): os.remove(tmp_p2)

            print(f"[SUCCESS] Hi-Res charts exported to: {self.chart_filepath}")

        except Exception as ex:
            print(f"[WARNING] ImageExporter failed: {ex}. Falling back to widget grab.")
            pixmap = self.centralWidget().grab()
            pixmap.save(self.chart_filepath, "JPG", 92)

        # Сохранение CSV
        evolution_df = pd.DataFrame()
        evolution_df['Time_Sec'] = self.get_resampled_time(self.current_step)

        for label, sid in PROFILE["export_sensors"]:
            fcol = self.get_col_fn(sid)
            if fcol is not None:
                evolution_df[label] = self.resample_series(self.df[fcol], self.current_step)

        evolution_df.to_csv(self.summary_filepath, index=False)

        print(f"\n[SUCCESS] Hi-Res JPG chart saved to : {self.chart_filepath}")
        print(f"[SUCCESS] Evolution CSV report saved to : {self.summary_filepath} (Avg Step: {self.current_step})\n")


# =======================================================
#                      MAIN ENTRY
# =======================================================
if __name__ == '__main__':
    if not os.path.exists(LOGS_DIR):
        print(f"Error: Directory '{LOGS_DIR}' not found!")
        sys.exit(1)

    os.makedirs(SUMMARY_DIR, exist_ok=True)

    hw_model_name = PROFILE["mode_name"]
    if os.path.exists(HW_INFO_FILE):
        try:
            with open(HW_INFO_FILE, "r", encoding="utf-8") as f:
                hw_info = json.load(f)
                for comp in hw_info.get("components", []):
                    c_name = comp.get("name", "")
                    c_lower = c_name.lower()
                    if PROFILE["mode_name"] == "CPU" and any(x in c_lower for x in ["ryzen", "core i", "threadripper"]) and "cpu" not in c_lower:
                        hw_model_name = c_name
                    elif PROFILE["mode_name"] == "GPU" and any(x in c_lower for x in ["rtx", "gtx", "geforce", "radeon"]):
                        hw_model_name = c_name
        except Exception:
            pass

    files = [f for f in os.listdir(LOGS_DIR) if f.endswith(".csv") and (f.startswith("table_raw_") or not (f.startswith("table_") or f.startswith("graph_") or f.startswith("summary_")))]
    if not files:
        print(f"No CSV test logs found in '{LOGS_DIR}' directory!")
        sys.exit(1)

    print("="*60)
    print(f"         COOLING ANALYZER SUITE [{PROFILE['mode_name']} MODE]         ")
    print("="*60)
    for idx, f in enumerate(files):
        print(f"  [{idx + 1}] {f}")
    print("="*60)

    choice = input(f"Select log file to analyze (default 1): ").strip()
    file_idx = int(choice) - 1 if choice.isdigit() and 1 <= int(choice) <= len(files) else 0

    selected_file = files[file_idx]
    file_path = os.path.join(LOGS_DIR, selected_file)

    try:
        df = pd.read_csv(file_path, header=[0, 1])
        print(f"\nAnalyzing: {selected_file} ({len(df)} samples)")
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        sys.exit(1)

    col_time_first = df.columns[0]
    t_arr = df[col_time_first].to_numpy().astype(float)
    t_norm = t_arr - t_arr[0]
    df[col_time_first] = t_norm

    act_start = float(TIME_START) if (isinstance(TIME_START, (int, float)) and TIME_START > 0.0) else 0.0
    act_end   = float(TIME_END) if (isinstance(TIME_END, (int, float)) and TIME_END < t_norm[-1]) else t_norm[-1]

    if act_start > 0.0 or act_end < t_norm[-1]:
        df = df[(df[col_time_first] >= act_start) & (df[col_time_first] <= act_end)].reset_index(drop=True)
        df[col_time_first] = df[col_time_first] - df[col_time_first].iloc[0]
        print(f"Time Range Cropped         : {act_start:.1f}s - {act_end:.1f}s ({len(df)} samples)")

    app = QtWidgets.QApplication(sys.argv)
    window = CoolingAnalyzerPro(df, selected_file, hw_model_name)
    window.show()
    sys.exit(app.exec())