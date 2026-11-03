"""Главный исполняемый модуль: единая студия аппаратной телеметрии и спектрального анализа."""
import os
import sys
import json
import numpy as np
import pandas as pd
from PyQt6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from core.defaults import (
    load_sensor_profile, get_available_profiles,
    save_all_session_view_states, load_user_view_state, load_last_active_mode,
    AUDIO_PROFILE
)
from core.telemetry_engine import TelemetryEngine
from core.audio_engine import AudioEngine, LIMIT_FREQ_MIN
from ui.viewboxes import OverlayViewBox
from ui.styles import (
    apply_pg_dark_theme, create_pen, create_value_tag, 
    create_clean_region, create_clean_2d_rect_item,
    BTN_GREEN_QSS, BTN_RED_QSS, get_move_btn_qss,
    COMBOBOX_CLEAN_QSS, TOP_BAR_FRAME_QSS, SPLITTER_HORIZONTAL_QSS,
    BTN_MODULE_ACTIVE_QSS, BTN_MODULE_INACTIVE_QSS
)
from ui.sidebar import StudioSidebar
from ui.telemetry_panel import TelemetryPanel
from ui.audio_panel import AudioPanel
from core.texts import (
    LBL_PROFILE, LBL_MODULES, BTN_TOGGLE_TELEMETRY, BTN_TOGGLE_AUDIO,
    HEADER_DATASET_INFO_TEMPLATE, WINDOW_TITLE_TEMPLATE, BTN_CSV_SAVED,
    BTN_SAVE_RESULT, MSG_SELECT_LOG, MSG_ANALYZING, MSG_PAIRED_AUDIO,
    MSG_ERR_NO_LOGS, MSG_ERR_DIR_NOT_FOUND, MSG_ERR_READ_CSV,
    MSG_EXPORT_SUCCESS, MSG_VIEW_PRESET_SAVED, MSG_WARN_NO_SENSORS,
    APP_BANNER
)

# Абсолютные системные пути проекта
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

SYS_INFO_DIR = os.path.join(PROJECT_ROOT, "system_info")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
HW_INFO_FILE = os.path.join(SYS_INFO_DIR, "hardware_info.json")

DEFAULT_SMOOTHING = 4
DEFAULT_RAW_ALPHA = 1.0
DEFAULT_TREND_ALPHA = 0.0
TIME_START = 0
TIME_END = "last"
ID_TIME = "TIME_SEC"
ISOLATE_FFT_ON_FILTER = AUDIO_PROFILE.get("isolate_fft_on_filter", 0)

apply_pg_dark_theme()


