from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableView, QMessageBox, QHeaderView, QLineEdit, QLabel, QHBoxLayout
from PyQt6.QtSql import QSqlDatabase, QSqlTableModel, QSqlQueryModel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
import os


class SubstanceTableModel(QSqlTableModel):
    """Style substance names like the links in the prediction results."""

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and index.column() == self.fieldIndex("name"):
            if role == Qt.ItemDataRole.ForegroundRole:
                return QColor(0, 102, 204)
            if role == Qt.ItemDataRole.ToolTipRole:
                return "Click to open substance details"
        return super().data(index, role)


class DatabaseTableWindow(QWidget):
    def __init__(self, table_name, db_path="Mytabolites.db"):
        super().__init__()
        self.table_name = table_name
        self.setWindowTitle(f"Reference: {table_name}")
        self.resize(800, 600)
        self.db_path = db_path
        
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Search Bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search...")
        self.search_input.textChanged.connect(self.filter_data)
        self.layout.addWidget(self.search_input)
        
        # Flag set by _configure_lichens_view to switch filter logic
        self._lichens_mode = False
        self._lichens_sort_column = "Lichen"
        self._lichens_sort_order = Qt.SortOrder.AscendingOrder

        self.setup_database()
        self.setup_ui()
        
        # Update placeholder based on table columns
        self.update_search_placeholder()

    def update_search_placeholder(self):
        if self._lichens_mode:
            self.search_input.setPlaceholderText("Search by Lichen, Substance, Genus, Family...")
            return
        cols = []
        for col in ["name", "Lichen", "Substance", "Genus"]:
            if self.model.fieldIndex(col) != -1:
                cols.append(col)
        if cols:
            self.search_input.setPlaceholderText(f"Search by {', '.join(cols)}")

    def filter_data(self, text):
        if self._lichens_mode:
            self._refresh_lichens_model(text)
            return

        if not text:
            self.model.setFilter("")
        else:
            # Safe SQL filtering for multiple identifying columns
            sanitized_text = text.replace("'", "''")
            filter_parts = []
            
            # Identify columns to search in
            for col in ["name", "Lichen", "Substance", "Genus"]:
                if self.model.fieldIndex(col) != -1:
                    filter_parts.append(f"{col} LIKE '%{sanitized_text}%'")
            
            if filter_parts:
                self.model.setFilter(" OR ".join(filter_parts))
            else:
                # If no known columns, don't filter to avoid SQL errors
                self.model.setFilter("")
        
        self.model.select()
        
    def setup_database(self):
        # Check if connection already exists
        if QSqlDatabase.contains("substances_connection"):
            self.db = QSqlDatabase.database("substances_connection")
        else:
            self.db = QSqlDatabase.addDatabase("QSQLITE", "substances_connection")
            self.db.setDatabaseName(self.db_path)
            
        if not self.db.open():
            QMessageBox.critical(self, "Database Error", 
                                 f"Could not open database at {self.db_path}.\n{self.db.lastError().text()}")
            return

    def setup_ui(self):
        model_class = SubstanceTableModel if self.table_name == "Substances" else QSqlTableModel
        self.model = model_class(self, self.db)
        self.model.setTable(self.table_name)
        self.model.select()
        
        # Set headers nicely if columns are known, otherwise default
        # Assuming table has standard cols, but auto-discovery is safer for first pass
        self.model.setEditStrategy(QSqlTableModel.EditStrategy.OnManualSubmit) # Read-onlyish behavior for view
        
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.view.setAlternatingRowColors(True)
        self.view.setSortingEnabled(True)
        
        header = self.view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.sortIndicatorChanged.connect(self._on_sort_indicator_changed)
        self.view.resizeColumnsToContents()

        # Custom column order/width for Substances table
        if self.table_name == "Substances":
            self._configure_substances_columns()
            self.view.clicked.connect(self.on_table_cell_clicked)

            content_layout = QHBoxLayout()
            content_layout.addWidget(self.view, stretch=3)

            self.detail_panel = QWidget()
            self.detail_panel_layout = QVBoxLayout(self.detail_panel)
            self.detail_panel_layout.setContentsMargins(0, 0, 0, 0)
            self.detail_panel.setMinimumWidth(300)
            self.detail_panel.hide()
            content_layout.addWidget(self.detail_panel, stretch=4)

            self.layout.addLayout(content_layout)
        else:
            if self.table_name == "Lichens":
                self._configure_lichens_view()
            self.layout.addWidget(self.view)

    def on_table_cell_clicked(self, index):
        """Show substance detail when clicking a substance name cell."""
        if self.table_name != "Substances":
            return

        name_idx = self.model.fieldIndex("name")
        if name_idx == -1 or index.column() != name_idx:
            return

        name = self.model.data(self.model.index(index.row(), name_idx))
        if not name:
            return

        from gui.substance_detail_window import SubstanceDetailWindow

        while self.detail_panel_layout.count():
            child = self.detail_panel_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

        detail = SubstanceDetailWindow(str(name), self.db)
        detail.setWindowFlags(Qt.WindowType.Widget)
        detail.setParent(self.detail_panel)
        detail.setWindowTitle(f"Substance Details: {name}")
        self.detail_panel_layout.addWidget(detail)
        detail.show()

        if not self.detail_panel.isVisible():
            self.detail_panel.show()
            self.resize(max(self.width(), 1150), self.height())

    def _configure_substances_columns(self):
        """Set preferred display order for Substances and shrink name column."""
        header = self.view.horizontalHeader()

        preferred = ["name", "A", "Bprime", "C", "B"]
        field_count = self.model.columnCount()

        # Keep all remaining columns in their original model order
        preferred_indices = []
        used = set()
        for col in preferred:
            idx = self.model.fieldIndex(col)
            if idx != -1 and idx not in used:
                preferred_indices.append(idx)
                used.add(idx)

        remaining_indices = [i for i in range(field_count) if i not in used]
        target_order = preferred_indices + remaining_indices

        # Move sections to match target visual order
        for target_visual, logical_idx in enumerate(target_order):
            current_visual = header.visualIndex(logical_idx)
            if current_visual != target_visual:
                header.moveSection(current_visual, target_visual)

        # Resize to contents first, then reduce name column width to ~2/3
        self.view.resizeColumnsToContents()
        name_idx = self.model.fieldIndex("name")
        if name_idx != -1:
            current_width = self.view.columnWidth(name_idx)
            self.view.setColumnWidth(name_idx, max(60, int(current_width * (2 / 3))))

        # Equalise width of B' column with the other Rf-value columns
        rf_cols = ["A", "B", "Bprime", "C", "E", "F", "G"]
        rf_widths = []
        for col in rf_cols:
            idx = self.model.fieldIndex(col)
            if idx != -1:
                rf_widths.append(self.view.columnWidth(idx))
        if rf_widths:
            target_width = min(rf_widths)
            for col in rf_cols:
                idx = self.model.fieldIndex(col)
                if idx != -1:
                    self.view.setColumnWidth(idx, target_width)

        bprime_idx = self.model.fieldIndex("Bprime")
        if bprime_idx != -1:
            self.model.setHeaderData(bprime_idx, Qt.Orientation.Horizontal, "B'")
        
    # ------------------------------------------------------------------
    # Lichens helpers
    # ------------------------------------------------------------------

    def _lichens_available_columns(self):
        """Return the list of column names present in the Lichens table."""
        record = self.db.record("Lichens")
        return [record.fieldName(i) for i in range(record.count())]

    def _lichens_query(self, filter_text="", sort_column=None, sort_order=None):
        """Return a GROUP_CONCAT aggregation query for the Lichens table.

        - ``Substance`` and (if present) ``SubstancesReference`` are
          aggregated with GROUP_CONCAT so multiple rows per species are
          collapsed into one.  DISTINCT is used for SubstancesReference to
          avoid repeating the same source tag.
        - ``Genus``, ``Family``, and ``FamilyReference`` (when present) are
          constant per species and are retrieved with MIN().
        - When *filter_text* is given the result is filtered via a HAVING
          clause that checks the Lichen name, the aggregated Substance string,
          and (if available) Genus / Family.
        - ``sort_column`` / ``sort_order`` are used to rebuild the query when
          the user clicks a table header, because the aggregated lichens view
          uses ``QSqlQueryModel`` rather than ``QSqlTableModel``.
        """
        available = self._lichens_available_columns()

        select_parts = [
            "Lichen",
            "GROUP_CONCAT(Substance, ', ') AS Substance",
        ]
        # Stable per-species columns – use MIN() to satisfy GROUP BY
        for col in ("Genus", "Family", "FamilyReference"):
            if col in available:
                select_parts.append(f"MIN({col}) AS {col}")
        # Reference column that can differ per substance row – deduplicate
        if "SubstancesReference" in available:
            select_parts.append(
                "GROUP_CONCAT(DISTINCT SubstancesReference) AS SubstancesReference"
            )

        q = f"SELECT {', '.join(select_parts)} FROM Lichens GROUP BY Lichen"

        if filter_text:
            safe = filter_text.replace("'", "''")
            having_parts = [
                f"Lichen LIKE '%{safe}%'",
                f"Substance LIKE '%{safe}%'",
            ]
            if "Genus" in available:
                having_parts.append(f"Genus LIKE '%{safe}%'")
            if "Family" in available:
                having_parts.append(f"Family LIKE '%{safe}%'")
            q += " HAVING " + " OR ".join(having_parts)

        projected = getattr(self, "_lichens_projected", ["Lichen", "Substance"])
        sort_column = sort_column or self._lichens_sort_column
        if sort_column not in projected:
            sort_column = "Lichen"

        direction = "DESC" if sort_order == Qt.SortOrder.DescendingOrder else "ASC"
        if sort_column == "Lichen":
            q += f" ORDER BY Lichen {direction}"
        else:
            q += f" ORDER BY {sort_column} {direction}, Lichen ASC"
        return q

    def _configure_lichens_view(self):
        """Replace the plain table model with an aggregated query model so
        that each species is shown as a single row with all its substances
        combined in the Substance column."""
        self._lichens_mode = True

        available = self._lichens_available_columns()

        self.model = QSqlQueryModel(self)

        # Build the ordered list of columns the query actually projects
        projected = ["Lichen", "Substance"]
        for col in ("Genus", "Family", "FamilyReference"):
            if col in available:
                projected.append(col)
        if "SubstancesReference" in available:
            projected.append("SubstancesReference")

        self._lichens_projected = projected  # store for filter refresh

        self.view.setModel(self.model)
        self.view.horizontalHeader().setSortIndicator(
            0, Qt.SortOrder.AscendingOrder
        )
        self._refresh_lichens_model()
        self.view.resizeColumnsToContents()

    def _refresh_lichens_model(self, filter_text=""):
        col_labels = {
            "Lichen": "Lichen",
            "Substance": "Substance",
            "Genus": "Genus",
            "Family": "Family",
            "FamilyReference": "Family Reference",
            "SubstancesReference": "Substance Reference",
        }
        self.model.setQuery(
            self._lichens_query(
                filter_text,
                sort_column=self._lichens_sort_column,
                sort_order=self._lichens_sort_order,
            ),
            self.db,
        )
        for visual_idx, col in enumerate(getattr(self, "_lichens_projected", [])):
            self.model.setHeaderData(
                visual_idx, Qt.Orientation.Horizontal, col_labels.get(col, col)
            )

    def _on_sort_indicator_changed(self, logical_index, sort_order):
        if not self._lichens_mode:
            return
        projected = getattr(self, "_lichens_projected", [])
        if logical_index < 0 or logical_index >= len(projected):
            return
        self._lichens_sort_column = projected[logical_index]
        self._lichens_sort_order = sort_order
        self._refresh_lichens_model(self.search_input.text())

    def closeEvent(self, event):
        # Optional: cleanup or hide
        if self.db.isOpen():
            pass
            # We don't necessarily close it here if we want to reuse connection
        super().closeEvent(event)
