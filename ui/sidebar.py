"""Левая панель управления: сводная таблица метрик и интерактивный паспорт датчиков."""
from PyQt6 import QtCore, QtGui, QtWidgets

from ui.styles import (
    SPINBOX_CLEAN_QSS, BTN_CYAN_QSS, TABLE_SUMMARY_QSS,
    BTN_SIDE_QSS, get_sensor_checkbox_qss, get_move_btn_qss,
    SIDEBAR_FRAME_QSS, LIST_WIDGET_DROP_QSS, PASSPORT_SCROLL_QSS
)
from core.texts import (
    TITLE_SUMMARY_METRICS, TABLE_HEADERS_SUMMARY,
    TITLE_SENSOR_PASSPORT, HEADER_PANEL_1, HEADER_PANEL_2,
    BTN_SAVE_VIEW, TIP_SAVE_VIEW, TIP_GRIP, TIP_AXIS_SIDE, TIP_BLOCK_ZOOM
)


class PassportDropListWidget(QtWidgets.QListWidget):
    """Список датчиков с визуальной полупрозрачной дымкой Drag & Drop."""
    def __init__(self, panel_name: str, parent_sidebar):
        super().__init__()
        self.panel_name = panel_name
        self.sidebar = parent_sidebar
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(QtCore.Qt.DropAction.MoveAction)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.setStyleSheet(LIST_WIDGET_DROP_QSS)

    def startDrag(self, supportedActions):
        """Создает полупрозрачный снимок строки и инициирует перенос."""
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
        """Прием перетаскиваемого объекта при входе в список."""
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """Обработка движения перетаскиваемого элемента над списком."""
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Обработка сброса датчика в целевую позицию."""
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
    """Сайдбар: таблица Summary Metrics и паспорта датчиков с разделителями."""
    def __init__(self, parent_analyzer):
        super().__init__()
        self.analyzer = parent_analyzer
        self.setMinimumWidth(260)
        self.setStyleSheet(SIDEBAR_FRAME_QSS)
        self.init_ui()

    def init_ui(self):
        """Построение разметки сайдбара и подключение виджетов."""
        sb_layout = QtWidgets.QVBoxLayout(self)
        sb_layout.setContentsMargins(8, 8, 8, 8)
        sb_layout.setSpacing(6)

        # 1. Внешний вертикальный сплиттер (Summary <-> Passport)
        self.sidebar_vsplitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.sidebar_vsplitter.setChildrenCollapsible(False)
        self.sidebar_vsplitter.setHandleWidth(5)

        # Блок таблицы Summary
        summary_container = QtWidgets.QWidget()
        sum_layout = QtWidgets.QVBoxLayout(summary_container)
        sum_layout.setContentsMargins(0, 0, 0, 2)
        sum_layout.setSpacing(4)

        self.lbl_summary_title = QtWidgets.QLabel(f"<b>{TITLE_SUMMARY_METRICS}</b>")
        self.lbl_summary_title.setStyleSheet("color: #FFFFFF; font-size: 9pt;")
        sum_layout.addWidget(self.lbl_summary_title)

        self.table_summary = QtWidgets.QTableWidget()
        self.table_summary.setColumnCount(4)
        self.table_summary.setHorizontalHeaderLabels(TABLE_HEADERS_SUMMARY)

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

        # Блок паспорта датчиков с внутренним сплиттером
        passport_container = QtWidgets.QWidget()
        pass_layout = QtWidgets.QVBoxLayout(passport_container)
        pass_layout.setContentsMargins(0, 2, 0, 0)
        pass_layout.setSpacing(4)

        lbl_passport_title = QtWidgets.QLabel(f"<b>{TITLE_SENSOR_PASSPORT}</b>")
        lbl_passport_title.setStyleSheet("color: #FFFFFF; font-size: 9pt;")
        pass_layout.addWidget(lbl_passport_title)

        self.passport_vsplitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.passport_vsplitter.setChildrenCollapsible(False)
        self.passport_vsplitter.setHandleWidth(4)

        # Контейнер Panel 1
        p1_container = QtWidgets.QWidget()
        p1_layout = QtWidgets.QVBoxLayout(p1_container)
        p1_layout.setContentsMargins(0, 0, 0, 2)
        p1_layout.setSpacing(3)

        self.lbl_p1_header = QtWidgets.QLabel(f"<b>{HEADER_PANEL_1}</b>")
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

        self.lbl_p2_header = QtWidgets.QLabel(f"<b>{HEADER_PANEL_2}</b>")
        self.lbl_p2_header.setStyleSheet("color: #FFFFFF; font-size: 8.5pt;")
        p2_layout.addWidget(self.lbl_p2_header)

        self.list_p2 = PassportDropListWidget("panel2", self)
        p2_layout.addWidget(self.list_p2)
        self.passport_vsplitter.addWidget(p2_container)

        self.passport_vsplitter.setStretchFactor(0, 0)
        self.passport_vsplitter.setStretchFactor(1, 1)

        pass_layout.addWidget(self.passport_vsplitter)
        self.sidebar_vsplitter.addWidget(passport_container)

        self.sidebar_vsplitter.setSizes([240, 480])
        sb_layout.addWidget(self.sidebar_vsplitter, stretch=1)

        # Кнопка сохранения пресета
        self.btn_save_view = QtWidgets.QPushButton(BTN_SAVE_VIEW)
        self.btn_save_view.setFixedHeight(30)
        self.btn_save_view.setToolTip(TIP_SAVE_VIEW)
        self.btn_save_view.setStyleSheet(BTN_CYAN_QSS)
        self.btn_save_view.clicked.connect(self.analyzer.save_view_preset_action)
        sb_layout.addWidget(self.btn_save_view)

        self.populate_passport_rows()

    def auto_fit_sidebar_splitters(self):
        """Рассчитывает геометрию разделителей для плотной посадки элементов."""
        row_count = self.table_summary.rowCount()
        header_h = self.table_summary.horizontalHeader().height() or 28
        row_h = self.table_summary.verticalHeader().defaultSectionSize() or 20
        h_summary_needed = header_h + (row_count * row_h) + 38

        total_sb_h = self.sidebar_vsplitter.height()
        if total_sb_h <= 100:
            total_sb_h = 750

        h_summary = min(h_summary_needed, int(total_sb_h * 0.50))
        h_passport = max(100, total_sb_h - h_summary - self.sidebar_vsplitter.handleWidth())
        self.sidebar_vsplitter.setSizes([h_summary, h_passport])

        p1_count = len(self.analyzer.p1_sensors)
        h_p1_needed = 22 + (p1_count * 26) + 4
        self.passport_vsplitter.setSizes([h_p1_needed, 10000])

    def populate_passport_rows(self):
        """Перерисовывает строки в списках Panel 1 и Panel 2."""
        self.list_p1.clear()
        self.list_p2.clear()

        for s in self.analyzer.p1_sensors:
            self.create_passport_item(self.list_p1, s)

        for s in self.analyzer.p2_sensors:
            self.create_passport_item(self.list_p2, s)

    def create_passport_item(self, list_widget: QtWidgets.QListWidget, s: dict):
        """Создает графическую строку элемента паспорта датчика."""
        k = s["key"]
        item = QtWidgets.QListWidgetItem()
        item.setData(QtCore.Qt.ItemDataRole.UserRole, k)
        item.setSizeHint(QtCore.QSize(220, 26))

        row_widget = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(1, 0, 6, 0)
        row_layout.setSpacing(3)
        row_widget.setFixedHeight(24)

        lbl_grip = QtWidgets.QLabel("⠿")
        lbl_grip.setStyleSheet("color: #555555; font-size: 11pt; padding-right: 2px;")
        lbl_grip.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        lbl_grip.setToolTip(TIP_GRIP)
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
        btn_side.setToolTip(TIP_AXIS_SIDE)
        btn_side.setStyleSheet(BTN_SIDE_QSS)
        btn_side.clicked.connect(lambda _, key=k, btn=btn_side: self.analyzer.toggle_axis_side(key, btn))
        row_layout.addWidget(btn_side)
        self.analyzer.side_buttons[k] = btn_side

        is_move = self.analyzer.sensor_move_active.get(k, False)
        btn_move = QtWidgets.QPushButton("B")
        btn_move.setFixedSize(20, 17)
        btn_move.setToolTip(TIP_BLOCK_ZOOM)
        btn_move.setStyleSheet(get_move_btn_qss(is_move))
        btn_move.clicked.connect(lambda _, key=k, btn=btn_move: self.analyzer.toggle_sensor_move(key, btn))
        row_layout.addWidget(btn_move)
        self.analyzer.move_buttons[k] = btn_move

        list_widget.addItem(item)
        list_widget.setItemWidget(item, row_widget)