"""Единый модуль стилей, цветовых палитр, QSS, перьев и графических фабрик."""
from PyQt6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

# =======================================================
#               ЦВЕТА И ГРАФИЧЕСКИЕ КОНСТАНТЫ
# =======================================================
DEFAULT_REGION_ALPHA = 80
COLOR_FFT_CURVE = '#00E5FF'
COLOR_PEAK = '#FF3366'

PEN_AXIS = pg.mkPen('#444444', width=1)
PEN_AXIS_TEXT = pg.mkPen('#AAAAAA')

AXIS_LABEL_STYLE = {'color': '#AAAAAA', 'font-size': '8.5pt'}
STATUS_LABEL_STYLE = "color: #888888; font-size: 8.5pt; font-family: 'Segoe UI', Arial, sans-serif;"
CONTROLS_LABEL_STYLE = "color: #888888; font-size: 8.5pt;"

HUD_2LINE_HTML_TEMPLATE = (
    "<div align='right' style='font-size: 7.5pt; font-family: Segoe UI, sans-serif; line-height: 110%;'>"
    "<span style='color: #AAAAAA; font-weight: bold;'>{time}</span><br>"
    "<span style='color: #777777;'>{coords}</span></div>"
)

HUD_1LINE_HTML_TEMPLATE = (
    "<div align='right' style='font-size: 7.5pt; font-family: Segoe UI, sans-serif;'>"
    "<span style='color: #777777;'>{coords}</span></div>"
)


def apply_pg_dark_theme():
    """Применяет базовую темную тему и OpenGL-ускорение для PyQtGraph."""
    pg.setConfigOptions(antialias=True, useOpenGL=True)
    pg.setConfigOption('background', '#0E0E0E')
    pg.setConfigOption('foreground', '#FFFFFF')


def create_pen(color_hex: str, width: float = 1.5, alpha: float = 1.0) -> QtGui.QPen:
    """Создает перо графиков с поддержкой прозрачности."""
    c = QtGui.QColor(color_hex)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return pg.mkPen(color=c, width=width)


def create_clean_region(min_val: float, max_val: float, orientation: str = 'vertical', alpha: int = DEFAULT_REGION_ALPHA) -> pg.LinearRegionItem:
    """Создает полупрозрачную вертикальную или горизонтальную зону выделения."""
    region = pg.LinearRegionItem(
        values=[min_val, max_val],
        orientation=orientation,
        brush=pg.mkBrush(255, 255, 255, alpha),
        pen=pg.mkPen(None),
        hoverPen=pg.mkPen(None),
        movable=False
    )
    for line in region.lines:
        line.setPen(pg.mkPen(None))
        line.setHoverPen(pg.mkPen(None))
    region.setZValue(50)
    return region


def create_clean_2d_rect_item(rect: QtCore.QRectF, alpha: int = DEFAULT_REGION_ALPHA) -> QtWidgets.QGraphicsRectItem:
    """Создает 2D-прямоугольник выделения для спектрограммы."""
    box = QtWidgets.QGraphicsRectItem(rect)
    box.setPen(QtGui.QPen(QtCore.Qt.PenStyle.NoPen))
    box.setBrush(pg.mkBrush(255, 255, 255, alpha))
    box.setZValue(15)
    return box


def create_timeline_cursor() -> pg.InfiniteLine:
    """Создает вертикальный курсор времени на графиках."""
    line = pg.InfiniteLine(
        pos=0.0,
        angle=90,
        movable=False,
        pen=pg.mkPen(color=(255, 255, 255, 150), width=1.4, style=QtCore.Qt.PenStyle.SolidLine)
    )
    line.setZValue(1000)
    return line


def create_value_tag(color_hex: str) -> pg.TextItem:
    """Создает плашку значения на пересечении курсора с графиком."""
    tag = pg.TextItem("", color=color_hex, anchor=(-0.15, 1.25))
    tag.setFont(QtGui.QFont("Segoe UI", 8, QtGui.QFont.Weight.Bold))
    tag.setZValue(150)
    return tag


def get_sensor_checkbox_qss(color_hex: str) -> str:
    """Генерирует индивидуальный цветной стиль для чекбокса датчика."""
    return f"""
        QCheckBox {{
            color: {color_hex};
            font-weight: bold;
            font-size: 8pt;
            font-family: 'Segoe UI', Arial, sans-serif;
            spacing: 5px;
        }}
        QCheckBox::indicator {{
            width: 12px;
            height: 12px;
            background-color: #1A1A1A;
            border: 1px solid {color_hex};
            border-radius: 2px;
        }}
        QCheckBox::indicator:checked {{
            background-color: {color_hex};
        }}
    """


