import os
import sys
import requests

# Output Paths
SYS_INFO_DIR = "system_info"
os.makedirs(SYS_INFO_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(SYS_INFO_DIR, "lhm_sensors_dump.txt")

URL = "http://localhost:8085/data.json"

print("=" * 70)
print("     LIBRE HARDWARE MONITOR APPLICATION — SENSOR DUMP TOOL     ")
print("=" * 70)

print(f"Connecting to LibreHardwareMonitor Web Server at {URL}...")
try:
    res = requests.get(URL, timeout=2.0)
    res.raise_for_status()
    raw_json = res.json()
    print("[OK] Connected successfully to LibreHardwareMonitor application!")
except Exception as e:
    print(f"\n[ERROR] Could not connect to LibreHardwareMonitor at {URL}")
    print("Ensure LibreHardwareMonitor.exe is running and 'Remote Web Server' is enabled in Options menu.")
    sys.exit(1)

lines = []
total_sensors_count = [0]

def traverse_json_tree(node, level=0):
    if isinstance(node, dict):
        text = node.get("Text", "Unknown")
        sensor_type = node.get("Type", "")
        sensor_id = node.get("SensorId", "")
        val_str = node.get("Value", "")
        children = node.get("Children", [])

        indent = "  " * level

        # Если это конечный датчик (есть SensorId и Value)
        if sensor_id and val_str is not None:
            total_sensors_count[0] += 1
            formatted_val = val_str.replace(".", ",")
            line = f"{indent}      ├─ [{sensor_type:<11}] {text:<36} | ID: {sensor_id:<38} | Val: {formatted_val}"
            lines.append(line)
        else:
            # Если это папка (Корень, ПК, Железо или Категория)
            if level >= 1:
                # Пустая строка перед папками категорий (Voltages, Temps, Fans...)
                lines.append(f"\n{indent}📁 [{text}]")
            else:
                lines.append(f"{indent}📁 [{text}]")

        for child in children:
            traverse_json_tree(child, level + 1)

    elif isinstance(node, list):
        for item in node:
            traverse_json_tree(item, level)

# Построение дерева датчиков
traverse_json_tree(raw_json)

lines.append("\n" + "=" * 95)
lines.append(f"TOTAL ACTIVE SENSORS FOUND IN APPLICATION: {total_sensors_count[0]}")
lines.append("=" * 95)

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"\n[SUCCESS] Application sensor dump complete!")
print(f" Total sensors scanned : {total_sensors_count[0]}")
print(f" Dump file saved to    : {OUTPUT_FILE}")
print("=" * 70)