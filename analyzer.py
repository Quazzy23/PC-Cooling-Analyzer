"""
Интерактивный визуализатор аппаратной телеметрии (PyQt6 + PyQtGraph)
"""
import os
import sys
sys.dont_write_bytecode = True
import json
import numpy as np
import pandas as pd
from PyQt6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from core.defaults import load_sensor_profile, save_user_view_state, load_user_view_state
from core.telemetry_engine import TelemetryEngine
from ui.viewboxes import CleanTimeViewBox, OverlayViewBox
from ui.styles import (
    apply_pg_dark_theme, create_pen, create_timeline_cursor, create_value_tag,
    SPINBOX_CLEAN_QSS, BTN_CYAN_QSS, BTN_GREEN_QSS, TABLE_SUMMARY_QSS,
    BTN_SIDE_QSS, get_sensor_checkbox_qss, get_move_btn_qss
)

# =======================================================
#               MODE & DIRECTORY CONFIGURATION
# =======================================================
ANALYSIS_MODE = "CPU"  # "CPU", "GPU" или None (брать active_mode из sensors_config.json)
PROFILE = load_sensor_profile(ANALYSIS_MODE)

RESULTS_DIR = "results"
LOGS_DIR = os.path.join(RESULTS_DIR, "sensors_logs")
SUMMARY_DIR = os.path.join(RESULTS_DIR, "summary_reports", PROFILE["summary_dir_name"])
HW_INFO_FILE = os.path.join("system_info", "hardware_info.json")

DEFAULT_SMOOTHING = 4
DEFAULT_RAW_ALPHA = 1.0
DEFAULT_TREND_ALPHA = 0.0
TIME_START = 0
TIME_END = "last"
ID_TIME = "TIME_SEC"
# =======================================================

