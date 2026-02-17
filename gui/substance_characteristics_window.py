from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QCheckBox, QSpinBox
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtSql import QSqlQuery

class SubstanceCharacteristicsWindow(QDialog):
    # sample_id, group_name, genus, bef_vis, bef_uvs, bef_uvl, aft_vis, aft_uv, assigned_name, show_on_plate, font_size
    filterChanged = pyqtSignal(int, str, str, bool, bool, bool, str, str, str, bool, int)

    def __init__(self, sample_id, sample_name, current_group, current_genus,
                 current_vis, current_uvs, current_uvl,
                 current_aft_vis, current_aft_uv, assigned_name, candidates, show_on_plate, font_size, db):
        super().__init__()
        self.setWindowTitle(f"Characteristics: {sample_name}")
        self.resize(400, 800)
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

        layout.addWidget(QLabel("<hr>"))

        # Substance Name Assignment
        layout.addWidget(QLabel(f"<b>Assign Substance Name:</b>"))
        self.combo_assigned = QComboBox()
        self.combo_assigned.setEditable(True)
        self.combo_assigned.addItem("Default (Substance X)", None)
        for c in candidates:
            self.combo_assigned.addItem(c, c)
        
        if assigned_name:
            self.combo_assigned.setEditText(assigned_name)
        else:
            self.combo_assigned.setCurrentIndex(0)

        self.combo_assigned.currentIndexChanged.connect(self.on_change)
        self.combo_assigned.editTextChanged.connect(self.on_change)
        layout.addWidget(self.combo_assigned)

        self.check_show_name = QCheckBox("Show name on plate")
        self.check_show_name.setChecked(show_on_plate)
        self.check_show_name.stateChanged.connect(self.on_change)
        layout.addWidget(self.check_show_name)

        layout.addWidget(QLabel("<hr>"))

        # Font Size for On-Plate Label
        layout.addWidget(QLabel(f"<b>Font Size for On-Plate Label:</b>"))

        # Use a horizontal layout to make spinbox occupy 33% of width
        font_layout = QHBoxLayout()
        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(6, 36)
        self.spin_font_size.setValue(font_size if font_size else 8)
        self.spin_font_size.valueChanged.connect(self.on_change)
        font_layout.addWidget(self.spin_font_size, stretch=1)  # 1/8 of the space
        font_layout.addStretch(stretch=7)  # 7/8 of the space
        layout.addLayout(font_layout)

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

        assigned_name = self.combo_assigned.currentText()
        if self.combo_assigned.currentIndex() == 0 and assigned_name == "Default (Substance X)":
            assigned_name = None

        show_on_plate = self.check_show_name.isChecked()
        font_size = self.spin_font_size.value()

        self.filterChanged.emit(self.sample_id, group_data, genus_data,
                                is_vis, is_uvs, is_uvl,
                                aft_vis, aft_uv, assigned_name, show_on_plate, font_size)
