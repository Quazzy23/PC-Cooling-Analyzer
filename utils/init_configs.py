"""
Утилита инициализации начальных файлов конфигурации (sensors_config.json и lhm_path.txt)
"""
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

SYS_INFO_DIR = "system_info"
SENSORS_CONFIG_FILE = os.path.join(SYS_INFO_DIR, "sensors_config.json")
LHM_PATH_FILE = os.path.join(SYS_INFO_DIR, "lhm_path.txt")

os.makedirs(SYS_INFO_DIR, exist_ok=True)

TEMPLATE_SENSORS = {
    "active_mode": "CPU",
    "CPU": {
        "summary_dir_name": "cpu",
        "chart_title_prefix": "CPU Thermal & Electrical Load Dynamics",
        "panel1_thermal_and_power": [
            {"id": "<PASTE_CPU_TEMP_SENSOR_ID_HERE>", "name": "CPU Temp (C)"},
            {"id": "<PASTE_CPU_POWER_SENSOR_ID_HERE>", "name": "CPU Package Power (W)"},
            {"id": "<PASTE_CPU_LOAD_SENSOR_ID_HERE>", "name": "CPU Total Load (%)"},
            {"id": "<PASTE_CPU_VOLTAGE_SENSOR_ID_HERE>", "name": "CPU Voltage (V)"},
            {"id": "<PASTE_CPU_CLOCK_SENSOR_ID_HERE>", "name": "Clock (MHz)"}
        ],
        "panel2_cooling_and_speed": [
            {"id": "<PASTE_CPU_FAN_RPM_SENSOR_ID_HERE>", "name": "CPU Fan (RPM)"},
            {"id": "<PASTE_CHASSIS_FAN_RPM_SENSOR_ID_HERE>", "name": "Chassis Fan 1 (RPM)"}
        ]
    },
    "GPU": {
        "summary_dir_name": "gpu",
        "chart_title_prefix": "GPU Thermal & Electrical Load Dynamics",
        "panel1_thermal_and_power": [
            {"id": "<PASTE_GPU_CORE_TEMP_SENSOR_ID_HERE>", "name": "GPU Core Temp (C)"},
            {"id": "<PASTE_GPU_HOTSPOT_TEMP_SENSOR_ID_HERE>", "name": "GPU Hot Spot (C)"},
            {"id": "<PASTE_GPU_POWER_SENSOR_ID_HERE>", "name": "GPU Power (W)"},
            {"id": "<PASTE_GPU_LOAD_SENSOR_ID_HERE>", "name": "GPU Load (%)"},
            {"id": "<PASTE_GPU_VOLTAGE_SENSOR_ID_HERE>", "name": "GPU Voltage (V)"},
            {"id": "<PASTE_GPU_CLOCK_SENSOR_ID_HERE>", "name": "GPU Clock (MHz)"}
        ],
        "panel2_cooling_and_speed": [
            {"id": "<PASTE_GPU_FAN_RPM_SENSOR_ID_HERE>", "name": "GPU Fan (RPM)"}
        ]
    }
}

# 1. Создание шаблона sensors_config.json
if not os.path.exists(SENSORS_CONFIG_FILE):
    with open(SENSORS_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(TEMPLATE_SENSORS, f, indent=4, ensure_ascii=False)
    print(f"[SUCCESS] Created sensors config template: '{SENSORS_CONFIG_FILE}'")
else:
    print(f"[INFO] Sensors config already exists: '{SENSORS_CONFIG_FILE}'")

# 2. Создание простого текстового файла lhm_path.txt
if not os.path.exists(LHM_PATH_FILE):
    with open(LHM_PATH_FILE, "w", encoding="utf-8") as f:
        f.write(r"C:\Path\To\LibreHardwareMonitor\LibreHardwareMonitor.exe" + "\n")
    print(f"[SUCCESS] Created LHM path file: '{LHM_PATH_FILE}'")
else:
    print(f"[INFO] LHM path file already exists: '{LHM_PATH_FILE}'")