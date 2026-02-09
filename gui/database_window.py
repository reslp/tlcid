from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableView, QMessageBox, QHeaderView
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
        
        self.setup_database()
        self.setup_ui()
        
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
