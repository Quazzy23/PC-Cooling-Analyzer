# ❄️ PC Cooling Analyzer

A high-performance, modular hardware telemetry and acoustic spectral analysis suite built for PC cooling benchmarks, thermal testing, and noise diagnostics.

> **Status:** 🚧 Under Development (Phase: Core Logic & User Experience)

---

## 🌍 Overview

**PC Cooling Analyzer** is an end-to-end benchmarking suite that bridges low-level hardware sensor telemetry with real-time acoustic spectral analysis. It synchronizes multi-sensor logging (temperatures, power draw, fan speeds) with calibrated audio recording and provides GPU-accelerated (60+ FPS) visualizers for deep thermal and acoustic inspection.

---

## 🌟 Key Features

*   **Synchronized Logging:** Captures all hardware sensors at 4 Hz via LibreHardwareMonitor alongside continuous calibrated noise recording (dBA).
*   **Hardware Visualizer (`analyzer.py`):** Interactive dual-panel time series for thermal and cooling dynamics with live on-curve values, custom time region statistics, and 1-click layout persistence.
*   **Spectral Audio DAW (`audio_analyzer.py`):** Real-time FFT acoustic spectrum and high-resolution 2D spectrogram with interactive bandpass filtering.
*   **Unified Controls:** Standardized mouse navigation across both visualizers (pan, zoom, timeline scrub, and region selection).
*   **Modular Architecture:** Clean separation between core math engines, graphics rendering, and hardware utilities.

---

## 🚀 Installation & Setup Guide

### 1. Clone the repository
```bash
git https://github.com/Quazzy23/PC-Cooling-Analyzer
```

### 2. Download LibreHardwareMonitor
Download [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) [1]. Run `LibreHardwareMonitor.exe` as Administrator, go to **Options**, and enable **Remote Web Server** (default port `8085`) [1].

### 3. Install Dependencies
Ensure **Python 3.10+** is installed, then install dependencies:
```bash
pip install numpy scipy pandas requests pyqt6 pyqtgraph sounddevice soundfile lameenc
```

### 4. Initialize Configurations
Run `utils/init_configs.py`. Open `system_info/lhm_path.txt` and paste the full path to your `LibreHardwareMonitor.exe`.

### 5. Discover and map sensors
Run `utils/dump_sensors.py` to scan all available hardware sensors and generate `system_info/lhm_sensors_dump.txt`.
Open `system_info/sensors_config.json` and paste your desired `SensorId`s from the dump file into the `CPU` or `GPU` section.

### 6. Select Microphone
Run `utils/select_mic.py` and select your input device index from the list.

### 7. Log Benchmark Data
Run `logger.py` to record telemetry to CSV and synchronized audio to MP3. Press `Ctrl+C` to stop logging.

### 8. Run analyzes
Run `analyzer.py` and select the target CSV log to inspect interactive charts and summary metrics.

---

## 📁 Repository Structure

Currently, this repository hosts the codebase required to run the benchmarking pipeline:
* `/core` — Data processing engines (telemetry smoothing, metrics, audio DSP, FFT).
* `/ui` — Stylesheets, custom axes, and the unified interactive ViewBox engine.
* `/utils` — LHM client, sensor discovery dumpers, mic configuration, and setup scripts.
* `analyzer.py` & `logger.py` — The primary executable interfaces.

---

## 👥 Authors & Credits

*   **Project Lead:** Quazzy ([@Quazzy23](https://github.com/Quazzy23))
*   **Development:** Created with the support of Google AI.