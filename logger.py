import os
import sys
import time
import csv
import json
import subprocess

import requests
import numpy as np
import sounddevice as sd

# Enable ANSI escape sequences in Windows Console
os.system("")

# ================= CONFIGURATION =================
URL = "http://localhost:8085/data.json"
INTERVAL = 0.25  # Poll every 250 ms (4 Hz)
POSTFIX = "test"  # Default log postfix

# Завершать ли процесс LibreHardwareMonitor при закрытии?
# 1 = Да (закрывать LHM при выходе), 0 = Нет (оставлять LHM работать в трее)
CLOSE_LHM_ON_EXIT = 1

# Укажите точный путь к вашему LibreHardwareMonitor.exe на ПК:
LHM_EXE_PATH = r"C:\Users\23spi\Downloads\LibreHardwareMonitor\LibreHardwareMonitor.exe"

RESULTS_DIR = "results"
LOGS_DIR = os.path.join(RESULTS_DIR, "sensors_logs")
SYS_INFO_DIR = "system_info"

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(SYS_INFO_DIR, exist_ok=True)

filename = os.path.join(LOGS_DIR, f"table_raw_{POSTFIX}.csv")
hw_info_filename = os.path.join(SYS_INFO_DIR, "hardware_info.json")
AUDIO_CFG_FILE = os.path.join(SYS_INFO_DIR, "audio_config.json")

# TARGET DISPLAY SENSORS FOR REAL-TIME CONSOLE TABLE
ID_CPU_TEMP  = "/amdcpu/0/temperature/4"  # CPU CCD1 (Tdie)
ID_CPU_POWER = "/amdcpu/0/power/0"        # CPU Package Power
ID_CPU_LOAD  = "/amdcpu/0/load/0"         # CPU Total Load
ID_CPU_PUMP  = "/lpc/nct6798d/0/fan/5"    # AIO_PUMP (Fan #6)

ID_GPU_TEMP  = "/gpu-nvidia/0/temperature/0" # GPU Core Temp
ID_GPU_POWER = "/gpu-nvidia/0/power/0"       # GPU Package Power
ID_GPU_LOAD  = "/gpu-nvidia/0/load/0"        # GPU Core Load
ID_GPU_FAN   = "/gpu-nvidia/0/fan/1"         # GPU Fan Speed
# ================================================

# --- AUDIO ENCODER SETUP ---
try:
    import lameenc
    HAS_LAME = True
except ImportError:
    import wave
    HAS_LAME = False

audio_ext = ".mp3" if HAS_LAME else ".wav"
audio_filename = os.path.join(LOGS_DIR, f"audio_raw_{POSTFIX}{audio_ext}")

# --- АВТОЗАПУСК ПРИЛОЖЕНИЯ ПРИ НЕОБХОДИМОСТИ ---
def ensure_lhm_running():
    try:
        r = requests.get(URL, timeout=0.8)
        r.raise_for_status()
        return False
    except Exception:
        print("[INFO] LibreHardwareMonitor is not running. Auto-starting background process...")
        if os.path.exists(LHM_EXE_PATH):
            try:
                os.startfile(LHM_EXE_PATH, "runas")
                print("[OK] Launched LibreHardwareMonitor.exe with Admin rights. Waiting for web server...")
                for _ in range(10):
                    time.sleep(0.5)
                    try:
                        check_res = requests.get(URL, timeout=0.8)
                        if check_res.status_code == 200:
                            print("[OK] Web server is ready!")
                            return True
                    except Exception:
                        pass
                return True
            except Exception as e:
                print(f"[WARNING] Could not auto-launch {LHM_EXE_PATH}: {e}")
                return False
        else:
            print(f"[WARNING] Executable not found at: {LHM_EXE_PATH}")
            print("Check the 'LHM_EXE_PATH' variable at the top of logger.py")
            return False

ensure_lhm_running()

def close_lhm_if_needed():
    """Завершает процесс LibreHardwareMonitor при выходе, если включен флаг CLOSE_LHM_ON_EXIT=1"""
    if CLOSE_LHM_ON_EXIT == 1:
        try:
            subprocess.run("taskkill /F /IM LibreHardwareMonitor.exe", shell=True, capture_output=True)
            print("\n[OK] LibreHardwareMonitor process closed on exit.")
        except Exception:
            pass

def clean_val(val_str):
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

def flatten_json_tree(node, sensor_map, parent_hw_name="System"):
    if isinstance(node, dict):
        text = node.get("Text", "")
        sensor_id = node.get("SensorId")
        val_str = node.get("Value")
        children = node.get("Children", [])

        current_hw = parent_hw_name
        if children and not sensor_id and text:
            if text not in ["Voltages", "Powers", "Temperatures", "Clocks", "Load", "Fans", "Controls", "Currents", "Data", "Timings", "Factors", "Levels", "Throughput"]:
                current_hw = text

        if sensor_id and val_str is not None:
            full_display_name = f"{current_hw} - {text}" if current_hw != "System" else text
            sensor_map[sensor_id] = {
                "display_name": full_display_name,
                "value": clean_val(val_str)
            }

        for child in children:
            flatten_json_tree(child, sensor_map, current_hw)

    elif isinstance(node, list):
        for item in node:
            flatten_json_tree(item, sensor_map, parent_hw_name)

