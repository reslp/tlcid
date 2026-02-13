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
        
        self.layout.addWidget(self.view)
        
    def closeEvent(self, event):
        # Optional: cleanup or hide
        if self.db.isOpen():
            pass
            # We don't necessarily close it here if we want to reuse connection
        super().closeEvent(event)
