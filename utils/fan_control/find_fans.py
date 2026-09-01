import os
import sys
import ctypes

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

try:
    is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    if not is_admin:
        print("[WARNING] Run terminal as Administrator to access all motherboard fan headers!\n")
except Exception:
    pass

computer = Computer()
computer.IsMotherboardEnabled = True
computer.IsControllerEnabled = True
computer.IsGpuEnabled = True
computer.Open()

print("\n=== AVAILABLE CONTROLLABLE FANS & PUMPS ===")
found = False

try:
    for hardware in computer.Hardware:
        hardware.Update()
        for sub in hardware.SubHardware:
            sub.Update()
            for sensor in sub.Sensors:
                if str(sensor.SensorType) == "Control":
                    print(f" Name: '{sensor.Name}' | Controller: {hardware.Name}")
                    found = True

        for sensor in hardware.Sensors:
            if str(sensor.SensorType) == "Control":
                print(f" Name: '{sensor.Name}' | Controller: {hardware.Name}")
                found = True

    if not found:
        print(" No controllable fans found. Make sure the script is running as Administrator.")

    print("===========================================\n")
finally:
    computer.Close()