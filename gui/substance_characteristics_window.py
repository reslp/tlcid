from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QCheckBox, QSpinBox, QGridLayout, QWidget, QSizePolicy, QColorDialog
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtSql import QSqlQuery


class SubstanceCharacteristicsWindow(QDialog):
    # sample_id, group_name, genus, family, bef_vis, bef_uvs, bef_uvl, aft_vis, aft_uv, assigned_name, show_on_plate, font_size, spot_color
    filterChanged = pyqtSignal(int, str, str, str, bool, bool, bool, str, str, str, bool, int, object)

    def __init__(self, sample_id, sample_name, current_group, current_genus, current_family,
                 current_vis, current_uvs, current_uvl,
                 current_aft_vis, current_aft_uv, assigned_name, candidates, show_on_plate, font_size, current_color, db):
        super().__init__()
        self.setWindowTitle(f"Characteristics: {sample_name}")
        self.resize(650, 450)
        self.sample_id = sample_id
        self.db = db
        self.selected_color = QColor(current_color) if QColor(current_color).isValid() else QColor("white")

        layout = QVBoxLayout(self)

        header_label = QLabel(f"<b>Assign key features to substance \'{sample_name}\':</b>")
        header_label.setWordWrap(True)
        layout.addWidget(header_label)

        group_row = QHBoxLayout()
        label_group = QLabel("Assign substance class to predicted substance:")
        group_row.addWidget(label_group)
        self.combo_group = QComboBox()
        self.combo_group.addItem("All Groups", None)
        self.load_groups(current_group)
        self._set_fixed_filter_combo_width(self.combo_group)
        self.combo_group.currentIndexChanged.connect(self.on_change)
        group_row.addWidget(self.combo_group)
        group_row.addStretch()
        layout.addLayout(group_row)


        characteristics_grid = QGridLayout()
        characteristics_grid.setColumnStretch(0, 0)
        characteristics_grid.setColumnStretch(1, 1)
        characteristics_grid.setHorizontalSpacing(12)
        characteristics_grid.setVerticalSpacing(8)

        before_label = QLabel("Spot visibility on TLC plates\nbefore treatment with H₂SO₄")
        before_label.setWordWrap(True)
        characteristics_grid.addWidget(before_label, 0, 0, alignment=Qt.AlignmentFlag.AlignTop)

        before_controls_widget = QWidget()
        before_controls_layout = QHBoxLayout(before_controls_widget)
        before_controls_layout.setContentsMargins(0, 0, 0, 0)
        before_controls_layout.setSpacing(12)

        self.check_vis = QCheckBox("Daylight")
        self.check_vis.setChecked(current_vis)
        self.check_vis.stateChanged.connect(self.on_change)
        before_controls_layout.addWidget(self.check_vis)

        self.check_uvs = QCheckBox("UV₂₅₄")
        self.check_uvs.setChecked(current_uvs)
        self.check_uvs.stateChanged.connect(self.on_change)
        before_controls_layout.addWidget(self.check_uvs)

        self.check_uvl = QCheckBox("UV₃₆₆")
        self.check_uvl.setChecked(current_uvl)
        self.check_uvl.stateChanged.connect(self.on_change)
        before_controls_layout.addWidget(self.check_uvl)

        before_controls_layout.addStretch()
        characteristics_grid.addWidget(before_controls_widget, 0, 1)

        after_label = QLabel("Spot color on TLC plates\nafter treatment with H₂SO₄\nand heating")
        after_label.setWordWrap(True)
        characteristics_grid.addWidget(after_label, 1, 0, alignment=Qt.AlignmentFlag.AlignTop)

        after_controls_widget = QWidget()
        after_controls_layout = QHBoxLayout(after_controls_widget)
        after_controls_layout.setContentsMargins(0, 0, 0, 0)
        after_controls_layout.setSpacing(12)

        after_vis_label = QLabel("Daylight:")
        after_controls_layout.addWidget(after_vis_label)
        self.combo_aft_vis = QComboBox()
        self.combo_aft_vis.addItem("All Colors", None)
        self.load_aft_vis(current_aft_vis)
        self.combo_aft_vis.currentIndexChanged.connect(self.on_change)
        after_controls_layout.addWidget(self.combo_aft_vis)

        after_uv_label = QLabel("UV₃₆₆:")
        after_controls_layout.addWidget(after_uv_label)
        self.combo_aft_uv = QComboBox()
        self.combo_aft_uv.addItem("All Colors", None)
        self.load_aft_uv(current_aft_uv)
        self.combo_aft_uv.currentIndexChanged.connect(self.on_change)
        after_controls_layout.addWidget(self.combo_aft_uv)

        after_controls_layout.addStretch()
        characteristics_grid.addWidget(after_controls_widget, 1, 1)

        layout.addLayout(characteristics_grid)

        layout.addWidget(QLabel("<hr>"))

        systematics_label = QLabel("<b>Filter predicted substance based on lichen systematics:</b>")
        systematics_label.setWordWrap(True)
        layout.addWidget(systematics_label)

        systematics_filters_row = QHBoxLayout()
        label_genus = QLabel("By genus:")
        systematics_filters_row.addWidget(label_genus)
        self.combo_genus = QComboBox()
        self.combo_genus.addItem("All Genera", None)
        self.load_genera(current_genus)
        self._set_fixed_filter_combo_width(self.combo_genus)
        self.combo_genus.currentIndexChanged.connect(self.on_change)
        systematics_filters_row.addWidget(self.combo_genus)

        label_family = QLabel("By family:")
        systematics_filters_row.addWidget(label_family)
        self.combo_family = QComboBox()
        self.combo_family.addItem("All Families", None)
        self.load_families(current_family)
        self._set_fixed_filter_combo_width(self.combo_family)
        self.combo_family.currentIndexChanged.connect(self.on_change)
        systematics_filters_row.addWidget(self.combo_family)
        systematics_filters_row.addStretch()
        layout.addLayout(systematics_filters_row)

        layout.addWidget(QLabel("<hr>"))

        substance_display_label = QLabel("<b>Modify how the substance spot is displayed on the plates:</b>")
        substance_display_label.setWordWrap(True)
        layout.addWidget(substance_display_label)

        # Substance Name Assignment
        substance_name_row = QHBoxLayout()
        substance_name_row.addWidget(QLabel("Assign substance name:"))
        self.combo_assigned = QComboBox()
        self.combo_assigned.setEditable(True)
        self.combo_assigned.addItem("select from list or enter your own", None)
        self.combo_assigned.addItem(sample_name, sample_name)
        for score, name in candidates:
            if self.combo_assigned.findData(name) < 0:
                self.combo_assigned.addItem(name, name)
        
        if assigned_name:
            index = self.combo_assigned.findData(assigned_name)
            if index >= 0:
                self.combo_assigned.setCurrentIndex(index)
            else:
                self.combo_assigned.setEditText(assigned_name)
        else:
            self.combo_assigned.setCurrentIndex(0)

        self.combo_assigned.currentIndexChanged.connect(self.on_change)
        self.combo_assigned.editTextChanged.connect(self.on_change)
        self.combo_assigned.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.combo_assigned.setFixedWidth(280)
        substance_name_row.addWidget(self.combo_assigned)
        substance_name_row.addStretch()
        layout.addLayout(substance_name_row)

        show_name_row = QHBoxLayout()
        self.check_show_name = QCheckBox("Show substance name on plates")
        self.check_show_name.setChecked(show_on_plate)
        self.check_show_name.stateChanged.connect(self.on_change)
        show_name_row.addWidget(self.check_show_name)

        show_name_row.addSpacing(8)

        show_name_row.addWidget(QLabel("Font size on plate:"))

        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(6, 36)
        self.spin_font_size.setValue(font_size if font_size else 8)
        self.spin_font_size.valueChanged.connect(self.on_change)
        show_name_row.addWidget(self.spin_font_size)

        show_name_row.addWidget(QLabel("Spot color:"))
        self.color_button = QPushButton()
        self.color_button.setFixedWidth(110)
        self.color_button.clicked.connect(self.select_spot_color)
        self._update_color_button()
        show_name_row.addWidget(self.color_button)

        show_name_row.addStretch()
        layout.addLayout(show_name_row)

        layout.addStretch()

        close_row = QHBoxLayout()
        close_row.addStretch()
        btn = QPushButton("Close")
        btn.setFixedWidth(120)
        btn.clicked.connect(self.accept)
        close_row.addWidget(btn)
        layout.addLayout(close_row)

    def _set_fixed_filter_combo_width(self, combo):
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        text_width = 0
        font_metrics = combo.fontMetrics()
        for index in range(combo.count()):
            text_width = max(text_width, font_metrics.horizontalAdvance(combo.itemText(index)))

        frame_width = combo.style().pixelMetric(combo.style().PixelMetric.PM_DefaultFrameWidth, None, combo)
        arrow_width = combo.style().pixelMetric(combo.style().PixelMetric.PM_ScrollBarExtent, None, combo)
        fixed_width = text_width + (2 * frame_width) + arrow_width + 32
        combo.setFixedWidth(max(fixed_width, combo.minimumSizeHint().width()))

    def _update_color_button(self):
        color_name = self.selected_color.name().upper()
        self.color_button.setText("")
        self.color_button.setToolTip(f"Spot color: {color_name}")
        self.color_button.setStyleSheet(
            f"background-color: {color_name}; border: 1px solid #666; padding: 4px 8px;"
        )

    def _create_color_dialog(self):
        dialog = QColorDialog(self.selected_color, self)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setWindowTitle("Select Spot Color")
        return dialog

    def _restore_focus_after_color_dialog(self):
        self.raise_()
        self.activateWindow()
        self.color_button.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _apply_selected_color(self, new_color):
        if not new_color.isValid():
            return
        self.selected_color = QColor(new_color)
        self._update_color_button()
        self.on_change()

    def select_spot_color(self):
        dialog = self._create_color_dialog()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._apply_selected_color(dialog.selectedColor())
        QTimer.singleShot(0, self._restore_focus_after_color_dialog)

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
        # Extract unique genera from Lichens table (new format)
        genus_set = set()
        if query.exec("SELECT DISTINCT Genus FROM Lichens ORDER BY Genus"):
            while query.next():
                genus = query.value(0)
                if genus:
                    genus_set.add(genus)

        sorted_genera = sorted(list(genus_set))
        for genus in sorted_genera:
            self.combo_genus.addItem(genus, genus)

        if current_genus:
            index = self.combo_genus.findData(current_genus)
            if index >= 0:
                self.combo_genus.setCurrentIndex(index)

    def load_families(self, current_family):
        query = QSqlQuery(self.db)
        family_set = set()
        if query.exec("SELECT DISTINCT Family FROM Lichens ORDER BY Family"):
            while query.next():
                family = query.value(0)
                if family:
                    family_set.add(family)

        sorted_families = sorted(list(family_set))
        for family in sorted_families:
            self.combo_family.addItem(family, family)

        if current_family:
            index = self.combo_family.findData(current_family)
            if index >= 0:
                self.combo_family.setCurrentIndex(index)

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
        family_data = self.combo_family.currentData()
        is_vis = self.check_vis.isChecked()
        is_uvs = self.check_uvs.isChecked()
        is_uvl = self.check_uvl.isChecked()
        aft_vis = self.combo_aft_vis.currentData()
        aft_uv = self.combo_aft_uv.currentData()

        assigned_name = self.combo_assigned.currentText()
        if self.combo_assigned.currentIndex() == 0 and assigned_name == "select from list or enter your own":
            assigned_name = None

        show_on_plate = self.check_show_name.isChecked()
        font_size = self.spin_font_size.value()

        self.filterChanged.emit(self.sample_id, group_data, genus_data, family_data,
                                is_vis, is_uvs, is_uvl,
                                aft_vis, aft_uv, assigned_name, show_on_plate, font_size, QColor(self.selected_color))