class StudioSuiteWindow(QtWidgets.QMainWindow):
    """Главное окно приложения: объединяет сайдбар, телеметрию P1/P2 и аудиоанализатор."""
    def __init__(self, df, selected_file, cpu_name="CPU", gpu_name="GPU", audio_path=None):
        super().__init__()
        self.df = df
        self.selected_file = selected_file
        self.cpu_name = cpu_name
        self.gpu_name = gpu_name
        self.clean_file_name = selected_file.replace("table_raw_", "").replace("table_", "")

        # Загрузка профиля и путей отчетов
        self.current_mode = load_last_active_mode()
        self.profile = load_sensor_profile(self.current_mode)
        self.update_report_paths()

        # Инициализация аудиодвижка при наличии аудиодорожки
        self.audio_path = audio_path
        self.engine = AudioEngine(audio_path) if (audio_path and os.path.exists(audio_path)) else None
        self.total_duration_audio = self.engine.total_duration if self.engine else 0.0

        self.setWindowTitle(WINDOW_TITLE_TEMPLATE.format(mode=self.profile['mode_name'], file=self.clean_file_name))
        self.resize(1850, 960)

        # Состояния рендера и параметров
        self.current_step = 1
        self.current_raw_alpha = DEFAULT_RAW_ALPHA
        self.current_trend_alpha = DEFAULT_TREND_ALPHA
        self.y_fit_mode = "Raw"
        self.current_time_cursor = 0.0
        self.freq_scale_mode = "Log"
        self.spec_db_matrix = None
        self.spec_f_min = LIMIT_FREQ_MIN
        self.spec_f_max = (self.engine.sample_rate / 2.0) if self.engine else 8000.0

        # Реестры элементов графиков и настроек
        self.sensor_sides = {}
        self.sensor_move_active = {}
        self.sensor_visibility = {}
        self.sensor_colors = {}
        self.sensor_y_limits = {}
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
        self.session_view_states = {}

        self.resolve_sensors()
        self.init_ui()
        self.apply_saved_or_default_view()
        self.populate_summary_table()
        self.update_plots_data()
        self.update_y_limits()
        self.seek_to_time(0.0)

        if self.engine:
            self.calculate_and_render_spectrogram()
            self.audio_timer = QtCore.QTimer()
            self.audio_timer.timeout.connect(self.update_playhead)
            self.audio_timer.start(16)

    def get_current_hardware_name(self) -> str:
        """Возвращает строку модели активного процессора и видеокарты."""
        if self.current_mode == "CPU":
            return self.cpu_name
        elif self.current_mode == "GPU":
            return self.gpu_name
        return f"{self.cpu_name} | {self.gpu_name}"

    def update_report_paths(self):
        """Обновляет пути сохранения отчетов для активного профиля."""
        self.summary_dir = os.path.join(RESULTS_DIR, "summary_reports", self.profile["summary_dir_name"])
        self.chart_filename = f"graph_{self.clean_file_name.replace('.csv', '.jpg')}"
        self.chart_filepath = os.path.join(self.summary_dir, self.chart_filename)
        self.summary_filename = f"table_{self.clean_file_name}"
        self.summary_filepath = os.path.join(self.summary_dir, self.summary_filename)

    def resolve_sensors(self):
        """Сопоставляет датчики профиля с колонками датасета и восстанавливает сохраненные слои."""
        self.col_time = TelemetryEngine.find_column_by_sensor_id(self.df, ID_TIME) or self.df.columns[0]
        raw_t = self.df[self.col_time].to_numpy().astype(float)
        self.time_data = raw_t - raw_t[0]
        self.total_duration_telemetry = float(self.time_data[-1])
        self.total_duration = max(self.total_duration_telemetry, self.total_duration_audio)

        all_raw_sensors = {}
        for s in self.profile.get("panel1_sensors", []) + self.profile.get("panel2_sensors", []):
            col = TelemetryEngine.find_column_by_sensor_id(self.df, s["id"])
            if col is not None:
                all_raw_sensors[s["id"]] = {**s, "col": col}

        saved_state = self.session_view_states.get(self.profile["mode_name"])
        if saved_state is None:
            saved_state = load_user_view_state(self.profile["mode_name"])

        self.p1_sensors = []
        self.p2_sensors = []

        if isinstance(saved_state, dict) and ("panel1" in saved_state or "panel2" in saved_state):
            assigned_ids = set()
            for item in saved_state.get("panel1", []):
                sid = item.get("id")
                if sid in all_raw_sensors:
                    s_data = dict(all_raw_sensors[sid])
                    if item.get("color"):
                        s_data["color"] = item["color"]
                    self.p1_sensors.append(s_data)
                    assigned_ids.add(sid)

            for item in saved_state.get("panel2", []):
                sid = item.get("id")
                if sid in all_raw_sensors:
                    s_data = dict(all_raw_sensors[sid])
                    if item.get("color"):
                        s_data["color"] = item["color"]
                    self.p2_sensors.append(s_data)
                    assigned_ids.add(sid)

            for sid, s_data in all_raw_sensors.items():
                if sid not in assigned_ids:
                    self.p1_sensors.append(s_data)
        else:
            for s in self.profile.get("panel1_sensors", []):
                if s["id"] in all_raw_sensors:
                    self.p1_sensors.append(dict(all_raw_sensors[s["id"]]))
            for s in self.profile.get("panel2_sensors", []):
                if s["id"] in all_raw_sensors:
                    self.p2_sensors.append(dict(all_raw_sensors[s["id"]]))

        for s in self.p1_sensors + self.p2_sensors:
            self.sensor_colors[s["key"]] = s["color"]

        total_found = len(self.p1_sensors) + len(self.p2_sensors)
        if total_found == 0:
            configured_cnt = len(self.profile.get('panel1_sensors', [])) + len(self.profile.get('panel2_sensors', []))
            print(MSG_WARN_NO_SENSORS.format(mode=self.current_mode, file=self.selected_file, configured=configured_cnt))

    def attach_overlay_view(self, plot_widget, color_hex, default_side):
        """Создает и привязывает независимый ViewBox и шкалы оси Y для датчика."""
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

        ax_left.setVisible(default_side == 'left')
        ax_right.setVisible(default_side == 'right')

        def sync_views():
            rect = plot_widget.plotItem.vb.sceneBoundingRect()
            if rect.width() > 1 and rect.height() > 1:
                vb.setGeometry(rect)
                vb.setXRange(*plot_widget.plotItem.vb.viewRange()[0], padding=0)
                ax_left.setGeometry(QtCore.QRectF(rect.left() - 50, rect.top(), 50, rect.height()))
                ax_right.setGeometry(QtCore.QRectF(rect.right(), rect.top(), 50, rect.height()))

        plot_widget.plotItem.vb.sigResized.connect(sync_views)
        plot_widget.plotItem.vb.sigRangeChanged.connect(sync_views)
        sync_views()
        return vb, ax_left, ax_right

    def setup_sensors_for_plot(self, sensors: list, plot_widget: pg.PlotWidget):
        """Инициализирует графические элементы кривых и меток для списка датчиков."""
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
            c_raw.setVisible(False)
            c_trend.setVisible(False)

            self.curves[f"{k}_raw"] = c_raw
            self.curves[f"{k}_trend"] = c_trend
            self._persistent_curves.extend([c_raw, c_trend])
            vb.addItem(c_raw)
            vb.addItem(c_trend)

            tag = create_value_tag(s['color'])
            tag.setVisible(False)
            vb.addItem(tag)
            self.intersection_tags[k] = tag

    def init_ui(self):
        """Сборка основного интерфейса приложения."""
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QtWidgets.QVBoxLayout(central_widget)
        root_layout.setContentsMargins(12, 8, 12, 10)
        root_layout.setSpacing(8)

        # Верхняя панель управления (Top Bar)
        top_bar = QtWidgets.QFrame()
        top_bar.setFixedHeight(40)
        top_bar.setStyleSheet(TOP_BAR_FRAME_QSS)
        top_layout = QtWidgets.QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 4, 10, 4)
        top_layout.setSpacing(10)

        lbl_prof = QtWidgets.QLabel(f"<b>{LBL_PROFILE}</b>")
        lbl_prof.setStyleSheet("color: #00E5FF; font-size: 9pt; border: none;")
        top_layout.addWidget(lbl_prof)

        self.combo_profile = QtWidgets.QComboBox()
        self.combo_profile.setStyleSheet(COMBOBOX_CLEAN_QSS)
        self.combo_profile.setFixedWidth(100)
        available_modes = get_available_profiles()
        self.combo_profile.addItems(available_modes)

        curr_idx = self.combo_profile.findText(self.profile["mode_name"])
        if curr_idx >= 0:
            self.combo_profile.setCurrentIndex(curr_idx)

        self.combo_profile.currentTextChanged.connect(self.on_profile_switched)
        top_layout.addWidget(self.combo_profile)

        top_layout.addSpacing(6)
        sep1 = QtWidgets.QFrame()
        sep1.setFrameShape(QtWidgets.QFrame.Shape.VLine)
        sep1.setStyleSheet("color: #333333; border: none;")
        top_layout.addWidget(sep1)

        lbl_modules = QtWidgets.QLabel(f"<b>{LBL_MODULES}</b>")
        lbl_modules.setStyleSheet("color: #888888; font-size: 8.5pt; border: none;")
        top_layout.addWidget(lbl_modules)

        self.btn_toggle_telemetry = QtWidgets.QPushButton(BTN_TOGGLE_TELEMETRY)
        self.btn_toggle_telemetry.setCheckable(True)
        self.btn_toggle_telemetry.setChecked(True)
        self.btn_toggle_telemetry.setFixedHeight(28)
        self.btn_toggle_telemetry.clicked.connect(self.toggle_telemetry_module)
        top_layout.addWidget(self.btn_toggle_telemetry)

        self.btn_toggle_audio = QtWidgets.QPushButton(BTN_TOGGLE_AUDIO)
        self.btn_toggle_audio.setCheckable(True)
        self.btn_toggle_audio.setChecked(True)
        self.btn_toggle_audio.setFixedHeight(28)
        self.btn_toggle_audio.clicked.connect(self.toggle_audio_module)
        top_layout.addWidget(self.btn_toggle_audio)

        self._update_module_buttons_style()
        top_layout.addStretch()

        lbl_info = QtWidgets.QLabel(HEADER_DATASET_INFO_TEMPLATE.format(
            file=self.clean_file_name, cpu=self.cpu_name, gpu=self.gpu_name
        ))
        lbl_info.setStyleSheet("font-size: 8.5pt; border: none;")
        top_layout.addWidget(lbl_info)

        root_layout.addWidget(top_bar)

        # Главная область сплиттеров графиков
        self.sidebar = StudioSidebar(self)
        self.telemetry_panel = TelemetryPanel(self)
        self.audio_panel = AudioPanel(self)

        self.audio_panel.spec_vb.setXLink(self.telemetry_panel.vb1)
        self.telemetry_panel.vb2.setXLink(self.telemetry_panel.vb1)

        self.plots_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.plots_splitter.setHandleWidth(8)
        self.plots_splitter.setChildrenCollapsible(False)
        self.plots_splitter.setStyleSheet(SPLITTER_HORIZONTAL_QSS)
        self.plots_splitter.addWidget(self.telemetry_panel)
        self.plots_splitter.addWidget(self.audio_panel)
        self.plots_splitter.setStretchFactor(0, 1)
        self.plots_splitter.setStretchFactor(1, 1)

        self.outer_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.outer_splitter.setHandleWidth(8)
        self.outer_splitter.setChildrenCollapsible(False)
        self.outer_splitter.setStyleSheet(SPLITTER_HORIZONTAL_QSS)
        self.outer_splitter.addWidget(self.sidebar)
        self.outer_splitter.addWidget(self.plots_splitter)
        self.outer_splitter.setStretchFactor(0, 0)
        self.outer_splitter.setStretchFactor(1, 1)

        root_layout.addWidget(self.outer_splitter, stretch=1)

    def _update_module_buttons_style(self):
        """Обновляет подсветку активных тумблеров модулей."""
        self.btn_toggle_telemetry.setStyleSheet(
            BTN_MODULE_ACTIVE_QSS if self.btn_toggle_telemetry.isChecked() else BTN_MODULE_INACTIVE_QSS
        )
        self.btn_toggle_audio.setStyleSheet(
            BTN_MODULE_ACTIVE_QSS if self.btn_toggle_audio.isChecked() else BTN_MODULE_INACTIVE_QSS
        )

    def toggle_telemetry_module(self, checked):
        """Включает или скрывает блок аппаратной телеметрии."""
        if not checked and not self.btn_toggle_audio.isChecked():
            self.btn_toggle_telemetry.setChecked(True)
            return
        self.sidebar.setVisible(checked)
        self.telemetry_panel.setVisible(checked)
        self._update_module_buttons_style()
        self._rebalance_splitter()

    def toggle_audio_module(self, checked):
        """Включает или скрывает блок акустического анализатора."""
        if not checked and not self.btn_toggle_telemetry.isChecked():
            self.btn_toggle_audio.setChecked(True)
            return
        self.audio_panel.setVisible(checked)
        self._update_module_buttons_style()
        self._rebalance_splitter()

    def _fit_timelines_to_full_duration(self):
        """Синхронно подгоняет шкалу времени графиков к общей длительности записи."""
        if hasattr(self, 'telemetry_panel') and hasattr(self.telemetry_panel, 'vb1'):
            self.telemetry_panel.vb1.setXRange(0.0, self.total_duration, padding=0)
        if hasattr(self, 'audio_panel') and hasattr(self.audio_panel, 'spec_vb'):
            self.audio_panel.spec_vb.setXRange(0.0, self.total_duration, padding=0)
        self.sync_all_overlay_views()

    def sync_all_overlay_views(self):
        """Синхронизирует геометрию всех наложенных шкал и вьюбоксов."""
        for p_plot, sensors in [(self.telemetry_panel.p1_plot, self.p1_sensors), (self.telemetry_panel.p2_plot, self.p2_sensors)]:
            rect = p_plot.plotItem.vb.sceneBoundingRect()
            if rect.width() <= 1 or rect.height() <= 1:
                continue
            vr_x = p_plot.plotItem.vb.viewRange()[0]
            for s in sensors:
                k = s["key"]
                if k in self.viewboxes_map:
                    vb = self.viewboxes_map[k]
                    vb.setGeometry(rect)
                    vb.setXRange(vr_x[0], vr_x[1], padding=0)
                if k in self.axes_map:
                    ax_l = self.axes_map[k]['left']
                    ax_r = self.axes_map[k]['right']
                    ax_l.setGeometry(QtCore.QRectF(rect.left() - 50, rect.top(), 50, rect.height()))
                    ax_r.setGeometry(QtCore.QRectF(rect.right(), rect.top(), 50, rect.height()))

    def showEvent(self, event):
        """Обработка начального показа окна и пропорций сплиттеров."""
        super().showEvent(event)
        QtCore.QTimer.singleShot(30, self.sync_all_overlay_views)
        QtCore.QTimer.singleShot(30, self.update_y_limits)
        QtCore.QTimer.singleShot(50, lambda: self.outer_splitter.setSizes([340, 1500]))
        QtCore.QTimer.singleShot(50, lambda: self.plots_splitter.setSizes([750, 750]))
        QtCore.QTimer.singleShot(70, self._fit_timelines_to_full_duration)
        QtCore.QTimer.singleShot(80, self.sidebar.auto_fit_sidebar_splitters)

    def _rebalance_splitter(self):
        """Перераспределяет пространство сплиттеров при скрытии одного из модулей."""
        t_vis = self.btn_toggle_telemetry.isChecked()
        a_vis = self.btn_toggle_audio.isChecked()

        if t_vis and a_vis:
            self.sidebar.setVisible(True)
            self.telemetry_panel.setVisible(True)
            self.audio_panel.setVisible(True)
            self.outer_splitter.setSizes([340, 1500])
            self.plots_splitter.setSizes([750, 750])
        elif t_vis and not a_vis:
            self.sidebar.setVisible(True)
            self.telemetry_panel.setVisible(True)
            self.audio_panel.setVisible(False)
            self.outer_splitter.setSizes([340, 1500])
        elif not t_vis and a_vis:
            self.sidebar.setVisible(False)
            self.telemetry_panel.setVisible(False)
            self.audio_panel.setVisible(True)

        QtCore.QTimer.singleShot(50, self._fit_timelines_to_full_duration)

    def on_profile_switched(self, new_mode: str):
        """Переключает профиль датчиков (CPU, GPU и др.) с сохранением состояния текущего."""
        if not new_mode or new_mode == self.current_mode:
            return

        current_state = {}
        for s in self.p1_sensors + self.p2_sensors:
            k = s["key"]
            sid = s["id"]
            current_state[sid] = {
                "visible": self.sensor_checkboxes[k].isChecked() if k in self.sensor_checkboxes else False,
                "axis": self.sensor_sides.get(k, "left"),
                "move": self.sensor_move_active.get(k, False)
            }
        self.session_view_states[self.current_mode] = current_state

        self.current_mode = new_mode
        self.profile = load_sensor_profile(self.current_mode)
        self.update_report_paths()

        self.setWindowTitle(WINDOW_TITLE_TEMPLATE.format(mode=self.profile['mode_name'], file=self.clean_file_name))

        for k, vb in list(self.viewboxes_map.items()):
            if vb.scene() is not None:
                vb.scene().removeItem(vb)
        for k, axes in list(self.axes_map.items()):
            for ax in axes.values():
                if ax.scene() is not None:
                    ax.scene().removeItem(ax)
        for k, tag in list(self.intersection_tags.items()):
            if tag.scene() is not None:
                tag.scene().removeItem(tag)

        self.sensor_sides.clear()
        self.sensor_move_active.clear()
        self.sensor_y_limits.clear()
        self.curves.clear()
        self._persistent_curves.clear()
        self.axes_map.clear()
        self.viewboxes_map.clear()
        self.plot_map.clear()
        self.sensor_checkboxes.clear()
        self.side_buttons.clear()
        self.move_buttons.clear()
        self.intersection_tags.clear()

        self.resolve_sensors()
        self.setup_sensors_for_plot(self.p1_sensors, self.telemetry_panel.p1_plot)
        self.setup_sensors_for_plot(self.p2_sensors, self.telemetry_panel.p2_plot)
        self.sidebar.populate_passport_rows()

        self.apply_saved_or_default_view()
        self.update_curve_z_values()
        self.populate_summary_table()
        self.update_plots_data()
        self.sync_all_overlay_views()
        self.update_y_limits()
        self.seek_to_time(self.current_time_cursor)

    def toggle_axis_side(self, key, btn, force_side=None):
        """Переключает положение оси Y (слева или справа)."""
        if key not in self.axes_map: return
        current_side = self.sensor_sides.get(key, "left")
        new_side = force_side if force_side else ("right" if current_side == "left" else "left")
        self.sensor_sides[key] = new_side
        btn.setText("L" if new_side == "left" else "R")

        is_visible = self.sensor_checkboxes[key].isChecked() if key in self.sensor_checkboxes else True
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
        """Включает или выключает блокировку [B] масштабирования по Y для датчика."""
        current_state = self.sensor_move_active.get(key, False)
        new_state = force_state if force_state is not None else (not current_state)
        self.sensor_move_active[key] = new_state
        btn.setStyleSheet(get_move_btn_qss(new_state))

    def update_curve_z_values(self):
        """Пересчитывает Z-слои кривых: верхние в паспорте датчики рисуются поверх остальных."""
        n1 = len(self.p1_sensors)
        for idx, s in enumerate(self.p1_sensors):
            k = s["key"]
            z = 100 + (n1 - idx) * 3
            if f"{k}_raw" in self.curves:
                self.curves[f"{k}_raw"].setZValue(z)
                self.curves[f"{k}_trend"].setZValue(z + 1)
            if k in self.intersection_tags:
                self.intersection_tags[k].setZValue(z + 2)

        n2 = len(self.p2_sensors)
        for idx, s in enumerate(self.p2_sensors):
            k = s["key"]
            z = 100 + (n2 - idx) * 3
            if f"{k}_raw" in self.curves:
                self.curves[f"{k}_raw"].setZValue(z)
                self.curves[f"{k}_trend"].setZValue(z + 1)
            if k in self.intersection_tags:
                self.intersection_tags[k].setZValue(z + 2)

    def handle_sensor_drag_drop(self, sensor_key: str, source_panel: str, target_panel: str, target_row: int):
        """Обрабатывает смену слоев внутри панели и перенос датчика между Panel 1 и Panel 2."""
        source_list = self.p1_sensors if source_panel == "panel1" else self.p2_sensors
        target_list = self.p1_sensors if target_panel == "panel1" else self.p2_sensors

        found_idx = None
        for i, s in enumerate(source_list):
            if s["key"] == sensor_key:
                found_idx = i
                break

        if found_idx is None:
            return

        sensor_data = source_list.pop(found_idx)

        if source_panel != target_panel:
            target_plot = self.telemetry_panel.p1_plot if target_panel == "panel1" else self.telemetry_panel.p2_plot
            self.transfer_sensor_to_plot(sensor_data, target_plot)

        insert_idx = min(max(0, target_row), len(target_list))
        target_list.insert(insert_idx, sensor_data)

        self.update_curve_z_values()
        self.sidebar.populate_passport_rows()
        self.sync_all_overlay_views()
        self.update_y_limits()
        self.populate_summary_table()
        self.seek_to_time(self.current_time_cursor)

    def transfer_sensor_to_plot(self, s: dict, target_plot: pg.PlotWidget):
        """Переносит датчик на новый график с безопасным пересозданием объектов OpenGL."""
        k = s["key"]
        c_color = self.sensor_colors.get(k, s.get('color', '#FFFFFF'))

        old_raw = self.curves.get(f"{k}_raw")
        old_trend = self.curves.get(f"{k}_trend")
        old_tag = self.intersection_tags.get(k)

        x_raw, y_raw = old_raw.getData() if old_raw is not None else ([], [])
        x_trend, y_trend = old_trend.getData() if old_trend is not None else ([], [])
        was_visible = old_raw.isVisible() if old_raw is not None else False

        if k in self.viewboxes_map:
            vb_old = self.viewboxes_map[k]
            if vb_old.scene():
                vb_old.scene().removeItem(vb_old)
        if k in self.axes_map:
            for ax in self.axes_map[k].values():
                if ax.scene():
                    ax.scene().removeItem(ax)
        if old_tag and old_tag.scene():
            old_tag.scene().removeItem(old_tag)
        
        if old_raw in self._persistent_curves:
            self._persistent_curves.remove(old_raw)
        if old_trend in self._persistent_curves:
            self._persistent_curves.remove(old_trend)

        cur_side = self.sensor_sides.get(k, "left")
        vb_new, ax_l, ax_r = self.attach_overlay_view(target_plot, c_color, cur_side)
        self.plot_map[k] = target_plot
        self.viewboxes_map[k] = vb_new
        self.axes_map[k] = {'left': ax_l, 'right': ax_r}

        pen_raw = create_pen(c_color, 1.2, self.current_raw_alpha)
        pen_trend = create_pen(c_color, 2.4, self.current_trend_alpha)
        
        new_raw = pg.PlotCurveItem(x_raw, y_raw, pen=pen_raw)
        new_trend = pg.PlotCurveItem(x_trend, y_trend, pen=pen_trend)
        new_raw.setVisible(was_visible)
        new_trend.setVisible(was_visible)

        vb_new.addItem(new_raw)
        vb_new.addItem(new_trend)

        self.curves[f"{k}_raw"] = new_raw
        self.curves[f"{k}_trend"] = new_trend
        self._persistent_curves.extend([new_raw, new_trend])

        new_tag = create_value_tag(c_color)
        new_tag.setVisible(was_visible)
        vb_new.addItem(new_tag)
        self.intersection_tags[k] = new_tag

        is_visible = self.sensor_visibility.get(k, False)
        target_axis = self.axes_map[k][cur_side]
        target_axis.setVisible(is_visible)

    def toggle_curve_visibility(self, key, is_visible):
        """Включает или выключает отображение кривой и шкалы оси датчика."""
        self.sensor_visibility[key] = is_visible

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
        """Сохраняет раскладку слоев, панели P1/P2, цвета и параметры в view_state.json."""
        p1_state = []
        for s in self.p1_sensors:
            k = s["key"]
            p1_state.append({
                "id": s["id"],
                "color": self.sensor_colors.get(k, s["color"]),
                "visible": self.sensor_visibility.get(k, False),
                "axis": self.sensor_sides.get(k, "left"),
                "move": self.sensor_move_active.get(k, False)
            })

        p2_state = []
        for s in self.p2_sensors:
            k = s["key"]
            p2_state.append({
                "id": s["id"],
                "color": self.sensor_colors.get(k, s["color"]),
                "visible": self.sensor_visibility.get(k, False),
                "axis": self.sensor_sides.get(k, "left"),
                "move": self.sensor_move_active.get(k, False)
            })

        current_state = {
            "panel1": p1_state,
            "panel2": p2_state
        }

        self.session_view_states[self.profile["mode_name"]] = current_state
        save_all_session_view_states(self.profile["mode_name"], self.session_view_states)

        self.sidebar.btn_save_view.setText("Preset Saved!")
        QtCore.QTimer.singleShot(2000, lambda: self.sidebar.btn_save_view.setText("Save View Preset"))
        print(MSG_VIEW_PRESET_SAVED.format(mode=self.profile['mode_name']))

    def apply_saved_or_default_view(self):
        """Восстанавливает сохраненное состояние вида или устанавливает безопасный дефолт."""
        saved_state = self.session_view_states.get(self.profile["mode_name"])
        if saved_state is None:
            saved_state = load_user_view_state(self.profile["mode_name"])

        lookup = {}
        if isinstance(saved_state, dict):
            if "panel1" in saved_state or "panel2" in saved_state:
                for item in saved_state.get("panel1", []) + saved_state.get("panel2", []):
                    lookup[item["id"]] = item
            else:
                lookup = saved_state

        all_sensors = self.p1_sensors + self.p2_sensors
        for s in all_sensors:
            k = s["key"]
            sid = s["id"]
            if sid in lookup:
                cfg = lookup[sid]
                is_vis = cfg.get("visible", False)
                axis_side = cfg.get("axis", "left")
                is_move = cfg.get("move", False)
                if cfg.get("color"):
                    s["color"] = cfg["color"]
                    self.sensor_colors[k] = cfg["color"]
            else:
                # По умолчанию все датчики включены (True) при первом открытии
                is_vis = True
                axis_side = "left"
                is_move = False

            self.sensor_visibility[k] = is_vis
            self.sensor_sides[k] = axis_side
            self.sensor_move_active[k] = is_move

            if k in self.sensor_checkboxes:
                self.sensor_checkboxes[k].blockSignals(True)
                self.sensor_checkboxes[k].setChecked(is_vis)
                self.sensor_checkboxes[k].blockSignals(False)
            if k in self.side_buttons:
                self.toggle_axis_side(k, self.side_buttons[k], force_side=axis_side)
            if k in self.move_buttons:
                self.toggle_sensor_move(k, self.move_buttons[k], force_state=is_move)
            self.toggle_curve_visibility(k, is_vis)

        self.update_curve_z_values()

    def seek_to_time(self, target_sec: float):
        """Синхронно позиционирует мастер-курсор времени и числовые плашки значений."""
        self.current_time_cursor = max(0.0, min(self.total_duration, target_sec))
        
        if self.engine:
            self.engine.current_sample_idx = int(self.current_time_cursor * self.engine.sample_rate)

        self.telemetry_panel.cursor_line_p1.setPos(self.current_time_cursor)
        self.telemetry_panel.cursor_line_p2.setPos(self.current_time_cursor)
        if self.engine:
            self.audio_panel.cursor_line_audio.setPos(self.current_time_cursor)
            self.compute_and_draw_fft_at(int(self.current_time_cursor * self.engine.sample_rate))

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

    def calculate_and_render_spectrogram(self):
        """Вычисляет и отрисовывает базовую 2D-спектрограмму."""
        if not self.engine: return
        Sxx_db, f_min, f_max = self.engine.render_spectrogram_slice(0.0, self.total_duration)
        if Sxx_db is not None:
            self.spec_db_matrix = Sxx_db
            self.spec_f_min = f_min
            self.spec_f_max = f_max
            colormap = pg.colormap.get('inferno')
            self._spec_lut = colormap.getLookupTable(0.0, 1.0, 256)
            self.audio_panel.img_overview.setLookupTable(self._spec_lut)
            self.audio_panel.img_highres.setLookupTable(self._spec_lut)
            spec_min_v, spec_max_v = np.percentile(Sxx_db, [5, 99.5])
            self.audio_panel.img_overview.setImage(Sxx_db.T, levels=[spec_min_v, spec_max_v])
            self.audio_panel.img_overview.setRect(QtCore.QRectF(0, f_min, self.total_duration, f_max - f_min))
            self.audio_panel.plot_spec.setRange(xRange=[0, self.total_duration], yRange=[LIMIT_FREQ_MIN, self.engine.sample_rate / 2.0], padding=0)

    def get_spec_db_at(self, t_sec: float, f_hz: float) -> float:
        """Делегирует расчет децибел в точке звуковому движку."""
        return self.engine.get_db_at_time_and_freq(t_sec, f_hz) if self.engine else 0.0

    def render_current_view(self):
        """Рендерит срез спектрограммы повышенного разрешения для текущего масштаба."""
        if not self.engine: return
        x_range = self.audio_panel.plot_spec.plotItem.vb.viewRange()[0]
        t_start, t_end = max(0.0, x_range[0]), min(self.total_duration, x_range[1])
        span = t_end - t_start
        Sxx_db, f_min, f_max = self.engine.render_spectrogram_slice(t_start, t_end)
        if Sxx_db is not None:
            spec_min_v, spec_max_v = np.percentile(Sxx_db, [5, 99.5])
            self.audio_panel.img_highres.setImage(Sxx_db.T, levels=[spec_min_v, spec_max_v])
            self.audio_panel.img_highres.setRect(QtCore.QRectF(t_start, f_min, span, f_max - f_min))

    def toggle_freq_scale(self):
        """Переключает шкалу частот FFT между Log и Linear."""
        if self.freq_scale_mode == "Log":
            self.freq_scale_mode = "Linear"
            self.audio_panel.btn_scale.setText("Scale: Linear")
            nyq = (self.engine.sample_rate / 2.0) if self.engine else 8000.0
            self.audio_panel.plot_fft.setXRange(LIMIT_FREQ_MIN, nyq, padding=0)
        else:
            self.freq_scale_mode = "Log"
            self.audio_panel.btn_scale.setText("Scale: Log")
            nyq = (self.engine.sample_rate / 2.0) if self.engine else 8000.0
            self.audio_panel.plot_fft.setXRange(np.log10(LIMIT_FREQ_MIN), np.log10(nyq), padding=0)

        if self.engine:
            with self.engine.filter_lock:
                for filt in self.engine.active_filters:
                    x_min = np.log10(filt['f_min']) if self.freq_scale_mode == "Log" else filt['f_min']
                    x_max = np.log10(filt['f_max']) if self.freq_scale_mode == "Log" else filt['f_max']
                    filt['top_item'].setRegion([x_min, x_max])
            self.compute_and_draw_fft_at(self.engine.current_sample_idx)

    def add_filter_from_fft(self, f_min, f_max, x_min, x_max):
        """Создает полосовой фильтр частот из графика FFT."""
        f_min, f_max = max(1.0, float(f_min)), max(f_min + 5.0, float(f_max))
        top_region = create_clean_region(x_min, x_max)
        self.audio_panel.plot_fft.addItem(top_region, ignoreBounds=True)
        bot_rect = create_clean_2d_rect_item(QtCore.QRectF(0, f_min, self.total_duration, f_max - f_min))
        self.audio_panel.plot_spec.addItem(bot_rect, ignoreBounds=True)

        filter_entry = {'t_min': None, 't_max': None, 'f_min': f_min, 'f_max': f_max, 'top_item': top_region, 'bottom_item': bot_rect}
        if self.engine:
            with self.engine.filter_lock:
                self.engine.active_filters.append(filter_entry)
            self.compute_and_draw_fft_at(self.engine.current_sample_idx)

    def add_2d_spectrogram_filter(self, t_min, t_max, f_min, f_max):
        """Создает 2D бокс фильтрации на спектрограмме."""
        f_min, f_max = max(1.0, float(f_min)), max(f_min + 5.0, float(f_max))
        bot_rect = create_clean_2d_rect_item(QtCore.QRectF(t_min, f_min, t_max - t_min, f_max - f_min))
        self.audio_panel.plot_spec.addItem(bot_rect, ignoreBounds=True)
        x_min = np.log10(f_min) if self.freq_scale_mode == "Log" else f_min
        x_max = np.log10(f_max) if self.freq_scale_mode == "Log" else f_max
        top_region = create_clean_region(x_min, x_max)
        self.audio_panel.plot_fft.addItem(top_region, ignoreBounds=True)

        filter_entry = {'t_min': t_min, 't_max': t_max, 'f_min': f_min, 'f_max': f_max, 'top_item': top_region, 'bottom_item': bot_rect}
        if self.engine:
            with self.engine.filter_lock:
                self.engine.active_filters.append(filter_entry)
            self.compute_and_draw_fft_at(self.engine.current_sample_idx)

    def remove_filter_at_pos(self, t_click, f_click, is_fft=False):
        """Удаляет полосовой фильтр в точке клика мышью."""
        if not self.engine: return
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
            self.audio_panel.plot_fft.removeItem(removed_filt['top_item'])
            self.audio_panel.plot_spec.removeItem(removed_filt['bottom_item'])
            self.compute_and_draw_fft_at(self.engine.current_sample_idx)
        else:
            self.clear_all_filters()

    def clear_all_filters(self):
        """Очищает все активные фильтры аудио."""
        if not self.engine: return
        with self.engine.filter_lock:
            filters_to_remove = list(self.engine.active_filters)
            self.engine.active_filters.clear()
        for filt in filters_to_remove:
            self.audio_panel.plot_fft.removeItem(filt['top_item'])
            self.audio_panel.plot_spec.removeItem(filt['bottom_item'])
        self.compute_and_draw_fft_at(self.engine.current_sample_idx)

    def compute_and_draw_fft_at(self, sample_idx):
        """Перерисовывает мгновенный спектр и пики FFT."""
        if not self.engine: return
        for txt in self.audio_panel.peak_text_items:
            txt.setText("")
        x_coords, valid_db, peak_xs, peak_ys, peak_labels = self.engine.compute_fft_at(
            sample_idx, self.freq_scale_mode, ISOLATE_FFT_ON_FILTER
        )
        if x_coords is not None:
            self.audio_panel.fft_curve.setData(x_coords, valid_db)
            self.audio_panel.peak_scatter.setData(peak_xs, peak_ys)
            y_max_limit = self.audio_panel.spin_ymax.value() if hasattr(self.audio_panel, 'spin_ymax') else 40
            for idx, (px, py, label) in enumerate(zip(peak_xs, peak_ys, peak_labels)):
                if idx < len(self.audio_panel.peak_text_items):
                    txt_item = self.audio_panel.peak_text_items[idx]
                    txt_item.setText(label)
                    txt_item.setPos(px, min(y_max_limit - 1, py + 3))

    def update_playhead(self):
        """Синхронно обновляет положение курсора воспроизведения (60 FPS)."""
        if self.engine and self.engine.is_playing:
            cur_sec = self.engine.current_sample_idx / self.engine.sample_rate
            self.seek_to_time(cur_sec)
            
            if not self.engine.is_playing and hasattr(self, 'audio_panel'):
                self.audio_panel.btn_play.setText("Play")
                self.audio_panel.btn_play.setStyleSheet(BTN_GREEN_QSS)

    def toggle_play(self):
        """Запуск или пауза воспроизведения аудиодорожки."""
        if not self.engine: return
        if not self.engine.is_playing:
            self.engine.current_sample_idx = int(self.current_time_cursor * self.engine.sample_rate)

        self.engine.is_playing = not self.engine.is_playing
        if hasattr(self, 'audio_panel'):
            if self.engine.is_playing:
                self.audio_panel.btn_play.setText("Pause")
                self.audio_panel.btn_play.setStyleSheet(BTN_RED_QSS)
            else:
                self.audio_panel.btn_play.setText("Play")
                self.audio_panel.btn_play.setStyleSheet(BTN_GREEN_QSS)

    def on_boost_changed(self, val):
        """Обновляет коэффициент цифрового усиления звука."""
        if self.engine:
            self.engine.boost_db = float(val)

    def add_time_region(self, t_min, t_max):
        """Добавляет синхронную временную область на P1 и P2."""
        reg_p1 = create_clean_region(t_min, t_max)
        reg_p2 = create_clean_region(t_min, t_max)
        self.telemetry_panel.p1_plot.addItem(reg_p1, ignoreBounds=True)
        self.telemetry_panel.p2_plot.addItem(reg_p2, ignoreBounds=True)
        self.time_regions.append({'t_min': t_min, 't_max': t_max, 'item_p1': reg_p1, 'item_p2': reg_p2})
        self.populate_summary_table()

    def handle_right_click_on_timeline(self, t_click):
        """Удаляет кликнутый временной регион или очищает все."""
        target_idx = None
        for idx, reg in enumerate(self.time_regions):
            if reg['t_min'] <= t_click <= reg['t_max']:
                target_idx = idx
                break
        if target_idx is not None:
            removed = self.time_regions.pop(target_idx)
            self.telemetry_panel.p1_plot.removeItem(removed['item_p1'])
            self.telemetry_panel.p2_plot.removeItem(removed['item_p2'])
        else:
            self.clear_all_time_regions()
        self.populate_summary_table()

    def clear_all_time_regions(self):
        """Очищает все временные регионы телеметрии."""
        for reg in self.time_regions:
            self.telemetry_panel.p1_plot.removeItem(reg['item_p1'])
            self.telemetry_panel.p2_plot.removeItem(reg['item_p2'])
        self.time_regions.clear()
        self.populate_summary_table()

    def populate_summary_table(self):
        """Пересчитывает статистику Summary Metrics (Min, Max, Avg) по времени."""
        smooth_val = self.telemetry_panel.spin_smooth.value() if hasattr(self.telemetry_panel, 'spin_smooth') else DEFAULT_SMOOTHING
        rows, ranges_title = TelemetryEngine.compute_summary_rows(
            self.df, self.col_time, self.time_regions,
            self.p1_sensors, self.p2_sensors,
            smoothing_window=smooth_val
        )
        if self.time_regions:
            self.sidebar.lbl_summary_title.setText(f"<b>SUMMARY METRICS</b> <span style='color:#AAAAAA; font-size:7.5pt;'>({ranges_title})</span>")
        else:
            self.sidebar.lbl_summary_title.setText("<b>SUMMARY METRICS</b>")

        self.sidebar.table_summary.setRowCount(len(rows))
        for r_idx, (m, mn, mx, av) in enumerate(rows):
            item_m = QtWidgets.QTableWidgetItem(m)
            item_mn = QtWidgets.QTableWidgetItem(mn)
            item_mx = QtWidgets.QTableWidgetItem(mx)
            item_av = QtWidgets.QTableWidgetItem(av)

            item_m.setForeground(QtGui.QColor("#FFFFFF"))
            item_mn.setForeground(QtGui.QColor("#FFFFFF"))
            item_mx.setForeground(QtGui.QColor("#FFFFFF"))
            item_av.setForeground(QtGui.QColor("#FFFFFF"))

            item_m.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            item_mn.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            item_mx.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            item_av.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

            self.sidebar.table_summary.setItem(r_idx, 0, item_m)
            self.sidebar.table_summary.setItem(r_idx, 1, item_mn)
            self.sidebar.table_summary.setItem(r_idx, 2, item_mx)
            self.sidebar.table_summary.setItem(r_idx, 3, item_av)

    def update_plots_data(self):
        """Обновляет массивы данных линий тренда."""
        t_res = TelemetryEngine.get_resampled_time(self.time_data, self.current_step)
        for s in self.p1_sensors + self.p2_sensors:
            k = s["key"]
            trend_data = TelemetryEngine.resample_series(self.df[s["col"]], self.current_step)
            self.curves[f"{k}_trend"].setData(t_res, trend_data)

    def update_y_limits(self, reset_x=False):
        """Рассчитывает автомасштаб осей Y для датчиков."""
        def compute_limits(col):
            if col is None: return None, None
            s_data = TelemetryEngine.smooth_series(self.df[col], DEFAULT_SMOOTHING) if self.y_fit_mode == "Raw" else TelemetryEngine.resample_series(self.df[col], self.current_step)
            valid = s_data[~np.isnan(s_data)]
            if len(valid) == 0: return 0.0, 1.0
            mn, mx = float(np.min(valid)), float(np.max(valid))
            pad = (mx - mn) * 0.08 if mx != mn else 1.0
            return mn - pad, mx + pad

        if reset_x:
            self.telemetry_panel.vb1.setXRange(0.0, self.total_duration, padding=0)

        for s in self.p1_sensors + self.p2_sensors:
            k = s["key"]
            mn, mx = compute_limits(s["col"])
            if mn is None or mx is None: continue
            self.sensor_y_limits[k] = [mn, mx]
            if k in self.viewboxes_map:
                self.viewboxes_map[k].setYRange(mn, mx, padding=0)
                cur_side = self.sensor_sides.get(k, "left")
                target_axis = self.axes_map[k][cur_side]
                target_axis.picture = None
                target_axis.setRange(mn, mx)
                target_axis.update()

    def on_smooth_changed(self, val):
        """Обрабатывает изменение окна скользящего среднего."""
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
        """Обрабатывает изменение шага прореживания (Step downsampling)."""
        self.current_step = max(1, val)
        if self.current_step > 1:
            self.telemetry_panel.spin_raw.setValue(0.25)
            self.telemetry_panel.spin_trend.setValue(1.00)
        else:
            self.telemetry_panel.spin_raw.setValue(1.00)
            self.telemetry_panel.spin_trend.setValue(0.00)
        self.update_plots_data()

    def on_raw_alpha_changed(self, val):
        """Меняет прозрачность сырых кривых."""
        self.current_raw_alpha = float(val)
        for s in self.p1_sensors + self.p2_sensors:
            self.curves[f"{s['key']}_raw"].setPen(create_pen(s['color'], 1.2, self.current_raw_alpha))

    def on_trend_alpha_changed(self, val):
        """Меняет прозрачность линий тренда."""
        self.current_trend_alpha = float(val)
        for s in self.p1_sensors + self.p2_sensors:
            self.curves[f"{s['key']}_trend"].setPen(create_pen(s['color'], 2.4, self.current_trend_alpha))

    def toggle_y_fit(self):
        """Переключает автомасштаб между сырыми данными и линией тренда."""
        self.y_fit_mode = "Trend" if self.y_fit_mode == "Raw" else "Raw"
        self.telemetry_panel.btn_fit.setText(f"Fit: {self.y_fit_mode}")
        self.update_y_limits()

    def save_result_action(self):
        """Экспортирует эволюцию датчиков в CSV."""
        QtWidgets.QApplication.processEvents()
        TelemetryEngine.export_summary_csv(
            summary_dir=self.summary_dir,
            summary_filepath=self.summary_filepath,
            df=self.df,
            time_data=self.time_data,
            current_step=self.current_step,
            export_sensors=self.profile["export_sensors"],
            get_col_fn=lambda sid: TelemetryEngine.find_column_by_sensor_id(self.df, sid)
        )
        print(MSG_EXPORT_SUCCESS.format(path=self.summary_filepath))

        if hasattr(self, 'telemetry_panel') and hasattr(self.telemetry_panel, 'btn_save'):
            self.telemetry_panel.btn_save.setText(BTN_CSV_SAVED)
            QtCore.QTimer.singleShot(2000, lambda: self.telemetry_panel.btn_save.setText(BTN_SAVE_RESULT))

    def keyPressEvent(self, event):
        """Глобальные горячие клавиши: Space (воспроизведение) и Escape (сброс выделений)."""
        if event.key() == QtCore.Qt.Key.Key_Space:
            self.toggle_play()
            event.accept()
        elif event.key() == QtCore.Qt.Key.Key_Escape:
            self.clear_all_time_regions()
            if hasattr(self, 'clear_all_filters'):
                self.clear_all_filters()
            event.accept()
        else:
            super().keyPressEvent(event)


