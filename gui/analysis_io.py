"""Save/load serialization for TLCid analysis files."""

from __future__ import annotations

import json
import os
from typing import Any

from PyQt6.QtGui import QColor, QPixmap

from gui.calibration import CALIBRATION_MODE_LINEAR, normalize_calibration_mode
from gui.reference_standards import get_reference_standard


class AnalysisSerializer:
    """Serialize and apply TLCid analysis state."""

    @staticmethod
    def save_to_path(file_name: str, data: dict[str, Any]) -> None:
        with open(file_name, 'w') as f:
            json.dump(data, f, indent=4)

    @staticmethod
    def load_from_path(file_name: str) -> dict[str, Any]:
        with open(file_name, 'r') as f:
            return json.load(f)

    @staticmethod
    def from_window_state(window) -> dict[str, Any]:
        data = {
            "version": 2,
            "detection_method": window.detection_method,
            "detection_range": window.detection_range,
            "relative_rf_display": window.relative_rf_display,
            "allow_missing_rf_values": window.allow_missing_rf_values,
            "display_support_lines": window.display_support_lines,
            "display_rf_classes": window.display_rf_classes,
            "plate_ranges": window.plate_ranges,
            "plate_calibration_modes": window.plate_calibration_modes,
            "samples": {},
            "plates": [],
        }

        for sid, sdata in window.samples.items():
            data["samples"][sid] = {
                "color": serialize_qcolor(sdata.get("color")),
                "name": sdata["name"],
                "assigned_name": sdata.get('assigned_name'),
                "show_on_plate": sdata.get('show_on_plate', False),
                "filter_group": sdata.get('filter_group'),
                "filter_genus": sdata.get('filter_genus'),
                "filter_family": sdata.get('filter_family'),
                "filter_vis": sdata.get('filter_vis', False),
                "filter_uvs": sdata.get('filter_uvs', False),
                "filter_uvl": sdata.get('filter_uvl', False),
                "filter_aft_vis": sdata.get('filter_aft_vis'),
                "filter_aft_uv": sdata.get('filter_aft_uv'),
                "font_size": sdata.get('font_size', 8),
                "allow_missing_rf_values": sdata.get('allow_missing_rf_values', False),
                "is_reference": sdata.get('is_reference', False),
                "reference_rf": sdata.get('reference_rf'),
            }

        for i, slot in enumerate(window.slots):
            data["plates"].append({
                "id": i,
                "image_path": slot.image_path,
                "start_line_y": slot.image_label.start_line_y,
                "front_line_y": slot.image_label.front_line_y,
                "show_support_lines": slot.image_label.show_support_lines,
                "show_rf_classes": slot.rf_classes_checked(),
                "calibration_mode": window.get_plate_calibration_mode(i),
                "custom_lines": slot.image_label.custom_lines,
                "spots": slot.image_label.spots,
            })

        return data

    @staticmethod
    def apply_to_window(window, data: dict[str, Any]) -> None:
        window.samples = {}
        _apply_detection_settings(window, data)
        window.update_detection_status_label()
        _apply_slot_settings(window)

        blocked_slots = []
        try:
            for slot in window.slots:
                slot.image_label.blockSignals(True)
                blocked_slots.append(slot)
                slot._action_support_lines.setChecked(False)
                slot.image_label.show_support_lines = False
                slot.image_label.custom_lines = []
                slot.set_custom_line_controls_enabled(False)

            window.next_sample_id = _restore_samples(window, data)
            _restore_plates(window, data)
        finally:
            for slot in blocked_slots:
                slot.image_label.blockSignals(False)

        color_map = {k: v['color'] for k, v in window.samples.items()}
        for slot in window.slots:
            slot.image_label.set_global_colors(color_map)
            slot.image_label.update()

        window.update_results_display()
        window._update_reference_button_colors(_plate_presence_from_slots(window.slots))


def serialize_qcolor(color) -> str | None:
    if isinstance(color, QColor) and color.isValid():
        return color.name(QColor.NameFormat.HexArgb)
    return None


def deserialize_qcolor(value) -> QColor | None:
    color = QColor()
    if isinstance(value, str):
        color = QColor(value)
    elif isinstance(value, (tuple, list)) and len(value) >= 3:
        color = QColor(int(value[0]), int(value[1]), int(value[2]))
    elif isinstance(value, QColor):
        color = QColor(value)
    return color if color.isValid() else None


