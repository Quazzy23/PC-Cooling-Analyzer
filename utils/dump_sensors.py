"""Утилита диагностического дампа всех активных датчиков LHM в текстовый файл."""
import os
import sys
sys.dont_write_bytecode = True
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.lhm_client import LHM_URL, ensure_lhm_running
from core.texts import (
    MSG_DUMP_BANNER, MSG_CONNECTING_LHM, MSG_CONNECTED_LHM,
    MSG_ERR_CONNECT_LHM, MSG_DUMP_COMPLETE, MSG_TOTAL_SENSORS_HEADER
)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SYS_INFO_DIR = os.path.join(PROJECT_ROOT, "system_info")
os.makedirs(SYS_INFO_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(SYS_INFO_DIR, "lhm_sensors_dump.txt")

print(MSG_DUMP_BANNER)

# 1. Автозапуск LHM при необходимости
ensure_lhm_running()

# 2. Подключение к Web API
print(MSG_CONNECTING_LHM.format(url=LHM_URL))
try:
    res = requests.get(LHM_URL, timeout=2.0)
    res.raise_for_status()
    raw_json = res.json()
    print(MSG_CONNECTED_LHM)
except Exception:
    print(MSG_ERR_CONNECT_LHM.format(url=LHM_URL))
    sys.exit(1)

lines = []
total_sensors_count = [0]


def traverse_json_tree(node, level: int = 0):
    """Рекурсивно обходит дерево JSON и форматирует иерархический список датчиков."""
    if isinstance(node, dict):
        text = node.get("Text", "Unknown")
        sensor_type = node.get("Type", "")
        sensor_id = node.get("SensorId", "")
        val_str = node.get("Value", "")
        children = node.get("Children", [])

        indent = "  " * level

        if sensor_id and val_str is not None:
            total_sensors_count[0] += 1
            formatted_val = val_str.replace(".", ",")
            line = f"{indent}      |-- [{sensor_type:<11}] {text:<36} | ID: {sensor_id:<38} | Val: {formatted_val}"
            lines.append(line)
        else:
            line_prefix = f"\n{indent}" if level >= 1 else indent
            lines.append(f"{line_prefix}[{text}]")

        for child in children:
            traverse_json_tree(child, level + 1)

    elif isinstance(node, list):
        for item in node:
            traverse_json_tree(item, level)


# Построение дерева датчиков
traverse_json_tree(raw_json)

lines.append(MSG_TOTAL_SENSORS_HEADER.format(total=total_sensors_count[0]))

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(MSG_DUMP_COMPLETE.format(total=total_sensors_count[0], path=OUTPUT_FILE))