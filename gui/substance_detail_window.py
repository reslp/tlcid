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
    VISUAL_LABELS = {"BefVis": "Daylight:", "BefUVS": "UV₂₅₄:", "BefUVL": "UV₃₆₆:", "Archers": "Archers Reagens:", "AftVis": "Daylight:", "AftUV": "UV:"}
    SPOT_TEST_FIELDS = ["KResult", "CResult", "KCResult", "PDResult"]
    SPOT_TEST_LABELS = {"KResult": "K:", "CResult": "C:", "KCResult": "KC:", "PDResult": "PD:"}

    def __init__(self, substance_name, db):
        super().__init__()
        self.setWindowTitle(f"Substance Details: {substance_name}")
        self.resize(700, 650)
        self.db = db
        self._first_row_tlc_groups = []

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
        form_layout.setContentsMargins(10, 10, 10, 12)
        form_layout.setHorizontalSpacing(8)
        form_layout.setVerticalSpacing(6)
        return group, form_layout

    def _create_grid_cell(self, child=None, bottom_margin=2):
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

    def _add_value_row(self, form_layout, field_name, value):
        label_text = "B'" if field_name == "Bprime" else field_name
        label = QLabel(label_text)
        label.setStyleSheet("font-weight: bold;")

        val_label = QLabel(self._format_display_value(value))
        val_label.setWordWrap(True)
        val_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        form_layout.addRow(label, val_label)

    def _add_spot_test_row(self, form_layout, field_name, value):
        label_text = self.SPOT_TEST_LABELS.get(field_name, field_name)
        label = QLabel(label_text)
        label.setStyleSheet("font-weight: bold;")

        val_label = QLabel(self._format_display_value(value))
        val_label.setWordWrap(True)
        val_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        form_layout.addRow(label, val_label)

    def _add_visual_field_row(self, form_layout, field_name, value):
        label_text = self.VISUAL_LABELS.get(field_name, field_name)
        label = QLabel(label_text)
        label.setStyleSheet("font-weight: bold;")

        val_label = QLabel(self._format_display_value(value))
        val_label.setWordWrap(True)
        val_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        form_layout.addRow(label, val_label)

    def _sync_first_row_tlc_box_heights(self):
        if not self._first_row_tlc_groups:
            return

        target_height = 0
        for group in self._first_row_tlc_groups:
            group_width = group.width() if group.width() > 0 else group.sizeHint().width()
            group_height = group.sizeHint().height()
            if group.layout() is not None and group.layout().hasHeightForWidth() and group_width > 0:
                contents = group.contentsMargins()
                inner_width = max(0, group_width - contents.left() - contents.right())
                group_height = max(group_height, group.layout().totalHeightForWidth(inner_width) + contents.top() + contents.bottom())
            target_height = max(target_height, group_height)

        if target_height <= 0:
            return

        for group in self._first_row_tlc_groups:
            group.setFixedHeight(target_height)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._sync_first_row_tlc_box_heights)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_first_row_tlc_box_heights()

    def load_data(self, name):
        query = QSqlQuery(self.db)
        query.prepare("SELECT * FROM Substances WHERE name = :name")
        query.bindValue(":name", name)

        if query.exec() and query.next():
            record = query.record()

            tlc_group = QGroupBox("TLC spot characters")
            tlc_group_layout = QVBoxLayout(tlc_group)
            tlc_group_layout.setContentsMargins(10, 10, 10, 12)
            tlc_group_layout.setSpacing(10)

            rf_group, rf_layout = self._create_group_box("Rf values")
            before_group, before_layout = self._create_group_box("Color before H₂SO₄ treatment")
            after_group, after_layout = self._create_group_box("After H₂SO₄ treatment")
            spot_group, spot_layout = self._create_group_box("Spot Tests")
            archers_group, archers_layout = self._create_group_box("Archers Reagens")
            additional_group, additional_layout = self._create_group_box("Additional Substance information")

            for group in (rf_group, before_group, after_group, spot_group, archers_group):
                group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

            tlc_values = {}
            visual_values = {}
            spot_test_values = {}
            archers_value = None

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

                if field_name == "name":
                    continue

                value = query.value(i)

                if field_name in self.TLC_FIELDS:
                    tlc_values[field_name] = value
                elif field_name in self.VISUAL_FIELDS:
                    if field_name == "Archers":
                        archers_value = value
                    else:
                        visual_values[field_name] = value
                elif field_name in self.SPOT_TEST_FIELDS:
                    spot_test_values[field_name] = value
                elif field_name == "GLossID":
                    pass
                elif field_name == "Lichens":
                    self._add_value_row(additional_layout, field_name, lichen_genera_text)
                else:
                    self._add_value_row(additional_layout, field_name, value)

            self._add_compact_row(rf_layout, [("A", tlc_values.get("A")), ("Bprime", tlc_values.get("Bprime")), ("C", tlc_values.get("C"))])
            self._add_compact_row(rf_layout, [("B", tlc_values.get("B")), ("E", tlc_values.get("E")), ("F", tlc_values.get("F"))])
            self._add_compact_row(rf_layout, [("G", tlc_values.get("G")), ("HPLC", tlc_values.get("HPLC"))])

            self._add_compact_row(before_layout, [("Daylight", visual_values.get("BefVis")), ("UV₂₅₄", visual_values.get("BefUVS")), ("UV₃₆₆", visual_values.get("BefUVL"))])
            self._add_compact_row(after_layout, [("Daylight", visual_values.get("AftVis")), ("UV", visual_values.get("AftUV"))])

            self._add_compact_row(spot_layout, [("K", spot_test_values.get("KResult")), ("C", spot_test_values.get("CResult"))])
            self._add_compact_row(spot_layout, [("KC", spot_test_values.get("KCResult")), ("PD", spot_test_values.get("PDResult"))])
            self._add_compact_row(archers_layout, [("Archers", archers_value)])

            tlc_boxes_layout = QGridLayout()
            tlc_boxes_layout.setContentsMargins(0, 0, 0, 2)
            tlc_boxes_layout.setHorizontalSpacing(10)
            tlc_boxes_layout.setVerticalSpacing(6)
            tlc_boxes_layout.setColumnStretch(0, 1)
            tlc_boxes_layout.setColumnStretch(1, 1)
            tlc_boxes_layout.setColumnStretch(2, 1)
            tlc_boxes_layout.setRowStretch(0, 0)
            tlc_boxes_layout.setRowStretch(1, 0)

            self._first_row_tlc_groups = [rf_group, before_group, spot_group]

            row0_col0 = self._create_grid_cell(rf_group, bottom_margin=1)
            row0_col1 = self._create_grid_cell(before_group, bottom_margin=1)
            row0_col2 = self._create_grid_cell(spot_group, bottom_margin=1)
            row1_col0 = self._create_grid_cell()
            row1_col1 = self._create_grid_cell(after_group)
            row1_col2 = self._create_grid_cell(archers_group)

            # Strict geometry: the three first-row boxes are sibling widgets in grid row 0,
            # each wrapped by an identical zero-margin cell and anchored to the cell top.
            tlc_boxes_layout.addWidget(row0_col0, 0, 0, alignment=Qt.AlignmentFlag.AlignTop)
            tlc_boxes_layout.addWidget(row0_col1, 0, 1, alignment=Qt.AlignmentFlag.AlignTop)
            tlc_boxes_layout.addWidget(row0_col2, 0, 2, alignment=Qt.AlignmentFlag.AlignTop)
            tlc_boxes_layout.addWidget(row1_col0, 1, 0, alignment=Qt.AlignmentFlag.AlignTop)
            tlc_boxes_layout.addWidget(row1_col1, 1, 1, alignment=Qt.AlignmentFlag.AlignTop)
            tlc_boxes_layout.addWidget(row1_col2, 1, 2, alignment=Qt.AlignmentFlag.AlignTop)

            tlc_group_layout.addLayout(tlc_boxes_layout)

            self.grid_layout.addWidget(tlc_group, 0, 0, 1, 3)
            self.grid_layout.addWidget(additional_group, 1, 0, 1, 3)
            QTimer.singleShot(0, self._sync_first_row_tlc_box_heights)
        else:
            error_group, error_layout = self._create_group_box("Error")
            self._add_value_row(error_layout, "Message", "Substance not found in database.")
            self.grid_layout.addWidget(error_group, 0, 0, 1, 3)
