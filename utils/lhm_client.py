"""
Клиент для взаимодействия с LibreHardwareMonitor:
- Определение CPU и GPU строго через встроенный Enum: HardwareType
- Автозапуск и безопасное закрытие процесса LHM
- Опрос и парсинг дерева датчиков Web API
"""
import os
import json
import time
import subprocess
import requests

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SYS_INFO_DIR = os.path.join(PROJECT_ROOT, "system_info")
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


def get_lhm_dll_path() -> str:
    """Находит LibreHardwareMonitorLib.dll рядом с исполняемым файлом LHM"""
    exe_path = get_lhm_exe_path()
    lhm_dir = os.path.dirname(exe_path) if exe_path.lower().endswith(".exe") else exe_path
    dll_path = os.path.join(lhm_dir, "LibreHardwareMonitorLib.dll")
    if os.path.exists(dll_path):
        return dll_path
    return None

def unblock_file(file_path: str):
    """Снимает блокировку безопасности Windows (Zone.Identifier) с файла"""
    if not file_path or not os.path.exists(file_path):
        return
    # Способ 1: прямое удаление потока NTFS через Win32 API
    try:
        import ctypes
        ctypes.windll.kernel32.DeleteFileW(f"{file_path}:Zone.Identifier")
    except Exception:
        pass
    # Способ 2: нативная команда PowerShell
    try:
        subprocess.run(
            f'powershell -NoProfile -Command "Unblock-File -LiteralPath \'{file_path}\'"',
            shell=True, capture_output=True
        )
    except Exception:
        pass


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
        .replace("ns", "")
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


def extract_hardware_structure(raw_json=None):
    """
    Определяет CPU и GPU строго через встроенный enum HardwareType библиотеки LibreHardwareMonitor.
    Никакого парсинга строк и догадок.
    """
    pc_name = "Unknown PC"
    if raw_json:
        root_children = raw_json.get("Children", [])
        if root_children and isinstance(root_children[0], dict) and "Children" in root_children[0]:
            pc_name = root_children[0].get("Text", "Unknown PC")
        else:
            pc_name = raw_json.get("Text", "Unknown PC")

    detected_cpu = "CPU"
    detected_gpu = "GPU"
    hardware_list = []

    dll_path = get_lhm_dll_path()
    if dll_path:
        unblock_file(dll_path)
        try:
            import clr
            clr.AddReference(dll_path)
            from LibreHardwareMonitor.Hardware import Computer, HardwareType  # type: ignore

            computer = Computer()
            computer.IsCpuEnabled = True
            computer.IsGpuEnabled = True
            computer.IsMotherboardEnabled = True
            computer.Open()

            try:
                for hardware in computer.Hardware:
                    hw_name = hardware.Name
                    hw_type_enum = hardware.HardwareType

                    # Строгая проверка по системному перечислению LHM HardwareType
                    if hw_type_enum == HardwareType.Cpu:
                        hw_type_str = "CPU"
                        if detected_cpu == "CPU":
                            detected_cpu = hw_name
                    elif hw_type_enum in (HardwareType.GpuNvidia, HardwareType.GpuAmd, HardwareType.GpuIntel):
                        hw_type_str = "GPU"
                        if detected_gpu == "GPU":
                            detected_gpu = hw_name
                    else:
                        hw_type_str = str(hw_type_enum)

                    hardware_list.append({
                        "name": hw_name,
                        "type": hw_type_str
                    })
            finally:
                computer.Close()

        except Exception as e:
            print(f"[WARNING] Could not read hardware via LibreHardwareMonitorLib.HardwareType: {e}")

    # Резервный случай: если DLL заблокирована или не загрузилась
    if not hardware_list and raw_json:
        for hw in raw_json.get("Children", [{}])[0].get("Children", []):
            if isinstance(hw, dict):
                hardware_list.append({
                    "name": hw.get("Text", "Hardware"),
                    "type": "Other"
                })

    system_metadata = {
        "computer_name": pc_name,
        "cpu_name": detected_cpu,
        "gpu_name": detected_gpu,
        "hardware_count": len(hardware_list),
        "components": hardware_list
    }
    return pc_name, system_metadata