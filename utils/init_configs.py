"""
Initial Setup & Sensors Configuration Wizard
1. Prompts for and validates LibreHardwareMonitor path (folder or .exe).
2. Auto-launches LibreHardwareMonitor with Administrator privileges.
3. Launches the Graphical Sensors Configuration Wizard (PyQt6).
"""
import os
import sys
sys.dont_write_bytecode = True
import re
import json
import time
import requests
from PyQt6 import QtCore, QtGui, QtWidgets

# Добавляем корень проекта в путь импорта
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.lhm_client import LHM_URL, LHM_PATH_FILE, ensure_lhm_running

SYS_INFO_DIR = "system_info"
CONFIG_FILE = os.path.join(SYS_INFO_DIR, "sensors_config.json")
DEFAULT_LHM_PATH = r"C:\Program Files\LibreHardwareMonitor\LibreHardwareMonitor.exe"

os.makedirs(SYS_INFO_DIR, exist_ok=True)


def resolve_lhm_path(raw_input: str) -> str:
    """Resolves folder path or direct executable path to valid LibreHardwareMonitor.exe"""
    clean = raw_input.strip().strip('"').strip("'")
    if not clean:
        return ""

    norm = os.path.normpath(clean)

    # Если ввели путь к папке
    if os.path.isdir(norm):
        target = os.path.join(norm, "LibreHardwareMonitor.exe")
        if os.path.isfile(target):
            return target
        for f in os.listdir(norm):
            if f.lower() == "librehardwaremonitor.exe":
                return os.path.join(norm, f)
        return ""

    # Если ввели прямой путь к .exe
    if os.path.isfile(norm) and norm.lower().endswith(".exe"):
        return norm

    # Если опустили расширение .exe
    if not norm.lower().endswith(".exe"):
        target = os.path.join(norm, "LibreHardwareMonitor.exe")
        if os.path.isfile(target):
            return target

    return ""


def ensure_valid_lhm_path_on_disk():
    """Checks existing lhm_path.txt or prompts user to specify the folder/executable"""
    current_path = ""
    if os.path.exists(LHM_PATH_FILE):
        try:
            with open(LHM_PATH_FILE, "r", encoding="utf-8") as f:
                saved = f.read().strip()
                resolved = resolve_lhm_path(saved)
                if resolved and os.path.isfile(resolved):
                    current_path = resolved
        except Exception:
            pass

    if current_path and os.path.isfile(current_path):
        print(f"[OK] Verified LibreHardwareMonitor path: '{current_path}'")
        return current_path

    print("=" * 70)
    print("      LIBRE HARDWARE MONITOR — INITIAL PATH CONFIGURATION      ")
    print("=" * 70)
    if os.path.exists(LHM_PATH_FILE) and not current_path:
        print("[WARNING] The previously configured path is invalid or executable was not found.")

    print("\nPlease enter the path to the folder containing LibreHardwareMonitor.exe")
    print("Hint: You can just copy and paste the folder path from Windows Explorer.")
    print(f"Default fallback: {DEFAULT_LHM_PATH}\n")

    while True:
        try:
            user_input = input("Enter LHM folder path or .exe path (Press Enter for default): ").strip()
        except KeyboardInterrupt:
            print("\nSetup cancelled by user.")
            sys.exit(0)

        target_candidate = user_input if user_input else DEFAULT_LHM_PATH
        resolved = resolve_lhm_path(target_candidate)

        if resolved and os.path.isfile(resolved):
            with open(LHM_PATH_FILE, "w", encoding="utf-8") as f:
                f.write(resolved + "\n")
            print(f"\n[SUCCESS] LibreHardwareMonitor found: '{resolved}'")
            print(f"[SUCCESS] Saved to '{LHM_PATH_FILE}'\n")
            return resolved
        else:
            print(f"\n[ERROR] 'LibreHardwareMonitor.exe' was NOT found in '{target_candidate}'!")
            print("Please check the path and try again.\n")


