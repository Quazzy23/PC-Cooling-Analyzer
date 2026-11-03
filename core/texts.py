"""Централизованное хранилище всех пользовательских строк, подписей, тултипов и логов."""

# =======================================================
#                  AUDIO ENGINE & DAW TEXTS
# =======================================================
PEAK_LABEL_TEMPLATE = "Peak: {freq:.0f} Hz ({db:.1f} dB)"
HUD_FFT_COORDS_TEMPLATE = "P1: {freq:.0f} Hz | {db:.1f} dB | {time:.1f}s"
HUD_SPEC_COORDS_TEMPLATE = "P2: {time:.1f}s | {freq:.0f} Hz | {db:.1f} dB"


# =======================================================
#                    TELEMETRY TEXTS
# =======================================================
TEXT_EMPTY_METRIC = "—"
TEXT_TOTAL_RANGES = "Total"
HEADER_TIME_SEC = "Time_Sec"


# =======================================================
#                  DEFAULTS & PROFILES
# =======================================================
DEFAULT_CPU_MODE = "CPU"
DEFAULT_GPU_MODE = "GPU"
CHART_TITLE_P1_PREFIX = "{mode} Thermal & Electrical Load Dynamics"
CHART_TITLE_P2 = "Cooling Hardware Speeds & Sound Level"
LABEL_SOUND_DBA = "Sound (dBA)"
LABEL_SOUND_LEVEL = "Sound Level (dBA)"


# =======================================================
#                 UI PANELS & CHARTS
# =======================================================
CHART_TITLE_1 = "<span style='color: #FFFFFF; font-size: 10pt;'><b>1. Thermal & Electrical Parameters</b></span>"
CHART_TITLE_2 = "<span style='color: #FFFFFF; font-size: 10pt;'><b>2. Cooling Speeds & Sound Level</b></span>"
CHART_TITLE_3 = "<span style='color: #FFFFFF; font-size: 10pt;'><b>3. Real-time Acoustic Spectrum</b></span>"
CHART_TITLE_4 = "<span style='color: #FFFFFF; font-size: 10pt;'><b>4. 2D Spectrogram Timeline</b></span>"

AXIS_LABEL_FREQ = "Frequency"
AXIS_UNIT_HZ = "Hz"
AXIS_LABEL_SPL = "Sound Pressure Level"
AXIS_UNIT_DB = "dB"
AXIS_LABEL_TIME = "Time"
AXIS_UNIT_S = "s"

BTN_PLAY = "Play"
BTN_PAUSE = "Pause"
LBL_BOOST = "Boost:"
SUFFIX_DB = " dB"
BTN_RENDER_VIEW = "Render View"
BTN_SCALE_LOG = "Scale: Log"
BTN_SCALE_LIN = "Scale: Linear"
LBL_Y_MIN = "Y Min:"
LBL_Y_MAX = "Y Max:"

LBL_SMOOTH = "Smooth:"
LBL_STEP = "Trend:"
LBL_RAW_FOG = "Raw Fog:"
LBL_TREND_A = "Trend A:"
BTN_FIT_RAW = "Fit: Raw"
BTN_FIT_TREND = "Fit: Trend"
BTN_SAVE_RESULT = "Save Result"
BTN_CSV_SAVED = "CSV Saved"


# =======================================================
#                    SIDEBAR & PASSPORT
# =======================================================
TITLE_SUMMARY_METRICS = "SUMMARY METRICS"
TABLE_HEADERS_SUMMARY = ["Metric", "Min", "Max", "Avg"]
TITLE_SENSOR_PASSPORT = "SENSOR PASSPORT"
HEADER_PANEL_1 = "Panel 1"
HEADER_PANEL_2 = "Panel 2"
BTN_SAVE_VIEW = "Save View Preset"
TIP_SAVE_VIEW = "Saves current layers order, colors, panels, visibility and axes"
TIP_GRIP = "Drag up/down to change Z-layer, or drag into another panel"
TIP_AXIS_SIDE = "Toggle Axis Side (Left / Right)"
TIP_BLOCK_ZOOM = "Block Y-Axis zoom for this sensor"


