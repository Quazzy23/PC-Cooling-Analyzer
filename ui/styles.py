"""
Модуль единых стилей, цветовых палитр и фабрик графических элементов (QSS, Pen, Region)
"""
from PyQt6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

# Базовая темная тема PyQtGraph
def apply_pg_dark_theme():
    pg.setConfigOptions(antialias=True, useOpenGL=True)
    pg.setConfigOption('background', '#0E0E0E')
    pg.setConfigOption('foreground', '#FFFFFF')


# Фабрика создания перьев графиков с прозрачностью
def create_pen(color_hex: str, width: float = 1.5, alpha: float = 1.0) -> QtGui.QPen:
    c = QtGui.QColor(color_hex)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return pg.mkPen(color=c, width=width)


# Единая прозрачность для всех зон выделения (во время драга и после отпускания)
DEFAULT_REGION_ALPHA = 80


# Фабрика создания полупрозрачной полосы выделения (LinearRegionItem)
def create_clean_region(min_val: float, max_val: float, orientation: str = 'vertical', alpha: int = DEFAULT_REGION_ALPHA) -> pg.LinearRegionItem:
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


# Фабрика создания 2D-прямоугольника выделения для спектрограммы
def create_clean_2d_rect_item(rect: QtCore.QRectF, alpha: int = DEFAULT_REGION_ALPHA) -> QtWidgets.QGraphicsRectItem:
    box = QtWidgets.QGraphicsRectItem(rect)
    box.setPen(QtGui.QPen(QtCore.Qt.PenStyle.NoPen))
    box.setBrush(pg.mkBrush(255, 255, 255, alpha))
    box.setZValue(15)
    return box


# =======================================================
#                      QSS СТИЛИ
# =======================================================

# Чистые поля ввода (SpinBox) без стрелочек
SPINBOX_CLEAN_QSS = """
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

# Стиль кнопок действий (Save, Fit, Play)
BTN_CYAN_QSS = """
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
"""

BTN_GREEN_QSS = """
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
"""

BTN_RED_QSS = """
    QPushButton {
        background-color: #1A1A1A;
        color: #FF3366;
        font-weight: bold;
        font-size: 9pt;
        border-radius: 4px;
        border: 1px solid #333333;
    }
    QPushButton:hover {
        background-color: #2A2A2A;
        border: 1px solid #FF3366;
    }
"""

# Таблица Summary
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

# =======================================================
#               ДИНАМИЧЕСКИЕ СТИЛИ ДАТЧИКОВ
# =======================================================

def get_sensor_checkbox_qss(color_hex: str) -> str:
    """Генерирует цветной стиль для чекбокса конкретного датчика"""
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
    """Стиль кнопки [M] (активна / неактивна)"""
    if is_active:
        return """
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


# Фабрика создания тонкого полупрозрачного белого курсора времени
def create_timeline_cursor() -> pg.InfiniteLine:
    line = pg.InfiniteLine(
        pos=0.0,
        angle=90,
        movable=False,
        pen=pg.mkPen(color=(255, 255, 255, 150), width=1.4, style=QtCore.Qt.PenStyle.SolidLine)
    )
    line.setZValue(1000)
    return line

# Фабрика создания плашки значения на пересечении курсора с графиком
def create_value_tag(color_hex: str) -> pg.TextItem:
    tag = pg.TextItem("", color=color_hex, anchor=(-0.15, 1.25))
    tag.setFont(QtGui.QFont("Segoe UI", 8, QtGui.QFont.Weight.Bold))
    tag.setZValue(150)
    return tag

# Стиль горизонтального ползунка (QSlider)
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

# Стиль выпадающего списка (QComboBox)
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