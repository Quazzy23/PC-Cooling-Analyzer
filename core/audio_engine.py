"""
Аудиодвижок цифровой обработки сигналов (DSP):
- Воспроизведение звука через sounddevice.OutputStream
- Потокобезопасная IIR SOS (Баттерворт 4-го порядка) фильтрация
- ЕДИНЫЙ расчет dB SPL для Live FFT и 2D-Спектрограммы через amplitude_to_db_spl
"""
import os
import threading
import numpy as np
import scipy.signal as signal
import sounddevice as sd
import soundfile as sf

from core.defaults import AUDIO_PROFILE

TARGET_SPEC_WIDTH = AUDIO_PROFILE["target_spec_width"]
LIMIT_FREQ_MIN = AUDIO_PROFILE["limit_freq_min"]
LIMIT_FREQ_MAX = AUDIO_PROFILE["limit_freq_max"]


def amplitude_to_db_spl(fft_magnitude, window_length: int, cal_offset: float):
    """
    ЕДИНАЯ для всего проекта формула перевода магнитуды FFT в калиброванные dB SPL.
    Когерентное усиление окна Ханнинга: sum(w) = N / 2.
    Пиковая амплитуда гармоники: A = 2.0 * |FFT| / sum(w) = |FFT| / (N / 4).
    """
    w_sum = window_length / 2.0
    amplitude = (2.0 * fft_magnitude) / w_sum
    return 20.0 * np.log10(amplitude + 1e-6) + cal_offset