# =======================================================
#                   STUDIO SUITE (ANALYZER)
# =======================================================
LBL_PROFILE = "PROFILE:"
LBL_MODULES = "MODULES:"
BTN_TOGGLE_TELEMETRY = "Telemetry (P1 / P2)"
BTN_TOGGLE_AUDIO = "Audio DAW (FFT / Spec)"
HEADER_DATASET_INFO_TEMPLATE = "<span style='color:#888888;'>Dataset:</span> <b style='color:#00E5FF;'>{file}</b> <span style='color:#444444;'>|</span> <span style='color:#888888;'>Hardware: {cpu} | {gpu}</span>"
WINDOW_TITLE_TEMPLATE = "PC Cooling Studio Suite [{mode}] — {file}"

MSG_SELECT_LOG = "Select log file to analyze (default 1): "
MSG_ANALYZING = "Analyzing: {file} ({samples} samples)"
MSG_PAIRED_AUDIO = "Paired Audio: {file}"
MSG_ERR_NO_LOGS = "No CSV test logs found in '{dir}' directory!"
MSG_ERR_DIR_NOT_FOUND = "Error: Directory '{dir}' not found!"
MSG_ERR_READ_CSV = "Error reading CSV file: {err}"
MSG_EXPORT_SUCCESS = "[SUCCESS] Exported CSV to: {path}"
MSG_VIEW_PRESET_SAVED = "[OK] View preset for [{mode}] saved (layers, colors, panels)."
MSG_WARN_NO_SENSORS = (
    "\n[WARNING] Profile '{mode}' has NO matching sensors in '{file}'!\n"
    " • Configured sensors in profile: {configured}\n"
    " • Did you save sensors in this profile? Run 'python utils/init_configs.py' and click 'Save Configuration'.\n"
    " • Or switch to another profile in the top-left dropdown if you created a custom one.\n"
)
APP_BANNER = "=" * 60 + "\n         PC COOLING STUDIO SUITE         \n" + "=" * 60


# =======================================================
#                     LOGGER & AUDIO RECORDER
# =======================================================
MSG_AUDIO_CONFIG_NOT_FOUND = "[INFO] Audio config not found. Run 'python select_mic.py' to enable noise logging."
MSG_AUDIO_LOGGING_DISABLED = "[INFO] Audio logging is disabled in 'system_info/audio_config.json'."
MSG_NO_MIC_FOUND = "[WARNING] No suitable microphone input device found!"
MSG_AUDIO_STREAM_ACTIVE = "[OK] Background audio stream active: {mic} ({ext})"
MSG_AUDIO_START_FAIL = "[WARNING] Could not start audio stream: {err}"
MSG_AUDIO_SAVED = "[SUCCESS] Audio {ext} saved to: {file}"

MSG_CONNECTING_LHM = "Connecting to LibreHardwareMonitor Web Server at {url}..."
MSG_CONNECTED_LHM = "[OK] Connected to LibreHardwareMonitor application successfully!"
MSG_ERR_CONNECT_LHM = (
    "\n[ERROR] Could not connect to LibreHardwareMonitor at {url}\n"
    "Ensure LibreHardwareMonitor.exe is running and 'Remote Web Server' is enabled."
)
MSG_DISCOVERY_COMPLETE = "\n[OK] Discovery complete. Total active sensors found: {count}"
MSG_MONITORED_PROFILES = "Monitored Profiles:"
MSG_HOST_PC = "Host PC: {pc}"
MSG_LOGGING_ALL = "Logging ALL {count} sensors to CSV: {file}"
MSG_RECORDING_AUDIO = "Recording raw audio stream to: {file}"
MSG_PRESS_CTRL_C = "Press Ctrl+C to stop logging.\n"
MSG_LOGGING_STOPPED = "[STOP] Logging stopped by user."
MSG_CSV_SAVED = "[SUCCESS] Telemetry CSV saved to: {file}"

LABEL_ELAPSED_TIME = "Elapsed Time (s)"
LABEL_BUFFER_WINDOW = "Buffer Window"
HINT_PRESS_CTRL_C = "Press Ctrl+C to stop logging."
VALUE_NA = "N/A"
ID_TIME_SEC = "TIME_SEC"
ID_AUDIO_SOUND = "/audio/0/sound/0"