def extract_hardware_structure(data):
    pc_name = "Unknown PC"
    hardware_list = []

    root_children = data.get("Children", [])
    computer_node = None

    if root_children and isinstance(root_children[0], dict):
        if "Children" in root_children[0]:
            computer_node = root_children[0]
            pc_name = computer_node.get("Text", "Unknown PC")
        else:
            pc_name = data.get("Text", "Unknown PC")
            computer_node = data
    else:
        computer_node = data

    def get_categories_recursive(hw_node):
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
                categories = get_categories_recursive(hw)
                hardware_list.append({
                    "name": hw_name,
                    "categories": categories
                })

    return pc_name, hardware_list

# --- CHECK CONNECTION TO APPLICATION ---
print(f"Connecting to LibreHardwareMonitor Web Server at {URL}...")
session = requests.Session()
try:
    res = session.get(URL, timeout=2.0)
    res.raise_for_status()
    raw_json = res.json()
    print("[OK] Connected to LibreHardwareMonitor application successfully!")
except Exception as e:
    print(f"\n[ERROR] Could not connect to LibreHardwareMonitor at {URL}")
    print("Ensure LibreHardwareMonitor.exe is running and 'Remote Web Server' is enabled in Options menu.")
    sys.exit(1)

# --- INITIALIZE BACKGROUND AUDIO STREAM ---
current_sound_dba = None
audio_stream = None
mic_name_str = "Microphone"
mp3_encoder = None
audio_file_obj = None

if os.path.exists(AUDIO_CFG_FILE):
    try:
        with open(AUDIO_CFG_FILE, "r", encoding="utf-8") as f:
            acfg = json.load(f)

        if acfg.get("audio_logging_enabled", False):
            mic_idx = acfg.get("device_index")
            mic_name_str = acfg.get("device_name", "Microphone")
            cal_offset = acfg.get("calibration_offset", 90.0)

            dev_info = sd.query_devices(mic_idx)
            sr = int(dev_info['default_samplerate'])

            if HAS_LAME:
                mp3_encoder = lameenc.Encoder()
                mp3_encoder.set_bit_rate(128)
                mp3_encoder.set_in_sample_rate(sr)
                mp3_encoder.set_channels(1)
                mp3_encoder.set_quality(2)
                audio_file_obj = open(audio_filename, "wb")
            else:
                audio_file_obj = wave.open(audio_filename, "wb")
                audio_file_obj.setnchannels(1)
                audio_file_obj.setsampwidth(2)
                audio_file_obj.setframerate(sr)

            def audio_callback(indata, frames, time_info, status):
                global current_sound_dba
                sig = np.nan_to_num(indata[:, 0], nan=0.0, posinf=0.0, neginf=0.0)
                sig = np.clip(sig, -1.0, 1.0)
                
                rms = np.sqrt(np.mean(sig**2) + 1e-12)
                db = round(20 * np.log10(rms) + cal_offset, 1)
                current_sound_dba = max(0.0, db)

                pcm16_bytes = (sig * 32767).astype(np.int16).tobytes()
                if HAS_LAME and mp3_encoder and audio_file_obj:
                    chunk = mp3_encoder.encode(pcm16_bytes)
                    if chunk:
                        audio_file_obj.write(chunk)
                elif audio_file_obj:
                    audio_file_obj.writeframes(pcm16_bytes)

            audio_stream = sd.InputStream(
                device=mic_idx,
                channels=1,
                samplerate=sr,
                blocksize=int(sr * 0.25),
                callback=audio_callback
            )
            audio_stream.start()
            print(f"[OK] Background audio stream active: {mic_name_str} ({audio_ext})")
    except Exception as e:
        print(f"[WARNING] Could not start audio stream: {e}")

# 1. Export hardware metadata to system_info/hardware_info.json
pc_name, hardware_components = extract_hardware_structure(raw_json)
system_metadata = {
    "computer_name": pc_name,
    "hardware_count": len(hardware_components),
    "components": hardware_components
}
with open(hw_info_filename, "w", encoding="utf-8") as hw_file:
    json.dump(system_metadata, hw_file, indent=4, ensure_ascii=False)

# 2. Scan ALL sensors from JSON
sensor_map = {}
flatten_json_tree(raw_json, sensor_map)

print(f"\n[OK] Discovery complete. Total active sensors found: {len(sensor_map)}")
print(f"Host PC: {pc_name}")
print("Discovered Hardware Components:")
for hw in hardware_components:
    print(f" • {hw['name']}")
print()

# 3. Prepare 2-Row CSV Header
row_names = ["Time_Sec"]
row_ids   = ["TIME_SEC"]
active_sensor_ids = []

