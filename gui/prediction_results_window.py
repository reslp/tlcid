from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem,
                             QHeaderView, QPushButton, QLabel, QHBoxLayout)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtSql import QSqlDatabase, QSqlQuery

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
        self.resize(900, 600)

        self.setup_ui()

    def parse_rf(self, val):
        """Convert database Rf value (e.g., 45) to 0-1 range (e.g., 0.45)."""
        if val is None or val == "":
            return None
        try:
            return float(val) / 100.0
        except:
            return None

    def get_substance_rf_from_db(self, substance_name):
        """Query the database to get Rf values for a substance."""
        # Check cache first
        if substance_name in self.db_rf_values:
            return self.db_rf_values[substance_name]

        # Get database connection
        db = QSqlDatabase.database()
        if not db.isOpen():
            # Try to open connection if not already open
            db_path = None
            if self.parent() is not None and hasattr(self.parent(), "db_path"):
                db_path = self.parent().db_path

            if db_path is None:
                import os
                base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                db_path = os.path.join(base_path, "Mytabolites.db")

            db = QSqlDatabase.addDatabase("QSQLITE")
            db.setDatabaseName(db_path)
            if not db.open():
                return None

        # Query the database for Rf values
        query = QSqlQuery(db)
        query.prepare("SELECT A, Bprime, C FROM Substances WHERE name = :name")
        query.bindValue(":name", substance_name)

        if query.exec() and query.next():
            rf_a = self.parse_rf(query.value(0))
            rf_b = self.parse_rf(query.value(1))
            rf_c = self.parse_rf(query.value(2))

            result = [rf_a, rf_b, rf_c]
            self.db_rf_values[substance_name] = result
            return result

        return None


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

        # Header with substance name and match count
        header_layout = QHBoxLayout()
        header_label = QLabel(f"<b>Prediction Results for {self.substance_name}</b>")
        header_label.setStyleSheet("font-size: 14px;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        count_label = QLabel(f"{len(self.matches)} substance(s) found")
        count_label.setStyleSheet("color: gray;")
        header_layout.addWidget(count_label)

        layout.addLayout(header_layout)

        # Results table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Substance Name", "Plate A (Rf)", "Plate B' (Rf)", "Plate C (Rf)", "Match Score"])

        # Configure table appearance
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Substance name
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Plate A
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Plate B'
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Plate C
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Score

        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        # Populate table
        self.populate_table()

        layout.addWidget(self.table)

        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)

    def populate_table(self):
        """Populate the table with prediction results."""
        self.table.setRowCount(len(self.matches))

        for row, (score, name) in enumerate(self.matches):
            # Substance name
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, name)  # Store name for sorting
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
        self.table.sortByColumn(4, Qt.SortOrder.AscendingOrder)
