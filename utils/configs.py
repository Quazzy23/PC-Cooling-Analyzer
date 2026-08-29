# =======================================================
#            PROFILES FOR CPU AND GPU ANALYSIS
# =======================================================

CPU_PROFILE = {
    "mode_name": "CPU",
    "summary_dir_name": "cpu",
    "chart_title_prefix": "CPU Thermal & Electrical Load Dynamics",
    
    # --- PANEL 1 SENSORS (THERMAL & ELECTRICAL) ---
    "panel1_sensors": [
        {"key": "t1",    "id": "/amdcpu/0/temperature/4", "label": "CCD1 Temp (C)",       "color": "#FF3366", "axis": "left",  "visible": True},
        {"key": "t2",    "id": "/amdcpu/0/temperature/2", "label": "Tctl/Tdie Temp (C)",  "color": "#FF9900", "axis": "left",  "visible": True},
        {"key": "pwr",   "id": "/amdcpu/0/power/0",       "label": "Power (W)",           "color": "#00E5FF", "axis": "right", "visible": True},
        {"key": "load",  "id": "/amdcpu/0/load/0",        "label": "CPU Load (%)",        "color": "#AA00FF", "axis": "right", "visible": True},
        {"key": "volt",  "id": "/amdcpu/0/voltage/0",     "label": "Voltage (V)",         "color": "#00FFCC", "axis": "right", "visible": False},
    ],

    # --- PANEL 2 SENSORS (COOLING SPEEDS & ACOUSTICS) ---
    "panel2_title": "2. Cooling Hardware Speeds & Sound Level",
    "panel2_sensors": [
        {"key": "aio",   "id": "/lpc/nct6798d/0/fan/5",   "label": "AIO_PUMP (RPM)",      "color": "#33FF57", "axis": "left",  "visible": True},
        {"key": "cpu_f", "id": "/lpc/nct6798d/0/fan/1",   "label": "CPU_FAN (RPM)",       "color": "#FFD700", "axis": "left",  "visible": True},
        {"key": "cha1",  "id": "/lpc/nct6798d/0/fan/0",   "label": "CHA_FAN_1 (RPM)",     "color": "#00BFFF", "axis": "left",  "visible": False},
        {"key": "cha2",  "id": "/lpc/nct6798d/0/fan/2",   "label": "CHA_FAN_2 (RPM)",     "color": "#FF1493", "axis": "left",  "visible": False},
        {"key": "cha3",  "id": "/lpc/nct6798d/0/fan/3",   "label": "CHA_FAN_3 (RPM)",     "color": "#B8860B", "axis": "left",  "visible": False},
        {"key": "sound", "id": "/audio/0/sound/0",         "label": "Sound (dBA)",         "color": "#FF5500", "axis": "right", "visible": True},
    ],

    # --- SUMMARY TABLE SENSORS ---
    "clock_id": "/amdcpu/0/clock/1",
    "voltage_id": "/amdcpu/0/voltage/0",
    
    "fan_matrix": [
        ("AIO_PUMP",  "/lpc/nct6798d/0/fan/5"),
        ("CPU_FAN",   "/lpc/nct6798d/0/fan/1"),
        ("CHA_FAN_1", "/lpc/nct6798d/0/fan/0"),
        ("CHA_FAN_2", "/lpc/nct6798d/0/fan/2"),
        ("CHA_FAN_3", "/lpc/nct6798d/0/fan/3"),
    ],

    # --- EXPORT TARGET SENSORS FOR EVOLUTION CSV ---
    "export_sensors": [
        ("Core (Tctl/Tdie)",      "/amdcpu/0/temperature/2"),
        ("CCD1 (Tdie)",           "/amdcpu/0/temperature/4"),
        ("Package Power",         "/amdcpu/0/power/0"),
        ("CPU Total Load",        "/amdcpu/0/load/0"),
        ("Cores (Average) Clock", "/amdcpu/0/clock/1"),
        ("Core (SVI2 TFN) Volt",  "/amdcpu/0/voltage/0"),
        ("Sound Level (dBA)",     "/audio/0/sound/0"),
        ("AIO_PUMP",              "/lpc/nct6798d/0/fan/5"),
        ("CPU_FAN",               "/lpc/nct6798d/0/fan/1"),
        ("CHA_FAN_1",             "/lpc/nct6798d/0/fan/0"),
        ("CHA_FAN_2",             "/lpc/nct6798d/0/fan/2"),
        ("CHA_FAN_3",             "/lpc/nct6798d/0/fan/3"),
    ]
}

GPU_PROFILE = {
    "mode_name": "GPU",
    "summary_dir_name": "gpu",
    "chart_title_prefix": "GPU Thermal & Electrical Load Dynamics",
    
    # --- PANEL 1 SENSORS ---
    "panel1_sensors": [
        {"key": "t1",    "id": "/gpu-nvidia/0/temperature/0", "label": "GPU Core Temp (C)", "color": "#FF3366", "axis": "left",  "visible": True},
        {"key": "t2",    "id": "/gpu-nvidia/0/temperature/2", "label": "GPU Hot Spot (C)",  "color": "#FF9900", "axis": "left",  "visible": True},
        {"key": "pwr",   "id": "/gpu-nvidia/0/power/0",       "label": "Power (W)",         "color": "#00E5FF", "axis": "right", "visible": True},
        {"key": "load",  "id": "/gpu-nvidia/0/load/0",        "label": "GPU Load (%)",      "color": "#AA00FF", "axis": "right", "visible": True},
        {"key": "volt",  "id": "/gpu-nvidia/0/voltage/0",     "label": "Voltage (V)",       "color": "#00FFCC", "axis": "right", "visible": False},
    ],

    # --- PANEL 2 SENSORS ---
    "panel2_title": "2. GPU Cooling Fan Speed & Sound Level",
    "panel2_sensors": [
        {"key": "gpu_f", "id": "/gpu-nvidia/0/fan/1",         "label": "GPU Fan (RPM)",     "color": "#33FF57", "axis": "left",  "visible": True},
        {"key": "sound", "id": "/audio/0/sound/0",             "label": "Sound (dBA)",       "color": "#FF5500", "axis": "right", "visible": True},
    ],

    # --- SUMMARY TABLE SENSORS ---
    "clock_id": "/gpu-nvidia/0/clock/0",
    "voltage_id": "/gpu-nvidia/0/voltage/0",
    
    "fan_matrix": [
        ("GPU_FAN", "/gpu-nvidia/0/fan/1"),
    ],

    # --- EXPORT TARGET SENSORS FOR EVOLUTION CSV ---
    "export_sensors": [
        ("GPU Core Temp",      "/gpu-nvidia/0/temperature/0"),
        ("GPU Hot Spot",       "/gpu-nvidia/0/temperature/2"),
        ("GPU Package Power",  "/gpu-nvidia/0/power/0"),
        ("GPU Core Load",      "/gpu-nvidia/0/load/0"),
        ("GPU Core Clock",     "/gpu-nvidia/0/clock/0"),
        ("GPU Core Voltage",   "/gpu-nvidia/0/voltage/0"),
        ("Sound Level (dBA)",  "/audio/0/sound/0"),
        ("GPU Fan Speed",      "/gpu-nvidia/0/fan/1"),
    ]
}