class AudioEngine:
    def __init__(self, audio_path: str):
        self.audio_path = audio_path
        data, self.sample_rate = sf.read(audio_path, dtype='float32')
        self.audio_samples = data[:, 0] if data.ndim > 1 else data
        self.total_duration = len(self.audio_samples) / self.sample_rate

        self.is_playing = False
        self.current_sample_idx = 0
        self.boost_db = 30.0
        self.fft_size = 4096

        # Единая калибровка
        self.cal_offset = AUDIO_PROFILE.get("calibration_offset", 90.0)
        cfg_path = os.path.join("system_info", "audio_config.json")
        if os.path.exists(cfg_path):
            try:
                import json
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.cal_offset = float(cfg.get("calibration_offset", self.cal_offset))
            except Exception:
                pass

        self.active_filters = []
        self.filter_lock = threading.Lock()
        self._filter_states = {}
        self._block_size = 1024

        self.init_stream()

    def get_bandpass_sos(self, f_low: float, f_high: float):
        nyq = self.sample_rate / 2.0
        low = max(20.0, float(f_low))
        high = min(nyq - 50.0, float(f_high))

        if low >= high:
            low = max(20.0, high - 50.0)

        w_low = low / nyq
        w_high = min(0.999, high / nyq)

        if w_low >= w_high:
            w_low = max(0.001, w_high - 0.01)

        return signal.butter(4, [w_low, w_high], btype='bandpass', output='sos')

    def init_stream(self):
        def audio_callback(outdata, frames, time_info, status):
            if not self.is_playing:
                outdata.fill(0)
                self._filter_states.clear()
                return

            try:
                start_idx = self.current_sample_idx
                end_idx = start_idx + frames
                total_len = len(self.audio_samples)

                if start_idx >= total_len:
                    outdata.fill(0)
                    self.is_playing = False
                    self.current_sample_idx = 0
                    self._filter_states.clear()
                    return

                if end_idx > total_len:
                    actual_chunk = self.audio_samples[start_idx:total_len]
                    chunk_raw = np.zeros(frames, dtype=np.float32)
                    chunk_raw[:len(actual_chunk)] = actual_chunk
                    self.current_sample_idx = 0
                    self.is_playing = False
                else:
                    chunk_raw = self.audio_samples[start_idx:end_idx].copy()
                    self.current_sample_idx = end_idx

                gain = float(10.0 ** (self.boost_db / 20.0))

                with self.filter_lock:
                    num_filters = len(self.active_filters)
                    active_bands = []
                    if num_filters > 0:
                        cur_t = start_idx / self.sample_rate
                        for filt in self.active_filters:
                            t_min, t_max = filt['t_min'], filt['t_max']
                            if t_min is None or (t_min <= cur_t <= t_max):
                                active_bands.append((int(filt['f_min']), int(filt['f_max'])))

                if num_filters == 0:
                    self._filter_states.clear()
                    outdata[:, 0] = np.clip(chunk_raw * gain, -1.0, 1.0)
                    return

                if not active_bands:
                    outdata.fill(0)
                    self._filter_states.clear()
                    return

                accumulated = np.zeros(frames, dtype=np.float32)
                active_keys = set(active_bands)
                dead_keys = [k for k in self._filter_states if k not in active_keys]
                for k in dead_keys:
                    del self._filter_states[k]

                for f_min, f_max in active_bands:
                    band_key = (f_min, f_max)
                    if band_key not in self._filter_states:
                        try:
                            sos = self.get_bandpass_sos(f_min, f_max)
                            zi = signal.sosfilt_zi(sos) * chunk_raw[0]
                            self._filter_states[band_key] = {'sos': sos, 'zi': zi}
                        except Exception:
                            continue

                    filt_data = self._filter_states[band_key]
                    filtered_band, filt_data['zi'] = signal.sosfilt(filt_data['sos'], chunk_raw, zi=filt_data['zi'])
                    accumulated += filtered_band.astype(np.float32)

                outdata[:, 0] = np.clip(accumulated * gain, -1.0, 1.0)
            except Exception:
                outdata.fill(0)

        self.stream = sd.OutputStream(
            channels=1,
            samplerate=self.sample_rate,
            blocksize=self._block_size,
            dtype='float32',
            callback=audio_callback
        )
        self.stream.start()

    def compute_fft_magnitude_db(self, fft_vals, window_len: int):
        """ЕДИНАЯ формула перевода магнитуды FFT в калиброванные dB SPL для всего проекта"""
        return 20.0 * np.log10((fft_vals / (window_len / 2.0)) + 1e-6) + self.cal_offset

    def get_db_at_time_and_freq(self, t_sec: float, f_hz: float) -> float:
        """Вычисляет точный уровень громкости dB SPL в точке (t, f) по единой формуле FFT"""
        sample_idx = int(np.clip(t_sec * self.sample_rate, 0, len(self.audio_samples) - 1))
        fft_size = self.fft_size
        start_s = max(0, sample_idx - fft_size // 2)
        end_s = start_s + fft_size

        if end_s > len(self.audio_samples):
            start_s = max(0, len(self.audio_samples) - fft_size)
            end_s = len(self.audio_samples)

        slice_data = self.audio_samples[start_s:end_s]
        if len(slice_data) < fft_size:
            return 0.0

        window = np.hanning(fft_size)
        fft_vals = np.abs(np.fft.rfft(slice_data * window))
        freqs = np.fft.rfftfreq(fft_size, 1.0 / self.sample_rate)

        idx_f = int(np.argmin(np.abs(freqs - f_hz)))
        db_val = self.compute_fft_magnitude_db(fft_vals[idx_f], fft_size)
        return round(float(db_val), 1)

    def render_spectrogram_slice(self, t_start: float, t_end: float):
        """Возвращает оригинальную плавную спектрограмму высокого качества"""
        s_idx = int(max(0.0, t_start) * self.sample_rate)
        e_idx = int(min(self.total_duration, t_end) * self.sample_rate)
        slice_audio = self.audio_samples[s_idx:e_idx]

        if len(slice_audio) < 128:
            return None, 0.0, LIMIT_FREQ_MAX

        span = max(0.05, t_end - t_start)
        nper = 1024 if span < 15 else 2048
        hop = max(16, len(slice_audio) // TARGET_SPEC_WIDTH)
        nov = max(0, nper - hop) if nper > hop else 0

        # Исходный расчет SciPy с идеальным наложением окон
        f_spec, t_spec, Sxx = signal.spectrogram(
            slice_audio,
            fs=self.sample_rate,
            nperseg=nper,
            noverlap=nov
        )
        mask = (f_spec >= LIMIT_FREQ_MIN) & (f_spec <= LIMIT_FREQ_MAX)
        if not np.any(mask):
            return None, LIMIT_FREQ_MIN, LIMIT_FREQ_MAX

        # Учитываем половину ширины бина (df / 2), чтобы пиксели центрировались идеально точно
        df_bin = float(f_spec[1] - f_spec[0])
        f_min_actual = float(f_spec[mask][0]) - (df_bin / 2.0)
        f_max_actual = float(f_spec[mask][-1]) + (df_bin / 2.0)

        # Исходная плавная логарифмическая шкала
        Sxx_db = 10 * np.log10(Sxx[mask, :] + 1e-12)

        return Sxx_db, f_min_actual, f_max_actual

    def compute_fft_at(self, sample_idx: int, freq_scale_mode: str = "Log", isolate_on_filter: bool = False):
        """Считает Live FFT по той же формуле amplitude_to_db_spl"""
        start_s = max(0, sample_idx - self.fft_size // 2)
        end_s = start_s + self.fft_size

        if end_s > len(self.audio_samples):
            return None, None, [], [], []

        slice_data = self.audio_samples[start_s:end_s]
        window = np.hanning(len(slice_data))
        fft_vals = np.abs(np.fft.rfft(slice_data * window))
        freqs = np.fft.rfftfreq(len(slice_data), 1.0 / self.sample_rate)

        # Вызываем ту же ЕДИНУЮ функцию перевода в dB SPL
        fft_db = self.compute_fft_magnitude_db(fft_vals, len(slice_data))

        valid_mask = freqs >= LIMIT_FREQ_MIN
        cur_t = sample_idx / self.sample_rate
        active_bands = []

        with self.filter_lock:
            if self.active_filters:
                for filt in self.active_filters:
                    t_min, t_max = filt['t_min'], filt['t_max']
                    if t_min is None or (t_min <= cur_t <= t_max):
                        active_bands.append((filt['f_min'], filt['f_max']))

        if isolate_on_filter and self.active_filters:
            if active_bands:
                band_mask = np.zeros_like(freqs, dtype=bool)
                for f_min, f_max in active_bands:
                    band_mask |= (freqs >= f_min) & (freqs <= f_max)
                valid_mask = valid_mask & band_mask
            else:
                valid_mask = np.zeros_like(freqs, dtype=bool)

        x_coords = np.log10(freqs[valid_mask]) if freq_scale_mode == "Log" else freqs[valid_mask]
        valid_db = fft_db[valid_mask]

        peak_xs, peak_ys, peak_labels = [], [], []

        if active_bands:
            for idx, (f_min, f_max) in enumerate(active_bands):
                local_mask = (freqs >= f_min) & (freqs <= f_max)
                if np.any(local_mask):
                    sub_f, sub_db = freqs[local_mask], fft_db[local_mask]
                    max_i = np.argmax(sub_db)
                    peak_f, peak_p = sub_f[max_i], sub_db[max_i]
                    peak_x = np.log10(peak_f) if freq_scale_mode == "Log" else peak_f

                    peak_xs.append(peak_x)
                    peak_ys.append(peak_p)
                    peak_labels.append(f"Peak: {peak_f:.0f} Hz ({peak_p:.1f} dB)")
        elif not self.active_filters:
            global_mask = (freqs >= 50) & (freqs <= LIMIT_FREQ_MAX)
            if np.any(global_mask):
                sub_f, sub_db = freqs[global_mask], fft_db[global_mask]
                max_i = np.argmax(sub_db)
                peak_f, peak_p = sub_f[max_i], sub_db[max_i]
                peak_x = np.log10(peak_f) if freq_scale_mode == "Log" else peak_f

                peak_xs.append(peak_x)
                peak_ys.append(peak_p)
                peak_labels.append(f"Peak: {peak_f:.0f} Hz ({peak_p:.1f} dB)")

        return x_coords, valid_db, peak_xs, peak_ys, peak_labels

    def close(self):
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass