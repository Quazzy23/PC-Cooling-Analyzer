"""
Движок обработки телеметрии датчиков:
- Чтение и нормализация двухстрочных CSV-логов LHM.
- Сглаживание данных скользящим средним (Rolling Mean).
- Рессемплинг и прореживание точек для линий тренда (Downsampling).
- Расчет метрик (Min, Max, Avg) по всей шкале или активным зонам выделения.
- Экспорт обработанной эволюции датчиков в CSV.
"""
import os
import numpy as np
import pandas as pd

from core.texts import TEXT_EMPTY_METRIC, TEXT_TOTAL_RANGES, HEADER_TIME_SEC


class TelemetryEngine:
    """
    Класс статических методов математической обработки данных аппаратных сенсоров.
    """

    @staticmethod
    def load_log_file(file_path: str, time_start: float = 0.0, time_end: str = "last") -> tuple[pd.DataFrame, str]:
        """
        Загружает CSV-лог с двухстрочным заголовком (имена и ID) и нормализует шкалу времени от 0.
        :param file_path: Путь к CSV файлу.
        :param time_start: Начальная секунда обрезки.
        :param time_end: Конечная секунда обрезки или 'last'.
        :return: (DataFrame с данными, имя колонки времени).
        """
        df = pd.read_csv(file_path, header=[0, 1])
        col_time = df.columns[0]

        # Нормализация времени от нуля
        t_arr = df[col_time].to_numpy().astype(float)
        t_norm = t_arr - t_arr[0]
        df[col_time] = t_norm

        act_start = float(time_start) if (isinstance(time_start, (int, float)) and time_start > 0.0) else 0.0
        act_end = float(time_end) if (isinstance(time_end, (int, float)) and time_end < t_norm[-1]) else t_norm[-1]

        # Обрезка временного интервала, если задано пользователем
        if act_start > 0.0 or act_end < t_norm[-1]:
            df = df[(df[col_time] >= act_start) & (df[col_time] <= act_end)].reset_index(drop=True)
            df[col_time] = df[col_time] - df[col_time].iloc[0]

        return df, col_time

    @staticmethod
    def find_column_by_sensor_id(df: pd.DataFrame, sensor_id: str):
        """
        Находит точный кортеж-колонку в двухстрочном DataFrame по строковому Sensor ID.
        :param df: DataFrame с мульти-заголовком.
        :param sensor_id: Уникальный путь датчика LHM.
        :return: Кортеж колонки или None.
        """
        if not sensor_id:
            return None
        target_sid = str(sensor_id).strip()
        for col in df.columns:
            col_id = (col[1] if isinstance(col, tuple) else str(col)).strip()
            if col_id == target_sid:
                return col
        return None

    @staticmethod
    def smooth_series(series: pd.Series, window: int = 1) -> np.ndarray | None:
        """
        Скользящее среднее (Rolling Mean) для сглаживания шумов сырых графиков.
        :param series: Исходный временной ряд.
        :param window: Размер окна сглаживания в отсчетах.
        """
        if series is not None:
            w = max(1, int(window))
            return series.rolling(window=w, min_periods=1).mean().to_numpy()
        return None

    @staticmethod
    def resample_series(series: pd.Series, step: int = 1) -> np.ndarray | None:
        """
        Прореживание данных с предварительным усреднением шага для построения линий тренда.
        :param series: Исходный временной ряд.
        :param step: Шаг прореживания (Step downsampling).
        """
        if series is not None and step > 1:
            return series.rolling(window=step, min_periods=1).mean().iloc[::step].to_numpy()
        elif series is not None:
            return series.to_numpy()
        return None

    @staticmethod
    def get_resampled_time(time_arr: np.ndarray, step: int = 1) -> np.ndarray:
        """Возвращает массив меток времени с учетом шага прореживания."""
        return time_arr[::step] if step > 1 else time_arr

    @staticmethod
    def compute_summary_rows(
        df: pd.DataFrame,
        col_time,
        time_regions: list,
        p1_sensors: list,
        p2_sensors: list,
        smoothing_window: int = 1
    ) -> tuple[list, str]:
        """
        Рассчитывает Min, Max, Avg для всех датчиков с учетом выбранных пользователем зон на графиках.
        :param df: DataFrame с логом.
        :param col_time: Колонка времени.
        :param time_regions: Список словарей выделенных зон [{'t_min', 't_max'}, ...].
        :param p1_sensors: Список датчиков Panel 1.
        :param p2_sensors: Список датчиков Panel 2.
        :param smoothing_window: Текущее окно сглаживания для расчета метрик.
        :return: (Список строк таблицы [(Metric, Min, Max, Avg), ...], строка диапазона времени).
        """
        time_arr = df[col_time].to_numpy()

        # Фильтрация данных по активным зонам выделения
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
            ranges_title = TEXT_TOTAL_RANGES

        rows = []

        def add_row(label: str, col_data, fmt: str = "%.1f"):
            """Вспомогательный расчет метрик по одной колонке."""
            if col_data is not None and not target_df.empty:
                series_full = df[col_data]
                smoothed_full = series_full.rolling(window=max(1, smoothing_window), min_periods=1).mean()
                s_valid = smoothed_full[target_df.index].dropna()

                if not s_valid.empty:
                    mn = fmt % s_valid.min()
                    mx = fmt % s_valid.max()
                    av = fmt % s_valid.mean()
                else:
                    mn, mx, av = TEXT_EMPTY_METRIC, TEXT_EMPTY_METRIC, TEXT_EMPTY_METRIC
                rows.append((label, mn, mx, av))

        # Расчет датчиков Panel 1 (Теплофизика и питание)
        for s in p1_sensors:
            fmt = "%.3f" if "volt" in s["key"].lower() or "(v)" in s["label"].lower() else "%.1f"
            if "clock" in s["label"].lower() or "mhz" in s["label"].lower():
                fmt = "%.0f"
            add_row(s["label"], s.get("col"), fmt=fmt)

        # Расчет датчиков Panel 2 (Обороты кулеров и звук)
        for s in p2_sensors:
            fmt = "%.0f" if "rpm" in s["label"].lower() else "%.1f"
            add_row(s["label"], s.get("col"), fmt=fmt)

        return rows, ranges_title

    @staticmethod
    def export_summary_csv(
        summary_dir: str,
        summary_filepath: str,
        df: pd.DataFrame,
        time_data: np.ndarray,
        current_step: int,
        export_sensors: list,
        get_col_fn
    ):
        """
        Экспортирует таблицу эволюции датчиков в CSV:
        - Если Step > 1: выгрузка строго по точкам времени и значениям линии тренда.
        - Если Step == 1: выгрузка по всем исходным точкам времени без потерь.
        """
        os.makedirs(summary_dir, exist_ok=True)

        step = max(1, int(current_step))
        evolution_df = pd.DataFrame()
        evolution_df[HEADER_TIME_SEC] = TelemetryEngine.get_resampled_time(time_data, step)

        for label, sid in export_sensors:
            fcol = get_col_fn(sid)
            if fcol is not None:
                evolution_df[label] = TelemetryEngine.resample_series(df[fcol], step)

        evolution_df.to_csv(summary_filepath, index=False)