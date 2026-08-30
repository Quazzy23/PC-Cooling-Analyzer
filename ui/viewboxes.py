"""
Единый модуль ViewBox проекта (PyQt6 + PyQtGraph) с нулевым дублированием:
- BaseInteractiveViewBox: ЕДИНСТВЕННЫЙ обработчик Pan (СКМ), Zoom (Alt/Shift), Scroll (Wheel),
  ЛКМ-курсора (Seek/Scrub), ПКМ-выделения (1D / 2D) и нативного Hover-трекинга (hoverEvent)
- CleanTimeViewBox: Графики датчиков (синхронные зоны P1/P2 + зум шкал по кнопке M)
- FFTFilterViewBox: Live FFT спектр (1D полоса частот)
- SpectrogramTimelineViewBox: 2D-Спектрограмма (2D бокс Время x Частота)
- OverlayViewBox: Пассивный оверлей для независимых осей Y
"""
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from core.defaults import AUDIO_PROFILE
from ui.styles import create_clean_region, create_clean_2d_rect_item


def clamp_rigid_range(cur_range, min_limit, max_limit):
    """Ограничивает диапазон без изменения масштаба (span)"""
    span = cur_range[1] - cur_range[0]
    total_allowed = max_limit - min_limit

    if span >= total_allowed:
        return min_limit, max_limit

    clamped_min = max(min_limit, cur_range[0])
    clamped_max = clamped_min + span
    if clamped_max >= max_limit:
        clamped_max = max_limit
        clamped_min = max(min_limit, max_limit - span)

    return clamped_min, clamped_max


