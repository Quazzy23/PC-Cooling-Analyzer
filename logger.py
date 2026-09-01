"""
Главный универсальный логгер телеметрии датчиков и синхронной аудиозаписи
Стандартный чистый консольный вывод (без сторонних библиотек).
"""
import os
import sys
sys.dont_write_bytecode = True
import time
import csv
import json
import requests
import numpy as np
import sounddevice as sd

from utils.lhm_client import (
    LHM_URL, ensure_lhm_running, close_lhm_process,
    flatten_json_tree, extract_hardware_structure
)
from core.defaults import get_available_profiles, load_sensor_profile, AUDIO_PROFILE

# Включаем поддержку ANSI-последовательностей в Windows
os.system("")

# ================= CONFIGURATION =================
INTERVAL = 0.25      # Опрос каждые 250 мс (4 Гц)
POSTFIX = "test"     # Постфикс имени лога

CLOSE_LHM_ON_EXIT = 1 # 1 = закрывать LHM при выходе, 0 = оставлять в трее

RESULTS_DIR = "results"
LOGS_DIR = os.path.join(RESULTS_DIR, "sensors_logs")
SYS_INFO_DIR = "system_info"

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(SYS_INFO_DIR, exist_ok=True)

CSV_FILENAME = os.path.join(LOGS_DIR, f"table_raw_{POSTFIX}.csv")
HW_INFO_FILENAME = os.path.join(SYS_INFO_DIR, "hardware_info.json")
AUDIO_CFG_FILE = os.path.join(SYS_INFO_DIR, "audio_config.json")

# Загрузка всех настроенных профилей (CPU, GPU и др.)
all_modes = [m for m in get_available_profiles() if m != "ALL"]
profile_sensors = {}

for mode in all_modes:
    prof = load_sensor_profile(mode)
    s_list = []
    for s in prof.get("panel1_sensors", []) + prof.get("panel2_sensors", []):
        if s["id"] != "/audio/0/sound/0":
            s_list.append(s)
    if s_list:
        profile_sensors[mode] = s_list

# ================================================

try:
    import lameenc
    HAS_LAME = True
except ImportError:
    import wave
    HAS_LAME = False

AUDIO_EXT = ".mp3" if HAS_LAME else ".wav"
AUDIO_FILENAME = os.path.join(LOGS_DIR, f"audio_raw_{POSTFIX}{AUDIO_EXT}")


