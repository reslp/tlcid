"""Save/load serialization for TLCid analysis files."""

from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import json
import math
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, is_zipfile

from PyQt6.QtCore import QBuffer, QIODevice, QSignalBlocker
from PyQt6.QtGui import QColor, QPixmap

from gui.calibration import CALIBRATION_MODE_LINEAR, normalize_calibration_mode
from gui.reference_standards import get_reference_standard


MAX_MANIFEST_BYTES = 10 * 1024 * 1024
MAX_IMAGE_BYTES = 256 * 1024 * 1024


class AnalysisSerializer:
    """Serialize and apply TLCid analysis state."""

    @staticmethod
    def save_to_path(file_name: str, data: dict[str, Any], images: dict[int, QPixmap | None] | None = None) -> None:
        """Atomically save JSON and full-resolution, unannotated images as a ZIP."""
        source_version = _integer(data.get('version', 1), 'version')
        document = deepcopy(data)
        document['version'] = 3
        destination = Path(file_name)
        temporary_path = None
        try:
            with NamedTemporaryFile(dir=destination.parent, prefix=f'.{destination.name}.', suffix='.tmp', delete=False) as temporary:
                temporary_path = Path(temporary.name)
                with ZipFile(temporary, 'w', compression=ZIP_DEFLATED) as archive:
                    seen = set()
                    for plate in document['plates']:
                        idx = _integer(plate.get('id'), 'plate ID')
                        member = _image_member(idx)
                        if idx in seen:
                            raise ValueError(f'Duplicate plate ID: {idx}')
                        seen.add(idx)
                        if images is not None:
                            pixmap = images.get(idx)
                        else:
                            pixmap = _plate_pixmap(plate, source_version)
                        plate.pop('_image_data', None)
                        if pixmap is not None and not pixmap.isNull():
                            archive.writestr(member, _encode_pixmap(pixmap), compress_type=ZIP_STORED)
                            plate['image_path'] = member
                        elif plate.get('image_path'):
                            raise ValueError(f'Cannot embed the image for plate {idx + 1}: image unavailable. Load it before saving.')
                        else:
                            plate['image_path'] = None
                    manifest = json.dumps(document, indent=4, ensure_ascii=False, allow_nan=False).encode('utf-8')
                    if len(manifest) > MAX_MANIFEST_BYTES:
                        raise ValueError('Analysis metadata is too large.')
                    archive.writestr('analysis.json', manifest)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, destination)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def load_from_path(file_name: str) -> dict[str, Any]:
        if is_zipfile(file_name):
            return _load_archive(file_name)
        with open(file_name, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def from_window_state(window) -> dict[str, Any]:
        data = {
            "version": 2,
            "detection_method": window.detection_method,
            "detection_range": window.detection_range,
            "global_genus_filter": window.global_genus_filter,
            "global_family_filter": window.global_family_filter,
            "relative_rf_display": window.relative_rf_display,
            "allow_missing_rf_values": window.allow_missing_rf_values,
            "display_support_lines": window.display_support_lines,
            "display_rf_classes": window.display_rf_classes,
            "distinct_reference_sequences": window.distinct_reference_sequences,
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
                "note": sdata.get('note', ''),
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
    def apply_to_window(window, data: dict[str, Any]) -> list[str]:
        """Validate and stage everything first; return paths of unavailable images."""
        settings, samples, plates, missing_images = _prepare_analysis(window, data)
        previous = _snapshot_window(window, settings)

        # Block all load-related signals, preserving even previously blocked states.
        with ExitStack() as stack:
            for obj in _load_controls(window):
                stack.enter_context(QSignalBlocker(obj))
            try:
                _install_analysis(window, settings, samples, plates)
                _refresh_window(window)
            except Exception:
                _restore_window(window, previous)
                raise

        # Old editors must not update samples with reused IDs in the new analysis.
        old_editors = list(previous['window']['char_windows'].values())
        old_editors.append(getattr(window, 'species_window', None))
        for editor in old_editors:
            if editor is not None:
                try:
                    editor.close()
                    editor.deleteLater()
                except RuntimeError:
                    pass  # Qt may already have deleted a closed editor.
        window.species_window = None
        return missing_images


def _image_member(idx):
    if not 0 <= idx < 3:
        raise ValueError(f'Invalid plate ID: {idx}')
    return f"images/plate-{'abc'[idx]}.png"


def _encode_pixmap(pixmap):
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not pixmap.save(buffer, 'PNG'):
        raise ValueError('Could not encode a plate image.')
    encoded = bytes(buffer.data())
    if len(encoded) > MAX_IMAGE_BYTES:
        raise ValueError('Plate image is too large.')
    return encoded


def _read_member(archive, member, limit):
    if archive.getinfo(member).file_size > limit:
        raise ValueError(f'Archive entry is too large: {member}')
    return archive.read(member)


def _load_archive(file_name):
    with ZipFile(file_name) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Analysis archive contains duplicate entries.')
        data = json.loads(_read_member(archive, 'analysis.json', MAX_MANIFEST_BYTES))
        _require(data, dict, 'analysis')
        if _integer(data.get('version'), 'version') != 3:
            raise ValueError('Unsupported analysis archive version.')
        for plate in _require(data.get('plates'), list, 'plates'):
            _require(plate, dict, 'plate')
            member = plate.get('image_path')
            plate.pop('_image_data', None)
            if member is not None:
                expected = _image_member(_integer(plate.get('id'), 'plate ID'))
                if member != expected:
                    raise ValueError(f'Invalid embedded image path: {member}')
                # Read bytes only; archive entries are never extracted to disk.
                plate['_image_data'] = _read_member(archive, member, MAX_IMAGE_BYTES)
        return data


def _plate_pixmap(plate, version):
    path = plate.get('image_path')
    if not path:
        return None
    if version == 3:
        if path != _image_member(_integer(plate.get('id'), 'plate ID')):
            raise ValueError(f'Invalid embedded image path: {path}')
        encoded = _require(plate.get('_image_data'), bytes, 'embedded image')
        pixmap = QPixmap()
        if not pixmap.loadFromData(encoded):
            raise ValueError(f'Embedded image is unreadable: {path}')
        return pixmap
    pixmap = QPixmap(path)
    return None if pixmap.isNull() else pixmap


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


def _require(value, expected_type, field):
    if not isinstance(value, expected_type):
        raise ValueError(f"{field} must be a {expected_type.__name__}.")
    return value


def _integer(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{field} must be an integer.")
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{field} must be an integer.") from None


def _number(value, field, bounded=True):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{field} must be a finite number.")
    try:
        number = float(value)
    except (ValueError, OverflowError):
        raise ValueError(f"{field} must be a finite number.") from None
    if not math.isfinite(number) or (bounded and not 0.0 <= number <= 1.0):
        raise ValueError(f"{field} must be finite" + (" and between 0 and 1." if bounded else "."))
    return number


def _flag(data, key, default=False):
    return _require(data.get(key, default), bool, key)


def _prepare_settings(data, slot_count):
    method = data.get('detection_method', 'Range')
    if method not in ('Range', 'MSE'):
        raise ValueError("Unknown detection method.")
    legacy_mode = normalize_calibration_mode(data.get('calibration_mode', CALIBRATION_MODE_LINEAR))
    genus = data.get('global_genus_filter')
    if genus is not None:
        _require(genus, str, 'global_genus_filter')
    family = data.get('global_family_filter')
    if family is not None:
        _require(family, str, 'global_family_filter')
    settings = {
        'detection_method': method,
        'global_genus_filter': genus or None,
        'global_family_filter': family or None,
        'detection_range': _number(data.get('detection_range', 0.05), 'detection_range'),
        'relative_rf_display': _flag(data, 'relative_rf_display', True),
        'allow_missing_rf_values': _flag(data, 'allow_missing_rf_values'),
        'display_support_lines': _flag(data, 'display_support_lines', any(
            _flag(plate, 'show_support_lines') for plate in data['plates']
        )),
        'display_rf_classes': _flag(data, 'display_rf_classes'),
        'distinct_reference_sequences': _flag(data, 'distinct_reference_sequences'),
        'calibration_mode': legacy_mode,
        'plate_ranges': {i: 0.05 for i in range(slot_count)},
        'plate_calibration_modes': {i: legacy_mode for i in range(slot_count)},
    }
    for key in ('plate_ranges', 'plate_calibration_modes'):
        values = _require(data.get(key, {}), dict, key)
        seen = set()
        for raw_idx, value in values.items():
            idx = _integer(raw_idx, key)
            if not 0 <= idx < slot_count or idx in seen:
                raise ValueError(f"Invalid or duplicate plate ID in {key}: {raw_idx}")
            seen.add(idx)
            settings[key][idx] = (
                _number(value, key) if key == 'plate_ranges' else normalize_calibration_mode(value)
            )
    return settings


def _apply_slot_settings(window) -> None:
    for i, slot in enumerate(window.slots):
        slot.set_relative_rf_display(window.relative_rf_display)
        slot.set_range(window.plate_ranges.get(i, 0.05))
        slot.set_calibration_mode(window.get_plate_calibration_mode(i))


def _prepare_samples(window, data):
    samples = {}
    for sid_str, sdata in _require(data['samples'], dict, 'samples').items():
        sid = _integer(sid_str, 'sample ID')
        if sid in samples:
            raise ValueError(f"Duplicate sample ID: {sid}")
        _require(sdata, dict, f'sample {sid}')
        _require(sdata.get('name'), str, f'sample {sid} name')
        note = _require(sdata.get('note', ''), str, f'sample {sid} note')
        for key in ('assigned_name', 'filter_group', 'filter_genus', 'filter_family', 'filter_aft_vis', 'filter_aft_uv'):
            if sdata.get(key) is not None:
                _require(sdata[key], str, key)
        for key in ('show_on_plate', 'filter_vis', 'filter_uvs', 'filter_uvl', 'allow_missing_rf_values', 'is_reference'):
            _flag(sdata, key)
        font_size = _integer(sdata.get('font_size', 8), 'font_size')
        if not 1 <= font_size < 2**31:
            raise ValueError('font_size must be a positive Qt integer.')
        reference_rf = sdata.get('reference_rf')
        if reference_rf is not None:
            reference_rf = [
                None if value is None else _number(value, 'reference_rf', bounded=False)
                for value in _require(reference_rf, list, 'reference_rf')
            ]

        color = deserialize_qcolor(sdata.get("color"))
        if color is None:
            standard = get_reference_standard(sid)
            if standard is not None:
                color = standard.color()
            else:
                color = window.colors[(sid - 1) % len(window.colors)]

        samples[sid] = {
            'color': color,
            'name': sdata['name'],
            'assigned_name': sdata.get('assigned_name'),
            'note': note,
            'show_on_plate': sdata.get('show_on_plate', False),
            'filter_group': sdata.get('filter_group'),
            'filter_genus': sdata.get('filter_genus'),
            'filter_family': sdata.get('filter_family'),
            'filter_vis': sdata.get('filter_vis', False),
            'filter_uvs': sdata.get('filter_uvs', False),
            'filter_uvl': sdata.get('filter_uvl', False),
            'filter_aft_vis': sdata.get('filter_aft_vis'),
            'filter_aft_uv': sdata.get('filter_aft_uv'),
            'font_size': font_size,
            'allow_missing_rf_values': sdata.get('allow_missing_rf_values', False),
            'is_reference': sdata.get('is_reference', False),
            'reference_rf': reference_rf,
        }
    return samples


def _prepare_analysis(window, data):
    _require(data, dict, 'analysis')
    if 'samples' not in data or 'plates' not in data:
        raise ValueError('Analysis must contain samples and plates.')
    version = _integer(data.get('version', 1), 'version')
    if version not in (1, 2, 3):
        raise ValueError(f'Unsupported analysis version: {version}')
    for plate in _require(data['plates'], list, 'plates'):
        _require(plate, dict, 'plate')
    settings = _prepare_settings(data, len(window.slots))
    samples = _prepare_samples(window, data)
    plates = {}
    for plate in data['plates']:
        idx = _integer(plate.get('id'), 'plate ID')
        if not 0 <= idx < len(window.slots) or idx in plates:
            raise ValueError(f'Invalid or duplicate plate ID: {idx}')
        path = plate.get('image_path')
        if path is not None:
            _require(path, str, 'image_path')
        spots = _safe_spots(plate.get('spots', []))
        if any(spot['sample_id'] not in samples for spot in spots):
            raise ValueError(f'Plate {idx} contains a spot with an unknown sample ID.')
        plates[idx] = {
            'image_path': path or None,
            'start_line_y': _number(plate.get('start_line_y', 0.9), 'start_line_y'),
            'front_line_y': _number(plate.get('front_line_y', 0.1), 'front_line_y'),
            'show_support_lines': _flag(plate, 'show_support_lines', settings['display_support_lines']),
            'show_rf_classes': _flag(plate, 'show_rf_classes', settings['display_rf_classes']),
            'custom_lines': _safe_custom_lines(plate.get('custom_lines', [])),
            'spots': spots,
        }
        settings['plate_calibration_modes'][idx] = normalize_calibration_mode(
            plate.get('calibration_mode', settings['plate_calibration_modes'][idx])
        )

    # Decode images before touching the UI; installation never reads from disk.
    missing_images = []
    for source in data['plates']:
        plate = plates[_integer(source['id'], 'plate ID')]
        plate['pixmap'] = _plate_pixmap(source, version)
        if plate['image_path'] and plate['pixmap'] is None:
            missing_images.append(plate['image_path'])
    return settings, samples, plates, missing_images


def _safe_custom_lines(custom_lines) -> list[dict[str, Any]]:
    safe_custom_lines = []
    for line in _require(custom_lines, list, 'custom_lines'):
        _require(line, dict, 'custom line')
        orientation = line.get("orientation")
        if orientation not in ("horizontal", "vertical"):
            raise ValueError('Unknown custom line orientation.')
        safe_custom_lines.append({
            "orientation": orientation,
            "position": _number(line.get('position', 0.5), 'custom line position'),
        })
    return safe_custom_lines


def _safe_spots(spots) -> list[dict[str, Any]]:
    result = []
    for spot in _require(spots, list, 'spots'):
        _require(spot, dict, 'spot')
        result.append({
            'sample_id': _integer(spot.get('sample_id'), 'spot sample_id'),
            'x': _number(spot.get('x'), 'spot x'),
            'y': _number(spot.get('y'), 'spot y'),
        })
    return result


def _empty_label_state():
    return {
        '_original_pixmap': None,
        'start_line_y': 0.9, 'front_line_y': 0.1,
        'show_lines': False, 'show_support_lines': False,
        'show_start_line_adjust_hint': False,
        'spots': [], 'custom_lines': [],
        'global_colors': {}, 'global_names': {}, 'global_font_sizes': {},
        'highlighted_samples': set(), 'distinct_reference_ids': set(),
        'support_line_y_mapper': None, 'support_line_specs_provider': None,
        'custom_line_rf_label_provider': None,
        'adding_sample_mode': False, 'current_sample_id': None,
        'dragged_spot_index': None, 'dragged_line': None,
        'dragged_custom_line_index': None,
    }


def _set_attributes(obj, values):
    for name, value in values.items():
        setattr(obj, name, value)


def _slot_actions(slot):
    return (slot._action_support_lines, slot._action_rf_classes,
            slot._action_calibration_linear, slot._action_calibration_nearest)


def _mark_buttons(window):
    return [window.mark_substance_button, *window.reference_buttons.values()]


def _load_controls(window):
    controls = [window.range_main, window.results_table, *_mark_buttons(window)]
    for slot in window.slots:
        controls.extend([slot, slot.image_label, slot.range_spin, *_slot_actions(slot)])
    settings = getattr(window, 'settings_window', None)
    if settings is not None:
        controls.extend([
            settings, settings.method_combo, settings.range_spin,
            settings.relative_rf_checkbox, settings.allow_missing_rf_checkbox,
            settings.display_support_lines_checkbox, settings.display_rf_classes_checkbox,
            settings.distinct_reference_sequences_checkbox, settings.global_genus_combo,
            settings.global_family_combo,
        ])
    return controls


def _snapshot_window(window, settings):
    fields = [*settings, 'samples', 'next_sample_id', 'active_regular_marking_sid',
              'manual_selected_sid', 'char_windows', '_rf_classes_missing_popup_shown']
    state = {name: getattr(window, name) for name in fields}
    state['_prediction_hover_link_by_sid'] = getattr(window, '_prediction_hover_link_by_sid', {})
    return {
        'window': state,
        'slots': [{
            'image_path': slot.image_path,
            'label': {name: getattr(slot.image_label, name) for name in _empty_label_state()},
            'text': slot.image_label.text(),
            'cursor': slot.image_label.cursor(),
            'actions': [action.isChecked() for action in _slot_actions(slot)],
            'controls': [button.isEnabled() for button in (
                slot.export_button, slot.horizontal_line_button, slot.vertical_line_button
            )],
        } for slot in window.slots],
        'buttons': [(button.isChecked(), button.text(), button.styleSheet())
                    for button in _mark_buttons(window)],
    }


def _install_analysis(window, settings, samples, plates):
    _set_attributes(window, settings)
    window.samples = samples
    window.next_sample_id = max([0, *samples]) + 1
    window.active_regular_marking_sid = None
    window.manual_selected_sid = None
    window.char_windows = {}
    window._prediction_hover_link_by_sid = {}
    window._rf_classes_missing_popup_shown = False
    for button in _mark_buttons(window):
        button.setChecked(False)
        button.setStyleSheet('')
    window.mark_substance_button.setText('New Substance')
    for sid, button in window.reference_buttons.items():
        button.setText(get_reference_standard(sid).button_text)

    _apply_slot_settings(window)
    for idx, slot in enumerate(window.slots):
        label = slot.image_label
        _set_attributes(label, _empty_label_state())
        label.set_add_sample_mode(False)
        label.clear()
        label.setText('No Image Loaded')
        slot.image_path = None
        slot._action_support_lines.setChecked(False)
        slot._action_rf_classes.setChecked(False)
        slot.set_custom_line_controls_enabled(False)

        plate = plates.get(idx)
        if plate is None:
            continue
        slot.image_path = plate['image_path']
        if plate['pixmap'] is not None:
            slot.set_loaded_image(plate['pixmap'], plate['image_path'], show_start_line_adjust_hint=False)
        elif plate['image_path']:
            # Retain the saved path for resaving/recovery, never the previous image.
            label.setText('Image unavailable')
        for field in ('start_line_y', 'front_line_y', 'show_support_lines', 'custom_lines', 'spots'):
            setattr(label, field, plate[field])
        slot._action_support_lines.setChecked(plate['show_support_lines'])
        slot._action_rf_classes.setChecked(plate['show_rf_classes'])


def _refresh_window(window, restoring=False):
    window.update_detection_status_label()
    settings = getattr(window, 'settings_window', None)
    if settings is not None:
        settings.set_current_settings(
            window.detection_method, window.detection_range, window.relative_rf_display,
            window.allow_missing_rf_values, window.display_rf_classes, window.display_support_lines,
        )
        settings.set_current_appearance(window.distinct_reference_sequences)
        settings.set_genus_options(window.genus_to_substances, window.global_genus_filter)
        settings.set_family_options(window.family_to_substances, window.global_family_filter)
    color_map = {sid: sample['color'] for sid, sample in window.samples.items()}
    for slot in window.slots:
        slot.image_label.set_global_colors(color_map)
        slot.image_label.update()
    if not restoring:
        window.update_results_display()
        return

    # Rebuild the old table without pruning pending samples, stopping marking,
    # closing editors, or replacing the restored overlay providers.
    samples = window.samples
    window.samples = {sid: dict(sample) for sid, sample in samples.items()}
    try:
        aggregated = window._aggregate_spots()
        window._render_result_rows(aggregated, window._build_active_standards(aggregated))
        window._restore_manual_table_selection()
    finally:
        window.samples = samples


def _restore_window(window, previous):
    # Restore original in-memory images/state, even if their files no longer exist.
    _set_attributes(window, previous['window'])
    _apply_slot_settings(window)
    for slot, state in zip(window.slots, previous['slots']):
        slot.image_path = state['image_path']
        _set_attributes(slot.image_label, state['label'])
        slot.image_label.clear()
        slot.image_label.setText(state['text'])
        slot.image_label.update_display()
        slot.image_label.setCursor(state['cursor'])
        for action, checked in zip(_slot_actions(slot), state['actions']):
            action.setChecked(checked)
        for button, enabled in zip((slot.export_button, slot.horizontal_line_button, slot.vertical_line_button), state['controls']):
            button.setEnabled(enabled)
    for button, (checked, text, style) in zip(_mark_buttons(window), previous['buttons']):
        button.setChecked(checked)
        button.setText(text)
        button.setStyleSheet(style)
    _refresh_window(window, restoring=True)
