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
    """Возвращает список доступных профилей из sensors_config.json + режим ALL"""
    if not os.path.exists(config_path):
        return ["CPU", "GPU", "ALL"]
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        modes = [k for k in data.keys() if k not in ("active_mode",)]
        if "ALL" not in modes:
            modes.append("ALL")
        return modes
    except Exception:
        return ["CPU", "GPU", "ALL"]


def load_sensor_profile(mode: str = None, config_path: str = DEFAULT_CONFIG_PATH) -> dict:
    """Загружает профиль датчиков (CPU, GPU или комбинированный ALL с дедупликацией)"""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Sensor configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Определяем режим
    saved_active = load_last_active_mode()
    target_mode = (mode or saved_active or data.get("active_mode", "CPU")).upper()

    p1_sensors = []
    p2_sensors = []
    export_sensors = []
    seen_sids = set()

    # --- РЕЖИМ ALL (Объединение всех профилей без дубликатов) ---
    if target_mode == "ALL":
        all_modes = [k for k in data.keys() if k not in ("active_mode",)]
        
        # Собираем P1 со всех профилей
        for m_key in all_modes:
            m_data = data.get(m_key, {})
            raw_p1 = m_data.get("panel1_thermal_and_power") or m_data.get("P1_thermal_and_power") or []
            for item in raw_p1:
                sid = str(item.get("id", "")).strip()
                if sid and sid not in seen_sids:
                    seen_sids.add(sid)
                    idx = len(p1_sensors)
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

        # Собираем P2 со всех профилей
        for m_key in all_modes:
            m_data = data.get(m_key, {})
            raw_p2 = m_data.get("panel2_cooling_and_speed") or m_data.get("P2_cooling_and_speed") or []
            for item in raw_p2:
                sid = str(item.get("id", "")).strip()
                if sid and sid not in seen_sids:
                    seen_sids.add(sid)
                    idx = len(p2_sensors)
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

        summary_dir = "all"
        chart_title = "Full System Thermal & Electrical Load Dynamics"

    # --- СТАНДАРТНЫЙ РЕЖИМ (CPU или GPU) ---
    else:
        mode_data = data.get(target_mode, data.get("CPU", {}))
        
        raw_p1 = mode_data.get("panel1_thermal_and_power") or mode_data.get("P1_thermal_and_power") or []
        for idx, item in enumerate(raw_p1):
            sid = str(item.get("id", "")).strip()
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
        for idx, item in enumerate(raw_p2):
            sid = str(item.get("id", "")).strip()
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

    # Авто-добавление микрофона в конец P2 (ровно 1 раз, цвет по порядку из P2_PALETTE)
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