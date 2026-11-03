"""Графическое окно мастера настройки датчиков и фоновый воркер опроса LHM."""
import os
import sys
import re
import json
import time
import requests
from PyQt6 import QtCore, QtGui, QtWidgets

from utils.lhm_client import LHM_URL, ensure_lhm_running, extract_hardware_structure
from ui.styles import WIZARD_WINDOW_QSS, BTN_GREEN_QSS, BTN_DELETE_PROFILE_QSS
from core.texts import (
    TITLE_WIZARD_WINDOW, LBL_PROFILE, BTN_CREATE_PROFILE, BTN_DELETE_PROFILE,
    BTN_SAVE_CONFIG, BTN_CONFIG_SAVED, WIZARD_TREE_HEADERS, LBL_WIZARD_STATS_TEMPLATE,
    STATUS_CONNECTING_LHM, DIALOG_NEW_PROFILE_TITLE, DIALOG_NEW_PROFILE_PROMPT,
    DIALOG_DELETE_PROFILE_TITLE, DIALOG_DELETE_PROFILE_PROMPT, MSG_CANNOT_DELETE_LAST
)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SYS_INFO_DIR = os.path.join(PROJECT_ROOT, "system_info")
CONFIG_FILE = os.path.join(SYS_INFO_DIR, "sensors_config.json")
HW_INFO_FILE = os.path.join(SYS_INFO_DIR, "hardware_info.json")


def extract_unit_from_value(val_str: str) -> str:
    """Извлекает единицу измерения из строки показаний LHM."""
    if not val_str:
        return ""
    v = str(val_str).strip()
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?\s*(.+)$", v)
    if match:
        unit = match.group(1).strip()
        unit = unit.replace("°C", "C").replace("°", "").strip()
        return unit
    return ""


def format_sensor_name_with_unit(base_name: str, val_str: str, s_type: str = "") -> str:
    """Добавляет единицу измерения к имени датчика в круглых скобках."""
    name = str(base_name).strip()
    unit = extract_unit_from_value(val_str)

    if not unit:
        t = s_type.lower()
        if "temperature" in t: unit = "C"
        elif "fan" in t or "rpm" in t: unit = "RPM"
        elif "power" in t: unit = "W"
        elif "voltage" in t: unit = "V"
        elif "clock" in t: unit = "MHz"
        elif "load" in t: unit = "%"
        elif "data" in t: unit = "GB"

    if unit and not name.endswith(f"({unit})"):
        return f"{name} ({unit})"

    return name


def extract_sensor_values(node, result_dict):
    """Рекурсивно формирует словарь ID датчиков и их значений в фоне."""
    if isinstance(node, dict):
        sid = node.get("SensorId")
        val = node.get("Value")
        if sid and val is not None:
            result_dict[sid] = str(val)
        for child in node.get("Children", []):
            extract_sensor_values(child, result_dict)
    elif isinstance(node, list):
        for item in node:
            extract_sensor_values(item, result_dict)


class LHMWorker(QtCore.QThread):
    """Фоновый поток опроса Web API без заморозки графического интерфейса."""
    initial_tree_received = QtCore.pyqtSignal(dict)
    values_updated = QtCore.pyqtSignal(dict)
    connection_status = QtCore.pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self._running = True
        self._initial_tree_sent = False
        self.session = requests.Session()

    def run(self):
        """Цикл опроса API с интервалом 1 секунда."""
        while self._running:
            try:
                res = self.session.get(LHM_URL, timeout=1.0)
                if res.status_code == 200:
                    data = res.json()
                    self.connection_status.emit(True, "Connected to LibreHardwareMonitor Web API")
                    if not self._initial_tree_sent:
                        self.initial_tree_received.emit(data)
                        self._initial_tree_sent = True
                    else:
                        values_map = {}
                        extract_sensor_values(data, values_map)
                        self.values_updated.emit(values_map)
                else:
                    self.connection_status.emit(False, f"HTTP Error: {res.status_code}")
            except Exception:
                self.connection_status.emit(False, "LibreHardwareMonitor is not running")

            for _ in range(10):
                if not self._running:
                    break
                time.sleep(0.1)

    def stop(self):
        """Остановка фонового потока."""
        self._running = False
        self.wait()


