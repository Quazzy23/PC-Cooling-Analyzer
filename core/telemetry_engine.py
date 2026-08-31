"""
Движок обработки телеметрии датчиков:
- Чтение двухстрочных CSV-логов LHM
- Сглаживание (Rolling Mean) и рессемплинг (Step Downsampling)
- Динамический расчёт сводной таблицы метрик (Min, Max, Avg) по временным зонам
- Экспорт графиков в высоком разрешении и сжатых CSV эволюции
"""
import os
import numpy as np
import pandas as pd
from PyQt6 import QtGui


class TelemetryEngine:
    @staticmethod
    def load_log_file(file_path: str, time_start: float = 0.0, time_end: str = "last"):
        """Загружает CSV с двухстрочным заголовком и нормализует время от 0"""
        df = pd.read_csv(file_path, header=[0, 1])
        col_time = df.columns[0]
        
        t_arr = df[col_time].to_numpy().astype(float)
        t_norm = t_arr - t_arr[0]
        df[col_time] = t_norm

        act_start = float(time_start) if (isinstance(time_start, (int, float)) and time_start > 0.0) else 0.0
        act_end = float(time_end) if (isinstance(time_end, (int, float)) and time_end < t_norm[-1]) else t_norm[-1]

        if act_start > 0.0 or act_end < t_norm[-1]:
            df = df[(df[col_time] >= act_start) & (df[col_time] <= act_end)].reset_index(drop=True)
            df[col_time] = df[col_time] - df[col_time].iloc[0]

        return df, col_time

    @staticmethod
    def find_column_by_sensor_id(df: pd.DataFrame, sensor_id: str):
        """Находит кортеж-колонку в DataFrame по точному SensorId"""
        if not sensor_id:
            return None
        target_sid = str(sensor_id).strip()
        for col in df.columns:
            col_id = (col[1] if isinstance(col, tuple) else str(col)).strip()
            if col_id == target_sid:
                return col
        return None

    @staticmethod
    def smooth_series(series: pd.Series, window: int = 1):
        """Скользящее среднее для плавности графиков"""
        if series is not None:
            w = max(1, int(window))
            return series.rolling(window=w, min_periods=1).mean().to_numpy()
        return None

    @staticmethod
    def resample_series(series: pd.Series, step: int = 1):
        """Прореживание (downsampling) для линий тренда и сжатых отчетов"""
        if series is not None and step > 1:
            return series.rolling(window=step, min_periods=1).mean().iloc[::step].to_numpy()
        elif series is not None:
            return series.to_numpy()
        return None

    @staticmethod
    def get_resampled_time(time_arr: np.ndarray, step: int = 1):
        return time_arr[::step] if step > 1 else time_arr

    @staticmethod
    def compute_summary_rows(df: pd.DataFrame, col_time, time_regions: list, p1_sensors: list, p2_sensors: list, col_clock, smoothing_window: int = 1):
        """Рассчитывает Min, Max, Avg для всех датчиков с учетом активных зон выделения"""
        time_arr = df[col_time].to_numpy()

        if time_regions:
            mask = np.zeros(len(df), dtype=bool)
            ranges_str_list = []
            
            for reg in time_regions:
                t_min = min(reg['t_min'], reg['t_max'])
                t_max = max(reg['t_min'], reg['t_max'])
                region_mask = (time_arr >= t_min) & (time_arr <= t_max)
                mask |= region_mask
                
                valid_t = time_arr[region_mask]
                if len(valid_t) > 0:
                    ranges_str_list.append(f"{valid_t[0]:.1f}s - {valid_t[-1]:.1f}s")
                else:
                    ranges_str_list.append(f"{t_min:.1f}s - {t_max:.1f}s")
            
            target_df = df[mask]
            ranges_title = ", ".join(ranges_str_list)
        else:
            target_df = df
            ranges_title = "Total"

        rows = []
        def add_row(label, col_data, fmt="%.1f"):
            if col_data is not None and not target_df.empty:
                series_full = df[col_data]
                smoothed_full = series_full.rolling(window=max(1, smoothing_window), min_periods=1).mean()
                s_valid = smoothed_full[target_df.index].dropna()
                
                if not s_valid.empty:
                    mn, mx, av = fmt % s_valid.min(), fmt % s_valid.max(), fmt % s_valid.mean()
                else:
                    mn, mx, av = "—", "—", "—"
                rows.append((label, mn, mx, av))

        # Сенсоры P1
        for s in p1_sensors:
            fmt = "%.3f" if "volt" in s["key"].lower() else "%.1f"
            add_row(s["label"], s["col"], fmt=fmt)

        if col_clock:
            add_row("Clock (MHz)", col_clock, fmt="%.0f")

        # Сенсоры P2
        for s in p2_sensors:
            fmt = "%.0f" if "RPM" in s["label"] else "%.1f"
            add_row(s["label"], s["col"], fmt=fmt)

        return rows, ranges_title

    @staticmethod
    def export_summary_csv(summary_dir: str, summary_filepath: str, df: pd.DataFrame, time_data: np.ndarray, current_step: int, export_sensors: list, get_col_fn):
        """
        Экспортирует таблицу эволюции датчиков в CSV:
        - Если Step > 1: выгрузка строго по точкам времени и усреднению линии тренда.
        - Если Step == 1: выгрузка по всем существующим точкам времени 1 к 1.
        """
        os.makedirs(summary_dir, exist_ok=True)

        step = max(1, int(current_step))
        evolution_df = pd.DataFrame()
        evolution_df['Time_Sec'] = TelemetryEngine.get_resampled_time(time_data, step)

        for label, sid in export_sensors:
            fcol = get_col_fn(sid)
            if fcol is not None:
                evolution_df[label] = TelemetryEngine.resample_series(df[fcol], step)

        evolution_df.to_csv(summary_filepath, index=False)