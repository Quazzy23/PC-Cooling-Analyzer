"""
Левая панель управления (Sidebar):
- Сводная таблица (Summary Metrics) с автоподгонкой высоты под количество строк
- Паспорт датчиков (Sensor Passport) с Drag & Drop, плотной посадкой Panel 1 и независимым сплиттером
"""
import os
import json
from PyQt6 import QtCore, QtGui, QtWidgets

from ui.styles import (
    SPINBOX_CLEAN_QSS, BTN_CYAN_QSS, TABLE_SUMMARY_QSS,
    BTN_SIDE_QSS, get_sensor_checkbox_qss, get_move_btn_qss
)


class PassportDropListWidget(QtWidgets.QListWidget):
    """Список датчиков с визуальной полупрозрачной дымкой Drag & Drop"""
    def __init__(self, panel_name: str, parent_sidebar):
        super().__init__()
        self.panel_name = panel_name
        self.sidebar = parent_sidebar
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(QtCore.Qt.DropAction.MoveAction)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.setStyleSheet("""
            QListWidget {
                background-color: #121212;
                border: 1px solid #1A1A1A;
                border-radius: 4px;
                padding: 1px;
                outline: none;
            }
            QListWidget::item {
                background: transparent;
                margin: 0px;
                border: none;
            }
            QListWidget::item:selected {
                background: transparent;
            }
            QListWidget::indicator {
                background-color: #00E5FF;
            }
        """)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        sensor_key = item.data(QtCore.Qt.ItemDataRole.UserRole)
        widget = self.itemWidget(item)

        mime_data = QtCore.QMimeData()
        mime_data.setText(f"{self.panel_name}:{sensor_key}")

        drag = QtGui.QDrag(self)
        drag.setMimeData(mime_data)

        if widget:
            pixmap = widget.grab()
            transparent_pixmap = QtGui.QPixmap(pixmap.size())
            transparent_pixmap.fill(QtCore.Qt.GlobalColor.transparent)

            painter = QtGui.QPainter(transparent_pixmap)
            painter.setOpacity(0.70)
            painter.drawPixmap(0, 0, pixmap)
            painter.end()

            drag.setPixmap(transparent_pixmap)
            drag.setHotSpot(QtCore.QPoint(30, pixmap.height() // 2))

        drag.exec(QtCore.Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        text = event.mimeData().text()
        if ":" not in text:
            event.ignore()
            return

        source_panel, sensor_key = text.split(":", 1)
        drop_pos = event.position().toPoint()
        target_item = self.itemAt(drop_pos)
        target_row = self.row(target_item) if target_item else self.count()

        self.sidebar.analyzer.handle_sensor_drag_drop(sensor_key, source_panel, self.panel_name, target_row)
        event.acceptProposedAction()


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
                height: 4px;
                margin: 1px 0px;
                border-radius: 2px;
            }
            QSplitter::handle:vertical:hover {
                background-color: #00E5FF;
            }
            QScrollBar:vertical {
                background-color: #0E0E0E;
                width: 6px;
                margin: 0px;
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
        """)

        self.init_ui()

    def init_ui(self):
        sb_layout = QtWidgets.QVBoxLayout(self)
        sb_layout.setContentsMargins(8, 8, 8, 8)
        sb_layout.setSpacing(6)

        # 1. Внешний сплиттер (Summary Metrics <-> Sensor Passport)
        self.sidebar_vsplitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.sidebar_vsplitter.setChildrenCollapsible(False)
        self.sidebar_vsplitter.setHandleWidth(5)

        # --- БЛОК 1: Summary Metrics ---
        summary_container = QtWidgets.QWidget()
        sum_layout = QtWidgets.QVBoxLayout(summary_container)
        sum_layout.setContentsMargins(0, 0, 0, 2)
        sum_layout.setSpacing(4)

        self.lbl_summary_title = QtWidgets.QLabel(f"<b>SUMMARY METRICS</b> <span style='color:#888; font-size:8pt;'>({self.analyzer.profile['mode_name']})</span>")
        self.lbl_summary_title.setStyleSheet("color: #FFFFFF; font-size: 9pt;")
        sum_layout.addWidget(self.lbl_summary_title)

        self.table_summary = QtWidgets.QTableWidget()
        self.table_summary.setColumnCount(4)
        self.table_summary.setHorizontalHeaderLabels(["Metric", "Min", "Max", "Avg"])

        for col_idx in range(4):
            h_item = self.table_summary.horizontalHeaderItem(col_idx)
            if h_item:
                h_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

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

        # --- БЛОК 2: Sensor Passport ---
        passport_container = QtWidgets.QWidget()
        pass_layout = QtWidgets.QVBoxLayout(passport_container)
        pass_layout.setContentsMargins(0, 2, 0, 0)
        pass_layout.setSpacing(4)

        lbl_passport_title = QtWidgets.QLabel("<b>SENSOR PASSPORT & VISIBILITY</b>")
        lbl_passport_title.setStyleSheet("color: #FFFFFF; font-size: 9pt;")
        pass_layout.addWidget(lbl_passport_title)

        # Внутренний сплиттер между Panel 1 и Panel 2
        self.passport_vsplitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.passport_vsplitter.setChildrenCollapsible(False)
        self.passport_vsplitter.setHandleWidth(4)

        # Контейнер Panel 1
        p1_container = QtWidgets.QWidget()
        p1_layout = QtWidgets.QVBoxLayout(p1_container)
        p1_layout.setContentsMargins(0, 0, 0, 2)
        p1_layout.setSpacing(3)

        self.lbl_p1_header = QtWidgets.QLabel("<b>Panel 1</b>")
        self.lbl_p1_header.setStyleSheet("color: #FFFFFF; font-size: 8.5pt;")
        p1_layout.addWidget(self.lbl_p1_header)

        self.list_p1 = PassportDropListWidget("panel1", self)
        p1_layout.addWidget(self.list_p1)
        self.passport_vsplitter.addWidget(p1_container)

        # Контейнер Panel 2
        p2_container = QtWidgets.QWidget()
        p2_layout = QtWidgets.QVBoxLayout(p2_container)
        p2_layout.setContentsMargins(0, 2, 0, 0)
        p2_layout.setSpacing(3)

        self.lbl_p2_header = QtWidgets.QLabel("<b>Panel 2</b>")
        self.lbl_p2_header.setStyleSheet("color: #FFFFFF; font-size: 8.5pt;")
        p2_layout.addWidget(self.lbl_p2_header)

        self.list_p2 = PassportDropListWidget("panel2", self)
        p2_layout.addWidget(self.list_p2)
        self.passport_vsplitter.addWidget(p2_container)

        # Настраиваем приоритеты растяжения внутреннего сплиттера:
        # Panel 1 стремится к точному размеру контента, Panel 2 забирает остаток
        self.passport_vsplitter.setStretchFactor(0, 0)
        self.passport_vsplitter.setStretchFactor(1, 1)

        pass_layout.addWidget(self.passport_vsplitter)
        self.sidebar_vsplitter.addWidget(passport_container)

        sb_layout.addWidget(self.sidebar_vsplitter, stretch=1)

        # Кнопка сохранения пресета
        self.btn_save_view = QtWidgets.QPushButton("Save View Preset")
        self.btn_save_view.setFixedHeight(30)
        self.btn_save_view.setToolTip("Saves current layers order, colors, panels, visibility and axes")
        self.btn_save_view.setStyleSheet(BTN_CYAN_QSS)
        self.btn_save_view.clicked.connect(self.analyzer.save_view_preset_action)
        sb_layout.addWidget(self.btn_save_view)

        self.populate_passport_rows()

    def auto_fit_sidebar_splitters(self):
        """Динамически рассчитывает идеальные высоты для Summary Metrics и Panel 1 без лишних пустот"""
        # 1. Точная высота для Summary Metrics по числу строк
        row_count = self.table_summary.rowCount()
        header_h = self.table_summary.horizontalHeader().height() or 28
        row_h = self.table_summary.verticalHeader().defaultSectionSize() or 20
        # шапка + строки + заголовок таблицы + отступы
        h_summary_needed = header_h + (row_count * row_h) + 38

        total_sb_h = self.sidebar_vsplitter.height()
        if total_sb_h <= 100:
            total_sb_h = 750

        # Ограничиваем таблицу Summary максимум 50% высоты сайдбара
        h_summary = min(h_summary_needed, int(total_sb_h * 0.50))
        h_passport = max(100, total_sb_h - h_summary - self.sidebar_vsplitter.handleWidth())

        self.sidebar_vsplitter.setSizes([h_summary, h_passport])

        # 2. Точная плотная посадка Panel 1 по количеству строк датчиков
        p1_count = len(self.analyzer.p1_sensors)
        # заголовок 'Panel 1' (~20px) + строки датчиков (по 26px) + минимальный отступ
        h_p1_needed = 22 + (p1_count * 26) + 4

        # Задаем Panel 1 ровно столько, сколько нужно, а остальное отдаем Panel 2
        self.passport_vsplitter.setSizes([h_p1_needed, 10000])

    def populate_passport_rows(self):
        """Очищает и заполняет списки датчиков"""
        self.list_p1.clear()
        self.list_p2.clear()

        for s in self.analyzer.p1_sensors:
            self.create_passport_item(self.list_p1, s)

        for s in self.analyzer.p2_sensors:
            self.create_passport_item(self.list_p2, s)

    def create_passport_item(self, list_widget: QtWidgets.QListWidget, s: dict):
        k = s["key"]
        item = QtWidgets.QListWidgetItem()
        item.setData(QtCore.Qt.ItemDataRole.UserRole, k)
        item.setSizeHint(QtCore.QSize(220, 26))

        row_widget = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row_widget)
        # Добавлен отступ 6px справа, чтобы кнопки не прилипали к краю
        row_layout.setContentsMargins(1, 0, 6, 0)
        row_layout.setSpacing(3)
        row_widget.setFixedHeight(24)

        lbl_grip = QtWidgets.QLabel("⠿")
        lbl_grip.setStyleSheet("color: #555555; font-size: 11pt; padding-right: 2px;")
        lbl_grip.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        lbl_grip.setToolTip("Drag up/down to change Z-layer, or drag into another panel")
        row_layout.addWidget(lbl_grip)

        cb = QtWidgets.QCheckBox(s['label'])
        cb.blockSignals(True)
        is_checked = self.analyzer.sensor_visibility.get(k, False)
        cb.setChecked(is_checked)
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

        is_move = self.analyzer.sensor_move_active.get(k, False)
        btn_move = QtWidgets.QPushButton("B")
        btn_move.setFixedSize(20, 17)
        btn_move.setToolTip("Block Y-Axis zoom for this sensor")
        btn_move.setStyleSheet(get_move_btn_qss(is_move))
        btn_move.clicked.connect(lambda _, key=k, btn=btn_move: self.analyzer.toggle_sensor_move(key, btn))
        row_layout.addWidget(btn_move)
        self.analyzer.move_buttons[k] = btn_move

        list_widget.addItem(item)
        list_widget.setItemWidget(item, row_widget)