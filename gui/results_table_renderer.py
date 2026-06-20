"""Result-table rendering for TLCid."""

from __future__ import annotations

import html
from urllib.parse import quote

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel, QPushButton, QCheckBox, QHBoxLayout, QWidget, QTableWidgetItem

from gui.calibration import calibrate_spot
from gui.reference_standards import REFERENCE_STANDARD_IDS


class SortableTableWidgetItem(QTableWidgetItem):
    """QTableWidgetItem that sorts by a stored underlying value when available."""

    def __lt__(self, other):
        left_value = self.data(Qt.ItemDataRole.UserRole)
        right_value = other.data(Qt.ItemDataRole.UserRole) if other is not None else None
        if left_value is not None and right_value is not None:
            return left_value < right_value
        return super().__lt__(other)


class ResultsTableRenderer:
    """Render aggregated sample results into the main results table."""

    def __init__(self, table, window):
        self.table = table
        self.window = window

    def render(self, aggregated, active_standards):
        window = self.window
        table = self.table

        v_scroll = table.verticalScrollBar().value()
        h_scroll = table.horizontalScrollBar().value()
        header = table.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        table.setSortingEnabled(False)

        table.setRowCount(0)
        sorted_ids = sorted(aggregated.keys())

        window._safe_print("=" * 80)
        window._safe_print("SUBSTANCE PREDICTIONS")
        window._safe_print("=" * 80)

        for sid in sorted_ids:
            if sid not in window.samples:
                continue

            current_row = table.rowCount()
            table.insertRow(current_row)

            self._render_color_cell(current_row, sid)
            self._render_name_cell(current_row, sid)

            prediction_input, calibration_info = self._render_plate_cells(
                current_row,
                sid,
                aggregated[sid],
                active_standards,
            )
            self._debug_print_sample_calibration(sid, calibration_info)

            matches, current_filter, current_genus, current_family = self._predict_matches(sid, prediction_input)
            self._render_prediction_cell(current_row, sid, matches, current_filter, current_genus, current_family)
            self._render_reference_cell(current_row, sid, aggregated)
            self._render_all_results_cell(current_row, sid, matches, prediction_input)

        table.setSortingEnabled(True)
        if sort_column >= 0:
            table.sortItems(sort_column, sort_order)
        table.verticalScrollBar().setValue(v_scroll)
        table.horizontalScrollBar().setValue(h_scroll)

        window._safe_print("=" * 80)
        window._safe_print(f"PREDICTION COMPLETE: Processed {len([sid for sid in sorted_ids if sid > 0])} substances")
        window._safe_print("=" * 80)
        window._safe_print()

    def _render_color_cell(self, row, sid):
        color_item = QTableWidgetItem()
        color_item.setBackground(self.window.samples[sid]['color'])
        color_item.setData(Qt.ItemDataRole.UserRole, sid)
        color_item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.table.setItem(row, self.window.RESULTS_COL_COLOR, color_item)

    def _render_name_cell(self, row, sid):
        name_text = self.window.samples[sid].get('assigned_name')
        if not name_text:
            name_text = self.window.samples[sid]['name']

        name_item = SortableTableWidgetItem(name_text)
        name_item.setData(Qt.ItemDataRole.UserRole, name_text.casefold())
        name_item.setData(Qt.ItemDataRole.UserRole + 1, sid)
        name_item.setForeground(QColor("steelblue"))
        name_item.setToolTip("Click to edit this substance; right-click to remove it")
        self.table.setItem(row, self.window.RESULTS_COL_SUBSTANCE, name_item)

    def _render_plate_cells(self, row, sid, plate_data, active_standards):
        prediction_input = {}
        calibration_info = []

        for plate_idx, label in enumerate(self.window.plate_labels):
            col_idx = self.window.RESULTS_COL_PLATE_A + plate_idx
            val_str = "-"
            sort_value = float("inf")

            if plate_idx in plate_data:
                raw_val = plate_data[plate_idx][0]
                standards = active_standards.get(plate_idx, [])
                calibration_mode = self.window.get_plate_calibration_mode(plate_idx)
                calibration = calibrate_spot(
                    raw_val,
                    standards,
                    calibration_mode,
                    lambda rf_value, plate_idx=plate_idx: self.window._reference_name_for_standard_value(plate_idx, rf_value),
                )
                corrected_val = calibration.corrected
                calibration_info.append({
                    'plate': label,
                    'raw': calibration.raw,
                    'corrected': calibration.corrected,
                    'standards': list(calibration.used_standards),
                    'mode': calibration.mode,
                })
                prediction_input[plate_idx] = corrected_val
                val_str = self.window.format_rf_value(corrected_val)
                sort_value = corrected_val

            item = SortableTableWidgetItem(val_str)
            item.setData(Qt.ItemDataRole.UserRole, sort_value)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, col_idx, item)

        return prediction_input, calibration_info

    def _debug_print_sample_calibration(self, sid, calibration_info):
        if sid <= 0 or not calibration_info:
            return

        window = self.window
        window._safe_print(f"\nSubstance: {window.samples[sid].get('assigned_name') or window.samples[sid]['name']}")
        window._safe_print("-" * 80)
        for cal in calibration_info:
            window._safe_print(
                f"  Plate {cal['plate']}: Rf raw={cal['raw']:.3f} -> "
                f"corrected={cal['corrected']:.3f} (mode: {cal['mode']})"
            )
            if cal['standards']:
                if len(cal['standards']) == 1:
                    window._safe_print(f"    Rf correction using reference: {cal['standards'][0]}")
                else:
                    window._safe_print(f"    Rf correction using references: {' and '.join(cal['standards'])}")
                    window._safe_print("    (Interpolation between calibration points)")
            else:
                window._safe_print("    No Rf correction applied (no reference standards on this plate)")
        window._safe_print("-" * 80)

    def _predict_matches(self, sid, prediction_input):
        window = self.window
        current_filter = window.samples[sid].get('filter_group')
        current_genus = window.samples[sid].get('filter_genus')
        current_family = window.samples[sid].get('filter_family')
        matches = []

        if sid > 0 and prediction_input:
            f_vis = window.samples[sid].get('filter_vis', False)
            f_uvs = window.samples[sid].get('filter_uvs', False)
            f_uvl = window.samples[sid].get('filter_uvl', False)
            f_aft_vis = window.samples[sid].get('filter_aft_vis')
            f_aft_uv = window.samples[sid].get('filter_aft_uv')

            matches = window.predict_matches(
                prediction_input,
                filter_group=current_filter,
                filter_genus=current_genus,
                filter_family=current_family,
                filter_vis=f_vis,
                filter_uvs=f_uvs,
                filter_uvl=f_uvl,
                filter_aft_vis=f_aft_vis,
                filter_aft_uv=f_aft_uv,
                allow_missing_rf_values=window.sample_allows_missing_rf_values(sid),
            )

            window._safe_print(f"  Predictions ({len(matches)} match{'es' if len(matches) != 1 else ''}):")
            if matches:
                for i, (score, name) in enumerate(matches[:10], 1):
                    window._safe_print(f"    {i}. {name} (score: {score:.6f})")
                if len(matches) > 10:
                    window._safe_print(f"    ... and {len(matches) - 10} more")
            else:
                window._safe_print("    No matches found")

        return matches, current_filter, current_genus, current_family

    def _filter_tags(self, sid, current_filter, current_genus, current_family):
        sample = self.window.samples[sid]
        filter_tags = ""
        current_filter = current_filter or ""
        current_genus = current_genus or ""
        current_family = current_family or ""
        f_vis = bool(sample.get('filter_vis', False))
        f_uvs = bool(sample.get('filter_uvs', False))
        f_uvl = bool(sample.get('filter_uvl', False))
        f_aft_vis = sample.get('filter_aft_vis') or ""
        f_aft_uv = sample.get('filter_aft_uv') or ""

        if current_filter:
            filter_tags += f" <small style='color:gray'>[{current_filter}]</small>"
        if current_genus:
            filter_tags += f" <small style='color:gray'>[Genus: {current_genus}]</small>"
        if current_family:
            filter_tags += f" <small style='color:gray'>[Family: {current_family}]</small>"
        if f_vis:
            filter_tags += " <small style='color:gray'>[Vis]</small>"
        if f_uvs:
            filter_tags += " <small style='color:gray'>[UVS]</small>"
        if f_uvl:
            filter_tags += " <small style='color:gray'>[UVL]</small>"
        if f_aft_vis:
            filter_tags += f" <small style='color:gray'>[After Vis: {f_aft_vis}]</small>"
        if f_aft_uv:
            filter_tags += f" <small style='color:gray'>[After UV: {f_aft_uv}]</small>"
        return filter_tags

    def _render_prediction_cell(self, row, sid, matches, current_filter, current_genus, current_family):
        pred_label = QLabel()
        self.window.samples[sid]['last_matches'] = matches
        filter_tags = self._filter_tags(sid, current_filter, current_genus, current_family)

        if matches:
            match_links = []
            for score, name in matches[:5]:
                encoded_name = quote(name, safe='')
                display_name = html.escape(name)
                match_links.append(
                    f'<a href="substance:{encoded_name}" title="Match score: {score:.6f}">{display_name}</a>'
                )
            match_str = ", ".join(match_links)

            if len(matches) > 5:
                match_str += f" + {len(matches) - 5} more"

            match_str += filter_tags
            pred_label.setText(match_str)
            pred_label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
            pred_label.linkActivated.connect(self.window.handle_link_click)
            if not hasattr(self.window, '_prediction_hover_link_by_sid'):
                self.window._prediction_hover_link_by_sid = {}
            pred_label.linkHovered.connect(
                lambda link, sid=sid: self.window._prediction_hover_link_by_sid.__setitem__(sid, link)
            )
            pred_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            pred_label.customContextMenuRequested.connect(
                lambda pos, sid=sid, w=pred_label: self.window.show_prediction_context_menu(sid, w, pos)
            )
        else:
            pred_label.setText(f"-{filter_tags}" if filter_tags else "-")

        pred_label.setContentsMargins(5, 0, 5, 0)
        self.table.setCellWidget(row, self.window.RESULTS_COL_PREDICTIONS, pred_label)

    def _render_reference_cell(self, row, sid, aggregated):
        if sid > 0 or sid in REFERENCE_STANDARD_IDS:
            ref_container = QWidget()
            ref_layout = QHBoxLayout(ref_container)
            ref_layout.setContentsMargins(0, 0, 0, 0)
            ref_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            ref_checkbox = QCheckBox()
            if sid in REFERENCE_STANDARD_IDS:
                is_marked_on_plates = sid in aggregated and len(aggregated[sid]) > 0
                if not is_marked_on_plates:
                    self.window.samples[sid]['is_reference'] = False
                    self.window.samples[sid]['reference_rf'] = None
                ref_checkbox.setChecked(self.window.samples[sid].get('is_reference', False))
                ref_checkbox.setEnabled(is_marked_on_plates)
            else:
                ref_checkbox.setChecked(self.window.samples[sid].get('is_reference', False))

            ref_checkbox.stateChanged.connect(lambda state, sid=sid: self.window.handle_reference_checkbox(state, sid))
            ref_layout.addWidget(ref_checkbox)
            self.table.setCellWidget(row, self.window.RESULTS_COL_REFERENCE, ref_container)

            is_ref = self.window.samples[sid].get('is_reference', False)
            ref_sort_item = SortableTableWidgetItem()
            ref_sort_item.setData(Qt.ItemDataRole.UserRole, 0 if is_ref else 1)
            ref_sort_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.table.setItem(row, self.window.RESULTS_COL_REFERENCE, ref_sort_item)
            return

        empty_label = QLabel()
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setCellWidget(row, self.window.RESULTS_COL_REFERENCE, empty_label)

        ref_sort_item = SortableTableWidgetItem()
        ref_sort_item.setData(Qt.ItemDataRole.UserRole, 2)
        ref_sort_item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.table.setItem(row, self.window.RESULTS_COL_REFERENCE, ref_sort_item)

    def _render_all_results_cell(self, row, sid, matches, prediction_input):
        if sid > 0 and matches:
            results_button = QPushButton("View All")
            results_button.setProperty('sid', sid)
            results_button.clicked.connect(
                lambda checked, s=sid, m=matches, p=prediction_input, n=self.window.samples[sid].get('assigned_name') or self.window.samples[sid]['name']: self.window.show_prediction_results(s, m, p, n)
            )
            self.table.setCellWidget(row, self.window.RESULTS_COL_ALL_RESULTS, results_button)
            return

        empty_button_label = QLabel()
        empty_button_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setCellWidget(row, self.window.RESULTS_COL_ALL_RESULTS, empty_button_label)
