import os
import sys
import json

try:
    import sounddevice as sd
except ImportError:
    print("[ERROR] Library 'sounddevice' is not installed! Run: pip install sounddevice numpy")
    sys.exit(1)

SYS_INFO_DIR = "system_info"
os.makedirs(SYS_INFO_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(SYS_INFO_DIR, "audio_config.json")

print("=" * 65)
print("          MICROPHONE SELECTION FOR COOLING BENCHMARKS          ")
print("=" * 65)

# 1. Query WASAPI input devices without duplicates
devices = sd.query_devices()
host_apis = sd.query_hostapis()

wasapi_idx = None
for h_idx, api in enumerate(host_apis):
    if "wasapi" in api['name'].lower():
        wasapi_idx = h_idx
        break

clean_input_devices = []
seen_core_names = set()

for idx, dev in enumerate(devices):
    if dev['max_input_channels'] > 0:
        if wasapi_idx is not None and dev['hostapi'] != wasapi_idx:
            continue

        raw_name = dev['name'].strip()
        core_name = raw_name
        if "(" in raw_name and ")" in raw_name:
            core_name = raw_name.split("(")[-1].replace(")", "").strip()

        norm_key = core_name.lower()
        if norm_key not in seen_core_names:
            seen_core_names.add(norm_key)
            clean_input_devices.append((idx, core_name, raw_name))

print("\nAvailable Physical Microphones:")
for choice_num, (dev_idx, core_name, raw_name) in enumerate(clean_input_devices):
    print(f" [{choice_num + 1}] {core_name}")

print(" [0] Disable Audio Recording")
print("-" * 65)

choice = input("Select microphone number for benchmarks: ").strip()

if choice == "0":
    cfg = {"audio_logging_enabled": False}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)
    print("\n[OK] Audio recording DISABLED.")
    sys.exit(0)

if choice.isdigit() and 1 <= int(choice) <= len(clean_input_devices):
    selected = clean_input_devices[int(choice) - 1]
else:
    selected = clean_input_devices[0]

selected_idx, selected_core_name, selected_raw_name = selected

cfg = {
    "audio_logging_enabled": True,
    "device_index": selected_idx,
    "device_name": selected_core_name,
    "calibration_offset": 90.0
}

with open(CONFIG_FILE, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=4, ensure_ascii=False)

print("\n" + "=" * 65)
print(f"[SUCCESS] Microphone configuration saved to: {CONFIG_FILE}")
print(f" Selected Device : {selected_core_name}")
print(" 'logger.py' will now automatically record noise levels from this microphone!")
print("=" * 65)