def _apply_detection_settings(window, data: dict[str, Any]) -> None:
    if "detection_method" in data:
        window.detection_method = data["detection_method"]
    if "detection_range" in data:
        window.detection_range = float(data["detection_range"])
    if "relative_rf_display" in data:
        window.relative_rf_display = bool(data["relative_rf_display"])
    if "allow_missing_rf_values" in data:
        window.allow_missing_rf_values = bool(data["allow_missing_rf_values"])
    if "display_support_lines" in data:
        window.display_support_lines = bool(data["display_support_lines"])
    else:
        window.display_support_lines = any(
            bool(plate.get("show_support_lines", False))
            for plate in data.get("plates", [])
        )
    if "display_rf_classes" in data:
        window.display_rf_classes = bool(data["display_rf_classes"])
    if "plate_ranges" in data:
        window.plate_ranges = {int(k): v for k, v in data["plate_ranges"].items()}

    legacy_calibration_mode = normalize_calibration_mode(data.get("calibration_mode", CALIBRATION_MODE_LINEAR))
    window.calibration_mode = legacy_calibration_mode
    if "plate_calibration_modes" in data:
        window.plate_calibration_modes = {
            int(k): normalize_calibration_mode(v)
            for k, v in data["plate_calibration_modes"].items()
        }
    else:
        window.plate_calibration_modes = {
            i: legacy_calibration_mode for i in range(len(window.slots))
        }


def _apply_slot_settings(window) -> None:
    for i, slot in enumerate(window.slots):
        slot.set_relative_rf_display(window.relative_rf_display)
        slot.set_range(window.plate_ranges.get(i, 0.05))
        slot.set_calibration_mode(window.get_plate_calibration_mode(i))


def _restore_samples(window, data: dict[str, Any]) -> int:
    max_sid = 0
    for sid_str, sdata in data.get("samples", {}).items():
        sid = int(sid_str)
        if sid > max_sid:
            max_sid = sid

        color = deserialize_qcolor(sdata.get("color"))
        if color is None:
            standard = get_reference_standard(sid)
            if standard is not None:
                color = standard.color()
            else:
                color = window.colors[(sid - 1) % len(window.colors)]

        window.samples[sid] = {
            'color': color,
            'name': sdata['name'],
            'assigned_name': sdata.get('assigned_name'),
            'show_on_plate': sdata.get('show_on_plate', False),
            'filter_group': sdata.get('filter_group'),
            'filter_genus': sdata.get('filter_genus'),
            'filter_family': sdata.get('filter_family'),
            'filter_vis': sdata.get('filter_vis', False),
            'filter_uvs': sdata.get('filter_uvs', False),
            'filter_uvl': sdata.get('filter_uvl', False),
            'filter_aft_vis': sdata.get('filter_aft_vis'),
            'filter_aft_uv': sdata.get('filter_aft_uv'),
            'font_size': sdata.get('font_size', 8),
            'allow_missing_rf_values': sdata.get('allow_missing_rf_values', False),
            'is_reference': sdata.get('is_reference', False),
            'reference_rf': sdata.get('reference_rf'),
        }
    return max_sid + 1


def _restore_plates(window, data: dict[str, Any]) -> None:
    for plate_info in data.get("plates", []):
        idx = plate_info.get("id")
        if idx is None or not (0 <= idx < len(window.slots)):
            continue

        slot = window.slots[idx]
        path = plate_info.get("image_path")
        start_y = plate_info.get("start_line_y", 0.9)
        front_y = plate_info.get("front_line_y", 0.1)
        show_support_lines = bool(plate_info.get("show_support_lines", window.display_support_lines))
        show_rf_classes = bool(plate_info.get("show_rf_classes", window.display_rf_classes))
        calibration_mode = normalize_calibration_mode(
            plate_info.get("calibration_mode", window.get_plate_calibration_mode(idx))
        )

        if path and os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                slot.set_loaded_image(pixmap, path, show_start_line_adjust_hint=False)

        slot.image_label.start_line_y = start_y
        slot.image_label.front_line_y = front_y
        slot._action_support_lines.setChecked(show_support_lines)
        slot._action_rf_classes.setChecked(show_rf_classes)
        slot.set_calibration_mode(calibration_mode)
        window.plate_calibration_modes[idx] = calibration_mode
        slot.image_label.show_support_lines = show_support_lines
        slot.image_label.custom_lines = _safe_custom_lines(plate_info.get("custom_lines", []))
        slot.image_label.spots = _safe_spots(plate_info.get("spots", []))


def _safe_custom_lines(custom_lines) -> list[dict[str, Any]]:
    safe_custom_lines = []
    for line in custom_lines:
        orientation = line.get("orientation")
        if orientation not in {"horizontal", "vertical"}:
            continue
        try:
            position = float(line.get("position", 0.5))
        except (TypeError, ValueError):
            position = 0.5
        safe_custom_lines.append({
            "orientation": orientation,
            "position": max(0.0, min(1.0, position)),
        })
    return safe_custom_lines


def _safe_spots(spots) -> list[dict[str, Any]]:
    return [
        {
            'sample_id': int(spot['sample_id']),
            'x': spot['x'],
            'y': spot['y'],
        }
        for spot in spots
    ]


def _plate_presence_from_slots(slots) -> dict[int, dict[int, list[int]]]:
    aggregated = {}
    for i, slot in enumerate(slots):
        for spot in slot.image_label.spots:
            sid = spot['sample_id']
            aggregated.setdefault(sid, {}).setdefault(i, []).append(0)
    return aggregated
