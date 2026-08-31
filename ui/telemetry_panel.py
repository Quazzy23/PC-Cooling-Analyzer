"""
Центральная панель аппаратных графиков (P1 - Теплофизика, P2 - Обороты и Шум)
"""
import pyqtgraph as pg
from PyQt6 import QtCore, QtWidgets

from ui.viewboxes import CleanTimeViewBox
from ui.styles import create_timeline_cursor, SPINBOX_CLEAN_QSS, BTN_CYAN_QSS, BTN_GREEN_QSS


class TelemetryPanel(QtWidgets.QWidget):
    def __init__(self, parent_analyzer):
        super().__init__()
        self.analyzer = parent_analyzer
        self.setMinimumWidth(380)
        
        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Вертикальный сплиттер для графиков P1 и P2
        self.v_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.v_splitter.setChildrenCollapsible(False)
        self.v_splitter.setStyleSheet("""
            QSplitter::handle:vertical {
                background-color: #222222;
                height: 5px;
                margin: 2px 0px;
                border-radius: 2px;
            }
            QSplitter::handle:vertical:hover {
                background-color: #00E5FF;
            }
        """)

        # 1. Верхний график: Теплофизика (P1)
        cur_hw = self.analyzer.get_current_hardware_name()
        p1_title = f"<span style='color: #FFFFFF; font-size: 10pt;'><b>1. {self.analyzer.profile['chart_title_prefix']} ({cur_hw} — {self.analyzer.clean_file_name})</b></span>"
        self.p1_plot, self.vb1, self.cursor_line_p1 = self.create_telemetry_plot(p1_title)
        self.analyzer.setup_sensors_for_plot(self.analyzer.p1_sensors, self.p1_plot)
        self.v_splitter.addWidget(self.p1_plot)

        # 2. Нижний график: Обороты и Шум (P2)
        p2_title = f"<span style='color: #FFFFFF; font-size: 10pt;'><b>2. {self.analyzer.profile['panel2_title']}</b></span>"
        self.p2_plot, self.vb2, self.cursor_line_p2 = self.create_telemetry_plot(p2_title, show_bottom_label=True)
        self.vb2.setXLink(self.vb1)
        self.analyzer.setup_sensors_for_plot(self.analyzer.p2_sensors, self.p2_plot)
        self.v_splitter.addWidget(self.p2_plot)

        self.v_splitter.setSizes([5000, 5000])
        layout.addWidget(self.v_splitter, stretch=1)

        # 3. Нижняя панель управления (Smooth, Step, Fog, Trend, Fit, Save)
        controls_layout = QtWidgets.QHBoxLayout()
        controls_layout.setContentsMargins(2, 2, 2, 2)
        controls_layout.setSpacing(6)

        lbl_smooth = QtWidgets.QLabel("Smooth:")
        lbl_smooth.setStyleSheet("color: #888888; font-size: 8.5pt;")
        controls_layout.addWidget(lbl_smooth)

        self.spin_smooth = QtWidgets.QSpinBox()
        self.spin_smooth.setRange(1, 30)
        self.spin_smooth.setValue(4)
        self.spin_smooth.setFixedWidth(44)
        self.spin_smooth.setStyleSheet(SPINBOX_CLEAN_QSS)
        self.spin_smooth.valueChanged.connect(self.analyzer.on_smooth_changed)
        controls_layout.addWidget(self.spin_smooth)

        lbl_step = QtWidgets.QLabel("Step:")
        lbl_step.setStyleSheet("color: #888888; font-size: 8.5pt;")
        controls_layout.addWidget(lbl_step)

        self.spin_step = QtWidgets.QSpinBox()
        self.spin_step.setRange(1, 200)
        self.spin_step.setSingleStep(5)
        self.spin_step.setValue(1)
        self.spin_step.setFixedWidth(44)
        self.spin_step.setStyleSheet(SPINBOX_CLEAN_QSS)
        self.spin_step.valueChanged.connect(self.analyzer.on_step_changed)
        controls_layout.addWidget(self.spin_step)

        lbl_raw = QtWidgets.QLabel("Raw Fog:")
        lbl_raw.setStyleSheet("color: #888888; font-size: 8.5pt;")
        controls_layout.addWidget(lbl_raw)

        self.spin_raw = QtWidgets.QDoubleSpinBox()
        self.spin_raw.setRange(0.0, 1.0)
        self.spin_raw.setSingleStep(0.05)
        self.spin_raw.setValue(1.0)
        self.spin_raw.setFixedWidth(52)
        self.spin_raw.setStyleSheet(SPINBOX_CLEAN_QSS)
        self.spin_raw.valueChanged.connect(self.analyzer.on_raw_alpha_changed)
        controls_layout.addWidget(self.spin_raw)

        lbl_trend = QtWidgets.QLabel("Trend A:")
        lbl_trend.setStyleSheet("color: #888888; font-size: 8.5pt;")
        controls_layout.addWidget(lbl_trend)

        self.spin_trend = QtWidgets.QDoubleSpinBox()
        self.spin_trend.setRange(0.0, 1.0)
        self.spin_trend.setSingleStep(0.05)
        self.spin_trend.setValue(0.0)
        self.spin_trend.setFixedWidth(52)
        self.spin_trend.setStyleSheet(SPINBOX_CLEAN_QSS)
        self.spin_trend.valueChanged.connect(self.analyzer.on_trend_alpha_changed)
        controls_layout.addWidget(self.spin_trend)

        controls_layout.addSpacing(2)

        self.btn_fit = QtWidgets.QPushButton("Fit: Raw")
        self.btn_fit.setFixedSize(78, 26)
        self.btn_fit.setStyleSheet(BTN_CYAN_QSS)
        self.btn_fit.clicked.connect(self.analyzer.toggle_y_fit)
        controls_layout.addWidget(self.btn_fit)

        self.btn_save = QtWidgets.QPushButton("Save Result")
        self.btn_save.setFixedSize(92, 26)
        self.btn_save.setStyleSheet(BTN_GREEN_QSS)
        self.btn_save.clicked.connect(self.analyzer.save_result_action)
        controls_layout.addWidget(self.btn_save)

        # Текстовый статус координат справа от кнопки Save Result
        self.lbl_telemetry_status = QtWidgets.QLabel("")
        self.lbl_telemetry_status.setFixedHeight(30)
        self.lbl_telemetry_status.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.lbl_telemetry_status.setStyleSheet("color: #888888; font-size: 8pt; font-family: 'Segoe UI', Arial, sans-serif;")
        controls_layout.addWidget(self.lbl_telemetry_status, stretch=1)

        layout.addLayout(controls_layout)

    def create_telemetry_plot(self, title_html: str, show_bottom_label: bool = False):
        vb = CleanTimeViewBox(self.analyzer)
        plot = pg.PlotWidget(viewBox=vb)
        vb.plot_widget = plot

        plot.showGrid(x=True, y=True, alpha=0.18)
        plot.setTitle(title_html, justify='left')
        plot.hideAxis('left')
        plot.hideAxis('right')
        
        b_axis = plot.getAxis('bottom')
        b_axis.setPen(pg.mkPen('#444444', width=1))
        b_axis.setTextPen(pg.mkPen('#AAAAAA'))
        b_axis.enableAutoSIPrefix(True)

        plot.plotItem.layout.setContentsMargins(55, 0, 55, 0)

        if show_bottom_label:
            plot.setLabel('bottom', 'Time', units='s', **{'color': '#AAAAAA', 'font-size': '8.5pt'})

        cursor = create_timeline_cursor()
        plot.addItem(cursor, ignoreBounds=True)
        return plot, vb, cursor