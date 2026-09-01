"""
Системные настройки разработчика, палитры цветов, поддержка режима ALL и сохранение пресетов
"""
import os
import json

# =======================================================
#               ЦВЕТОВЫЕ ПАЛИТРЫ ПО УМОЛЧАНИЮ
# =======================================================
P1_PALETTE = [
    "#FF3366", "#FF9900", "#00E5FF", "#AA00FF", "#00FFCC",
    "#FFD700", "#FF1493", "#00BFFF", "#33FF57", "#FF6F00"
]

P2_PALETTE = [
    "#33FF57", "#FFD700", "#00BFFF", "#FF1493", "#B8860B",
    "#FF6F00", "#00FFCC", "#AA00FF", "#00E5FF", "#FF3366"
]

# =======================================================
#               AUDIO ANALYZER PROFILE (DEV)
# =======================================================
AUDIO_PROFILE = {
    "limit_freq_min": 20.0,
    "limit_freq_max": 8000.0,
    "limit_db_min": -50.0,
    "limit_db_max": 200.0,
    "default_db_min": -10.0,
    "default_db_max": 50.0,
    "target_spec_width": 10000,
    "isolate_fft_on_filter": 0,
    "calibration_offset": 90.0
}

DEFAULT_CONFIG_PATH = os.path.join("system_info", "sensors_config.json")
AUDIO_CONFIG_PATH = os.path.join("system_info", "audio_config.json")
VIEW_STATE_PATH = os.path.join("system_info", "view_state.json")


def determine_default_axis(label_name: str) -> str:
    l = label_name.lower()
    if "(c)" in l or "temp" in l or "rpm" in l or "fan" in l or "pump" in l:
        return "left"
    return "right"


def get_available_profiles(config_path: str = DEFAULT_CONFIG_PATH) -> list:
    """Возвращает список реальных доступных профилей из sensors_config.json"""
    if not os.path.exists(config_path):
        return ["CPU", "GPU"]
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        modes = [k for k in data.keys() if k != "active_mode"]
        return modes if modes else ["CPU", "GPU"]
    except Exception:
        return ["CPU", "GPU"]


def load_sensor_profile(mode: str = None, config_path: str = DEFAULT_CONFIG_PATH) -> dict:
    """Загружает конкретный профиль датчиков (CPU, GPU, RAM и др.) с учетом поля order"""
    saved_active = load_last_active_mode()
    target_mode = (mode or saved_active or "CPU").upper()

    if not os.path.exists(config_path):
        return {
            "mode_name": target_mode,
            "summary_dir_name": target_mode.lower(),
            "chart_title_prefix": f"{target_mode} Thermal & Electrical Load Dynamics",
            "panel1_sensors": [],
            "panel2_title": "Cooling Hardware Speeds & Sound Level",
            "panel2_sensors": [],
            "export_sensors": []
        }

    with open(config_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception:
            data = {}

    target_mode = (mode or saved_active or "CPU").upper()

    p1_sensors = []
    p2_sensors = []
    export_sensors = []
    seen_sids = set()

    mode_data = data.get(target_mode, {})

    raw_p1 = mode_data.get("panel1_thermal_and_power") or mode_data.get("P1_thermal_and_power") or []
    raw_p1 = sorted(raw_p1, key=lambda x: x.get("order", 999))
    for idx, item in enumerate(raw_p1):
        sid = str(item.get("id", "")).strip()
        if sid and sid not in seen_sids:
            seen_sids.add(sid)
            name = item.get("name", f"Sensor P1_{idx+1}")
            p1_sensors.append({
                "key": f"p1_{idx+1}",
                "id": sid,
                "label": name,
                "color": P1_PALETTE[idx % len(P1_PALETTE)],
                "axis": "left",
                "visible": False
            })
            export_sensors.append((name, sid))

    raw_p2 = mode_data.get("panel2_cooling_and_speed") or mode_data.get("P2_cooling_and_speed") or []
    raw_p2 = sorted(raw_p2, key=lambda x: x.get("order", 999))
    for idx, item in enumerate(raw_p2):
        sid = str(item.get("id", "")).strip()
        if sid and sid not in seen_sids:
            seen_sids.add(sid)
            name = item.get("name", f"Fan {idx+1}")
            p2_sensors.append({
                "key": f"p2_{idx+1}",
                "id": sid,
                "label": name,
                "color": P2_PALETTE[idx % len(P2_PALETTE)],
                "axis": "left",
                "visible": False
            })
            export_sensors.append((name, sid))

    summary_dir = mode_data.get("summary_dir_name", target_mode.lower())
    chart_title = mode_data.get("chart_title_prefix", f"{target_mode} Thermal & Electrical Load Dynamics")

    # Авто-добавление микрофона в конец P2 (если включено в audio_config.json)
    if os.path.exists(AUDIO_CONFIG_PATH) and "/audio/0/sound/0" not in seen_sids:
        try:
            with open(AUDIO_CONFIG_PATH, "r", encoding="utf-8") as af:
                acfg = json.load(af)
            if acfg.get("audio_logging_enabled", False):
                idx = len(p2_sensors)
                p2_sensors.append({
                    "key": "sound",
                    "id": "/audio/0/sound/0",
                    "label": "Sound (dBA)",
                    "color": P2_PALETTE[idx % len(P2_PALETTE)],
                    "axis": "left",
                    "visible": False
                })
                export_sensors.append(("Sound Level (dBA)", "/audio/0/sound/0"))
        except Exception:
            pass

    return {
        "mode_name": target_mode,
        "summary_dir_name": summary_dir,
        "chart_title_prefix": chart_title,
        "panel1_sensors": p1_sensors,
        "panel2_title": "Cooling Hardware Speeds & Sound Level",
        "panel2_sensors": p2_sensors,
        "export_sensors": export_sensors
    }


def save_user_view_state(mode: str, state_dict: dict, path: str = VIEW_STATE_PATH):
    """Сохраняет текущий вид и запоминает активный режим"""
    all_states = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                all_states = json.load(f)
        except Exception:
            pass

    all_states["last_active_mode"] = mode
    all_states[mode] = state_dict
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(all_states, f, indent=4, ensure_ascii=False)


def load_user_view_state(mode: str, path: str = VIEW_STATE_PATH) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                all_states = json.load(f)
                return all_states.get(mode, {})
        except Exception:
            pass
    return {}


def load_last_active_mode(path: str = VIEW_STATE_PATH) -> str:
    """Считывает последний активный режим из view_state.json"""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                all_states = json.load(f)
                return all_states.get("last_active_mode", "CPU")
        except Exception:
            pass
    return "CPU"

def save_all_session_view_states(active_mode: str, session_states: dict, path: str = VIEW_STATE_PATH):
    """Сохраняет на диск сразу ВСЕ настроенные в сессии профили (CPU, GPU, ALL)"""
    all_states = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                all_states = json.load(f)
        except Exception:
            pass

    all_states["last_active_mode"] = active_mode
    for mode_name, state_dict in session_states.items():
        all_states[mode_name] = state_dict

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(all_states, f, indent=4, ensure_ascii=False)