"""Скрипт первоначальной настройки путей и запуска графического мастера конфигурации датчиков."""
import os
import sys
sys.dont_write_bytecode = True
from PyQt6 import QtWidgets

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.lhm_client import LHM_PATH_FILE, ensure_lhm_running
from ui.wizard_dialog import SimpleSensorsWizard
from core.texts import (
    MSG_INIT_BANNER, MSG_INIT_PROMPT_PATH, MSG_INIT_INPUT_PROMPT,
    MSG_INIT_CANCELLED, MSG_INIT_SUCCESS, MSG_INIT_PATH_ERROR
)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SYS_INFO_DIR = os.path.join(PROJECT_ROOT, "system_info")
DEFAULT_LHM_PATH = r"C:\Program Files\LibreHardwareMonitor\LibreHardwareMonitor.exe"

os.makedirs(SYS_INFO_DIR, exist_ok=True)


def resolve_lhm_path(raw_input: str) -> str:
    """Определяет путь к .exe по пути к папке или прямому пути к файлу."""
    clean = raw_input.strip().strip('"').strip("'")
    if not clean:
        return ""
    norm = os.path.normpath(clean)

    if os.path.isdir(norm):
        target = os.path.join(norm, "LibreHardwareMonitor.exe")
        if os.path.isfile(target):
            return target
        for f in os.listdir(norm):
            if f.lower() == "librehardwaremonitor.exe":
                return os.path.join(norm, f)
        return ""

    if os.path.isfile(norm) and norm.lower().endswith(".exe"):
        return norm

    if not norm.lower().endswith(".exe"):
        target = os.path.join(norm, "LibreHardwareMonitor.exe")
        if os.path.isfile(target):
            return target

    return ""


def ensure_valid_lhm_path_on_disk():
    """Проверяет сохраненный путь или запрашивает у пользователя ввод директории."""
    current_path = ""
    if os.path.exists(LHM_PATH_FILE):
        try:
            with open(LHM_PATH_FILE, "r", encoding="utf-8") as f:
                saved = f.read().strip()
                resolved = resolve_lhm_path(saved)
                if resolved and os.path.isfile(resolved):
                    current_path = resolved
        except Exception:
            pass

    if current_path and os.path.isfile(current_path):
        print(f"[OK] Verified LibreHardwareMonitor path: '{current_path}'")
        lhm_dir = os.path.dirname(current_path)
        dll_path = os.path.join(lhm_dir, "LibreHardwareMonitorLib.dll")
        if os.path.exists(dll_path):
            from utils.lhm_client import unblock_file
            unblock_file(dll_path)
            print(f"[OK] Unblocked 'LibreHardwareMonitorLib.dll' successfully.\n")
        return current_path

    print(MSG_INIT_BANNER)
    print(MSG_INIT_PROMPT_PATH.format(default=DEFAULT_LHM_PATH))

    while True:
        try:
            user_input = input(MSG_INIT_INPUT_PROMPT).strip()
        except KeyboardInterrupt:
            print(MSG_INIT_CANCELLED)
            sys.exit(0)

        target_candidate = user_input if user_input else DEFAULT_LHM_PATH
        resolved = resolve_lhm_path(target_candidate)

        if resolved and os.path.isfile(resolved):
            with open(LHM_PATH_FILE, "w", encoding="utf-8") as f:
                f.write(resolved + "\n")
            print(MSG_INIT_SUCCESS.format(path=resolved, file=LHM_PATH_FILE))

            lhm_dir = os.path.dirname(resolved)
            dll_path = os.path.join(lhm_dir, "LibreHardwareMonitorLib.dll")
            if os.path.exists(dll_path):
                from utils.lhm_client import unblock_file
                unblock_file(dll_path)
                print(f"[OK] Unblocked 'LibreHardwareMonitorLib.dll' successfully.\n")
            else:
                print()
            return resolved
        else:
            print(MSG_INIT_PATH_ERROR.format(path=target_candidate))


if __name__ == "__main__":
    lhm_exe = ensure_valid_lhm_path_on_disk()
    ensure_lhm_running(lhm_exe)

    app = QtWidgets.QApplication(sys.argv)
    win = SimpleSensorsWizard()
    win.show()
    sys.exit(app.exec())