for sid, sinfo in sensor_map.items():
    row_names.append(sinfo["display_name"])
    row_ids.append(sid)
    active_sensor_ids.append(sid)

if audio_stream is not None:
    row_names.append(f"Sound Level ({mic_name_str})")
    row_ids.append("/audio/0/sound/0")

print(f"Logging ALL {len(sensor_map)} sensors to CSV: {filename}")
if audio_stream is not None:
    print(f"Recording raw audio stream to: {audio_filename}")
print("Press Ctrl+C to stop logging.\n")

start_time = time.time()
first_run = True

with open(filename, mode='w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerow(row_names)  # Row 1: Names
    writer.writerow(row_ids)    # Row 2: SensorIDs
    file.flush()

    try:
        while True:
            t0 = time.time()
            elapsed = t0 - start_time

            try:
                response = session.get(URL, timeout=1.0)
                curr_json = response.json()
            except Exception:
                time.sleep(INTERVAL)
                continue

            curr_sensor_map = {}
            flatten_json_tree(curr_json, curr_sensor_map)

            row_data = [round(elapsed, 2)]
            for sid in active_sensor_ids:
                val = curr_sensor_map.get(sid, {}).get("value")
                row_data.append(val)

            if audio_stream is not None:
                row_data.append(current_sound_dba)

            writer.writerow(row_data)

            cpu_temp = curr_sensor_map.get(ID_CPU_TEMP, {}).get("value")
            cpu_pwr  = curr_sensor_map.get(ID_CPU_POWER, {}).get("value")
            cpu_load = curr_sensor_map.get(ID_CPU_LOAD, {}).get("value")
            cpu_pump = curr_sensor_map.get(ID_CPU_PUMP, {}).get("value")

            gpu_temp = curr_sensor_map.get(ID_GPU_TEMP, {}).get("value")
            gpu_pwr  = curr_sensor_map.get(ID_GPU_POWER, {}).get("value")
            gpu_load = curr_sensor_map.get(ID_GPU_LOAD, {}).get("value")
            gpu_fan  = curr_sensor_map.get(ID_GPU_FAN, {}).get("value")

            cpu_t_str = f"{cpu_temp:.1f} C" if cpu_temp is not None else "N/A C"
            cpu_p_str = f"{cpu_pwr:.1f} W" if cpu_pwr is not None else "N/A W"
            cpu_l_str = f"{cpu_load:.1f} %" if cpu_load is not None else "N/A %"
            cpu_s_str = f"{cpu_pump:.0f} RPM" if cpu_pump is not None else "N/A RPM"

            gpu_t_str = f"{gpu_temp:.1f} C" if gpu_temp is not None else "N/A C"
            gpu_p_str = f"{gpu_pwr:.1f} W" if gpu_pwr is not None else "N/A W"
            gpu_l_str = f"{gpu_load:.1f} %" if gpu_load is not None else "N/A %"
            gpu_s_str = f"{gpu_fan:.0f} RPM" if gpu_fan is not None else "N/A RPM"

            sound_line = f"Sound Level: {current_sound_dba:.1f} dBA ({mic_name_str[:22]})\n" if (audio_stream and current_sound_dba is not None) else ""

            out_text = (
                f"HARDWARE  | TEMP (C) | POWER (W) | LOAD (%) | SPEED (RPM)\n"
                f"---------------------------------------------------------\n"
                f"CPU       | {cpu_t_str:>8} | {cpu_p_str:>9} | {cpu_l_str:>8} | {cpu_s_str:>11}\n"
                f"GPU       | {gpu_t_str:>8} | {gpu_p_str:>9} | {gpu_l_str:>8} | {gpu_s_str:>11}\n"
                f"---------------------------------------------------------\n"
                f"{sound_line}"
                f"Elapsed Time: {elapsed:6.1f}s"
            )

            num_ansi_lines = 7 if (audio_stream and current_sound_dba is not None) else 6

            if not first_run:
                print(f"\033[{num_ansi_lines}A\033[J", end="", flush=True)
            else:
                first_run = False

            print(out_text, flush=True)

            exec_time = time.time() - t0
            time.sleep(max(0.0, INTERVAL - exec_time))

    except KeyboardInterrupt:
        print("\n\nLogging stopped by user.")
    finally:
        if audio_stream is not None:
            try:
                audio_stream.stop()
                audio_stream.close()
            except Exception:
                pass
        if HAS_LAME and mp3_encoder and audio_file_obj:
            try:
                tail = mp3_encoder.flush()
                if tail:
                    audio_file_obj.write(tail)
                audio_file_obj.close()
                print(f"[SUCCESS] Audio MP3 saved to: {audio_filename}")
            except Exception:
                pass
        elif audio_file_obj:
            try:
                audio_file_obj.close()
                print(f"[SUCCESS] Audio WAV saved to: {audio_filename}")
            except Exception:
                pass
        
        # Закрытие процесса по флагу CLOSE_LHM_ON_EXIT
        close_lhm_if_needed()