def get_move_btn_qss(is_active: bool) -> str:
    """Возвращает стиль кнопки блокировки [B] в зависимости от ее состояния."""
    if is_active:
        return """
            QPushButton {
                background-color: #1A1A1A;
                color: #00E5FF;
                font-weight: bold;
                font-size: 7.5pt;
                font-family: 'Segoe UI', Arial, sans-serif;
                border: 1px solid #00E5FF;
                border-radius: 2px;
                padding: 0px;
                margin: 0px;
            }
        """
    return """
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
    """


# =======================================================
#                      QSS СТИЛИ
# =======================================================

SPINBOX_CLEAN_QSS = """
    QAbstractSpinBox {
        background-color: #161616;
        color: #00E5FF;
        font-weight: bold;
        font-size: 8.5pt;
        font-family: 'Segoe UI', Arial, sans-serif;
        border: 1px solid #2C2C2C;
        border-radius: 4px;
        padding-left: 4px;
        padding-right: 4px;
        min-height: 26px;
        max-height: 26px;
    }
    QAbstractSpinBox:hover {
        border: 1px solid #444444;
    }
    QAbstractSpinBox:focus {
        border: 1px solid #008B9E;
    }
    QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
        width: 0px;
        border: none;
        background: transparent;
    }
"""

BTN_CYAN_QSS = """
    QPushButton {
        background-color: #161616;
        color: #00E5FF;
        font-weight: bold;
        font-size: 8.5pt;
        font-family: 'Segoe UI', Arial, sans-serif;
        border-radius: 4px;
        border: 1px solid #2C2C2C;
        min-height: 26px;
        max-height: 26px;
    }
    QPushButton:hover {
        background-color: #202020;
        border: 1px solid #008B9E;
    }
"""

BTN_GREEN_QSS = """
    QPushButton {
        background-color: #122016;
        color: #33FF57;
        font-weight: bold;
        font-size: 8.5pt;
        font-family: 'Segoe UI', Arial, sans-serif;
        border-radius: 4px;
        border: 1px solid #1E4626;
        min-height: 26px;
        max-height: 26px;
    }
    QPushButton:hover {
        background-color: #182C1E;
        border: 1px solid #33FF57;
    }
"""

BTN_RED_QSS = """
    QPushButton {
        background-color: #221216;
        color: #FF3366;
        font-weight: bold;
        font-size: 8.5pt;
        font-family: 'Segoe UI', Arial, sans-serif;
        border-radius: 4px;
        border: 1px solid #461C26;
        min-height: 26px;
        max-height: 26px;
    }
    QPushButton:hover {
        background-color: #2C181D;
        border: 1px solid #FF3366;
    }
"""

BTN_SIDE_QSS = """
    QPushButton {
        background-color: #1A1A1A;
        color: #00E5FF;
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
        border: 1px solid #00E5FF;
    }
"""

TABLE_SUMMARY_QSS = """
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
"""

COMBOBOX_CLEAN_QSS = """
    QComboBox {
        background-color: #1A1A1A;
        color: #00E5FF;
        font-weight: bold;
        font-size: 9pt;
        border: 1px solid #333333;
        border-radius: 4px;
        padding-left: 8px;
        padding-right: 8px;
        min-height: 28px;
    }
    QComboBox:hover {
        border: 1px solid #00E5FF;
    }
    QComboBox::drop-down {
        border: none;
        width: 20px;
    }
    QComboBox QAbstractItemView {
        background-color: #141414;
        color: #FFFFFF;
        selection-background-color: #222222;
        selection-color: #00E5FF;
        border: 1px solid #333333;
    }
"""

SLIDER_CYAN_QSS = """
    QSlider::groove:horizontal {
        height: 4px;
        background: #222222;
        border-radius: 2px;
    }
    QSlider::sub-page:horizontal {
        background: #00E5FF;
        border-radius: 2px;
    }
    QSlider::handle:horizontal {
        background: #FFFFFF;
        border: 1px solid #00E5FF;
        width: 12px;
        height: 12px;
        margin: -4px 0;
        border-radius: 6px;
    }
    QSlider::handle:horizontal:hover {
        background: #00E5FF;
    }
"""

TOP_BAR_FRAME_QSS = """
    QFrame {
        background-color: #121212;
        border: 1px solid #2A2A2A;
        border-radius: 6px;
    }
"""