class SimpleSensorsWizard(QtWidgets.QMainWindow):
    """Окно визуального выбора датчиков с сохранением профилей."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle(TITLE_WIZARD_WINDOW)
        self.resize(980, 720)
        self.setStyleSheet(WIZARD_WINDOW_QSS)

        self.profiles_db = self.load_initial_config()
        self.current_profile = "CPU" if "CPU" in self.profiles_db else list(self.profiles_db.keys())[0]
        self.sensor_items_map = {}
        self.tree_initialized = False

        self.init_ui()

        self.worker = LHMWorker()
        self.worker.initial_tree_received.connect(self.build_tree_from_data)
        self.worker.values_updated.connect(self.on_values_updated)
        self.worker.connection_status.connect(self.on_connection_status_changed)
        self.worker.start()

    def load_initial_config(self):
        """Загружает существующий конфиг или создает чистую структуру."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "active_mode" in data:
                        del data["active_mode"]
                    return data
            except Exception:
                pass
        return {
            "CPU": {
                "summary_dir_name": "cpu",
                "panel1_thermal_and_power": [],
                "panel2_cooling_and_speed": []
            },
            "GPU": {
                "summary_dir_name": "gpu",
                "panel1_thermal_and_power": [],
                "panel2_cooling_and_speed": []
            }
        }

    def init_ui(self):
        """Создает элементы интерфейса визарда."""
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Верхняя панель управления
        top_bar = QtWidgets.QHBoxLayout()
        top_bar.setSpacing(8)

        lbl_p = QtWidgets.QLabel(f"<b>{LBL_PROFILE}</b>")
        lbl_p.setStyleSheet("color: #00E5FF; font-size: 9pt;")
        top_bar.addWidget(lbl_p)

        self.combo_profile = QtWidgets.QComboBox()
        self.combo_profile.setFixedWidth(110)
        self.update_profile_combo_items()
        self.combo_profile.currentTextChanged.connect(self.on_profile_switched)
        top_bar.addWidget(self.combo_profile)

        self.btn_new_profile = QtWidgets.QPushButton(BTN_CREATE_PROFILE)
        self.btn_new_profile.clicked.connect(self.create_new_profile_dialog)
        top_bar.addWidget(self.btn_new_profile)

        self.btn_delete_profile = QtWidgets.QPushButton(BTN_DELETE_PROFILE)
        self.btn_delete_profile.setStyleSheet(BTN_DELETE_PROFILE_QSS)
        self.btn_delete_profile.clicked.connect(self.delete_current_profile_dialog)
        top_bar.addWidget(self.btn_delete_profile)

        top_bar.addSpacing(10)

        self.btn_save = QtWidgets.QPushButton(BTN_SAVE_CONFIG)
        self.btn_save.setStyleSheet(BTN_GREEN_QSS)
        self.btn_save.clicked.connect(self.save_config_to_file)
        top_bar.addWidget(self.btn_save)

        top_bar.addStretch()

        self.lbl_status = QtWidgets.QLabel(STATUS_CONNECTING_LHM)
        self.lbl_status.setStyleSheet("color: #888888; font-size: 8.5pt; font-style: italic;")
        top_bar.addWidget(self.lbl_status)

        layout.addLayout(top_bar)

        # Дерево сенсоров
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(WIZARD_TREE_HEADERS)

        header = self.tree.header()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Interactive)

        self.tree.setColumnWidth(1, 85)
        self.tree.setColumnWidth(2, 220)
        self.tree.setColumnWidth(3, 200)

        self.tree.itemChanged.connect(self.on_item_check_state_changed)
        layout.addWidget(self.tree, stretch=1)

        # Нижняя инфо-строка
        self.lbl_stats = QtWidgets.QLabel("")
        self.lbl_stats.setStyleSheet("color: #888888; font-size: 8.5pt;")
        layout.addWidget(self.lbl_stats)

    def update_profile_combo_items(self):
        """Обновляет элементы в выпадающем списке профилей."""
        self.combo_profile.blockSignals(True)
        self.combo_profile.clear()
        modes = [k for k in self.profiles_db.keys() if k != "active_mode"]
        if not modes:
            modes = ["CPU", "GPU"]
        self.combo_profile.addItems(modes)
        idx = self.combo_profile.findText(self.current_profile)
        if idx >= 0:
            self.combo_profile.setCurrentIndex(idx)
        self.combo_profile.blockSignals(False)

    def create_new_profile_dialog(self):
        """Диалог создания нового профиля."""
        name, ok = QtWidgets.QInputDialog.getText(self, DIALOG_NEW_PROFILE_TITLE, DIALOG_NEW_PROFILE_PROMPT)
        if ok and name.strip():
            clean_name = name.strip().upper()
            if clean_name not in self.profiles_db:
                self.profiles_db[clean_name] = {
                    "summary_dir_name": clean_name.lower(),
                    "panel1_thermal_and_power": [],
                    "panel2_cooling_and_speed": []
                }
                self.current_profile = clean_name
                self.update_profile_combo_items()
                self.sync_tree_checkboxes_with_profile()

    def delete_current_profile_dialog(self):
        """Удаляет активный профиль с подтверждением."""
        active_modes = [k for k in self.profiles_db.keys() if k != "active_mode"]
        if len(active_modes) <= 1:
            QtWidgets.QMessageBox.warning(self, DIALOG_DELETE_PROFILE_TITLE, MSG_CANNOT_DELETE_LAST)
            return

        reply = QtWidgets.QMessageBox.question(
            self, DIALOG_DELETE_PROFILE_TITLE,
            DIALOG_DELETE_PROFILE_PROMPT.format(profile=self.current_profile),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            if self.current_profile in self.profiles_db:
                del self.profiles_db[self.current_profile]

            remaining = [k for k in self.profiles_db.keys() if k != "active_mode"]
            self.current_profile = remaining[0] if remaining else "CPU"
            self.update_profile_combo_items()
            self.sync_tree_checkboxes_with_profile()

    def on_profile_switched(self, new_profile):
        """Переключает текущий профиль в визарде."""
        if not new_profile or new_profile == self.current_profile:
            return
        self.save_current_tree_to_profile_memory()
        self.current_profile = new_profile
        self.sync_tree_checkboxes_with_profile()

    def on_connection_status_changed(self, is_connected, status_text):
        """Отображает статус подключения к Web API."""
        if is_connected:
            self.lbl_status.setText(status_text)
            self.lbl_status.setStyleSheet("color: #33FF57; font-size: 8.5pt;")
        else:
            self.lbl_status.setText(status_text)
            self.lbl_status.setStyleSheet("color: #FF3366; font-size: 8.5pt;")
            if not self.tree_initialized:
                ensure_lhm_running()

    def build_tree_from_data(self, data: dict):
        """Строит дерево LHM и автоматически сохраняет паспорт железа."""
        try:
            _, system_metadata = extract_hardware_structure(data)
            with open(HW_INFO_FILE, "w", encoding="utf-8") as hw_f:
                json.dump(system_metadata, hw_f, indent=4, ensure_ascii=False)
        except Exception:
            pass

        self.tree.blockSignals(True)
        self.tree.clear()
        self.sensor_items_map.clear()

        def add_node(node, parent_item=None):
            if isinstance(node, dict):
                text = node.get("Text", "")
                val = node.get("Value", "")
                s_type = node.get("Type", "")
                s_id = node.get("SensorId")
                children = node.get("Children", [])

                if parent_item is None:
                    item = QtWidgets.QTreeWidgetItem(self.tree, [text, str(val) if val is not None else "", "", ""])
                    item.setExpanded(True)
                else:
                    item = QtWidgets.QTreeWidgetItem(parent_item, [text, str(val) if val is not None else "", "", ""])

                if s_id:
                    item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)

                    default_formatted = format_sensor_name_with_unit(text, str(val), s_type)
                    edit_name = QtWidgets.QLineEdit()
                    edit_name.setText(default_formatted)
                    edit_name.setEnabled(False)
                    self.tree.setItemWidget(item, 2, edit_name)

                    item.setText(3, s_id)
                    item.setForeground(3, QtGui.QBrush(QtGui.QColor("#666666")))

                    item.setData(0, QtCore.Qt.ItemDataRole.UserRole, {
                        "id": s_id, "name": text, "type": s_type, "value": val, "is_checked": False
                    })
                    self.sensor_items_map[s_id] = (item, edit_name)
                else:
                    font = item.font(0)
                    font.setBold(True)
                    item.setFont(0, font)
                    item.setExpanded(True)

                for child in children:
                    add_node(child, item)

            elif isinstance(node, list):
                for item in node:
                    add_node(item, parent_item)

        add_node(data)
        self.tree.blockSignals(False)
        self.sync_tree_checkboxes_with_profile()

    def on_values_updated(self, values_map: dict):
        """Атомарно обновляет показания датчиков без лагов."""
        self.tree.blockSignals(True)
        self.tree.setUpdatesEnabled(False)
        for sid, new_val in values_map.items():
            entry = self.sensor_items_map.get(sid)
            if entry:
                item = entry[0]
                if item.text(1) != new_val:
                    item.setText(1, new_val)
        self.tree.setUpdatesEnabled(True)
        self.tree.blockSignals(False)

    def sync_tree_checkboxes_with_profile(self):
        """Синхронизирует состояние галочек в дереве с данными профиля."""
        self.tree.blockSignals(True)

        prof_data = self.profiles_db.get(self.current_profile, {})
        saved_names = {}
        for s in prof_data.get("panel1_thermal_and_power", []) + prof_data.get("panel2_cooling_and_speed", []):
            saved_names[s.get("id")] = s.get("name", "")

        checked_count = 0
        for sid, (item, edit_name) in self.sensor_items_map.items():
            data = item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}
            if sid in saved_names:
                item.setCheckState(0, QtCore.Qt.CheckState.Checked)
                data["is_checked"] = True
                edit_name.setEnabled(True)
                if saved_names[sid]:
                    edit_name.setText(saved_names[sid])
                checked_count += 1
            else:
                item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
                data["is_checked"] = False
                edit_name.setEnabled(False)

            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, data)

        self.tree.blockSignals(False)
        self.update_stats_label(checked_count)

    def on_item_check_state_changed(self, item, column):
        """Обрабатывает включение и выключение датчика пользователем."""
        if column != 0:
            return
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not data:
            return

        sid = data["id"]
        if sid not in self.sensor_items_map:
            return

        _, edit_name = self.sensor_items_map[sid]
        is_checked = (item.checkState(0) == QtCore.Qt.CheckState.Checked)
        was_checked = data.get("is_checked", False)

        if is_checked == was_checked:
            return

        data["is_checked"] = is_checked
        item.setData(0, QtCore.Qt.ItemDataRole.UserRole, data)
        edit_name.setEnabled(is_checked)

        if is_checked and not was_checked:
            raw_name = data.get("name", "Sensor")
            val_str = item.text(1) or data.get("value", "")
            s_type = data.get("type", "")
            if not edit_name.text().strip():
                edit_name.setText(format_sensor_name_with_unit(raw_name, val_str, s_type))

        self.update_stats_from_tree()

    def update_stats_from_tree(self):
        """Считает количество активных датчиков в профиле."""
        checked_count = sum(1 for it, _ in self.sensor_items_map.values() if it.checkState(0) == QtCore.Qt.CheckState.Checked)
        self.update_stats_label(checked_count)

    def update_stats_label(self, count):
        """Обновляет строку со статистикой выбранных датчиков."""
        self.lbl_stats.setText(LBL_WIZARD_STATS_TEMPLATE.format(profile=self.current_profile, count=count))

    def save_current_tree_to_profile_memory(self):
        """Сохраняет состояние дерева в структуру памяти активного профиля."""
        p1_list = []
        p2_list = []

        for sid, (item, edit_name) in self.sensor_items_map.items():
            if item.checkState(0) == QtCore.Qt.CheckState.Checked:
                data = item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}
                raw_name = data.get("name", "Sensor")
                s_type = data.get("type", "")
                val_str = item.text(1) or data.get("value", "")

                custom_name = edit_name.text().strip()
                if not custom_name:
                    custom_name = format_sensor_name_with_unit(raw_name, val_str, s_type)

                sensor_entry = {"id": sid, "name": custom_name}
                is_p2 = any(x in s_type.lower() for x in ["fan", "control", "rpm"])
                if is_p2:
                    p2_list.append(sensor_entry)
                else:
                    p1_list.append(sensor_entry)

        if self.current_profile not in self.profiles_db:
            self.profiles_db[self.current_profile] = {
                "summary_dir_name": self.current_profile.lower(),
                "chart_title_prefix": f"{self.current_profile} Thermal & Electrical Load Dynamics"
            }

        self.profiles_db[self.current_profile]["panel1_thermal_and_power"] = p1_list
        self.profiles_db[self.current_profile]["panel2_cooling_and_speed"] = p2_list

    def save_config_to_file(self):
        """Записывает актуальные профили в sensors_config.json."""
        self.save_current_tree_to_profile_memory()
        if "active_mode" in self.profiles_db:
            del self.profiles_db["active_mode"]

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.profiles_db, f, indent=4, ensure_ascii=False)

        self.btn_save.setText(BTN_CONFIG_SAVED)
        QtCore.QTimer.singleShot(2500, lambda: self.btn_save.setText(BTN_SAVE_CONFIG))

    def closeEvent(self, event):
        """Останавливает воркер при закрытии окна."""
        self.worker.stop()
        event.accept()