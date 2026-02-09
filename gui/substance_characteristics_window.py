from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtSql import QSqlQuery

class SubstanceCharacteristicsWindow(QDialog):
    filterChanged = pyqtSignal(int, str, str) # sample_id, group_name, genus

    def __init__(self, sample_id, sample_name, current_group, current_genus, db):
        super().__init__()
        self.setWindowTitle(f"Characteristics: {sample_name}")
        self.resize(400, 300)
        self.sample_id = sample_id
        self.db = db
        
        layout = QVBoxLayout(self)
        
        # Group Filter
        label_group = QLabel(f"Filter predictions for <b>{sample_name}</b> by Group:")
        layout.addWidget(label_group)
        
        self.combo_group = QComboBox()
        self.combo_group.addItem("All Groups", None)
        self.load_groups(current_group)
        self.combo_group.currentIndexChanged.connect(self.on_change)
        layout.addWidget(self.combo_group)

        # Genus Filter
        label_genus = QLabel("Filter by Lichen Genus:")
        layout.addWidget(label_genus)
        
        self.combo_genus = QComboBox()
        self.combo_genus.addItem("All Genera", None)
        self.load_genera(current_genus)
        self.combo_genus.currentIndexChanged.connect(self.on_change)
        layout.addWidget(self.combo_genus)

        layout.addStretch()
        
        # Close button
        btn = QPushButton("Close")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)
        
    def load_groups(self, current_group):
        query = QSqlQuery(self.db)
        if query.exec("SELECT DISTINCT GroupName FROM Substances ORDER BY GroupName"):
            while query.next():
                group = query.value(0)
                if group:
                    self.combo_group.addItem(group, group)
        
        if current_group:
            index = self.combo_group.findData(current_group)
            if index >= 0:
                self.combo_group.setCurrentIndex(index)

    def load_genera(self, current_genus):
        query = QSqlQuery(self.db)
        # Extract unique genera from Lichens column
        # SQLite doesn't have easy split, so fetch all distinct Lichens strings and parse in Python
        genera = set()
        if query.exec("SELECT DISTINCT Lichens FROM Substances"):
             while query.next():
                 lichens_val = query.value(0)
                 if lichens_val:
                     parts = lichens_val.strip().split()
                     if parts:
                         genera.add(parts[0])
        
        sorted_genera = sorted(list(genera))
        for genus in sorted_genera:
            self.combo_genus.addItem(genus, genus)
            
        if current_genus:
            index = self.combo_genus.findData(current_genus)
            if index >= 0:
                self.combo_genus.setCurrentIndex(index)
                
    def on_change(self):
        group_data = self.combo_group.currentData()
        genus_data = self.combo_genus.currentData()
        self.filterChanged.emit(self.sample_id, group_data, genus_data)
