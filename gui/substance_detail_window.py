from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QScrollArea,
    QWidget,
    QFormLayout,
    QGridLayout,
    QGroupBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtSql import QSqlQuery


class SubstanceDetailWindow(QDialog):
    TLC_FIELDS = ["A", "Bprime", "C", "B", "E", "F", "G", "HPLC"]
    VISUAL_FIELDS = ["BefVis", "BefUVS", "BefUVL", "Archers", "AftVis", "AftUV"]
    VISUAL_LABELS = {"BefVis": "Daylight:", "BefUVS": "Short Wavelength UV:", "BefUVL": "Long Wavelength UV:", "Archers": "Archers Reagens:", "AftVis": "Daylight:", "AftUV": "UV Light:"}
    SPOT_TEST_FIELDS = ["KResult", "CResult", "KCResult", "PDResult"]
    SPOT_TEST_LABELS = {"KResult": "K:", "CResult": "C:", "KCResult": "KC:", "PDResult": "PD:"}

    def __init__(self, substance_name, db):
        super().__init__()
        self.setWindowTitle(f"Substance Details: {substance_name}")
        self.resize(700, 650)
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

        self.grid_layout = QGridLayout(content_widget)
        self.grid_layout.setColumnStretch(0, 1)
        self.grid_layout.setColumnStretch(1, 1)
        self.grid_layout.setColumnStretch(2, 1)

        self.load_data(substance_name)

        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

    def _create_group_box(self, title):
        group = QGroupBox(title)
        form_layout = QFormLayout(group)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        return group, form_layout

    def _add_value_row(self, form_layout, field_name, value):
        label_text = "B'" if field_name == "Bprime" else field_name
        label = QLabel(label_text)
        label.setStyleSheet("font-weight: bold;")

        val_label = QLabel(str(value) if value is not None else "")
        val_label.setWordWrap(True)
        val_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        form_layout.addRow(label, val_label)

    def _add_spot_test_row(self, form_layout, field_name, value):
        # Use shortened label from SPOT_TEST_LABELS
        label_text = self.SPOT_TEST_LABELS.get(field_name, field_name)
        label = QLabel(label_text)
        label.setStyleSheet("font-weight: bold;")

        # Display "No Result" if value is empty, otherwise show the value
        val_label = QLabel(str(value) if value is not None and value != "" else "No Result")
        val_label.setWordWrap(True)
        val_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        form_layout.addRow(label, val_label)

    def _add_visual_field_row(self, form_layout, field_name, value):
        # Use shortened label from VISUAL_LABELS
        label_text = self.VISUAL_LABELS.get(field_name, field_name)
        label = QLabel(label_text)
        label.setStyleSheet("font-weight: bold;")

        # Display "No Result" if value is empty, otherwise show the value
        val_label = QLabel(str(value) if value is not None and value != "" else "No Result")
        val_label.setWordWrap(True)
        val_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        form_layout.addRow(label, val_label)

    def load_data(self, name):
        query = QSqlQuery(self.db)
        query.prepare("SELECT * FROM Substances WHERE name = :name")
        query.bindValue(":name", name)

        if query.exec() and query.next():
            record = query.record()

            tlc_group, tlc_layout = self._create_group_box("TLC Characteristics")
            spot_test_group, spot_test_layout = self._create_group_box("Spot Tests")
            additional_group, additional_layout = self._create_group_box("Additional Substance information")

            # Collect field values for grouped rendering
            tlc_values = {}
            visual_values = {}
            archers_value = None

            # Resolve lichen genera for this substance from Lichens mapping table
            lichen_genera_text = ""
            lichen_query = QSqlQuery(self.db)
            lichen_query.prepare("SELECT DISTINCT Genus FROM Lichens WHERE Substance = :substance ORDER BY Genus")
            lichen_query.bindValue(":substance", name)
            if lichen_query.exec():
                genus_list = []
                while lichen_query.next():
                    genus = lichen_query.value(0)
                    if genus:
                        genus_list.append(str(genus))
                lichen_genera_text = ", ".join(genus_list)

            for i in range(record.count()):
                field_name = record.fieldName(i)

                # Do not repeat the substance name inside the scrollable details form
                if field_name == "name":
                    continue

                value = query.value(i)

                if field_name in self.TLC_FIELDS:
                    tlc_values[field_name] = value
                elif field_name in self.VISUAL_FIELDS:
                    # Collect visual fields, but handle Archers separately
                    if field_name == "Archers":
                        archers_value = value
                    else:
                        visual_values[field_name] = value
                elif field_name in self.SPOT_TEST_FIELDS:
                    self._add_spot_test_row(spot_test_layout, field_name, value)
                elif field_name == "GLossID":
                    # Skip GLossID field from display
                    pass
                elif field_name == "Lichens":
                    # Show genera from Lichens mapping table instead of legacy Substances.Lichens content
                    self._add_value_row(additional_layout, field_name, lichen_genera_text)
                else:
                    self._add_value_row(additional_layout, field_name, value)

            # Render TLC fields in required order: A, Bprime, C, then remaining TLC fields
            ordered_tlc_fields = ["A", "Bprime", "C"] + [f for f in self.TLC_FIELDS if f not in {"A", "Bprime", "C"}]
            for field in ordered_tlc_fields:
                if field in tlc_values:
                    self._add_value_row(tlc_layout, field, tlc_values[field])

            # First row as three columns: TLC | Before treatment | After treatment
            self.grid_layout.addWidget(tlc_group, 0, 0, 1, 1)

            before_group, before_layout = self._create_group_box("Before sulfuric acid treatment")
            for field in ["BefVis", "BefUVS", "BefUVL"]:
                if field in visual_values:
                    self._add_visual_field_row(before_layout, field, visual_values[field])
            if before_layout.count() > 0:  # Only add if there are fields
                self.grid_layout.addWidget(before_group, 0, 1, 1, 1)

            after_group, after_layout = self._create_group_box("After sulfuric acid treatment")
            for field in ["AftVis", "AftUV"]:
                if field in visual_values:
                    self._add_visual_field_row(after_layout, field, visual_values[field])
            if after_layout.count() > 0:  # Only add if there are fields
                self.grid_layout.addWidget(after_group, 0, 2, 1, 1)

            # Row 1 (2 columns): Spot Tests | Archers
            self.grid_layout.addWidget(spot_test_group, 1, 0, 1, 2)

            archers_group, archers_layout = self._create_group_box("Archers Reagens")
            self._add_visual_field_row(archers_layout, "Archers", archers_value)
            self.grid_layout.addWidget(archers_group, 1, 2, 1, 1)

            # Row 2 (1 column): Additional Substance information
            self.grid_layout.addWidget(additional_group, 2, 0, 1, 3)
        else:
            error_group, error_layout = self._create_group_box("Error")
            self._add_value_row(error_layout, "Message", "Substance not found in database.")
            self.grid_layout.addWidget(error_group, 0, 0, 1, 3)
