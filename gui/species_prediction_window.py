from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QListWidget, QListWidgetItem, QPushButton, QTextEdit)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtSql import QSqlQuery

class SpeciesPredictionWindow(QDialog):
    def __init__(self, prediction_data, db, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lichen Species Prediction")
        self.resize(600, 500)
        self.prediction_data = prediction_data # list of {'name': str, 'sample_name': str, 'color': QColor}
        self.db = db
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("<b>Step 1: Select substances found on the plate:</b>"))
        
        # Substance Selection List
        self.substance_list = QListWidget()
        for item_data in self.prediction_data:
            display_text = f"{item_data['sample_name']}: {item_data['name']}"
            item = QListWidgetItem(display_text)
            
            # Add colored icon
            pix = QPixmap(12, 12)
            pix.fill(item_data['color'])
            item.setIcon(QIcon(pix))
            
            # Store the actual substance name for the query
            item.setData(Qt.ItemDataRole.UserRole, item_data['name'])
            
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.substance_list.addItem(item)
        layout.addWidget(self.substance_list)
        
        # Predict Button
        self.predict_button = QPushButton("Predict Lichen Species")
        self.predict_button.clicked.connect(self.run_prediction)
        layout.addWidget(self.predict_button)
        
        layout.addWidget(QLabel("<b>Step 2: Predicted Lichen Species:</b>"))
        
        # Results Area
        self.results_area = QTextEdit()
        self.results_area.setReadOnly(True)
        layout.addWidget(self.results_area)
        
        # Close button
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def run_prediction(self):
        # Get selected substances (unique names)
        selected_names = set()
        for i in range(self.substance_list.count()):
            item = self.substance_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_names.add(item.data(Qt.ItemDataRole.UserRole))
        
        selected = sorted(list(selected_names))
        
        if not selected:
            self.results_area.setText("Please select at least one substance.")
            return
            
        # SQL Logic: Find lichens that contain ALL selected substances
        sub_placeholders = ",".join(["?" for _ in selected])
        query_str = f"""
            SELECT Lichen FROM Lichens 
            WHERE Substance IN ({sub_placeholders})
            GROUP BY Lichen 
            HAVING COUNT(DISTINCT Substance) = {len(selected)}
            ORDER BY Lichen
        """
        
        query = QSqlQuery(self.db)
        query.prepare(query_str)
        for s in selected:
            query.addBindValue(s)
            
        results = []
        if query.exec():
            while query.next():
                results.append(query.value(0))
        
        if results:
            text = f"Found {len(results)} species containing: {', '.join(selected)}\n\n"
            text += "\n".join(results)
            self.results_area.setText(text)
        else:
            self.results_area.setText(f"No species found in the database containing all: {', '.join(selected)}")
