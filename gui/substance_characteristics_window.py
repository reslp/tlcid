from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton, QCheckBox
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtSql import QSqlQuery

class SubstanceCharacteristicsWindow(QDialog):
    # sample_id, group_name, genus, bef_vis, bef_uvs, bef_uvl, aft_vis, aft_uv
    filterChanged = pyqtSignal(int, str, str, bool, bool, bool, str, str)

    def __init__(self, sample_id, sample_name, current_group, current_genus, 
                 current_vis, current_uvs, current_uvl, 
                 current_aft_vis, current_aft_uv, db):
        super().__init__()
        self.setWindowTitle(f"Characteristics: {sample_name}")
        self.resize(400, 600)
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

        # Visual Characteristics (Before Treatment)
        layout.addWidget(QLabel("Visual Characteristics (Before Treatment):"))
        
        self.check_vis = QCheckBox("Visible (Vis)")
        self.check_vis.setChecked(current_vis)
        self.check_vis.stateChanged.connect(self.on_change)
        layout.addWidget(self.check_vis)

        self.check_uvs = QCheckBox("UV Short (UVS)")
        self.check_uvs.setChecked(current_uvs)
        self.check_uvs.stateChanged.connect(self.on_change)
        layout.addWidget(self.check_uvs)

        self.check_uvl = QCheckBox("UV Long (UVL)")
        self.check_uvl.setChecked(current_uvl)
        self.check_uvl.stateChanged.connect(self.on_change)
        layout.addWidget(self.check_uvl)

        # Visual Characteristics (After Treatment)
        layout.addWidget(QLabel("Visual Characteristics (After Treatment):"))

        # AftVis
        layout.addWidget(QLabel("After Vis (Color):"))
        self.combo_aft_vis = QComboBox()
        self.combo_aft_vis.addItem("All Colors", None)
        self.load_aft_vis(current_aft_vis)
        self.combo_aft_vis.currentIndexChanged.connect(self.on_change)
        layout.addWidget(self.combo_aft_vis)

        # AftUV
        layout.addWidget(QLabel("After UV (Color):"))
        self.combo_aft_uv = QComboBox()
        self.combo_aft_uv.addItem("All Colors", None)
        self.load_aft_uv(current_aft_uv)
        self.combo_aft_uv.currentIndexChanged.connect(self.on_change)
        layout.addWidget(self.combo_aft_uv)

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
        genus_set = set()
        if query.exec("SELECT DISTINCT Lichens FROM Substances"):
             while query.next():
                 lichens_val = query.value(0)
                 if lichens_val:
                     parts = lichens_val.strip().split()
                     if parts:
                         genus_set.add(parts[0])
        
        sorted_genera = sorted(list(genus_set))
        for genus in sorted_genera:
            self.combo_genus.addItem(genus, genus)
            
        if current_genus:
            index = self.combo_genus.findData(current_genus)
            if index >= 0:
                self.combo_genus.setCurrentIndex(index)

    def load_aft_vis(self, current_val):
        query = QSqlQuery(self.db)
        if query.exec("SELECT DISTINCT AftVis FROM Substances ORDER BY AftVis"):
            while query.next():
                val = query.value(0)
                if val:
                    self.combo_aft_vis.addItem(val, val)
        
        if current_val:
            index = self.combo_aft_vis.findData(current_val)
            if index >= 0:
                self.combo_aft_vis.setCurrentIndex(index)

    def load_aft_uv(self, current_val):
        query = QSqlQuery(self.db)
        if query.exec("SELECT DISTINCT AftUV FROM Substances ORDER BY AftUV"):
            while query.next():
                val = query.value(0)
                if val:
                    self.combo_aft_uv.addItem(val, val)
        
        if current_val:
            index = self.combo_aft_uv.findData(current_val)
            if index >= 0:
                self.combo_aft_uv.setCurrentIndex(index)
                
    def on_change(self):
        group_data = self.combo_group.currentData()
        genus_data = self.combo_genus.currentData()
        is_vis = self.check_vis.isChecked()
        is_uvs = self.check_uvs.isChecked()
        is_uvl = self.check_uvl.isChecked()
        aft_vis = self.combo_aft_vis.currentData()
        aft_uv = self.combo_aft_uv.currentData()
        
        self.filterChanged.emit(self.sample_id, group_data, genus_data, 
                                is_vis, is_uvs, is_uvl,
                                aft_vis, aft_uv)