class BaseInteractiveViewBox(pg.ViewBox):
    """
    Базовый интерактивный ViewBox:
    Содержит 100% логики мыши (СКМ Pan, Alt/Shift Zoom, Wheel Scroll, ЛКМ Seek, ПКМ Drag, Hover Telemetry)
    """
    def __init__(self, analyzer_ref=None, enable_time_seek=False, is_2d_selection=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.analyzer = analyzer_ref
        self.enable_time_seek = enable_time_seek
        self.is_2d_selection = is_2d_selection

        self.panning_data = None
        self.temp_selection_item = None
        self.setMouseMode(pg.ViewBox.RectMode)

    # 1. Лимиты осей
    def get_x_limits(self):
        return 0.0, float(getattr(self.analyzer, 'total_duration', 100.0))

    def get_y_limits(self):
        return 0.0, 100.0

    def clamp_view(self):
        min_x_lim, max_x_lim = self.get_x_limits()
        min_y_lim, max_y_lim = self.get_y_limits()
        new_x_min, new_x_max = clamp_rigid_range(self.viewRange()[0], min_x_lim, max_x_lim)
        new_y_min, new_y_max = clamp_rigid_range(self.viewRange()[1], min_y_lim, max_y_lim)
        self.setRange(xRange=[new_x_min, new_x_max], yRange=[new_y_min, new_y_max], padding=0)

    # 2. Нативное отслеживание движения мыши (Hover)
    def hoverEvent(self, ev):
        if ev.isExit():
            return
        if hasattr(self.analyzer, 'lbl_telemetry_status') and self.analyzer.lbl_telemetry_status is not None:
            # Преобразуем пиксели мыши в реальные координаты графика
            view_pos = self.mapSceneToView(ev.scenePos())
            top_time, coords_str = self.get_status_telemetry(view_pos, ev.scenePos())
            
            if coords_str is not None:
                if top_time is not None:
                    # 2-строчный вид для analyzer.py (с временем в правом верхнем углу)
                    formatted_text = f"""
                        <table width='100%' cellspacing='0' cellpadding='0' style='color: #AAAAAA; font-size: 8.5pt;'>
                            <tr><td align='right'><b>{top_time}</b></td></tr>
                            <tr><td align='left'>{coords_str}</td></tr>
                        </table>
                    """
                else:
                    # 1-строчный чистый вид для audio_analyzer.py (без верхней строки)
                    formatted_text = f"<span style='color: #AAAAAA; font-size: 8.5pt;'><b>{coords_str}</b></span>"
                self.analyzer.lbl_telemetry_status.setText(formatted_text)

    def get_status_telemetry(self, view_pos, scene_pos):
        """Возвращает (top_time_str, coords_str) для нижней строки статуса"""
        return None, None

    # 3. Единое панорамирование (СКМ)
    def mousePressEvent(self, ev):
        if ev.button() == QtCore.Qt.MouseButton.MiddleButton:
            ev.accept()
            self.panning_data = {
                'start_pos': ev.scenePos(),
                'start_x_range': self.viewRange()[0],
                'start_y_range': self.viewRange()[1],
                'overlay_ranges': self.get_active_overlay_ranges()
            }
        else:
            super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == QtCore.Qt.MouseButton.MiddleButton:
            ev.accept()
            self.panning_data = None
        else:
            super().mouseReleaseEvent(ev)

    def mouseMoveEvent(self, ev):
        if self.panning_data is not None:
            ev.accept()
            delta = ev.scenePos() - self.panning_data['start_pos']
            
            vr_x = self.panning_data['start_x_range']
            span_x = vr_x[1] - vr_x[0]
            dx = -delta.x() / max(1, self.width()) * span_x
            self.setXRange(vr_x[0] + dx, vr_x[0] + dx + span_x, padding=0)

            vr_y = self.panning_data['start_y_range']
            span_y = vr_y[1] - vr_y[0]
            dy = (delta.y() / max(1, self.height())) * span_y
            self.setYRange(vr_y[0] + dy, vr_y[0] + dy + span_y, padding=0)

            self.pan_overlays(delta.y(), max(1, self.height()))
            self.clamp_view()
        else:
            super().mouseMoveEvent(ev)

    # 4. Единое колесо мыши
    def wheelEvent(self, ev, axis=None):
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        delta = ev.delta()
        scale = 0.82 if delta > 0 else 1.22
        mouse_scene = ev.scenePos()

        if bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
            self.scaleBy(x=scale, y=1.0, center=self.mapSceneToView(mouse_scene))
            self.clamp_view()
            ev.accept()
        elif bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier):
            self.zoom_y(scale, mouse_scene)
            self.clamp_view()
            ev.accept()
        else:
            vr_x = self.viewRange()[0]
            span_x = vr_x[1] - vr_x[0]
            min_x_lim, max_x_lim = self.get_x_limits()
            if span_x < (max_x_lim - min_x_lim - 0.01):
                shift_x = span_x * 0.04 * (-1 if delta > 0 else 1)
                self.setXRange(vr_x[0] + shift_x, vr_x[1] + shift_x, padding=0)
                self.clamp_view()
            ev.accept()

    # 5. Единые клики
    def mouseClickEvent(self, ev):
        if self.enable_time_seek and ev.button() == QtCore.Qt.MouseButton.LeftButton:
            pos = self.mapToView(ev.pos())
            t = max(0.0, min(float(getattr(self.analyzer, 'total_duration', 100.0)), pos.x()))
            self.analyzer.seek_to_time(t)
            ev.accept()
        elif ev.button() == QtCore.Qt.MouseButton.RightButton:
            ev.accept()
            self.on_right_click(self.mapToView(ev.pos()))
        else:
            ev.ignore()

    # 6. Единый Драг
    def mouseDragEvent(self, ev, axis=None):
        if self.enable_time_seek and ev.button() == QtCore.Qt.MouseButton.LeftButton:
            ev.accept()
            pos = self.mapToView(ev.pos())
            t = max(0.0, min(float(getattr(self.analyzer, 'total_duration', 100.0)), pos.x()))
            self.analyzer.seek_to_time(t)

        elif ev.button() == QtCore.Qt.MouseButton.RightButton:
            ev.accept()
            modifiers = QtWidgets.QApplication.keyboardModifiers()
            is_ctrl = bool(modifiers & QtCore.Qt.KeyboardModifier.ControlModifier)

            p1 = self.mapToView(ev.buttonDownPos())
            p2 = self.mapToView(ev.pos())

            x_min, x_max = min(p1.x(), p2.x()), max(p1.x(), p2.x())
            y_min, y_max = min(p1.y(), p2.y()), max(p1.y(), p2.y())

            if ev.isStart():
                if not is_ctrl:
                    self.clear_existing_regions()
                self.start_temp_selection(x_min, y_min)

            if ev.isFinish():
                self.finish_temp_selection(x_min, x_max, y_min, y_max)
            else:
                self.update_temp_selection(x_min, x_max, y_min, y_max)
        else:
            ev.ignore()

    # Вспомогательные хуки
    def zoom_y(self, scale, mouse_scene):
        self.scaleBy(x=1.0, y=scale, center=self.mapSceneToView(mouse_scene))

    def get_active_overlay_ranges(self): return {}
    def pan_overlays(self, delta_y_pixels, height): pass

    def clear_existing_regions(self):
        if hasattr(self.analyzer, 'clear_all_filters'): self.analyzer.clear_all_filters()
        elif hasattr(self.analyzer, 'clear_all_time_regions'): self.analyzer.clear_all_time_regions()

    def start_temp_selection(self, x, y):
        if self.is_2d_selection:
            self.temp_selection_item = create_clean_2d_rect_item(QtCore.QRectF(0, 0, 0, 0))
        else:
            self.temp_selection_item = create_clean_region(x, x)
        self.addItem(self.temp_selection_item, ignoreBounds=True)

    def update_temp_selection(self, x_min, x_max, y_min, y_max):
        if self.temp_selection_item is not None:
            if self.is_2d_selection:
                self.temp_selection_item.setRect(QtCore.QRectF(x_min, y_min, x_max - x_min, y_max - y_min))
            else:
                self.temp_selection_item.setRegion([x_min, x_max])

    def finish_temp_selection(self, x_min, x_max, y_min, y_max):
        if self.temp_selection_item is not None:
            self.removeItem(self.temp_selection_item)
            self.temp_selection_item = None
            self.on_region_selected(x_min, x_max, y_min, y_max)

    def on_region_selected(self, x_min, x_max, y_min, y_max): pass
    def on_right_click(self, view_pos): pass


