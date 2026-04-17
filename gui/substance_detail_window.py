from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QScrollArea,
    QWidget,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QSizePolicy,
)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtSql import QSqlQuery


class SubstanceDetailWindow(QDialog):
    TLC_FIELDS = ["A", "Bprime", "C", "B", "E", "F", "G", "HPLC"]
    VISUAL_FIELDS = ["BefVis", "BefUVS", "BefUVL", "Archers", "AftVis", "AftUV"]
    SPOT_TEST_FIELDS = ["KResult", "CResult", "KCResult", "PDResult"]

    def __init__(self, substance_name, db):
        super().__init__()
        self.setWindowTitle(f"Substance Details: {substance_name}")
        self.resize(980, 760)
        self.db = db
        self._equal_height_groups = []

        layout = QVBoxLayout(self)

        title = QLabel(substance_name)
        title.setStyleSheet("font-size: 18pt; font-weight: bold; margin-bottom: 8px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()

        self.grid_layout = QGridLayout(content_widget)
        self.grid_layout.setContentsMargins(6, 6, 6, 6)
        self.grid_layout.setHorizontalSpacing(10)
        self.grid_layout.setVerticalSpacing(10)

        self.load_data(substance_name)

        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

    def _create_group_box(self, title):
        group = QGroupBox(title)
        group.setStyleSheet(
            """
            QGroupBox {
                font-size: 12pt;
                margin-top: 18px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px 0 4px;
            }
            """
        )
        form_layout = QFormLayout(group)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form_layout.setContentsMargins(10, 10, 10, 14)
        form_layout.setHorizontalSpacing(8)
        form_layout.setVerticalSpacing(6)
        return group, form_layout

    def _create_section_group(self, title):
        group = QGroupBox(title)
        group.setStyleSheet(
            """
            QGroupBox {
                font-size: 14pt;
                margin-top: 30px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 10px 4px 0 4px;
            }
            """
        )
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 12, 12, 14)
        layout.setSpacing(10)
        return group, layout

    def _create_grid_cell(self, child=None, bottom_margin=3):
        cell = QWidget()
        cell_layout = QVBoxLayout(cell)
        cell_layout.setContentsMargins(0, 0, 0, bottom_margin)
        cell_layout.setSpacing(0)
        if child is not None:
            cell_layout.addWidget(child, 0, Qt.AlignmentFlag.AlignTop)
        cell_layout.addStretch(1)
        return cell

    def _format_display_value(self, value, empty_text="-"):
        if value is None:
            return empty_text
        text = str(value).strip()
        if not text or text == "No Result":
            return empty_text
        return text

    def _create_compact_value_widget(self, field_name, value, empty_text="-"):
        label_text = "B'" if field_name == "Bprime" else field_name
        if not str(label_text).endswith(":"):
            label_text = f"{label_text}:"

        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        label = QLabel(label_text)
        label.setStyleSheet("font-weight: bold;")
        value_label = QLabel(self._format_display_value(value, empty_text))
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout.addWidget(label)
        layout.addWidget(value_label, 1)
        return widget

    def _add_compact_row(self, form_layout, items, empty_text="-"):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(14)

        for field_name, value in items:
            row_layout.addWidget(self._create_compact_value_widget(field_name, value, empty_text), 1)

        form_layout.addRow(row_widget)

    def _add_value_row(self, form_layout, field_name, value, label_override=None, empty_text="-"):
        label_text = label_override if label_override is not None else field_name
        if label_text == "Bprime":
            label_text = "B'"

        label = QLabel(label_text)
        label.setStyleSheet("font-weight: bold;")

        val_label = QLabel(self._format_display_value(value, empty_text))
        val_label.setWordWrap(True)
        val_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        form_layout.addRow(label, val_label)

    def _add_mass_spectrum_row(self, form_layout, values):
        parts = []
        for label, value in values:
            formatted = self._format_display_value(value)
            if formatted != "-":
                parts.append(f"{formatted}")
        text = ", ".join(parts) if parts else "-"
        self._add_value_row(
            form_layout,
            "Mass Spectrum",
            text,
            label_override="Mass Spectrum:",
        )

    def _sync_equal_height_groups(self):
        if not self._equal_height_groups:
            return

        for group in self._equal_height_groups:
            group.setMinimumHeight(0)
            group.setMaximumHeight(16777215)

        target_height = max(group.sizeHint().height() for group in self._equal_height_groups) + 4
        for group in self._equal_height_groups:
            group.setFixedHeight(target_height)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._sync_equal_height_groups)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_equal_height_groups()

    def _derive_lichen_genera_text(self, substance_name):
        lichen_query = QSqlQuery(self.db)
        lichen_query.prepare("SELECT DISTINCT Genus FROM Lichens WHERE Substance = :substance ORDER BY Genus")
        lichen_query.bindValue(":substance", substance_name)

        genus_list = []
        if lichen_query.exec():
            while lichen_query.next():
                genus = lichen_query.value(0)
                if genus:
                    genus_list.append(str(genus))
        return ", ".join(genus_list)

    def load_data(self, name):
        query = QSqlQuery(self.db)
        query.prepare("SELECT * FROM Substances WHERE name = :name")
        query.bindValue(":name", name)

        if not (query.exec() and query.next()):
            error_group, error_layout = self._create_group_box("Error")
            self._add_value_row(error_layout, "Message", "Substance not found in database.")
            self.grid_layout.addWidget(error_group, 0, 0)
            return

        record = query.record()
        data = {record.fieldName(i): query.value(i) for i in range(record.count())}
        genera_text = self._derive_lichen_genera_text(name)

        section_a, section_a_layout = self._create_section_group(
            "Spot characters on TLC plates (taken from Elix 2022)"
        )
        section_b, section_b_layout = self._create_section_group(
            "Substance characters based on HPLC and Mass Spectrometry (taken from Elix 2022)"
        )
        section_c, section_c_layout = self._create_section_group(
            "Additional Substance Information"
        )

        rf_group, rf_layout = self._create_group_box("Relative RF values in solvent systems")
        before_group, before_layout = self._create_group_box(
            "Spot visibility before H₂SO₄ treatment"
        )
        after_group, after_layout = self._create_group_box(
            "Spot color after H₂SO₄ treatment + heating"
        )
        spot_group, spot_layout = self._create_group_box(
            "'Spot-test'-color (on plates before H₂SO₄ treatment)"
        )
        archers_group, archers_layout = self._create_group_box(
            "Spot color after 'Archers Reagens' treatment"
        )

        for group in (rf_group, before_group, after_group, spot_group, archers_group):
            group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._equal_height_groups = [rf_group, before_group, after_group]

        self._add_compact_row(
            rf_layout,
            [("A", data.get("A")), ("Bprime", data.get("Bprime")), ("C", data.get("C"))],
        )
        self._add_compact_row(
            rf_layout,
            [("E", data.get("E")), ("B", data.get("B")), ("F", data.get("F"))],
        )
        self._add_compact_row(rf_layout, [("G", data.get("G"))])

        self._add_value_row(before_layout, "Daylight", data.get("BefVis"), label_override="Daylight:")
        self._add_value_row(before_layout, "UV254", data.get("BefUVS"), label_override="UV₂₅₄:")
        self._add_value_row(before_layout, "UV366", data.get("BefUVL"), label_override="UV₃₆₆:")

        self._add_value_row(after_layout, "Daylight", data.get("AftVis"), label_override="Daylight:")
        self._add_value_row(after_layout, "UV366", data.get("AftUV"), label_override="UV₃₆₆:")

        self._add_compact_row(
            spot_layout,
            [
                ("K", data.get("KResult")),
                ("C", data.get("CResult")),
                ("KC", data.get("KCResult")),
                ("Pd", data.get("PDResult")),
            ],
        )

        self._add_value_row(
            archers_layout,
            "Archers",
            data.get("Archers"),
            label_override="Daylight:",
        )

        section_a_grid = QGridLayout()
        section_a_grid.setContentsMargins(0, 0, 0, 0)
        section_a_grid.setHorizontalSpacing(10)
        section_a_grid.setVerticalSpacing(8)
        section_a_grid.setColumnStretch(0, 1)
        section_a_grid.setColumnStretch(1, 1)
        section_a_grid.setColumnStretch(2, 1)

        section_a_grid.addWidget(self._create_grid_cell(rf_group), 0, 0, alignment=Qt.AlignmentFlag.AlignTop)
        section_a_grid.addWidget(self._create_grid_cell(before_group), 0, 1, alignment=Qt.AlignmentFlag.AlignTop)
        section_a_grid.addWidget(self._create_grid_cell(after_group), 0, 2, alignment=Qt.AlignmentFlag.AlignTop)
        section_a_grid.addWidget(self._create_grid_cell(spot_group), 1, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignTop)
        section_a_grid.addWidget(self._create_grid_cell(archers_group), 1, 2, alignment=Qt.AlignmentFlag.AlignTop)
        section_a_layout.addLayout(section_a_grid)

        hplc_mass_group, hplc_mass_layout = self._create_group_box("")
        self._add_value_row(hplc_mass_layout, "HPLC", data.get("HPLC"), label_override="HPLC (RI value):")
        self._add_mass_spectrum_row(
            hplc_mass_layout,
            [("M", data.get("M")), ("F1", data.get("F1")), ("F2", data.get("F2")), ("F3", data.get("F3"))],
        )
        section_b_layout.addWidget(hplc_mass_group)

        left_group, left_layout = self._create_group_box("")
        right_group, right_layout = self._create_group_box("")

        self._add_value_row(left_layout, "Notes", data.get("Notes"), label_override="Notes:")
        self._add_value_row(left_layout, "Reference", data.get("Reference"), label_override="Reference:")
        self._add_value_row(left_layout, "Related", data.get("Related"), label_override="Related substances:")
        self._add_value_row(
            left_layout,
            "Lichens",
            genera_text,
            label_override="Substance occurrence in lichen genera\n(according to ITALIC and LIAS databases):",
        )

        self._add_value_row(right_layout, "Synonyms", data.get("Synonyms"), label_override="Synonyms of chemical name:")
        self._add_value_row(right_layout, "Path", data.get("Path"), label_override="Metabolic pathway:")
        self._add_value_row(right_layout, "GroupName", data.get("GroupName"), label_override="Parent Substance Group:")
        self._add_value_row(right_layout, "Class", data.get("Class"), label_override="Substance class:")

        section_c_grid = QGridLayout()
        section_c_grid.setContentsMargins(0, 0, 0, 0)
        section_c_grid.setHorizontalSpacing(10)
        section_c_grid.setVerticalSpacing(8)
        section_c_grid.setColumnStretch(0, 1)
        section_c_grid.setColumnStretch(1, 1)
        section_c_grid.addWidget(left_group, 0, 0)
        section_c_grid.addWidget(right_group, 0, 1)
        section_c_layout.addLayout(section_c_grid)

        self.grid_layout.addWidget(section_a, 0, 0)
        self.grid_layout.addWidget(section_b, 1, 0)
        self.grid_layout.addWidget(section_c, 2, 0)

        QTimer.singleShot(0, self._sync_equal_height_groups)
