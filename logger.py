"""
Главный универсальный логгер телеметрии датчиков и синхронной аудиозаписи
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
from core.defaults import load_sensor_profile, AUDIO_PROFILE

# Включаем ANSI-эскейп коды в Windows-терминале для живой таблицы
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

# Датчики для отображения в консоли автоматически подтягиваем из профилей
cpu_prof = load_sensor_profile("CPU")
gpu_prof = load_sensor_profile("GPU")

ID_CPU_TEMP  = cpu_prof["panel1_sensors"][0]["id"] if len(cpu_prof["panel1_sensors"]) > 0 else None
ID_CPU_POWER = cpu_prof["panel1_sensors"][2]["id"] if len(cpu_prof["panel1_sensors"]) > 2 else None
ID_CPU_LOAD  = cpu_prof["panel1_sensors"][3]["id"] if len(cpu_prof["panel1_sensors"]) > 3 else None
ID_CPU_PUMP  = cpu_prof["panel2_sensors"][0]["id"] if len(cpu_prof["panel2_sensors"]) > 0 else None

ID_GPU_TEMP  = gpu_prof["panel1_sensors"][0]["id"] if len(gpu_prof["panel1_sensors"]) > 0 else None
ID_GPU_POWER = gpu_prof["panel1_sensors"][2]["id"] if len(gpu_prof["panel1_sensors"]) > 2 else None
ID_GPU_LOAD  = gpu_prof["panel1_sensors"][3]["id"] if len(gpu_prof["panel1_sensors"]) > 3 else None
ID_GPU_FAN   = gpu_prof["panel2_sensors"][0]["id"] if len(gpu_prof["panel2_sensors"]) > 0 else None
# ================================================

# Проверяем поддержку MP3 кодирования
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
            print("[INFO] Audio config not found. Run 'python select_mic.py' to enable noise logging.")
            return

        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                acfg = json.load(f)

            if not acfg.get("audio_logging_enabled", False):
                print("[INFO] Audio logging is disabled in 'system_info/audio_config.json'.")
                return

            saved_idx = acfg.get("device_index")
            saved_name = acfg.get("device_name", "Microphone")
            self.mic_name = saved_name
            cal_offset = float(acfg.get("calibration_offset", AUDIO_PROFILE.get("calibration_offset", 90.0)))

            # Поиск устройства: сначала по сохраненному индексу, затем по имени
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
                # Если сохраненный микрофон не найден, берем дефолтный системный
                default_in = sd.default.device[0]
                if default_in is not None and default_in >= 0:
                    target_idx = default_in
                    self.mic_name = devices[target_idx]['name']

            if target_idx is None:
                print("[WARNING] No suitable microphone input device found!")
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
                # Извлекаем первый канал для моно-расчета dBA и записи
                mono_sig = indata[:, 0] if indata.ndim > 1 else indata
                sig = np.nan_to_num(mono_sig, nan=0.0, posinf=0.0, neginf=0.0)
                sig = np.clip(sig, -1.0, 1.0)

                # Расчет RMS и перевод в dBA
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
            print(f"[OK] Background audio stream active: {self.mic_name[:30]} ({AUDIO_EXT})")
        except Exception as e:
            print(f"[WARNING] Could not start audio stream: {e}")

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
                print(f"[SUCCESS] Audio MP3 saved to: {self.filename}")
            except Exception: pass
        elif self.audio_file:
            try:
                self.audio_file.close()
                print(f"[SUCCESS] Audio WAV saved to: {self.filename}")
            except Exception: pass

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
                print(f"[SUCCESS] Audio MP3 saved to: {self.filename}")
            except Exception: pass
        elif self.audio_file:
            try:
                self.audio_file.close()
                print(f"[SUCCESS] Audio WAV saved to: {self.filename}")
            except Exception: pass


# 1. Автозапуск LibreHardwareMonitor при необходимости
ensure_lhm_running()

# 2. Подключение к Web API
print(f"Connecting to LibreHardwareMonitor Web Server at {LHM_URL}...")
session = requests.Session()
try:
    res = session.get(LHM_URL, timeout=2.0)
    res.raise_for_status()
    raw_json = res.json()
    print("[OK] Connected to LibreHardwareMonitor application successfully!")
except Exception as e:
    print(f"\n[ERROR] Could not connect to LibreHardwareMonitor at {LHM_URL}")
    print("Ensure LibreHardwareMonitor.exe is running and 'Remote Web Server' is enabled.")
    sys.exit(1)

# 3. Инициализация фоновой аудиозаписи
recorder = AudioRecorder(AUDIO_FILENAME, AUDIO_CFG_FILE)

# 4. Сохранение паспорта оборудования (hardware_info.json)
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
print(f"Host PC: {pc_name}")
for hw in hardware_components:
    print(f" • {hw['name']}")
print()

# 6. Формирование двухстрочного заголовка CSV
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

# 7. Главный цикл логирования
with open(CSV_FILENAME, mode='w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerow(row_names)  # Строка 1: Имена
    writer.writerow(row_ids)    # Строка 2: SensorID
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

            row_data = [round(elapsed, 2)]
            for sid in active_sensor_ids:
                val = curr_sensor_map.get(sid, {}).get("value")
                row_data.append(val)

            if recorder.is_active:
                row_data.append(recorder.current_sound_dba)

            writer.writerow(row_data)

            # Извлечение ключевых метрик для консольной таблицы
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

            sound_line = f"Sound Level: {recorder.current_sound_dba:.1f} dBA ({recorder.mic_name[:22]})\n" if (recorder.is_active and recorder.current_sound_dba is not None) else ""

            out_text = (
                f"HARDWARE  | TEMP (C) | POWER (W) | LOAD (%) | SPEED (RPM)\n"
                f"---------------------------------------------------------\n"
                f"CPU       | {cpu_t_str:>8} | {cpu_p_str:>9} | {cpu_l_str:>8} | {cpu_s_str:>11}\n"
                f"GPU       | {gpu_t_str:>8} | {gpu_p_str:>9} | {gpu_l_str:>8} | {gpu_s_str:>11}\n"
                f"---------------------------------------------------------\n"
                f"{sound_line}"
                f"Elapsed Time: {elapsed:6.1f}s"
            )

            num_ansi_lines = 7 if (recorder.is_active and recorder.current_sound_dba is not None) else 6

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
        recorder.close()
        if CLOSE_LHM_ON_EXIT == 1:
            close_lhm_process()