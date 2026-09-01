import os
import sys
import time
import ctypes

# ==================== TEST CONFIGURATION ====================
TARGET_FAN_NAME = "Fan #3"   # Target header name (from find_fans.py)

START_PWM = 10               # Starting duty cycle (%)
END_PWM = 100                # Maximum duty cycle (%)

RAMP_UP_TIME_SEC = 100       # Ramp-up duration (seconds)
HOLD_TIME_SEC = 20           # Hold duration at max (seconds)
RAMP_DOWN_TIME_SEC = 100     # Ramp-down duration (seconds)
# ============================================================

# Locate lhm_path.txt across common project locations
def get_lhm_dll_path():
    candidates = [
        os.path.join("config", "lhm_path.txt"),
        "lhm_path.txt",
        os.path.join("system_info", "lhm_path.txt"),
        os.path.join(os.path.dirname(__file__), "..", "..", "config", "lhm_path.txt"),
        os.path.join(os.path.dirname(__file__), "..", "..", "lhm_path.txt"),
    ]
    txt_path = next((p for p in candidates if os.path.exists(p)), None)

    if not txt_path:
        print("[ERROR] 'lhm_path.txt' not found! Specify the path to LibreHardwareMonitor.exe inside it.")
        sys.exit(1)

    with open(txt_path, "r", encoding="utf-8") as f:
        exe_or_dir = f.read().strip().strip('"')

    lhm_dir = os.path.dirname(exe_or_dir) if exe_or_dir.lower().endswith(".exe") else exe_or_dir
    dll_path = os.path.join(lhm_dir, "LibreHardwareMonitorLib.dll")

    if not os.path.exists(dll_path):
        print(f"[ERROR] DLL not found at:\n--> {dll_path}")
        sys.exit(1)

    return dll_path


DLL_PATH = get_lhm_dll_path()

try:
    import clr
except ImportError:
    print("[ERROR] 'pythonnet' is not installed! Run: pip install pythonnet")
    sys.exit(1)

try:
    clr.AddReference(DLL_PATH)
    from LibreHardwareMonitor.Hardware import Computer  # type: ignore
except Exception as e:
    err_str = str(e)
    if "FileLoadException" in err_str or "NotSupportedException" in err_str or "0x80131515" in err_str:
        print("\n" + "=" * 70)
        print(" [WINDOWS SECURITY ERROR] DLL FILE IS BLOCKED!")
        print("=" * 70)
        print(f"Path: {DLL_PATH}")
        print("\nHOW TO UNBLOCK:")
        print("1. Open File Explorer and navigate to the file.")
        print("2. Right-click the DLL file -> select 'Properties'.")
        print("3. At the bottom of the 'General' tab, check: [✔] 'Unblock'.")
        print("4. Click 'Apply' and 'OK', then restart this script.")
        print("=" * 70 + "\n")
    else:
        print(f"[DLL LOAD ERROR]: {e}")
    sys.exit(1)

computer = Computer()
computer.IsMotherboardEnabled = True
computer.IsControllerEnabled = True
computer.IsGpuEnabled = True
computer.Open()


def find_control(target_name):
    for hardware in computer.Hardware:
        hardware.Update()
        for sub in hardware.SubHardware:
            sub.Update()
            for s in sub.Sensors:
                if str(s.SensorType) == "Control" and s.Name == target_name:
                    return s
        for s in hardware.Sensors:
            if str(s.SensorType) == "Control" and s.Name == target_name:
                return s
    return None


control = find_control(TARGET_FAN_NAME)

if not control:
    print(f"[ERROR] Header '{TARGET_FAN_NAME}' not found!")
    print("Run 'find_fans.py' to list available fan control headers.")
    computer.Close()
    sys.exit(1)

total_steps = abs(END_PWM - START_PWM)
delay_up = RAMP_UP_TIME_SEC / total_steps if total_steps > 0 else 0
delay_down = RAMP_DOWN_TIME_SEC / total_steps if total_steps > 0 else 0

print("=" * 65)
print(f"       FAN SPEED RAMP BENCHMARK: {TARGET_FAN_NAME}")
print("=" * 65)
print(f" 1. Ramp Up   : {START_PWM}% -> {END_PWM}% in {RAMP_UP_TIME_SEC}s")
print(f" 2. Hold      : {END_PWM}% for {HOLD_TIME_SEC}s")
print(f" 3. Ramp Down : {END_PWM}% -> {START_PWM}% in {RAMP_DOWN_TIME_SEC}s")
print("=" * 65)
print(" Press [Ctrl + C] for emergency abort and return to BIOS control.\n")

try:
    # 1. Ramp Up
    print("[ >> ] 1/3 RAMPING UP...")
    for pwm in range(START_PWM, END_PWM + 1):
        control.Control.SetSoftware(float(pwm))
        print(f"\r Current PWM: {pwm:3d}% | (Ramp Up)", end="", flush=True)
        time.sleep(delay_up)

    # 2. Hold at Maximum
    if HOLD_TIME_SEC > 0:
        print(f"\n\n[ == ] 2/3 HOLDING MAXIMUM ({HOLD_TIME_SEC}s)...")
        for remaining in range(HOLD_TIME_SEC, 0, -1):
            print(
                f"\r Holding {END_PWM}% | Remaining: {remaining:2d}s...",
                end="",
                flush=True,
            )
            time.sleep(1)

    # 3. Ramp Down
    print("\n\n[ << ] 3/3 RAMPING DOWN...")
    for pwm in range(END_PWM, START_PWM - 1, -1):
        control.Control.SetSoftware(float(pwm))
        print(f"\r Current PWM: {pwm:3d}% | (Ramp Down)", end="", flush=True)
        time.sleep(delay_down)

    print("\n\n[ OK ] Benchmark completed successfully!")

except KeyboardInterrupt:
    print("\n\n[ ! ] Benchmark aborted by user!")

finally:
    print("Restoring hardware control to BIOS / Motherboard...")
    try:
        control.Control.SetDefault()
    except Exception:
        pass
    computer.Close()
    print("Done.")