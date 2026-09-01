"""
Клиент для взаимодействия с LibreHardwareMonitor Web API:
- Считывание пути к исполняемому файлу из system_info/lhm_config.json
- Автозапуск и безопасное закрытие процесса
- Опрос и парсинг дерева датчиков
- Извлечение паспорта оборудования ПК
"""
import os
import json
import time
import subprocess
import requests

SYS_INFO_DIR = "system_info"
LHM_PATH_FILE = os.path.join(SYS_INFO_DIR, "lhm_path.txt")
LHM_CONFIG_FILE = os.path.join(SYS_INFO_DIR, "lhm_config.json")
LHM_URL = "http://localhost:8085/data.json"
FALLBACK_LHM_EXE_PATH = r"C:\Program Files\LibreHardwareMonitor\LibreHardwareMonitor.exe"


def get_lhm_exe_path() -> str:
    """Считывает путь к LibreHardwareMonitor.exe (поддерживает путь к папке или к файлу)"""
    if os.path.exists(LHM_PATH_FILE):
        try:
            with open(LHM_PATH_FILE, "r", encoding="utf-8") as f:
                path = f.read().strip().strip('"').strip("'")
                if path and not path.startswith("<"):
                    norm = os.path.normpath(path)
                    if os.path.isdir(norm):
                        candidate = os.path.join(norm, "LibreHardwareMonitor.exe")
                        if os.path.exists(candidate):
                            return candidate
                    return norm
        except Exception:
            pass

    return FALLBACK_LHM_EXE_PATH


def clean_sensor_value(val_str):
    """Очищает строку датчика от единиц измерения и преобразует в float"""
    if not val_str:
        return None
    cleaned = (
        val_str.replace("°C", "")
        .replace("W", "")
        .replace("%", "")
        .replace("MHz", "")
        .replace("RPM", "")
        .replace("V", "")
        .replace("GB", "")
        .replace("MB/s", "")
        .replace("KB/s", "")
        .replace("A", "")
        .replace(",", ".")
        .strip()
    )
    try:
        return float(cleaned)
    except ValueError:
        return None


def ensure_lhm_running(exe_path: str = None, url: str = LHM_URL):
    """Проверяет доступность LHM API и запускает процесс с правами админа с ожиданием веб-сервера"""
    try:
        r = requests.get(url, timeout=0.8)
        if r.status_code == 200:
            return True
    except Exception:
        pass

    target_exe = exe_path or get_lhm_exe_path()
    print("[INFO] LibreHardwareMonitor is not running. Auto-starting background process...")
    if os.path.exists(target_exe):
        try:
            os.startfile(target_exe, "runas")
            print(f"[OK] Launched {os.path.basename(target_exe)} (Admin). Waiting for web server at {url}...")
            for _ in range(20):
                time.sleep(0.5)
                try:
                    check_res = requests.get(url, timeout=0.8)
                    if check_res.status_code == 200:
                        print("[OK] Web server is ready!")
                        return True
                except Exception:
                    pass
            return True
        except Exception as e:
            print(f"[WARNING] Could not auto-launch {target_exe}: {e}")
            return False
    else:
        print(f"[WARNING] Executable not found at: {target_exe}")
        print(f"Please specify the correct path in '{LHM_PATH_FILE}' (run 'python utils/init_configs.py')")
        return False


def close_lhm_process():
    """Принудительно закрывает фоновый процесс LibreHardwareMonitor"""
    try:
        subprocess.run("taskkill /F /IM LibreHardwareMonitor.exe", shell=True, capture_output=True)
        print("\n[OK] LibreHardwareMonitor process closed.")
    except Exception:
        pass


def flatten_json_tree(node, sensor_map, parent_hw_name="System"):
    """Рекурсивно разворачивает JSON дерево LHM в плоский словарь датчиков"""
    if isinstance(node, dict):
        text = node.get("Text", "")
        sensor_id = node.get("SensorId")
        val_str = node.get("Value")
        children = node.get("Children", [])

        current_hw = parent_hw_name
        if children and not sensor_id and text:
            ignored_groups = [
                "Voltages", "Powers", "Temperatures", "Clocks", "Load",
                "Fans", "Controls", "Currents", "Data", "Timings",
                "Factors", "Levels", "Throughput"
            ]
            if text not in ignored_groups:
                current_hw = text

        if sensor_id and val_str is not None:
            full_display_name = f"{current_hw} - {text}" if current_hw != "System" else text
            sensor_map[sensor_id] = {
                "display_name": full_display_name,
                "value": clean_sensor_value(val_str)
            }

        for child in children:
            flatten_json_tree(child, sensor_map, current_hw)

    elif isinstance(node, list):
        for item in node:
            flatten_json_tree(item, sensor_map, parent_hw_name)


def extract_hardware_structure(data):
    """Извлекает имена устройств и категории датчиков для сохранения паспорта железа"""
    pc_name = "Unknown PC"
    hardware_list = []

    root_children = data.get("Children", [])
    computer_node = data
    if root_children and isinstance(root_children[0], dict):
        if "Children" in root_children[0]:
            computer_node = root_children[0]
            pc_name = computer_node.get("Text", "Unknown PC")
        else:
            pc_name = data.get("Text", "Unknown PC")

    def get_categories(hw_node):
        cats = set()
        def _search(curr):
            if isinstance(curr, dict):
                children = curr.get("Children", [])
                if any(isinstance(c, dict) and c.get("SensorId") for c in children):
                    cat_name = curr.get("Text")
                    if cat_name:
                        cats.add(cat_name)
                for c in children:
                    _search(c)
        _search(hw_node)
        return sorted(list(cats))

    for hw in computer_node.get("Children", []):
        if isinstance(hw, dict):
            hw_name = hw.get("Text")
            if hw_name:
                categories = get_categories(hw)
                hardware_list.append({
                    "name": hw_name,
                    "categories": categories
                })

    return pc_name, hardware_list