# =======================================================
#                     LHM CLIENT & DUMP
# =======================================================
MSG_LHM_NOT_RUNNING = "[INFO] LibreHardwareMonitor is not running. Auto-starting background process..."
MSG_LHM_LAUNCHED = "[OK] Launched {name} (Admin). Waiting for web server at {url}..."
MSG_LHM_READY = "[OK] Web server is ready!"
MSG_LHM_LAUNCH_FAIL = "[WARNING] Could not auto-launch {target}: {err}"
MSG_LHM_EXE_NOT_FOUND = (
    "[WARNING] Executable not found at: {path}\n"
    "Please specify the correct path in '{file}' (run 'python utils/init_configs.py')"
)
MSG_LHM_CLOSED = "\n[OK] LibreHardwareMonitor process closed."
MSG_DLL_READ_FAIL = "[WARNING] Could not read hardware via LibreHardwareMonitorLib.HardwareType: {err}"

MSG_DUMP_BANNER = "=" * 70 + "\n     LIBRE HARDWARE MONITOR APPLICATION — SENSOR DUMP TOOL     \n" + "=" * 70
MSG_DUMP_COMPLETE = "\n[SUCCESS] Application sensor dump complete!\n Total sensors scanned : {total}\n Dump file saved to    : {path}\n" + "=" * 70
MSG_TOTAL_SENSORS_HEADER = "\n" + "=" * 95 + "\nTOTAL ACTIVE SENSORS FOUND IN APPLICATION: {total}\n" + "=" * 95


# =======================================================
#                     MICROPHONE SELECTOR
# =======================================================
MSG_ERR_SOUNDDEVICE = "[ERROR] Library 'sounddevice' is not installed! Run: pip install sounddevice numpy"
MSG_MIC_BANNER = "=" * 65 + "\n          MICROPHONE SELECTION FOR COOLING BENCHMARKS          \n" + "=" * 65
MSG_AVAILABLE_MICS = "\nAvailable Physical Microphones:"
MSG_DISABLE_AUDIO = " [0] Disable Audio Recording"
MSG_MIC_PROMPT = "Select microphone number for benchmarks: "
MSG_AUDIO_DISABLED = "\n[OK] Audio recording DISABLED."
MSG_MIC_SAVED = (
    "\n" + "=" * 65 + "\n"
    "[SUCCESS] Microphone configuration saved to: {file}\n"
    " Selected Device     : {dev}\n"
    " Calibration Offset  : {cal:.1f} dB SPL\n"
    " 'logger.py' will now automatically record noise levels from this microphone!\n" + "=" * 65
)


# =======================================================
#                  CONFIG WIZARD DIALOG
# =======================================================
TITLE_WIZARD_WINDOW = "Sensors Configuration Wizard"
BTN_CREATE_PROFILE = "Create Profile"
BTN_DELETE_PROFILE = "Delete Profile"
BTN_SAVE_CONFIG = "Save Configuration"
BTN_CONFIG_SAVED = "Config Saved!"
WIZARD_TREE_HEADERS = ["Sensor / Hardware", "Value", "Name", "Sensor ID"]
LBL_WIZARD_STATS_TEMPLATE = "Profile <b>[{profile}]</b>: <span style='color:#00E5FF;'>{count} sensors selected</span>. (Reorder & Panel splitting are configured in Analyzer)"
STATUS_CONNECTING_LHM = "Connecting to LHM..."

DIALOG_NEW_PROFILE_TITLE = "New Profile"
DIALOG_NEW_PROFILE_PROMPT = "Enter new profile name (e.g. 'RAM', 'CHIPSET'):"
DIALOG_DELETE_PROFILE_TITLE = "Delete Profile"
DIALOG_DELETE_PROFILE_PROMPT = "Are you sure you want to delete profile '{profile}'?"
MSG_CANNOT_DELETE_LAST = "Cannot delete the only remaining profile."

MSG_INIT_BANNER = "=" * 70 + "\n      LIBRE HARDWARE MONITOR — INITIAL PATH CONFIGURATION      \n" + "=" * 70
MSG_INIT_PROMPT_PATH = (
    "\nPlease enter the path to the folder containing LibreHardwareMonitor.exe\n"
    "Hint: You can just copy and paste the folder path from Windows Explorer.\n"
    "Default fallback: {default}\n"
)
MSG_INIT_INPUT_PROMPT = "Enter LHM folder path or .exe path (Press Enter for default): "
MSG_INIT_CANCELLED = "\nSetup cancelled by user."
MSG_INIT_SUCCESS = "\n[SUCCESS] LibreHardwareMonitor found: '{path}'\n[SUCCESS] Saved to '{file}'"
MSG_INIT_PATH_ERROR = "\n[ERROR] 'LibreHardwareMonitor.exe' was NOT found in '{path}'!\nPlease check the path and try again.\n"