apply_pg_dark_theme()


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
        self.current_time_cursor = 0.0

        # Реестры управления
        self.sensor_sides = {}       # key -> "left" / "right"
        self.sensor_move_active = {} # key -> bool (кнопка M)
        self.sensor_y_limits = {}    # key -> [min_y, max_y]
        self.panning_data = None
        self.curves = {}
        self._persistent_curves = []
        self.time_regions = []
        self.axes_map = {}
        self.viewboxes_map = {}
        self.plot_map = {}
        self.sensor_checkboxes = {}
        self.side_buttons = {}
        self.move_buttons = {}
        self.intersection_tags = {}

        self.resolve_sensors()
        self.init_ui()
        self.populate_summary_table()
        self.apply_saved_or_default_view()
        self.update_plots_data()
        self.update_y_limits()
        self.seek_to_time(0.0)

    def resolve_sensors(self):
        self.col_time = TelemetryEngine.find_column_by_sensor_id(self.df, ID_TIME) or self.df.columns[0]
        raw_t = self.df[self.col_time].to_numpy().astype(float)
        self.time_data = raw_t - raw_t[0]
        self.total_duration = float(self.time_data[-1])

        self.p1_sensors = []
        for s in PROFILE.get("panel1_sensors", []):
            col = TelemetryEngine.find_column_by_sensor_id(self.df, s["id"])
            if col is not None:
                self.p1_sensors.append({**s, "col": col})

        self.p2_sensors = []
        for s in PROFILE.get("panel2_sensors", []):
            col = TelemetryEngine.find_column_by_sensor_id(self.df, s["id"])
            if col is not None:
                self.p2_sensors.append({**s, "col": col})

    def attach_overlay_view(self, plot_widget, color_hex, default_side):
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

    def create_telemetry_plot(self, title_html: str, show_bottom_label: bool = False):
        vb = CleanTimeViewBox(self)
        plot = pg.PlotWidget(viewBox=vb)
        vb.plot_widget = plot

        plot.showGrid(x=True, y=True, alpha=0.18)
        plot.setTitle(title_html, justify='left')
        plot.hideAxis('left')
        plot.hideAxis('right')
        plot.getAxis('bottom').enableAutoSIPrefix(False)
        plot.getAxis('bottom').setPen(pg.mkPen('#444444', width=1))
        plot.getAxis('bottom').setTextPen(pg.mkPen('#AAAAAA'))
        plot.plotItem.layout.setContentsMargins(55, 0, 55, 0)

        if show_bottom_label:
            plot.setLabel('bottom', 'Time (Seconds)')

        cursor = create_timeline_cursor()
        plot.addItem(cursor, ignoreBounds=True)
        return plot, vb, cursor

    def setup_sensors_for_plot(self, sensors: list, plot_widget: pg.PlotWidget):
        for s in sensors:
            k = s["key"]
            self.sensor_sides[k] = s.get("axis", "left")
            self.plot_map[k] = plot_widget

            vb, ax_l, ax_r = self.attach_overlay_view(plot_widget, s['color'], self.sensor_sides[k])
            self.axes_map[k] = {'left': ax_l, 'right': ax_r}
            self.viewboxes_map[k] = vb

            pen_raw = create_pen(s['color'], 1.2, self.current_raw_alpha)
            pen_trend = create_pen(s['color'], 2.4, self.current_trend_alpha)
            smoothed = TelemetryEngine.smooth_series(self.df[s["col"]], DEFAULT_SMOOTHING)

            c_raw = pg.PlotCurveItem(self.time_data, smoothed, pen=pen_raw)
            c_trend = pg.PlotCurveItem(self.time_data, smoothed, pen=pen_trend)

            self.curves[f"{k}_raw"] = c_raw
            self.curves[f"{k}_trend"] = c_trend
            self._persistent_curves.extend([c_raw, c_trend])
            vb.addItem(c_raw)
            vb.addItem(c_trend)

            tag = create_value_tag(s['color'])
            vb.addItem(tag)
            self.intersection_tags[k] = tag

    def init_ui(self):
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QtWidgets.QHBoxLayout(central_widget)
        self.main_layout.setContentsMargins(15, 10, 15, 10)
        self.main_layout.setSpacing(14)

        graphs_container = QtWidgets.QWidget()
        graphs_layout = QtWidgets.QVBoxLayout(graphs_container)
        graphs_layout.setContentsMargins(0, 0, 0, 0)
        graphs_layout.setSpacing(10)

        # 1. Верхний график: Теплофизика (P1)
        p1_title = f"<span style='color: #FFFFFF; font-size: 11pt;'><b>1. {PROFILE['chart_title_prefix']} ({self.hw_model_name} — {self.clean_file_name})</b></span>"
        self.p1_plot, self.vb1, self.cursor_line_p1 = self.create_telemetry_plot(p1_title)
        self.setup_sensors_for_plot(self.p1_sensors, self.p1_plot)
        graphs_layout.addWidget(self.p1_plot, stretch=5)

        # 2. Нижний график: Обороты и Шум (P2)
        p2_title = f"<span style='color: #FFFFFF; font-size: 10pt;'><b>2. {PROFILE['panel2_title']}</b></span>"
        self.p2_plot, self.vb2, self.cursor_line_p2 = self.create_telemetry_plot(p2_title, show_bottom_label=True)
        self.vb2.setXLink(self.vb1)
        self.setup_sensors_for_plot(self.p2_sensors, self.p2_plot)
        graphs_layout.addWidget(self.p2_plot, stretch=3)

        # 3. Нижняя панель управления
        controls_layout = QtWidgets.QHBoxLayout()
        controls_layout.setSpacing(12)

        lbl_smooth = QtWidgets.QLabel("Smooth:")
        lbl_smooth.setStyleSheet("color: white; font-size: 9pt;")
        controls_layout.addWidget(lbl_smooth)

        self.spin_smooth = QtWidgets.QSpinBox()
        self.spin_smooth.setRange(1, 30)
        self.spin_smooth.setValue(DEFAULT_SMOOTHING)
        self.spin_smooth.setFixedWidth(65)
        self.spin_smooth.setStyleSheet(SPINBOX_CLEAN_QSS)
        self.spin_smooth.valueChanged.connect(self.on_smooth_changed)
        controls_layout.addWidget(self.spin_smooth)

        controls_layout.addSpacing(6)

        lbl_step = QtWidgets.QLabel("Step:")
        lbl_step.setStyleSheet("color: white; font-weight: bold; font-size: 9pt;")
        controls_layout.addWidget(lbl_step)

        self.spin_step = QtWidgets.QSpinBox()
        self.spin_step.setRange(1, 200)
        self.spin_step.setSingleStep(5)
        self.spin_step.setValue(self.current_step)
        self.spin_step.setFixedWidth(65)
        self.spin_step.setStyleSheet(SPINBOX_CLEAN_QSS)
        self.spin_step.valueChanged.connect(self.on_step_changed)
        controls_layout.addWidget(self.spin_step)

        lbl_raw = QtWidgets.QLabel("Raw Fog:")
        lbl_raw.setStyleSheet("color: white; font-size: 9pt;")
        controls_layout.addWidget(lbl_raw)

        self.spin_raw = QtWidgets.QDoubleSpinBox()
        self.spin_raw.setRange(0.0, 1.0)
        self.spin_raw.setSingleStep(0.05)
        self.spin_raw.setValue(self.current_raw_alpha)
        self.spin_raw.setFixedWidth(65)
        self.spin_raw.setStyleSheet(SPINBOX_CLEAN_QSS)
        self.spin_raw.valueChanged.connect(self.on_raw_alpha_changed)
        controls_layout.addWidget(self.spin_raw)

        lbl_trend = QtWidgets.QLabel("Trend A:")
        lbl_trend.setStyleSheet("color: white; font-size: 9pt;")
        controls_layout.addWidget(lbl_trend)

        self.spin_trend = QtWidgets.QDoubleSpinBox()
        self.spin_trend.setRange(0.0, 1.0)
        self.spin_trend.setSingleStep(0.05)
        self.spin_trend.setValue(self.current_trend_alpha)
        self.spin_trend.setFixedWidth(65)
        self.spin_trend.setStyleSheet(SPINBOX_CLEAN_QSS)
        self.spin_trend.valueChanged.connect(self.on_trend_alpha_changed)
        controls_layout.addWidget(self.spin_trend)

        controls_layout.addSpacing(6)

        self.btn_fit = QtWidgets.QPushButton("Fit: Raw")
        self.btn_fit.setFixedSize(95, 32)
        self.btn_fit.setStyleSheet(BTN_CYAN_QSS)
        self.btn_fit.clicked.connect(self.toggle_y_fit)
        controls_layout.addWidget(self.btn_fit)

        self.btn_save = QtWidgets.QPushButton("Save Result")
        self.btn_save.setFixedSize(115, 32)
        self.btn_save.setStyleSheet(BTN_GREEN_QSS)
        self.btn_save.clicked.connect(self.save_result_action)
        controls_layout.addWidget(self.btn_save)

        controls_layout.addStretch()
        
        self.lbl_telemetry_status = QtWidgets.QLabel("Click [LMB] on charts to place timeline cursor...")
        self.lbl_telemetry_status.setStyleSheet("color: #888888; font-style: italic; font-size: 8.5pt;")
        controls_layout.addWidget(self.lbl_telemetry_status)

        graphs_layout.addLayout(controls_layout)

        # 4. Боковая панель: Таблица + Паспорт датчиков + Сохранение вида
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
        self.table_summary.setStyleSheet(TABLE_SUMMARY_QSS)
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

        # Кнопка сохранения текущего вида
        self.btn_save_view = QtWidgets.QPushButton("Save View Preset")
        self.btn_save_view.setFixedHeight(30)
        self.btn_save_view.setToolTip("Saves current visibility, axis side and zoom M-state to view_state.json")
        self.btn_save_view.setStyleSheet(BTN_CYAN_QSS)
        self.btn_save_view.clicked.connect(self.save_view_preset_action)
        sb_layout.addWidget(self.btn_save_view)

        self.main_layout.addWidget(graphs_container, stretch=7)
        self.main_layout.addWidget(sidebar, stretch=3)

    def add_passport_row(self, s):
        k = s["key"]
        row_widget = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(2, 0, 2, 0)
        row_layout.setSpacing(4)
        row_widget.setFixedHeight(24)

        is_default_vis = s.get("visible", False)
        cb = QtWidgets.QCheckBox(s['label'])
        cb.blockSignals(True)
        cb.setChecked(is_default_vis)
        cb.blockSignals(False)
        cb.setStyleSheet(get_sensor_checkbox_qss(s['color']))
        cb.toggled.connect(lambda checked, key=k: self.toggle_curve_visibility(key, checked))
        row_layout.addWidget(cb, stretch=1)
        self.sensor_checkboxes[k] = cb

        cur_side = self.sensor_sides.get(k, "left")
        side_text = "L" if cur_side == "left" else "R"
        btn_side = QtWidgets.QPushButton(side_text)
        btn_side.setFixedSize(20, 17)
        btn_side.setToolTip("Toggle Axis Side (Left / Right)")
        btn_side.setStyleSheet(BTN_SIDE_QSS)
        btn_side.clicked.connect(lambda _, key=k, btn=btn_side: self.toggle_axis_side(key, btn))
        row_layout.addWidget(btn_side)
        self.side_buttons[k] = btn_side

        self.sensor_move_active[k] = False
        btn_move = QtWidgets.QPushButton("M")
        btn_move.setFixedSize(20, 17)
        btn_move.setToolTip("Enable/Disable Zoom & Pan for this sensor")
        btn_move.setStyleSheet(get_move_btn_qss(False))
        btn_move.clicked.connect(lambda _, key=k, btn=btn_move: self.toggle_sensor_move(key, btn))
        row_layout.addWidget(btn_move)
        self.move_buttons[k] = btn_move

        self.passport_layout.addWidget(row_widget)

    def toggle_axis_side(self, key, btn, force_side=None):
        if key not in self.axes_map: return
        current_side = self.sensor_sides.get(key, "left")
        new_side = force_side if force_side else ("right" if current_side == "left" else "left")
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

    def toggle_sensor_move(self, key, btn, force_state=None):
        current_state = self.sensor_move_active.get(key, False)
        new_state = force_state if force_state is not None else (not current_state)
        self.sensor_move_active[key] = new_state
        btn.setStyleSheet(get_move_btn_qss(new_state))

    def toggle_curve_visibility(self, key, is_visible):
        if f"{key}_raw" in self.curves:
            self.curves[f"{key}_raw"].setVisible(is_visible)
            self.curves[f"{key}_trend"].setVisible(is_visible)

        if key in self.intersection_tags:
            self.intersection_tags[key].setVisible(is_visible)

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
        
        self.seek_to_time(self.current_time_cursor)

    def save_view_preset_action(self):
        """Сохраняет текущий вид (чекбоксы, оси L/R, кнопки M) в view_state.json"""
        state_dict = {}
        all_sensors = self.p1_sensors + self.p2_sensors
        for s in all_sensors:
            k = s["key"]
            sid = s["id"]
            state_dict[sid] = {
                "visible": self.sensor_checkboxes[k].isChecked() if k in self.sensor_checkboxes else True,
                "axis": self.sensor_sides.get(k, "left"),
                "move": self.sensor_move_active.get(k, False)
            }

        save_user_view_state(PROFILE["mode_name"], state_dict)
        self.btn_save_view.setText("Preset Saved!")
        QtCore.QTimer.singleShot(2000, lambda: self.btn_save_view.setText("Save View Preset"))
        print(f"[OK] View preset for {PROFILE['mode_name']} saved successfully.")

    def apply_saved_or_default_view(self):
        """Принудительно и строго применяет видимость и стороны осей к кривым и интерфейсу"""
        saved_state = load_user_view_state(PROFILE["mode_name"])
        all_sensors = self.p1_sensors + self.p2_sensors

        for s in all_sensors:
            k = s["key"]
            sid = s["id"]

            if sid in saved_state:
                s_cfg = saved_state[sid]
                is_vis = s_cfg.get("visible", False)
                axis_side = s_cfg.get("axis", "left")
                is_move = s_cfg.get("move", False)

                if k in self.sensor_checkboxes:
                    self.sensor_checkboxes[k].blockSignals(True)
                    self.sensor_checkboxes[k].setChecked(is_vis)
                    self.sensor_checkboxes[k].blockSignals(False)

                if k in self.side_buttons:
                    self.toggle_axis_side(k, self.side_buttons[k], force_side=axis_side)

                if k in self.move_buttons:
                    self.toggle_sensor_move(k, self.move_buttons[k], force_state=is_move)

                # ПРИНУДИТЕЛЬНО скрываем/показываем линию графика и шкалу
                self.toggle_curve_visibility(k, is_vis)
            else:
                if k in self.sensor_checkboxes:
                    self.sensor_checkboxes[k].blockSignals(True)
                    self.sensor_checkboxes[k].setChecked(False)
                    self.sensor_checkboxes[k].blockSignals(False)

                if k in self.side_buttons:
                    self.toggle_axis_side(k, self.side_buttons[k], force_side="left")

                if k in self.move_buttons:
                    self.toggle_sensor_move(k, self.move_buttons[k], force_state=False)

                # ПРИНУДИТЕЛЬНО скрываем всё для дефолта
                self.toggle_curve_visibility(k, False)

    def seek_to_time(self, target_sec: float):
        self.current_time_cursor = max(0.0, min(self.total_duration, target_sec))
        self.cursor_line_p1.setPos(self.current_time_cursor)
        self.cursor_line_p2.setPos(self.current_time_cursor)

        all_sensors = self.p1_sensors + self.p2_sensors
        for s in all_sensors:
            k = s["key"]
            is_vis = k in self.sensor_checkboxes and self.sensor_checkboxes[k].isChecked()
            tag = self.intersection_tags.get(k)

            if is_vis:
                series = TelemetryEngine.smooth_series(self.df[s["col"]], DEFAULT_SMOOTHING)
                val_at_t = float(np.interp(self.current_time_cursor, self.time_data, series))

                if "volt" in k.lower(): val_str = f"{val_at_t:.3f}"
                elif "RPM" in s["label"] or "clock" in s["label"].lower(): val_str = f"{val_at_t:.0f}"
                else: val_str = f"{val_at_t:.1f}"

                if tag is not None:
                    tag.setVisible(True)
                    tag.setText(f" {val_str}")
                    tag.setPos(self.current_time_cursor, val_at_t)
            else:
                if tag is not None:
                    tag.setVisible(False)

    def add_time_region(self, t_min, t_max):
        from ui.styles import create_clean_region
        reg_p1 = create_clean_region(t_min, t_max)
        reg_p2 = create_clean_region(t_min, t_max)

        self.p1_plot.addItem(reg_p1, ignoreBounds=True)
        self.p2_plot.addItem(reg_p2, ignoreBounds=True)

        self.time_regions.append({'t_min': t_min, 't_max': t_max, 'item_p1': reg_p1, 'item_p2': reg_p2})
        self.populate_summary_table()

    def handle_right_click_on_timeline(self, t_click):
        target_idx = None
        for idx, reg in enumerate(self.time_regions):
            if reg['t_min'] <= t_click <= reg['t_max']:
                target_idx = idx
                break

        if target_idx is not None:
            removed = self.time_regions.pop(target_idx)
            self.p1_plot.removeItem(removed['item_p1'])
            self.p2_plot.removeItem(removed['item_p2'])
        else:
            self.clear_all_time_regions()

        self.populate_summary_table()

    def clear_all_time_regions(self):
        for reg in self.time_regions:
            self.p1_plot.removeItem(reg['item_p1'])
            self.p2_plot.removeItem(reg['item_p2'])
        self.time_regions.clear()
        self.populate_summary_table()

    def populate_summary_table(self):
        smooth_val = self.spin_smooth.value() if hasattr(self, 'spin_smooth') else DEFAULT_SMOOTHING
        rows, ranges_title = TelemetryEngine.compute_summary_rows(
            self.df, self.col_time, self.time_regions,
            self.p1_sensors, self.p2_sensors, None,
            smoothing_window=smooth_val
        )

        if self.time_regions:
            self.lbl_summary_title.setText(f"<b>SUMMARY METRICS</b> <span style='color:#00E5FF; font-size:7.5pt;'>({ranges_title})</span>")
        else:
            self.lbl_summary_title.setText(f"<b>SUMMARY METRICS</b> <span style='color:#888; font-size:8pt;'>({PROFILE['mode_name']} Total)</span>")

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

    def update_plots_data(self):
        t_res = TelemetryEngine.get_resampled_time(self.time_data, self.current_step)
        for s in self.p1_sensors + self.p2_sensors:
            k = s["key"]
            trend_data = TelemetryEngine.resample_series(self.df[s["col"]], self.current_step)
            self.curves[f"{k}_trend"].setData(t_res, trend_data)

    def update_y_limits(self):
        def compute_limits(col):
            if col is None: return None, None
            s_data = TelemetryEngine.smooth_series(self.df[col], DEFAULT_SMOOTHING) if self.y_fit_mode == "Raw" else TelemetryEngine.resample_series(self.df[col], self.current_step)
            valid = s_data[~np.isnan(s_data)]
            if len(valid) == 0: return 0.0, 1.0
            mn, mx = float(np.min(valid)), float(np.max(valid))
            pad = (mx - mn) * 0.08 if mx != mn else 1.0
            return mn - pad, mx + pad

        self.vb1.setXRange(0.0, self.total_duration, padding=0)

        for s in self.p1_sensors + self.p2_sensors:
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
        global DEFAULT_SMOOTHING
        DEFAULT_SMOOTHING = max(1, val)
        t_full = self.time_data
        t_res = TelemetryEngine.get_resampled_time(self.time_data, self.current_step)

        for s in self.p1_sensors + self.p2_sensors:
            k = s["key"]
            raw_series = TelemetryEngine.smooth_series(self.df[s["col"]], DEFAULT_SMOOTHING)
            trend_data = TelemetryEngine.resample_series(self.df[s["col"]], self.current_step)
            self.curves[f"{k}_raw"].setData(t_full, raw_series)
            self.curves[f"{k}_trend"].setData(t_res, trend_data)

        self.populate_summary_table()
        self.seek_to_time(self.current_time_cursor)

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
            self.curves[f"{s['key']}_raw"].setPen(create_pen(s['color'], 1.2, self.current_raw_alpha))

    def on_trend_alpha_changed(self, val):
        self.current_trend_alpha = float(val)
        for s in self.p1_sensors + self.p2_sensors:
            self.curves[f"{s['key']}_trend"].setPen(create_pen(s['color'], 2.4, self.current_trend_alpha))

    def toggle_y_fit(self):
        self.y_fit_mode = "Trend" if self.y_fit_mode == "Raw" else "Raw"
        self.btn_fit.setText(f"Fit: {self.y_fit_mode}")
        self.update_y_limits()

    def save_result_action(self):
        QtWidgets.QApplication.processEvents()
        TelemetryEngine.export_summary_and_chart(
            summary_dir=SUMMARY_DIR,
            chart_filepath=self.chart_filepath,
            summary_filepath=self.summary_filepath,
            p1_plot=self.p1_plot,
            p2_plot=self.p2_plot,
            df=self.df,
            time_data=self.time_data,
            current_step=self.current_step,
            export_sensors=PROFILE["export_sensors"],
            get_col_fn=lambda sid: TelemetryEngine.find_column_by_sensor_id(self.df, sid)
        )
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
        df, _ = TelemetryEngine.load_log_file(file_path, TIME_START, TIME_END)
        print(f"\nAnalyzing: {selected_file} ({len(df)} samples)")
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        sys.exit(1)

    app = QtWidgets.QApplication(sys.argv)
    window = CoolingAnalyzerPro(df, selected_file, hw_model_name)
    window.show()
    sys.exit(app.exec())