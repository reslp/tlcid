from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem,
                             QHeaderView, QPushButton, QLabel, QHBoxLayout, QWidget, QMenu,
                             QCheckBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtSql import QSqlDatabase

from gui.reference_repository import ReferenceRepository, parse_rf


class PredictionResultsWindow(QDialog):
    """Dialog window showing all prediction results for a substance in a table format."""

    def __init__(self, substance_name, substance_id, matches, plate_data, parent=None):
        super().__init__(parent)
        self.substance_name = substance_name
        self.substance_id = substance_id
        self.matches = matches
        self.plate_data = plate_data
        self.db_rf_values = {}  # Cache for database Rf values

        self.setWindowTitle(f"All Prediction Results - {substance_name}")
        self.resize(300, 600)

        self.setup_ui()

    def parse_rf(self, val):
        """Convert database Rf value (e.g., 45) to 0-1 range (e.g., 0.45)."""
        return parse_rf(val)

    def get_substance_rf_from_db(self, substance_name):
        """Query the configured reference repository to get Rf values for a substance."""
        if substance_name in self.db_rf_values:
            return self.db_rf_values[substance_name]

        parent = self.parent()
        if parent is not None and hasattr(parent, "get_substance_rf_from_db"):
            result = parent.get_substance_rf_from_db(substance_name)
        else:
            import os
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_path, "tlcid_database.db")
            result = ReferenceRepository(db_path).get_substance_rf(substance_name)

        if result is not None:
            self.db_rf_values[substance_name] = result
        return result


    def format_rf_value(self, value):
        if value is None:
            return "-"
        relative = False
        if self.parent() is not None and hasattr(self.parent(), "relative_rf_display"):
            relative = self.parent().relative_rf_display
        if relative:
            return f"{value * 100:.0f}"
        return f"{value:.2f}"

    def setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Header with substance name, observed plate Rf values, and match count
        header_layout = QHBoxLayout()

        obs_a = self.format_rf_value(self.plate_data.get(0)) if isinstance(self.plate_data, dict) else "-"
        obs_b = self.format_rf_value(self.plate_data.get(1)) if isinstance(self.plate_data, dict) else "-"
        obs_c = self.format_rf_value(self.plate_data.get(2)) if isinstance(self.plate_data, dict) else "-"

        header_label = QLabel(
            f"<b>Prediction Results for {self.substance_name}</b>"
            f"  <span style='color: gray;'>| Spot Rf: A={obs_a}, B'={obs_b}, C={obs_c}</span>"
        )
        header_label.setStyleSheet("font-size: 14px;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        self.count_label = QLabel(f"{len(self.matches)} substance(s) found")
        self.count_label.setStyleSheet("color: gray;")
        header_layout.addWidget(self.count_label)

        layout.addLayout(header_layout)

        # Two-column content area: prediction table (left) + substance details (right)
        content_layout = QHBoxLayout()

        # Results table (left)
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Name", "Rf A", "Rf B'", "Rf C", "Score"])

        # Configure table appearance (resizable columns)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Substance name
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # Plate A
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)  # Plate B'
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)  # Plate C
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)  # Score
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 45)
        self.table.setColumnWidth(2, 45)
        self.table.setColumnWidth(3, 45)
        self.table.setColumnWidth(4, 80)

        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.cellClicked.connect(self.on_table_cell_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_prediction_context_menu)

        # Detail panel (left), shown after first click
        self.detail_panel = QWidget()
        self.detail_panel_layout = QVBoxLayout(self.detail_panel)
        self.detail_panel_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_panel.setMinimumWidth(300)
        self.detail_panel.hide()
        content_layout.addWidget(self.detail_panel, stretch=4)

        content_layout.addWidget(self.table, stretch=3)

        layout.addLayout(content_layout)

        # Populate table after the optional detail panel exists.
        self.populate_table()

        self.allow_missing_rf_checkbox = QCheckBox("Allow missing Rf values")
        self.allow_missing_rf_checkbox.stateChanged.connect(self.on_allow_missing_rf_changed)

        # Footer controls
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.allow_missing_rf_checkbox)
        button_layout.addStretch()

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)
        self.update_allow_missing_rf_checkbox_state()

    def _parent_window(self):
        return self.parent() if self.parent() is not None else None

    def _global_allow_missing_rf_values(self):
        parent = self._parent_window()
        return bool(getattr(parent, "allow_missing_rf_values", False))

    def _local_allow_missing_rf_values(self):
        parent = self._parent_window()
        if parent is None or not hasattr(parent, "samples"):
            return False
        return bool(parent.samples.get(self.substance_id, {}).get("allow_missing_rf_values", False))

    def update_allow_missing_rf_checkbox_state(self):
        global_enabled = self._global_allow_missing_rf_values()
        self.allow_missing_rf_checkbox.blockSignals(True)
        self.allow_missing_rf_checkbox.setChecked(global_enabled or self._local_allow_missing_rf_values())
        self.allow_missing_rf_checkbox.setEnabled(not global_enabled)
        self.allow_missing_rf_checkbox.setToolTip(
            "Enabled globally in Settings." if global_enabled else ""
        )
        self.allow_missing_rf_checkbox.blockSignals(False)

    def refresh_matches(self):
        parent = self._parent_window()
        if parent is None or not hasattr(parent, "predict_matches") or not hasattr(parent, "samples"):
            return

        sample = parent.samples.get(self.substance_id, {})
        self.matches = parent.predict_matches(
            self.plate_data,
            filter_group=sample.get('filter_group'),
            filter_genus=sample.get('filter_genus'),
            filter_family=sample.get('filter_family'),
            filter_vis=sample.get('filter_vis', False),
            filter_uvs=sample.get('filter_uvs', False),
            filter_uvl=sample.get('filter_uvl', False),
            filter_aft_vis=sample.get('filter_aft_vis'),
            filter_aft_uv=sample.get('filter_aft_uv'),
            allow_missing_rf_values=parent.sample_allows_missing_rf_values(self.substance_id),
        )
        self.populate_table()
        self.update_allow_missing_rf_checkbox_state()

    def on_allow_missing_rf_changed(self, state):
        parent = self._parent_window()
        if parent is None or not hasattr(parent, "set_sample_allow_missing_rf_values"):
            return
        parent.set_sample_allow_missing_rf_values(self.substance_id, state == Qt.CheckState.Checked.value)
        self.refresh_matches()

    def on_table_cell_clicked(self, row, column):
        """Show substance detail in right panel when clicking on the substance name cell."""
        if column != 0:
            return

        item = self.table.item(row, 0)
        if not item:
            return

        name = item.data(Qt.ItemDataRole.UserRole) or item.text()
        if not name:
            return

        from gui.substance_detail_window import SubstanceDetailWindow

        db = QSqlDatabase.database()
        if not db.isOpen() and self.parent() is not None and hasattr(self.parent(), "_ensure_default_db_connection"):
            db = self.parent()._ensure_default_db_connection()

        if not db.isOpen():
            return

        # Clear previous detail widget
        while self.detail_panel_layout.count():
            child = self.detail_panel_layout.takeAt(0)
            w = child.widget()
            if w is not None:
                w.deleteLater()

        # Embed detail dialog as a widget in the right column
        detail = SubstanceDetailWindow(str(name), db)
        detail.setWindowFlags(Qt.WindowType.Widget)
        detail.setParent(self.detail_panel)
        detail.setWindowTitle(f"Substance Details: {name}")
        self.detail_panel_layout.addWidget(detail)
        detail.show()

        # Reveal panel + expand window width once
        if not self.detail_panel.isVisible():
            self.detail_panel.show()
            self.resize(max(self.width(), 1150), self.height())

    def _name_from_row(self, row):
        """Return substance name for a table row (None if unavailable)."""
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        return item.data(Qt.ItemDataRole.UserRole) or item.text()

    def show_prediction_context_menu(self, pos):
        """Right-click context menu for prediction entries (matches main results behavior)."""
        parent = self.parent()
        if parent is None or not hasattr(parent, "assign_predicted_name_to_sample"):
            return

        row = self.table.rowAt(pos.y())
        clicked_name = self._name_from_row(row)

        menu = QMenu(self)

        if clicked_name:
            assign_action = menu.addAction(f"Assign substance name: {clicked_name}")
            assign_action.triggered.connect(
                lambda checked=False, s=self.substance_id, n=clicked_name: parent.assign_predicted_name_to_sample(s, n)
            )
        else:
            disabled = menu.addAction("Assign substance name")
            disabled.setEnabled(False)

        display_action = menu.addAction("Display name on plate")
        display_action.setCheckable(True)

        current_show = False
        if hasattr(parent, "samples"):
            current_show = bool(parent.samples.get(self.substance_id, {}).get("show_on_plate", False))
        display_action.setChecked(current_show)

        if clicked_name:
            display_action.triggered.connect(
                lambda checked=False, s=self.substance_id, n=clicked_name: (
                    parent.assign_predicted_name_to_sample(s, n) if checked else None,
                    parent.set_sample_show_on_plate(s, checked)
                )
            )
        else:
            display_action.triggered.connect(
                lambda checked=False, s=self.substance_id: parent.set_sample_show_on_plate(s, checked)
            )

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def populate_table(self):
        """Populate the table with prediction results."""
        self.table.setSortingEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(len(self.matches))
        self.count_label.setText(f"{len(self.matches)} substance(s) found")

        if hasattr(self, "detail_panel_layout"):
            while self.detail_panel_layout.count():
                child = self.detail_panel_layout.takeAt(0)
                widget = child.widget()
                if widget is not None:
                    widget.deleteLater()
        if hasattr(self, "detail_panel"):
            self.detail_panel.hide()

        for row, (score, name) in enumerate(self.matches):
            # Substance name
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, name)  # Store name for sorting
            name_item.setForeground(QColor(0, 102, 204))  # clickable-link style
            name_item.setToolTip("Click to open substance details")
            self.table.setItem(row, 0, name_item)

            # Get Rf values from the database for this predicted substance
            db_rf = self.get_substance_rf_from_db(name)
            rf_a = db_rf[0] if db_rf and len(db_rf) > 0 else None
            rf_b = db_rf[1] if db_rf and len(db_rf) > 1 else None
            rf_c = db_rf[2] if db_rf and len(db_rf) > 2 else None

            self.table.setItem(row, 1, QTableWidgetItem(self.format_rf_value(rf_a)))
            self.table.setItem(row, 2, QTableWidgetItem(self.format_rf_value(rf_b)))
            self.table.setItem(row, 3, QTableWidgetItem(self.format_rf_value(rf_c)))

            # Match score
            score_item = QTableWidgetItem(f"{score:.6f}")
            score_item.setData(Qt.ItemDataRole.UserRole, score)  # Store numeric value for sorting
            self.table.setItem(row, 4, score_item)

            # Color code the score cell (lower is better)
            # Keep text black for readability; use background color for quality indication
            score_item.setForeground(QColor(0, 0, 0))
            if score < 0.01:
                score_item.setBackground(QColor(200, 255, 200))  # Light green
            elif score < 0.05:
                score_item.setBackground(QColor(255, 255, 200))  # Light yellow
            else:
                score_item.setBackground(QColor(255, 220, 220))  # Light red

        # Sort by score (ascending) by default
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(4, Qt.SortOrder.AscendingOrder)
