"""
Кастомные шкалы и оси для графиков PyQtGraph
"""
import numpy as np
import pyqtgraph as pg


class CleanLogFrequencyAxis(pg.AxisItem):
    """Шкала частот с переключением между Linear и Log10 режимами"""
    def __init__(self, analyzer_ref=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.analyzer = analyzer_ref

    def tickValues(self, minVal, maxVal, size):
        ticks_hz = [20, 50, 100, 200, 500, 1000, 2000, 3000, 5000, 8000, 10000, 15000, 20000]
        is_lin = hasattr(self, 'analyzer') and self.analyzer and getattr(self.analyzer, 'freq_scale_mode', 'Log') == "Linear"

        if is_lin:
            vals = [float(hz) for hz in ticks_hz if minVal <= float(hz) <= maxVal]
            return [(1.0, vals)]
        else:
            log_vals = [float(np.log10(hz)) for hz in ticks_hz if minVal <= np.log10(hz) <= maxVal]
            return [(1.0, log_vals)]

    def tickStrings(self, values, scale, spacing):
        strings = []
        is_lin = hasattr(self, 'analyzer') and self.analyzer and getattr(self.analyzer, 'freq_scale_mode', 'Log') == "Linear"
        for val in values:
            hz = float(val) if is_lin else (10.0 ** val)
            if hz >= 1000:
                k_val = hz / 1000.0
                strings.append(f"{k_val:.0f}k" if k_val.is_integer() else f"{k_val:.1f}k")
            else:
                strings.append(f"{hz:.0f}")
        return strings