# =======================================================
#                      MAIN ENTRY
# =======================================================
if __name__ == '__main__':
    cpu_name = "CPU"
    gpu_name = "GPU"

    if not os.path.exists(RESULTS_DIR):
        print(f"Error: Results directory '{RESULTS_DIR}' not found!")
        sys.exit(1)

    # Сканируем папки тестов внутри results/ (например, results/test/, results/kaka/)
    available_runs = []
    
    for entry in os.listdir(RESULTS_DIR):
        entry_path = os.path.join(RESULTS_DIR, entry)
        if os.path.isdir(entry_path) and entry != "summary_reports":
            for f in os.listdir(entry_path):
                if f.endswith(".csv") and (f.startswith("table_") or f.startswith("table_raw_")):
                    csv_full_path = os.path.join(entry_path, f)
                    available_runs.append((entry, f, csv_full_path))

    # Также проверяем старые папки для обратной совместимости
    for legacy_d in [os.path.join(RESULTS_DIR, "raw_telemetry"), os.path.join(RESULTS_DIR, "sensors_logs")]:
        if os.path.exists(legacy_d):
            for f in os.listdir(legacy_d):
                if f.endswith(".csv") and (f.startswith("table_") or f.startswith("table_raw_")):
                    available_runs.append(("legacy", f, os.path.join(legacy_d, f)))

    if not available_runs:
        print(f"No test runs found in '{RESULTS_DIR}' directory!")
        sys.exit(1)

    print("=" * 55)
    print("        PC COOLING STUDIO SUITE — RUNS         ")
    print("=" * 55)
    for idx, (run_folder, _, _) in enumerate(available_runs):
        print(f"  [{idx + 1}] {run_folder}")
    print("=" * 55)

    choice = input(f"Select test run to analyze (default 1): ").strip()
    run_idx = int(choice) - 1 if choice.isdigit() and 1 <= int(choice) <= len(available_runs) else 0

    run_folder, selected_file, file_path = available_runs[run_idx]
    run_dir = os.path.dirname(file_path)

    # Автоматически ищем парный аудиофайл в той же папке запуск
    audio_file_name_mp3 = selected_file.replace("table_raw_", "audio_raw_").replace("table_", "audio_").replace(".csv", ".mp3")
    audio_path = os.path.join(run_dir, audio_file_name_mp3)

    if not os.path.exists(audio_path):
        audio_file_name_wav = selected_file.replace("table_raw_", "audio_raw_").replace("table_", "audio_").replace(".csv", ".wav")
        audio_path = os.path.join(run_dir, audio_file_name_wav)
        if not os.path.exists(audio_path):
            audio_path = None

    try:
        df, _ = TelemetryEngine.load_log_file(file_path, TIME_START, TIME_END)
        print(MSG_ANALYZING.format(file=selected_file, samples=len(df)))
        if audio_path:
            print(MSG_PAIRED_AUDIO.format(file=os.path.basename(audio_path)))
    except Exception as e:
        print(MSG_ERR_READ_CSV.format(err=e))
        sys.exit(1)

    app = QtWidgets.QApplication(sys.argv)
    window = StudioSuiteWindow(df, selected_file, cpu_name=cpu_name, gpu_name=gpu_name, audio_path=audio_path)
    window.show()
    sys.exit(app.exec())