SPLITTER_HORIZONTAL_QSS = """
    QSplitter::handle:horizontal {
        background-color: #222222;
        width: 6px;
        margin: 0px 2px;
        border-radius: 3px;
    }
    QSplitter::handle:horizontal:hover {
        background-color: #00E5FF;
    }
"""

SPLITTER_VERTICAL_QSS = """
    QSplitter::handle:vertical {
        background-color: #222222;
        height: 5px;
        margin: 2px 0px;
        border-radius: 2px;
    }
    QSplitter::handle:vertical:hover {
        background-color: #00E5FF;
    }
"""

SIDEBAR_FRAME_QSS = """
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
"""

LIST_WIDGET_DROP_QSS = """
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
"""

PASSPORT_SCROLL_QSS = """
    QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {
        background-color: #121212;
        border: none;
    }
"""

BTN_MODULE_ACTIVE_QSS = """
    QPushButton {
        background-color: #10252C;
        color: #5CE1E6;
        font-weight: bold;
        font-size: 8.5pt;
        border: 1px solid #008B9E;
        border-radius: 4px;
        padding: 0px 10px;
    }
"""

BTN_MODULE_INACTIVE_QSS = """
    QPushButton {
        background-color: #161616;
        color: #666666;
        font-size: 8.5pt;
        border: 1px solid #2C2C2C;
        border-radius: 4px;
        padding: 0px 10px;
    }
"""

# Стили для графического мастера настройки датчиков (Wizard)
WIZARD_WINDOW_QSS = """
    QMainWindow, QWidget {
        background-color: #0E0E0E;
        color: #FFFFFF;
        font-family: 'Segoe UI', Arial, sans-serif;
    }
    QTreeWidget {
        background-color: #121212;
        border: 1px solid #262626;
        border-radius: 6px;
        color: #FFFFFF;
        font-size: 9pt;
        padding: 4px;
    }
    QTreeWidget::item {
        padding: 2px 0px;
    }
    QTreeWidget::item:hover {
        background-color: #1A1A1A;
    }
    QTreeWidget::item:selected {
        background-color: #102B33;
        color: #00E5FF;
    }
    QTreeWidget::indicator {
        width: 14px;
        height: 14px;
        background-color: #161616;
        border: 1px solid #444444;
        border-radius: 3px;
    }
    QTreeWidget::indicator:checked {
        background-color: #00E5FF;
        border: 1px solid #00E5FF;
    }
    QHeaderView::section {
        background-color: #181818;
        color: #00E5FF;
        font-weight: bold;
        font-size: 8.5pt;
        padding: 5px;
        border: 1px solid #222222;
    }
    QComboBox {
        background-color: #161616;
        color: #00E5FF;
        font-weight: bold;
        font-size: 8.5pt;
        border: 1px solid #2C2C2C;
        border-radius: 3px;
        padding: 1px 4px;
        min-height: 22px;
        max-height: 22px;
    }
    QComboBox:disabled {
        color: #555555;
        border: 1px solid #222222;
    }
    QAbstractSpinBox {
        background-color: #161616;
        color: #00E5FF;
        font-weight: bold;
        font-size: 8.5pt;
        border: 1px solid #2C2C2C;
        border-radius: 3px;
        padding: 1px 2px;
        min-height: 22px;
        max-height: 22px;
    }
    QAbstractSpinBox:disabled {
        color: #555555;
        border: 1px solid #222222;
    }
    QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
        width: 0px;
        height: 0px;
        border: none;
        background: transparent;
    }
    QLineEdit {
        background-color: #161616;
        color: #00E5FF;
        font-size: 8.5pt;
        border: 1px solid #2C2C2C;
        border-radius: 3px;
        padding: 1px 5px;
        min-height: 22px;
        max-height: 22px;
    }
    QLineEdit:disabled {
        color: #555555;
        border: 1px solid #222222;
    }
    QPushButton {
        background-color: #161616;
        color: #00E5FF;
        font-weight: bold;
        font-size: 8.5pt;
        border-radius: 4px;
        border: 1px solid #2C2C2C;
        padding: 0px 12px;
        min-height: 28px;
    }
    QPushButton:hover {
        background-color: #222222;
        border: 1px solid #00E5FF;
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
"""

BTN_DELETE_PROFILE_QSS = """
    QPushButton {
        background-color: #221216;
        color: #FF3366;
        font-weight: bold;
        border: 1px solid #461C26;
        min-height: 28px;
    }
    QPushButton:hover {
        background-color: #2C181D;
        border: 1px solid #FF3366;
    }
"""