# 🌡️ PC Cooling & Acoustics Analyzer Suite

> A professional Python-based diagnostic suite for comprehensive thermal, electrical, and acoustic benchmarking of PC cooling systems (AIO liquid coolers and air cooling setups).

---

## 🚧 Project Status

This project is currently under **active development**. Core telemetry logging, real-time GUI analytics, and spectral audio analysis modules are fully functional, while advanced diagnostic features and UI refinements are continuously being polished.

---

## 🎯 About the Project

**PC-Cooling-Analyzer** is designed for enthusiasts, overclockers, and hardware reviewers who need precise, hardware-level diagnostic data. Unlike standard monitoring tools, this suite synchronizes high-frequency hardware telemetry (via LibreHardwareMonitor) with real-time acoustic spectrum analysis, allowing you to correlate thermal spikes, power loads, and fan RPMs with specific acoustic resonance frequencies and noise levels.

### 🌟 Key Features

*   **📊 Hardware Telemetry Logging:** Polls 273+ system sensors at 4 Hz (250ms interval) via LibreHardwareMonitor Web API.
*   **🎧 DAW-Style Spectral Audio Analyzer:** High-performance PyQt6 + PyQtGraph frequency analyzer featuring a real-time live FFT spectrum, 2D spectrogram heatmap, and selective bandpass audio filtering.
*   **⚡ Accelerated Visualization:** Built on PyQt6 and pyqtgraph with GPU (OpenGL) acceleration for butter-smooth telemetry rendering.
*   **🎛️ Interactive Analytics & LOD:** Adjustable trend smoothing, raw data opacity ("fog"), multi-Y axis overlays with dynamic L/R positioning, and real-time summary metric recalculation using custom time selections.
*   **📋 Sensor Passport & Visibility Control:** Compact sidebar widgets to toggle individual sensor curves and scale axes on the fly.
*   **💾 Clean Reporting:** Export publication-ready Hi-Res JPG charts and compressed CSV evolution reports with a single click.

---

## 🛠️ Tech Stack

*   **Language:** Python 3.10+
*   **GUI Framework:** PyQt6, PyQtGraph (OpenGL accelerated)
*   **Audio DSP:** NumPy, SciPy (STFT/Spectrogram, Butterworth filters), SoundDevice, SoundFile
*   **Data Processing:** Pandas, Matplotlib

---

## 🚀 Setup & Launch Guide

> **Note:** Because this project is currently in early active development, setting up the initial hardware telemetry pipeline requires a few manual steps. We will streamline and automate this process in future updates!

### Step 1: Install & Configure LibreHardwareMonitor
1. Download the latest release of **[LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)**.
2. Open LibreHardwareMonitor, go to **Options**, and ensure **Remote Web Server** is enabled (it runs locally on `http://localhost:8085`).
3. *(Recommended)* Check **Run Minimized** in LibreHardwareMonitor options so the app stays out of your way in the system tray.

### Step 2: Clone Repository & Install Dependencies
1. **Clone the repository:**
   ```bash
   git clone https://github.com/Quazzy23/PC-Cooling-Analyzer.git
   cd PC-Cooling-Analyzer
   ```
2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

### Step 3: Configure Paths & Sensor Mappings
1. **Set LHM Executable Path:** 
   Open `logger.py` and make sure `LHM_EXE_PATH` points directly to your local installation of LibreHardwareMonitor.exe (e.g., `r"C:\Users\YourUser\Downloads\LibreHardwareMonitor\LibreHardwareMonitor.exe"`). This allows the logger to automatically launch LHM in the background with Administrator privileges when started.
2. **Dump & Map Sensors:**
   Run the sensor dumper utility to capture a complete snapshot of all hardware sensors available on your motherboard/CPU/GPU:
   ```bash
   python utils/dump_sensors.py
   ```
   This will generate a reference file at `system_info/lhm_sensors_dump.txt`. Open it to find the exact Sensor IDs for your hardware components, and map them in **`utils/configs.py`**.

### Step 4: Calibrate Microphone (For Acoustic Testing)
If you are planning to record noise levels and run acoustic diagnostics, run the microphone selector utility once:
```bash
python utils/select_mic.py
```
This will filter available WASAPI audio devices and save your chosen USB microphone to `system_info/audio_config.json`.

### Step 5: Run the Diagnostic Suite
1. **Start Telemetry & Audio Logging:**
   ```bash
   python logger.py
   ```
   *(This launches LHM, starts recording all hardware sensors to a raw CSV log, and captures synchronous audio of your test session).*
2. **Analyze Telemetry & Hardware Dynamics:**
   ```bash
   python analyzer.py
   ```
3. **Analyze Acoustic Frequencies (DAW Spectrogram):**
   ```bash
   python utils/audio_analyzer.py
   ```

---

## 📂 Project Architecture

```text
PC-Cooling-Analyzer/
│
├── logger.py                 # Main universal telemetry & audio logger
├── analyzer.py               # Main interactive PyQtGraph hardware visualizer
├── audio_analyzer.py         # PyQt6 spectral DAW audio analyzer
│
├── system_info/              # PC hardware passport & sensor configs
│   ├── hardware_info.json    # System components data
│   ├── audio_config.json     # USB microphone calibration config
│   └── lhm_sensors_dump.txt  # Full text dump of all LHM sensors
│
├── utils/                    # Helper scripts & modules
│   ├── configs.py            # CPU & GPU sensor profile mappings
│   ├── select_mic.py         # WASAPI microphone selector utility
│   ├── dump_sensors.py       # LHM Web API sensor dumper
│
└── results/                  # Test results (git-ignored)
    ├── sensors_logs/         # Raw CSV sensor logs & sync MP3 audio
    └── summary_reports/      # Exported JPG charts & CSV reports
```

---

## 👥 Author

*   Quazzy ([@Quazzy23](https://github.com/Quazzy23))