class AudioRecorder:
    """Фоновый рекордер синхронной аудиодорожки и расчет уровня шума (dBA)"""
    def __init__(self, filename: str, cfg_path: str):
        self.filename = filename
        self.current_sound_dba = None
        self.is_active = False
        self.mic_name = "Microphone"
        self.stream = None
        self.mp3_encoder = None
        self.audio_file = None

        if not os.path.exists(cfg_path):
            return

        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                acfg = json.load(f)

            if not acfg.get("audio_logging_enabled", False):
                return

            saved_idx = acfg.get("device_index")
            saved_name = acfg.get("device_name", "Microphone")
            self.mic_name = saved_name
            cal_offset = float(acfg.get("calibration_offset", AUDIO_PROFILE.get("calibration_offset", 90.0)))

            devices = sd.query_devices()
            target_idx = None

            if saved_idx is not None and 0 <= saved_idx < len(devices) and devices[saved_idx]['max_input_channels'] > 0:
                target_idx = saved_idx
            else:
                for idx, dev in enumerate(devices):
                    if dev['max_input_channels'] > 0 and saved_name.lower() in dev['name'].lower():
                        target_idx = idx
                        break

            if target_idx is None:
                default_in = sd.default.device[0]
                if default_in is not None and default_in >= 0:
                    target_idx = default_in
                    self.mic_name = devices[target_idx]['name']

            if target_idx is None:
                return

            dev_info = sd.query_devices(target_idx)
            sr = int(dev_info['default_samplerate'])
            channels_in = min(int(dev_info['max_input_channels']), 2)

            if HAS_LAME:
                self.mp3_encoder = lameenc.Encoder()
                self.mp3_encoder.set_bit_rate(128)
                self.mp3_encoder.set_in_sample_rate(sr)
                self.mp3_encoder.set_channels(1)
                self.mp3_encoder.set_quality(2)
                self.audio_file = open(self.filename, "wb")
            else:
                self.audio_file = wave.open(self.filename, "wb")
                self.audio_file.setnchannels(1)
                self.audio_file.setsampwidth(2)
                self.audio_file.setframerate(sr)

            def audio_callback(indata, frames, time_info, status):
                mono_sig = indata[:, 0] if indata.ndim > 1 else indata
                sig = np.nan_to_num(mono_sig, nan=0.0, posinf=0.0, neginf=0.0)
                sig = np.clip(sig, -1.0, 1.0)

                rms = np.sqrt(np.mean(sig**2) + 1e-12)
                db = 20.0 * np.log10(rms) + cal_offset
                self.current_sound_dba = max(0.0, round(float(db), 1))

                pcm16_bytes = (sig * 32767).astype(np.int16).tobytes()
                if HAS_LAME and self.mp3_encoder and self.audio_file:
                    chunk = self.mp3_encoder.encode(pcm16_bytes)
                    if chunk:
                        self.audio_file.write(chunk)
                elif self.audio_file:
                    self.audio_file.writeframes(pcm16_bytes)

            self.stream = sd.InputStream(
                device=target_idx,
                channels=channels_in,
                samplerate=sr,
                blocksize=int(sr * 0.25),
                callback=audio_callback
            )
            self.stream.start()
            self.is_active = True
        except Exception:
            pass

    def close(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception: pass

        if HAS_LAME and self.mp3_encoder and self.audio_file:
            try:
                tail = self.mp3_encoder.flush()
                if tail:
                    self.audio_file.write(tail)
                self.audio_file.close()
            except Exception: pass
        elif self.audio_file:
            try:
                self.audio_file.close()
            except Exception: pass


# 1. Автозапуск LibreHardwareMonitor
ensure_lhm_running()

# 2. Подключение к Web API
session = requests.Session()
try:
    res = session.get(LHM_URL, timeout=2.0)
    res.raise_for_status()
    raw_json = res.json()
except Exception as e:
    print(f"\n[ERROR] Could not connect to LibreHardwareMonitor at {LHM_URL}")
    print("Ensure LibreHardwareMonitor.exe is running and 'Remote Web Server' is enabled.")
    sys.exit(1)

# 3. Инициализация аудиозаписи
recorder = AudioRecorder(AUDIO_FILENAME, AUDIO_CFG_FILE)

# 4. Сохранение паспорта оборудования
pc_name, hardware_components = extract_hardware_structure(raw_json)
system_metadata = {
    "computer_name": pc_name,
    "hardware_count": len(hardware_components),
    "components": hardware_components
}
with open(HW_INFO_FILENAME, "w", encoding="utf-8") as hw_file:
    json.dump(system_metadata, hw_file, indent=4, ensure_ascii=False)

# 5. Первичное сканирование всех доступных датчиков
sensor_map = {}
flatten_json_tree(raw_json, sensor_map)
print(f"\n[OK] Discovery complete. Total active sensors found: {len(sensor_map)}")
print("Monitored Profiles:")
for mode, s_list in profile_sensors.items():
    print(f" • [{mode}]: {len(s_list)} sensors")
print(f"Host PC: {pc_name}")
for hw in hardware_components:
    print(f" • {hw['name']}")
print()

# 6. Заголовки CSV
row_names = ["Time_Sec"]
row_ids   = ["TIME_SEC"]
active_sensor_ids = []

for sid, sinfo in sensor_map.items():
    row_names.append(sinfo["display_name"])
    row_ids.append(sid)
    active_sensor_ids.append(sid)

if recorder.is_active:
    row_names.append(f"Sound Level ({recorder.mic_name})")
    row_ids.append("/audio/0/sound/0")

print(f"Logging ALL {len(sensor_map)} sensors to CSV: {CSV_FILENAME}")
if recorder.is_active:
    print(f"Recording raw audio stream to: {AUDIO_FILENAME}")
print("Press Ctrl+C to stop logging.\n")

start_time = time.time()
first_run = True
prev_line_count = 0

# 7. Главный цикл логирования
with open(CSV_FILENAME, mode='w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerow(row_names)
    writer.writerow(row_ids)
    file.flush()

    try:
        while True:
            t0 = time.time()
            elapsed = t0 - start_time

            try:
                response = session.get(LHM_URL, timeout=1.0)
                curr_json = response.json()
            except Exception:
                time.sleep(INTERVAL)
                continue

            curr_sensor_map = {}
            flatten_json_tree(curr_json, curr_sensor_map)

            # Запись полной строки всех датчиков в CSV
            row_data = [round(elapsed, 2)]
            for sid in active_sensor_ids:
                val = curr_sensor_map.get(sid, {}).get("value")
                row_data.append(val)

            if recorder.is_active:
                row_data.append(recorder.current_sound_dba)

            writer.writerow(row_data)

            # Формирование строк вывода
            out_lines = []

            for mode, sensors in profile_sensors.items():
                out_lines.append(f"{f'[{mode}]':<36} {'VALUE':>12}")
                out_lines.append("-" * 50)

                for s in sensors:
                    label = s["label"]
                    clean_label = label[:36]
                    val = curr_sensor_map.get(s["id"], {}).get("value")

                    if val is None:
                        val_str = "N/A"
                    else:
                        l_lower = label.lower()
                        if "volt" in l_lower or "(v)" in l_lower:
                            val_str = f"{val:.3f}"
                        elif "rpm" in l_lower or "clock" in l_lower or "mhz" in l_lower:
                            val_str = f"{val:.0f}"
                        else:
                            val_str = f"{val:.1f}"

                    out_lines.append(f"{clean_label:<36} {val_str:>12}")

                out_lines.append("")

            # Блок уровня звука
            if recorder.is_active:
                if recorder.current_sound_dba is not None:
                    snd_str = f"{recorder.current_sound_dba:>12.1f}"
                else:
                    snd_str = f"{'--.-':>12}"
                out_lines.append(f"{'Sound Level (dBA)':<36} {snd_str}")
                out_lines.append("-" * 50)

            out_lines.append(f"{'Elapsed Time (s)':<36} {elapsed:>12.1f}")
            out_lines.append("-" * 50)
            out_lines.append("Press Ctrl+C to stop logging.")

            # Каждая строка снабжается маркером очистки остатка \033[K
            formatted_block = "\n".join(f"{line}\033[K" for line in out_lines)
            current_line_count = len(out_lines)

            # Перемещение курсора на начало блока и перезапись
            if not first_run:
                sys.stdout.write(f"\r\033[{prev_line_count - 1}A")
            else:
                first_run = False

            sys.stdout.write(formatted_block)
            sys.stdout.flush()
            prev_line_count = current_line_count

            exec_time = time.time() - t0
            time.sleep(max(0.0, INTERVAL - exec_time))

    except KeyboardInterrupt:
        sys.stdout.write("\n\n")
        print("[STOP] Logging stopped by user.")
        print(f"[SUCCESS] Telemetry CSV saved to: {CSV_FILENAME}")
        if recorder.is_active:
            print(f"[SUCCESS] Audio recording saved to: {AUDIO_FILENAME}")
    finally:
        recorder.close()
        if CLOSE_LHM_ON_EXIT == 1:
            close_lhm_process()