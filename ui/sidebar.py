"""
Левая панель управления (Sidebar): Сводная таблица (Summary) и паспорт датчиков (Passport)
"""
import os
import json
from PyQt6 import QtCore, QtGui, QtWidgets

from ui.styles import (
    SPINBOX_CLEAN_QSS, BTN_CYAN_QSS, TABLE_SUMMARY_QSS,
    BTN_SIDE_QSS, get_sensor_checkbox_qss, get_move_btn_qss
)


class StudioSidebar(QtWidgets.QFrame):
    def __init__(self, parent_analyzer):
        super().__init__()
        self.analyzer = parent_analyzer
        self.setMinimumWidth(260)
        self.setStyleSheet("""
            StudioSidebar {
                background-color: #121212;
                border: 1px solid #2A2A2A;
                border-radius: 6px;
            }
            QSplitter::handle:vertical {
                background-color: #222222;
                height: 5px;
                margin: 2px 0px;
                border-radius: 2px;
            }
            QSplitter::handle:vertical:hover {
                background-color: #00E5FF;
            }
            /* Единый тонкий темный скроллбар для сайдбара */
            QScrollBar:vertical {
                background-color: #0E0E0E;
                width: 6px;
                margin: 0px 0px 0px 1px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background-color: #262626;
                min-height: 25px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #00E5FF;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
                border: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
                border: none;
            }
        """)
        
        self.init_ui()

    def init_ui(self):
        sb_layout = QtWidgets.QVBoxLayout(self)
        sb_layout.setContentsMargins(8, 8, 8, 8)
        sb_layout.setSpacing(6)

        # 1. Вертикальный сплиттер между Summary Metrics и Sensor Passport
        self.sidebar_vsplitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.sidebar_vsplitter.setChildrenCollapsible(False)

        # --- Виджет 1: Блок Summary Metrics ---
        summary_container = QtWidgets.QWidget()
        summary_container.setMinimumHeight(0)
        sum_layout = QtWidgets.QVBoxLayout(summary_container)
        sum_layout.setContentsMargins(0, 0, 0, 4)
        sum_layout.setSpacing(4)

        self.lbl_summary_title = QtWidgets.QLabel(f"<b>SUMMARY METRICS</b> <span style='color:#888; font-size:8pt;'>({self.analyzer.profile['mode_name']})</span>")
        self.lbl_summary_title.setStyleSheet("color: #FFFFFF; font-size: 9pt;")
        sum_layout.addWidget(self.lbl_summary_title)

        self.table_summary = QtWidgets.QTableWidget()
        self.table_summary.setColumnCount(4)
        self.table_summary.setHorizontalHeaderLabels(["Metric", "Min", "Max", "Avg"])
        
        # Строгое центрирование всех 4 заголовков
        for col_idx in range(4):
            h_item = self.table_summary.horizontalHeaderItem(col_idx)
            if h_item:
                h_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # Настройка 100% растяжения: Metric забирает всё свободное место, Min/Max/Avg компактны справа
        header = self.table_summary.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Fixed)
        
        self.table_summary.setColumnWidth(1, 46)
        self.table_summary.setColumnWidth(2, 48)
        self.table_summary.setColumnWidth(3, 56)
        header.setStretchLastSection(False)

        self.table_summary.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table_summary.verticalHeader().setVisible(False)
        self.table_summary.verticalHeader().setDefaultSectionSize(20)
        self.table_summary.setShowGrid(False)
        self.table_summary.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_summary.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.table_summary.setStyleSheet(TABLE_SUMMARY_QSS)
        sum_layout.addWidget(self.table_summary)

        self.sidebar_vsplitter.addWidget(summary_container)

        # --- Виджет 2: Блок Sensor Passport ---
        passport_container = QtWidgets.QWidget()
        passport_container.setMinimumHeight(0)
        pass_layout = QtWidgets.QVBoxLayout(passport_container)
        pass_layout.setContentsMargins(0, 4, 0, 0)
        pass_layout.setSpacing(4)

        lbl_passport_title = QtWidgets.QLabel("<b>SENSOR PASSPORT & VISIBILITY</b>")
        lbl_passport_title.setStyleSheet("color: #FFFFFF; font-size: 9pt;")
        pass_layout.addWidget(lbl_passport_title)

        passport_scroll = QtWidgets.QScrollArea()
        passport_scroll.setWidgetResizable(True)
        passport_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        
        self.passport_widget = QtWidgets.QWidget()
        self.passport_layout = QtWidgets.QVBoxLayout(self.passport_widget)
        self.passport_layout.setContentsMargins(0, 0, 0, 0)
        self.passport_layout.setSpacing(3)

        self.populate_passport_rows()

        passport_scroll.setWidget(self.passport_widget)
        pass_layout.addWidget(passport_scroll)

        self.sidebar_vsplitter.addWidget(passport_container)
        self.sidebar_vsplitter.setSizes([260, 450])

        sb_layout.addWidget(self.sidebar_vsplitter, stretch=1)

        # 2. Кнопка сохранения пресета
        self.btn_save_view = QtWidgets.QPushButton("Save View Preset")
        self.btn_save_view.setFixedHeight(30)
        self.btn_save_view.setToolTip("Saves current visibility, axis side and zoom M-state for active profile")
        self.btn_save_view.setStyleSheet(BTN_CYAN_QSS)
        self.btn_save_view.clicked.connect(self.analyzer.save_view_preset_action)
        sb_layout.addWidget(self.btn_save_view)

    def populate_passport_rows(self):
        while self.passport_layout.count():
            item = self.passport_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for s in self.analyzer.p1_sensors + self.analyzer.p2_sensors:
            self.add_passport_row(s)
        self.passport_layout.addStretch()

    def add_passport_row(self, s):
        k = s["key"]
        row_widget = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(2, 0, 2, 0)
        row_layout.setSpacing(4)
        row_widget.setFixedHeight(24)

        cb = QtWidgets.QCheckBox(s['label'])
        cb.blockSignals(True)
        cb.setChecked(False)
        cb.blockSignals(False)
        cb.setStyleSheet(get_sensor_checkbox_qss(s['color']))
        cb.toggled.connect(lambda checked, key=k: self.analyzer.toggle_curve_visibility(key, checked))
        row_layout.addWidget(cb, stretch=1)
        self.analyzer.sensor_checkboxes[k] = cb

        cur_side = self.analyzer.sensor_sides.get(k, "left")
        side_text = "L" if cur_side == "left" else "R"
        btn_side = QtWidgets.QPushButton(side_text)
        btn_side.setFixedSize(20, 17)
        btn_side.setToolTip("Toggle Axis Side (Left / Right)")
        btn_side.setStyleSheet(BTN_SIDE_QSS)
        btn_side.clicked.connect(lambda _, key=k, btn=btn_side: self.analyzer.toggle_axis_side(key, btn))
        row_layout.addWidget(btn_side)
        self.analyzer.side_buttons[k] = btn_side

        self.analyzer.sensor_move_active[k] = False
        btn_move = QtWidgets.QPushButton("M")
        btn_move.setFixedSize(20, 17)
        btn_move.setToolTip("Enable/Disable Zoom & Pan for this sensor")
        btn_move.setStyleSheet(get_move_btn_qss(False))
        btn_move.clicked.connect(lambda _, key=k, btn=btn_move: self.analyzer.toggle_sensor_move(key, btn))
        row_layout.addWidget(btn_move)
        self.analyzer.move_buttons[k] = btn_move

        self.passport_layout.addWidget(row_widget)