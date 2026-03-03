from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableView, QMessageBox, QHeaderView, QLineEdit, QLabel
from PyQt6.QtSql import QSqlDatabase, QSqlTableModel
from PyQt6.QtCore import Qt
import os

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
        
        self.setup_database()
        self.setup_ui()
        
        # Update placeholder based on table columns
        self.update_search_placeholder()

    def update_search_placeholder(self):
        cols = []
        for col in ["name", "Lichen", "Substance", "Genus"]:
            if self.model.fieldIndex(col) != -1:
                cols.append(col)
        if cols:
            self.search_input.setPlaceholderText(f"Search by {', '.join(cols)}...")

    def filter_data(self, text):
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
        self.model = QSqlTableModel(self, self.db)
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
        
        # Stretch last column or resize to contents
        header = self.view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        # Custom column order/width for Substances table
        if self.table_name == "Substances":
            self._configure_substances_columns()
        
        self.layout.addWidget(self.view)

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
        
    def closeEvent(self, event):
        # Optional: cleanup or hide
        if self.db.isOpen():
            pass
            # We don't necessarily close it here if we want to reuse connection
        super().closeEvent(event)