def extract_unit_from_value(val_str: str) -> str:
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

    if unit:
        if not name.endswith(f"({unit})"):
            return f"{name} ({unit})"

    return name


def extract_sensor_values(node, result_dict):
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
    initial_tree_received = QtCore.pyqtSignal(dict)
    values_updated = QtCore.pyqtSignal(dict)
    connection_status = QtCore.pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self._running = True
        self._initial_tree_sent = False
        self.session = requests.Session()

    def run(self):
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
        self._running = False
        self.wait()


class SimpleSensorsWizard(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sensors Configuration Wizard")
        self.resize(1080, 750)
        self.setStyleSheet("""
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
        """)

        self.profiles_db = self.load_initial_config()
        self.current_profile = self.profiles_db.get("active_mode", "CPU")
        self.sensor_items_map = {}
        self.tree_initialized = False

        self.init_ui()

        self.worker = LHMWorker()
        self.worker.initial_tree_received.connect(self.build_tree_from_data)
        self.worker.values_updated.connect(self.on_values_updated)
        self.worker.connection_status.connect(self.on_connection_status_changed)
        self.worker.start()

    def load_initial_config(self):
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
                "chart_title_prefix": "CPU Thermal & Electrical Load Dynamics",
                "panel1_thermal_and_power": [],
                "panel2_cooling_and_speed": []
            },
            "GPU": {
                "summary_dir_name": "gpu",
                "chart_title_prefix": "GPU Thermal & Electrical Load Dynamics",
                "panel1_thermal_and_power": [],
                "panel2_cooling_and_speed": []
            }
        }

    def init_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        top_bar = QtWidgets.QHBoxLayout()
        top_bar.setSpacing(8)

        lbl_p = QtWidgets.QLabel("<b>PROFILE:</b>")
        lbl_p.setStyleSheet("color: #00E5FF; font-size: 9pt;")
        top_bar.addWidget(lbl_p)

        self.combo_profile = QtWidgets.QComboBox()
        self.combo_profile.setFixedWidth(110)
        self.update_profile_combo_items()
        self.combo_profile.currentTextChanged.connect(self.on_profile_switched)
        top_bar.addWidget(self.combo_profile)

        self.btn_new_profile = QtWidgets.QPushButton("Create Profile")
        self.btn_new_profile.clicked.connect(self.create_new_profile_dialog)
        top_bar.addWidget(self.btn_new_profile)

        self.btn_delete_profile = QtWidgets.QPushButton("Delete Profile")
        self.btn_delete_profile.setStyleSheet("""
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
        """)
        self.btn_delete_profile.clicked.connect(self.delete_current_profile_dialog)
        top_bar.addWidget(self.btn_delete_profile)

        top_bar.addSpacing(10)

        self.btn_save = QtWidgets.QPushButton("Save Configuration")
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #122216;
                color: #33FF57;
                font-weight: bold;
                border: 1px solid #1E4626;
                min-height: 28px;
            }
            QPushButton:hover {
                background-color: #182C1E;
                border: 1px solid #33FF57;
            }
        """)
        self.btn_save.clicked.connect(self.save_config_to_file)
        top_bar.addWidget(self.btn_save)

        top_bar.addStretch()

        self.lbl_status = QtWidgets.QLabel("Connecting to LHM...")
        self.lbl_status.setStyleSheet("color: #888888; font-size: 8.5pt; font-style: italic;")
        top_bar.addWidget(self.lbl_status)

        layout.addLayout(top_bar)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(["Sensor / Hardware", "Value", "Panel", "Order #", "Custom Name", "Sensor ID"])

        header = self.tree.header()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.Interactive)

        self.tree.setColumnWidth(1, 85)
        self.tree.setColumnWidth(2, 65)
        self.tree.setColumnWidth(3, 50)
        self.tree.setColumnWidth(4, 180)
        self.tree.setColumnWidth(5, 200)

        self.tree.itemChanged.connect(self.on_item_check_state_changed)
        layout.addWidget(self.tree, stretch=1)

        self.lbl_stats = QtWidgets.QLabel("Check sensors, select Panel (P1/P2), Order, and optionally type a Custom Name.")
        self.lbl_stats.setStyleSheet("color: #888888; font-size: 8.5pt;")
        layout.addWidget(self.lbl_stats)

    def update_profile_combo_items(self):
        self.combo_profile.blockSignals(True)
        self.combo_profile.clear()
        modes = [k for k in self.profiles_db.keys() if k not in ("active_mode",)]
        if not modes:
            modes = ["CPU", "GPU"]
        self.combo_profile.addItems(modes)
        idx = self.combo_profile.findText(self.current_profile)
        if idx >= 0:
            self.combo_profile.setCurrentIndex(idx)
        self.combo_profile.blockSignals(False)

    def create_new_profile_dialog(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "New Profile", "Enter new profile name (e.g. 'RAM', 'CHIPSET'):")
        if ok and name.strip():
            clean_name = name.strip().upper()
            if clean_name not in self.profiles_db:
                self.profiles_db[clean_name] = {
                    "summary_dir_name": clean_name.lower(),
                    "chart_title_prefix": f"{clean_name} Thermal & Electrical Load Dynamics",
                    "panel1_thermal_and_power": [],
                    "panel2_cooling_and_speed": []
                }
                self.current_profile = clean_name
                self.update_profile_combo_items()
                self.sync_tree_checkboxes_with_profile()

    def delete_current_profile_dialog(self):
        active_modes = [k for k in self.profiles_db.keys() if k not in ("active_mode",)]
        if len(active_modes) <= 1:
            QtWidgets.QMessageBox.warning(self, "Delete Profile", "Cannot delete the only remaining profile.")
            return

        reply = QtWidgets.QMessageBox.question(
            self, "Delete Profile",
            f"Are you sure you want to delete profile '{self.current_profile}'?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            if self.current_profile in self.profiles_db:
                del self.profiles_db[self.current_profile]

            remaining = [k for k in self.profiles_db.keys() if k not in ("active_mode",)]
            self.current_profile = remaining[0] if remaining else "CPU"
            self.update_profile_combo_items()
            self.sync_tree_checkboxes_with_profile()

    def on_profile_switched(self, new_profile):
        if not new_profile or new_profile == self.current_profile:
            return
        self.save_current_tree_to_profile_memory()
        self.current_profile = new_profile
        self.sync_tree_checkboxes_with_profile()

    def on_connection_status_changed(self, is_connected, status_text):
        if is_connected:
            self.lbl_status.setText(status_text)
            self.lbl_status.setStyleSheet("color: #33FF57; font-size: 8.5pt;")
        else:
            self.lbl_status.setText(status_text)
            self.lbl_status.setStyleSheet("color: #FF3366; font-size: 8.5pt;")
            if not self.tree_initialized:
                ensure_lhm_running()

    def build_tree_from_data(self, data: dict):
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
                    item = QtWidgets.QTreeWidgetItem(self.tree, [text, str(val) if val is not None else "", "", "", "", ""])
                    item.setExpanded(True)
                else:
                    item = QtWidgets.QTreeWidgetItem(parent_item, [text, str(val) if val is not None else "", "", "", "", ""])

                if s_id:
                    item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)

                    is_p2_default = any(x in s_type.lower() for x in ["fan", "control", "rpm"])

                    combo_panel = QtWidgets.QComboBox()
                    combo_panel.addItems(["P1", "P2"])
                    combo_panel.setCurrentText("P2" if is_p2_default else "P1")
                    combo_panel.setEnabled(False)
                    combo_panel.currentTextChanged.connect(self.update_stats_from_tree)
                    self.tree.setItemWidget(item, 2, combo_panel)

                    spin_order = QtWidgets.QSpinBox()
                    spin_order.setRange(1, 99)
                    spin_order.setValue(1)
                    spin_order.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
                    spin_order.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                    spin_order.setEnabled(False)
                    self.tree.setItemWidget(item, 3, spin_order)

                    default_formatted = format_sensor_name_with_unit(text, str(val), s_type)
                    edit_name = QtWidgets.QLineEdit()
                    edit_name.setText(default_formatted)
                    edit_name.setEnabled(False)
                    self.tree.setItemWidget(item, 4, edit_name)

                    item.setText(5, s_id)
                    item.setForeground(5, QtGui.QBrush(QtGui.QColor("#666666")))

                    item.setData(0, QtCore.Qt.ItemDataRole.UserRole, {
                        "id": s_id, "name": text, "type": s_type, "value": val, "is_checked": False
                    })

                    self.sensor_items_map[s_id] = (item, combo_panel, spin_order, edit_name)
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
        self.tree.blockSignals(True)

        prof_data = self.profiles_db.get(self.current_profile, {})

        p1_map = {}
        for idx, s in enumerate(prof_data.get("panel1_thermal_and_power", [])):
            p1_map[s.get("id")] = (s.get("order", idx + 1), s.get("name", ""))

        p2_map = {}
        for idx, s in enumerate(prof_data.get("panel2_cooling_and_speed", [])):
            p2_map[s.get("id")] = (s.get("order", idx + 1), s.get("name", ""))

        checked_p1 = 0
        checked_p2 = 0

        for sid, (item, combo_panel, spin_order, edit_name) in self.sensor_items_map.items():
            data = item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}

            if sid in p1_map:
                item.setCheckState(0, QtCore.Qt.CheckState.Checked)
                data["is_checked"] = True
                combo_panel.setEnabled(True)
                combo_panel.blockSignals(True)
                combo_panel.setCurrentText("P1")
                combo_panel.blockSignals(False)
                spin_order.setEnabled(True)
                order_val, saved_name = p1_map[sid]
                spin_order.setValue(order_val)
                edit_name.setEnabled(True)
                if saved_name:
                    edit_name.setText(saved_name)
                checked_p1 += 1
            elif sid in p2_map:
                item.setCheckState(0, QtCore.Qt.CheckState.Checked)
                data["is_checked"] = True
                combo_panel.setEnabled(True)
                combo_panel.blockSignals(True)
                combo_panel.setCurrentText("P2")
                combo_panel.blockSignals(False)
                spin_order.setEnabled(True)
                order_val, saved_name = p2_map[sid]
                spin_order.setValue(order_val)
                edit_name.setEnabled(True)
                if saved_name:
                    edit_name.setText(saved_name)
                checked_p2 += 1
            else:
                item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
                data["is_checked"] = False
                combo_panel.setEnabled(False)
                spin_order.setEnabled(False)
                edit_name.setEnabled(False)

            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, data)

        self.tree.blockSignals(False)
        self.update_stats_label(checked_p1, checked_p2)

    def on_item_check_state_changed(self, item, column):
        if column != 0:
            return
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not data:
            return

        sid = data["id"]
        if sid not in self.sensor_items_map:
            return

        _, combo_panel, spin_order, edit_name = self.sensor_items_map[sid]
        is_checked = (item.checkState(0) == QtCore.Qt.CheckState.Checked)
        was_checked = data.get("is_checked", False)

        if is_checked == was_checked:
            return

        data["is_checked"] = is_checked
        item.setData(0, QtCore.Qt.ItemDataRole.UserRole, data)

        combo_panel.setEnabled(is_checked)
        spin_order.setEnabled(is_checked)
        edit_name.setEnabled(is_checked)

        if is_checked and not was_checked:
            raw_name = data.get("name", "Sensor")
            val_str = item.text(1) or data.get("value", "")
            s_type = data.get("type", "")
            if not edit_name.text().strip():
                edit_name.setText(format_sensor_name_with_unit(raw_name, val_str, s_type))

            target_panel = combo_panel.currentText()
            existing_orders = []
            for s_id, (it, c_p, s_o, _) in self.sensor_items_map.items():
                if it.checkState(0) == QtCore.Qt.CheckState.Checked and s_id != sid:
                    if c_p.currentText() == target_panel:
                        existing_orders.append(s_o.value())

            next_order = max(existing_orders) + 1 if existing_orders else 1
            spin_order.setValue(next_order)

        self.update_stats_from_tree()

    def update_stats_from_tree(self):
        p1_cnt = 0
        p2_cnt = 0
        for sid, (item, combo_panel, spin_order, _) in self.sensor_items_map.items():
            if item.checkState(0) == QtCore.Qt.CheckState.Checked:
                if combo_panel.currentText() == "P2":
                    p2_cnt += 1
                else:
                    p1_cnt += 1
        self.update_stats_label(p1_cnt, p2_cnt)

    def update_stats_label(self, p1_cnt, p2_cnt):
        self.lbl_stats.setText(
            f"Profile <b>[{self.current_profile}]</b>: "
            f"<span style='color:#00E5FF;'>{p1_cnt} sensors in Panel 1</span> | "
            f"<span style='color:#33FF57;'>{p2_cnt} sensors in Panel 2</span> (Sorted by Order #)"
        )

    def save_current_tree_to_profile_memory(self):
        p1_entries = []
        p2_entries = []

        for sid, (item, combo_panel, spin_order, edit_name) in self.sensor_items_map.items():
            if item.checkState(0) == QtCore.Qt.CheckState.Checked:
                data = item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}
                raw_name = data.get("name", "Sensor")
                s_type = data.get("type", "")
                val_str = item.text(1) or data.get("value", "")

                target_panel = combo_panel.currentText()
                order_num = spin_order.value()

                custom_name = edit_name.text().strip()
                if not custom_name:
                    custom_name = format_sensor_name_with_unit(raw_name, val_str, s_type)

                sensor_dict = {
                    "order": order_num,
                    "id": sid,
                    "name": custom_name
                }

                if target_panel == "P2":
                    p2_entries.append((order_num, sensor_dict))
                else:
                    p1_entries.append((order_num, sensor_dict))

        p1_entries.sort(key=lambda x: x[0])
        p2_entries.sort(key=lambda x: x[0])

        p1_list = [entry[1] for entry in p1_entries]
        p2_list = [entry[1] for entry in p2_entries]

        if self.current_profile not in self.profiles_db:
            self.profiles_db[self.current_profile] = {
                "summary_dir_name": self.current_profile.lower(),
                "chart_title_prefix": f"{self.current_profile} Thermal & Electrical Load Dynamics"
            }

        self.profiles_db[self.current_profile]["panel1_thermal_and_power"] = p1_list
        self.profiles_db[self.current_profile]["panel2_cooling_and_speed"] = p2_list

    def save_config_to_file(self):
        self.save_current_tree_to_profile_memory()
        if "active_mode" in self.profiles_db:
            del self.profiles_db["active_mode"]

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.profiles_db, f, indent=4, ensure_ascii=False)

        self.btn_save.setText("Config Saved!")
        self.lbl_status.setText(f"File '{CONFIG_FILE}' updated successfully!")
        QtCore.QTimer.singleShot(2500, lambda: self.btn_save.setText("Save Configuration"))
        print(f"[SUCCESS] Configuration saved to: {CONFIG_FILE}")

    def closeEvent(self, event):
        self.worker.stop()
        event.accept()


# =======================================================
#                      MAIN ENTRY POINT
# =======================================================
if __name__ == "__main__":
    # 1. Проверяем или запрашиваем путь к LHM (поддерживает путь к папке)
    lhm_exe = ensure_valid_lhm_path_on_disk()

    # 2. Автозапуск LHM от Администратора
    ensure_lhm_running(lhm_exe)

    # 3. Открываем графический визард настройки датчиков
    app = QtWidgets.QApplication(sys.argv)
    win = SimpleSensorsWizard()
    win.show()
    sys.exit(app.exec())