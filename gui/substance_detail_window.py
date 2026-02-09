from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QScrollArea, QWidget, QFormLayout
from PyQt6.QtCore import Qt
from PyQt6.QtSql import QSqlQuery

class SubstanceDetailWindow(QDialog):
    def __init__(self, substance_name, db):
        super().__init__()
        self.setWindowTitle(f"Substance Details: {substance_name}")
        self.resize(500, 600)
        self.db = db
        
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel(substance_name)
        title.setStyleSheet("font-size: 18pt; font-weight: bold; margin-bottom: 10px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Scroll Area for details
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        self.form_layout = QFormLayout(content_widget)
        
        self.load_data(substance_name)
        
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)
        
    def load_data(self, name):
        query = QSqlQuery(self.db)
        query.prepare("SELECT * FROM Substances WHERE name = :name")
        query.bindValue(":name", name)
        
        if query.exec() and query.next():
            record = query.record()
            for i in range(record.count()):
                field_name = record.fieldName(i)
                value = query.value(i)
                if value is None:
                    value = ""
                
                # Format value
                val_str = str(value)
                
                label = QLabel(field_name)
                label.setStyleSheet("font-weight: bold;")
                
                val_label = QLabel(val_str)
                val_label.setWordWrap(True)
                val_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                
                self.form_layout.addRow(label, val_label)
        else:
            self.form_layout.addRow(QLabel("Error:"), QLabel("Substance not found in database."))