# =======================================================
#               СПЕЦИАЛИЗИРОВАННЫЕ КЛАССЫ
# =======================================================

class OverlayViewBox(pg.ViewBox):
    """Пассивный оверлейный ViewBox для наложения множества независимых шкал Y"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseEnabled(x=False, y=False)
        self.setMenuEnabled(False)
    def mouseDragEvent(self, ev, axis=None): ev.ignore()
    def mouseClickEvent(self, ev): ev.ignore()
    def wheelEvent(self, ev, axis=None): ev.ignore()
    def hoverEvent(self, ev): pass


class CleanTimeViewBox(BaseInteractiveViewBox):
    """Графики датчиков ПК"""
    def __init__(self, analyzer_ref=None, plot_widget_ref=None, *args, **kwargs):
        super().__init__(analyzer_ref=analyzer_ref, enable_time_seek=True, is_2d_selection=False, *args, **kwargs)
        self.plot_widget = plot_widget_ref
        self.temp_region_p2 = None

    def get_status_telemetry(self, view_pos, scene_pos):
        panel_label = "P1" if self.plot_widget == self.analyzer.p1_plot else "P2"
        target_sensors = self.analyzer.p1_sensors if panel_label == "P1" else self.analyzer.p2_sensors
        values_list = []

        for s in target_sensors:
            k = s["key"]
            if k in self.analyzer.sensor_checkboxes and self.analyzer.sensor_checkboxes[k].isChecked():
                if k in self.analyzer.viewboxes_map:
                    vb = self.analyzer.viewboxes_map[k]
                    val = vb.mapSceneToView(scene_pos).y()
                    if "volt" in k.lower(): val_str = f"{val:.3f}"
                    elif "RPM" in s["label"]: val_str = f"{val:.0f}"
                    else: val_str = f"{val:.1f}"
                    values_list.append(val_str)

        sensors_str = f"{panel_label}: {' | '.join(values_list)}" if values_list else f"{panel_label}: —"
        return f"{view_pos.x():.1f}", sensors_str

    def get_active_overlay_ranges(self):
        return {k: vb.viewRange()[1] for k, vb in self.analyzer.viewboxes_map.items() if self.analyzer.sensor_move_active.get(k, False)}

    def pan_overlays(self, delta_y_pixels, height):
        for k, start_vr_y in self.panning_data.get('overlay_ranges', {}).items():
            if k in self.analyzer.viewboxes_map:
                vb = self.analyzer.viewboxes_map[k]
                span_y = start_vr_y[1] - start_vr_y[0]
                dy = (delta_y_pixels / height) * span_y
                new_min_y, new_max_y = start_vr_y[0] + dy, start_vr_y[1] + dy

                if k in self.analyzer.sensor_y_limits:
                    orig_min, orig_max = self.analyzer.sensor_y_limits[k]
                    if new_min_y < orig_min: new_min_y = orig_min; new_max_y = orig_min + span_y
                    if new_max_y > orig_max: new_max_y = orig_max; new_min_y = orig_max - span_y

                vb.setYRange(new_min_y, new_max_y, padding=0)
                cur_side = self.analyzer.sensor_sides.get(k, "left")
                if k in self.analyzer.axes_map:
                    ax = self.analyzer.axes_map[k][cur_side]
                    ax.picture = None
                    ax.setRange(new_min_y, new_max_y)
                    ax.update()

    def zoom_y(self, scale, mouse_scene):
        target_sensors = self.analyzer.p1_sensors if self.plot_widget == self.analyzer.p1_plot else self.analyzer.p2_sensors
        target_keys = {s["key"] for s in target_sensors}

        for k, vb in self.analyzer.viewboxes_map.items():
            if k in target_keys and self.analyzer.sensor_move_active.get(k, False):
                vr_y = vb.viewRange()[1]
                mouse_y = vb.mapSceneToView(mouse_scene).y()
                new_min_y = mouse_y - (mouse_y - vr_y[0]) * scale
                new_max_y = mouse_y + (vr_y[1] - mouse_y) * scale

                if k in self.analyzer.sensor_y_limits:
                    orig_min, orig_max = self.analyzer.sensor_y_limits[k]
                    if new_min_y < orig_min: new_min_y = orig_min
                    if new_max_y > orig_max: new_max_y = orig_max
                    if new_min_y >= new_max_y: continue

                vb.setYRange(new_min_y, new_max_y, padding=0)
                cur_side = self.analyzer.sensor_sides.get(k, "left")
                if k in self.analyzer.axes_map:
                    ax = self.analyzer.axes_map[k][cur_side]
                    ax.picture = None
                    ax.setRange(new_min_y, new_max_y)
                    ax.update()

    def start_temp_selection(self, x, y):
        # Создаем ровно по одной рамке на P1 и P2
        self.temp_selection_item = create_clean_region(x, x)
        self.temp_region_p2 = create_clean_region(x, x)
        if hasattr(self.analyzer, 'p1_plot'):
            self.analyzer.p1_plot.addItem(self.temp_selection_item, ignoreBounds=True)
        if hasattr(self.analyzer, 'p2_plot'):
            self.analyzer.p2_plot.addItem(self.temp_region_p2, ignoreBounds=True)

    def update_temp_selection(self, x_min, x_max, y_min, y_max):
        if self.temp_selection_item is not None:
            self.temp_selection_item.setRegion([x_min, x_max])
        if self.temp_region_p2 is not None:
            self.temp_region_p2.setRegion([x_min, x_max])

    def finish_temp_selection(self, x_min, x_max, y_min, y_max):
        if self.temp_selection_item is not None:
            if hasattr(self.analyzer, 'p1_plot'):
                self.analyzer.p1_plot.removeItem(self.temp_selection_item)
            self.temp_selection_item = None
        if self.temp_region_p2 is not None:
            if hasattr(self.analyzer, 'p2_plot'):
                self.analyzer.p2_plot.removeItem(self.temp_region_p2)
            self.temp_region_p2 = None
        self.on_region_selected(x_min, x_max, y_min, y_max)

    def on_region_selected(self, x_min, x_max, y_min, y_max):
        if (x_max - x_min) > 0.1:
            self.analyzer.add_time_region(x_min, x_max)

    def on_right_click(self, view_pos):
        self.analyzer.handle_right_click_on_timeline(view_pos.x())


class FFTFilterViewBox(BaseInteractiveViewBox):
    """Live FFT Спектр"""
    def __init__(self, analyzer_ref=None, *args, **kwargs):
        super().__init__(analyzer_ref=analyzer_ref, enable_time_seek=False, is_2d_selection=False, *args, **kwargs)

    def get_x_limits(self):
        f_min = AUDIO_PROFILE["limit_freq_min"]
        nyq = float(getattr(self.analyzer.engine, 'sample_rate', 48000) / 2.0)
        if hasattr(self.analyzer, 'freq_scale_mode') and self.analyzer.freq_scale_mode == "Log":
            return np.log10(f_min), np.log10(nyq)
        return f_min, nyq

    def get_y_limits(self):
        ymin = float(self.analyzer.spin_ymin.value()) if hasattr(self.analyzer, 'spin_ymin') else AUDIO_PROFILE["limit_db_min"]
        ymax = float(self.analyzer.spin_ymax.value()) if hasattr(self.analyzer, 'spin_ymax') else AUDIO_PROFILE["limit_db_max"]
        return ymin, ymax

    def get_status_telemetry(self, view_pos, scene_pos):
        is_log = (getattr(self.analyzer, 'freq_scale_mode', 'Log') == "Log")
        freq = (10.0 ** view_pos.x()) if is_log else view_pos.x()
        freq_clamped = max(AUDIO_PROFILE["limit_freq_min"], min(AUDIO_PROFILE["limit_freq_max"], freq))
        db_val = view_pos.y()
        cur_t = self.analyzer.engine.current_sample_idx / self.analyzer.engine.sample_rate
        # Возвращаем None первым параметром, чтобы не было верхней строки
        return None, f"P1: {freq_clamped:.0f} | {db_val:.1f} | {cur_t:.1f}"

    def on_region_selected(self, x_min, x_max, y_min, y_max):
        if (x_max - x_min) > 0.01:
            is_log = hasattr(self.analyzer, 'freq_scale_mode') and self.analyzer.freq_scale_mode == "Log"
            f_min = (10.0 ** x_min) if is_log else x_min
            f_max = (10.0 ** x_max) if is_log else x_max
            self.analyzer.add_filter_from_fft(f_min, f_max, x_min, x_max)

    def on_right_click(self, view_pos):
        is_log = hasattr(self.analyzer, 'freq_scale_mode') and self.analyzer.freq_scale_mode == "Log"
        f_click = (10.0 ** view_pos.x()) if is_log else view_pos.x()
        self.analyzer.remove_filter_at_pos(t_click=None, f_click=f_click, is_fft=True)


class SpectrogramTimelineViewBox(BaseInteractiveViewBox):
    """2D-Спектрограмма"""
    def __init__(self, analyzer_ref=None, *args, **kwargs):
        super().__init__(analyzer_ref=analyzer_ref, enable_time_seek=True, is_2d_selection=True, *args, **kwargs)

    def get_y_limits(self):
        nyq = float(getattr(self.analyzer.engine, 'sample_rate', 48000) / 2.0)
        return AUDIO_PROFILE["limit_freq_min"], nyq

    def get_status_telemetry(self, view_pos, scene_pos):
        t_mouse = max(0.0, min(self.analyzer.total_duration, view_pos.x()))
        freq_mouse = max(AUDIO_PROFILE["limit_freq_min"], min(AUDIO_PROFILE["limit_freq_max"], view_pos.y()))
        db_at_point = self.analyzer.get_spec_db_at(t_mouse, freq_mouse)
        # Возвращаем None первым параметром, чтобы не было верхней строки
        return None, f"P2: {t_mouse:.1f} | {freq_mouse:.0f} | {db_at_point:.1f}"

    def on_region_selected(self, x_min, x_max, y_min, y_max):
        if (x_max - x_min) > 0.05 and (y_max - y_min) > 20:
            self.analyzer.add_2d_spectrogram_filter(x_min, x_max, y_min, y_max)

    def on_right_click(self, view_pos):
        self.analyzer.remove_filter_at_pos(t_click=view_pos.x(), f_click=view_pos.y(), is_fft=False)