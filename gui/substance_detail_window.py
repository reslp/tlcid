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

        self.load_data(substance_name)

        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

    def _create_group_box(self, title):
        group = QGroupBox(title)
        form_layout = QFormLayout(group)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        return group, form_layout

    def _add_value_row(self, form_layout, field_name, value):
        label = QLabel(field_name)
        label.setStyleSheet("font-weight: bold;")

        val_label = QLabel(str(value) if value is not None else "")
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
            visual_group, visual_layout = self._create_group_box("Visual Characteristics")
            additional_group, additional_layout = self._create_group_box("Additional Substance information")

            for i in range(record.count()):
                field_name = record.fieldName(i)

                # Do not repeat the substance name inside the scrollable details form
                if field_name == "name":
                    continue

                value = query.value(i)

                if field_name in self.TLC_FIELDS:
                    self._add_value_row(tlc_layout, field_name, value)
                elif field_name in self.VISUAL_FIELDS:
                    self._add_value_row(visual_layout, field_name, value)
                else:
                    self._add_value_row(additional_layout, field_name, value)

            # Row 0: two-column layout for TLC + Visual groups
            self.grid_layout.addWidget(tlc_group, 0, 0)
            self.grid_layout.addWidget(visual_group, 0, 1)

            # Row 1: single-column group spanning both columns
            self.grid_layout.addWidget(additional_group, 1, 0, 1, 2)
        else:
            error_group, error_layout = self._create_group_box("Error")
            self._add_value_row(error_layout, "Message", "Substance not found in database.")
            self.grid_layout.addWidget(error_group, 0, 0, 1, 2)
