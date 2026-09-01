# ❄️ PC Cooling Analyzer

A high-performance, modular hardware telemetry and acoustic spectral analysis suite built for PC cooling benchmarks, thermal testing, and noise diagnostics.

> **Status:** 🚧 Under Development (Phase: Core Logic & User Experience)

---

## 🌍 Overview

**PC Cooling Analyzer** is an end-to-end benchmarking suite that bridges low-level hardware sensor telemetry with real-time acoustic spectral analysis. It synchronizes multi-sensor logging (temperatures, power draw, fan speeds) with calibrated audio recording and provides GPU-accelerated visualizers for deep thermal and acoustic inspection.

---

## 🌟 Key Features

*   **Synchronized Logging (`logger.py`):** Captures hardware sensors at 4 Hz via LibreHardwareMonitor alongside continuous calibrated noise recording (dBA) with live multi-profile console dashboard.
*   **Unified Studio Suite (`analyzer.py`):** All-in-one 4-quadrant visualizer combining thermal/cooling telemetry (P1/P2) and spectral audio DAW (Live FFT and 2D Spectrogram Timeline) with module toggles and summary metrics.
*   **Visual Sensor Wizard (`utils/init_configs.py`):** Interactive tree-based sensor mapper with checkboxes, custom ordering, panel assignment, and editable sensor names.
*   **Unified Controls:** Standardized mouse navigation across all visualizers (pan, zoom, timeline scrub, and region selection).
*   **Modular Architecture:** Clean separation between core math engines, graphics rendering, and hardware utilities.

---

## 🚀 Installation & Setup Guide

### 1. Clone the repository
```bash
git clone https://github.com/Quazzy23/PC-Cooling-Analyzer.git
cd PC-Cooling-Analyzer
```

### 2. Download LibreHardwareMonitor
Download [LibreHardwareMonitor](https://github.com/LibreHardwaRemonitor/LibreHardwareMonitor). Run `LibreHardwareMonitor.exe`, go to **Options**, and enable **Remote Web Server**.

### 3. Install Dependencies
Ensure **Python 3.10+** is installed, then install dependencies:
```bash
pip install numpy scipy pandas requests pyqt6 pyqtgraph sounddevice soundfile lameenc uiautomation pynput
```

### 4. Setup LHM Path & Map Sensors
Run `utils/init_configs.py`. Enter the path to your LibreHardwareMonitor folder or `.exe`. The wizard will auto-launch LHM and open the visual sensor configuration window to map your profiles (CPU, GPU, etc.).

### 5. Select Microphone (Optional)
Run `utils/select_mic.py` and select your input device index from the list to enable acoustic noise logging (dBA).

### 6. Log Benchmark Data
Run `logger.py` to record telemetry to CSV and synchronized audio to MP3.

### 7. Run Analysis
Run `analyzer.py` and select the target CSV log to inspect interactive charts, summary metrics, and export reports.

---

## 📁 Repository Structure

Currently, this repository hosts the codebase required to run the benchmarking pipeline:
* `/core` — Data processing engines (telemetry smoothing, metrics, audio DSP, FFT).
* `/ui` — Stylesheets, custom axes, and the unified interactive ViewBox engine.
* `/utils` — LHM client, sensor config wizard, mic configuration, and setup scripts.
* `analyzer.py` & `logger.py` — The primary executable interfaces.

---

## 👥 Authors & Credits

*   **Project Lead:** Quazzy ([@Quazzy23](https://github.com/Quazzy23))
*   **Development:** Created with the support of Google AI.