from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QDoubleSpinBox,
    QCheckBox,
    QTabWidget,
)
from PyQt6.QtCore import QSignalBlocker, pyqtSignal


class SettingsWindow(QWidget):
    settingsChanged = pyqtSignal(str, float, bool, bool, bool, bool)
    appearanceChanged = pyqtSignal(bool)
    genusFilterChanged = pyqtSignal(str)
    familyFilterChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__()
        self.setWindowTitle("Settings")
        self.resize(360, 360)

        main_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        general_tab = QWidget()
        self.tabs.addTab(general_tab, "General")
        appearance_tab = QWidget()
        self.tabs.addTab(appearance_tab, "Appearance")
        appearance_layout = QVBoxLayout(appearance_tab)
        self.distinct_reference_sequences_checkbox = QCheckBox("Distinct reference substances")
        self.distinct_reference_sequences_checkbox.toggled.connect(self.appearanceChanged.emit)
        appearance_layout.addWidget(self.distinct_reference_sequences_checkbox)
        self.tabs.addTab(QWidget(), "Advanced")
        layout = QVBoxLayout(general_tab)

        # Method Selection
        label = QLabel("Select Substance Detection Method:")
        layout.addWidget(label)

        self.method_combo = QComboBox()
        self.method_combo.addItems(["MSE", "Range"])
        self.method_combo.currentTextChanged.connect(self.on_method_changed)
        layout.addWidget(self.method_combo)

        # Range Input (Sensitivity)
        self.range_label = QLabel("Sensitivity Range (+/- Rf):")
        layout.addWidget(self.range_label)

        self.range_spin = QDoubleSpinBox()
        self.range_spin.setRange(0.0, 1.0)
        self.range_spin.setSingleStep(0.01)
        self.range_spin.setValue(0.05)
        self.range_spin.valueChanged.connect(self.on_value_changed)
        layout.addWidget(self.range_spin)

        # Relative Rf display toggle (default: enabled)
        self.relative_rf_checkbox = QCheckBox("Toggle absolute Rf")
        self.relative_rf_checkbox.setChecked(True)
        self.relative_rf_checkbox.stateChanged.connect(self.on_value_changed)
        layout.addWidget(self.relative_rf_checkbox)

        self.allow_missing_rf_checkbox = QCheckBox("Allow missing Rf values")
        self.allow_missing_rf_checkbox.setChecked(False)
        self.allow_missing_rf_checkbox.stateChanged.connect(self.on_value_changed)
        layout.addWidget(self.allow_missing_rf_checkbox)

        genus_label = QLabel("Global Genus Filter:")
        layout.addWidget(genus_label)
        self.global_genus_combo = QComboBox()
        self.global_genus_combo.addItem("All genera", None)
        genus_label.setBuddy(self.global_genus_combo)
        self.global_genus_combo.currentIndexChanged.connect(
            lambda _: self.genusFilterChanged.emit(self.global_genus_combo.currentData() or '')
        )
        layout.addWidget(self.global_genus_combo)

        family_label = QLabel("Global Family Filter:")
        layout.addWidget(family_label)
        self.global_family_combo = QComboBox()
        self.global_family_combo.addItem("All families", None)
        family_label.setBuddy(self.global_family_combo)
        self.global_family_combo.currentIndexChanged.connect(
            lambda _: self.familyFilterChanged.emit(self.global_family_combo.currentData() or '')
        )
        layout.addWidget(self.global_family_combo)

        self.display_support_lines_checkbox = QCheckBox("Display support lines")
        self.display_support_lines_checkbox.setChecked(False)
        self.display_support_lines_checkbox.stateChanged.connect(self.on_value_changed)
        appearance_layout.addWidget(self.display_support_lines_checkbox)

        self.display_rf_classes_checkbox = QCheckBox("Display Rf classes")
        self.display_rf_classes_checkbox.setChecked(False)
        self.display_rf_classes_checkbox.stateChanged.connect(self.on_value_changed)
        appearance_layout.addWidget(self.display_rf_classes_checkbox)
        appearance_layout.addStretch()

        layout.addStretch()

        # Close Button
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        main_layout.addWidget(self.close_button)

        # Initial State
        self.on_method_changed(self.method_combo.currentText())

    def set_genus_options(self, genera, selected=None):
        with QSignalBlocker(self.global_genus_combo):
            self.global_genus_combo.clear()
            self.global_genus_combo.addItem("All genera", None)
            options = {genus for genus in genera if genus}
            if selected:
                options.add(selected)
            for genus in sorted(options, key=str.casefold):
                self.global_genus_combo.addItem(genus, genus)
            index = self.global_genus_combo.findData(selected)
            self.global_genus_combo.setCurrentIndex(max(0, index))

    def set_family_options(self, families, selected=None):
        with QSignalBlocker(self.global_family_combo):
            self.global_family_combo.clear()
            self.global_family_combo.addItem("All families", None)
            options = {family for family in families if family}
            if selected:
                options.add(selected)
            for family in sorted(options, key=str.casefold):
                self.global_family_combo.addItem(family, family)
            index = self.global_family_combo.findData(selected)
            self.global_family_combo.setCurrentIndex(max(0, index))

    def set_current_appearance(self, distinct_reference_sequences):
        with QSignalBlocker(self.distinct_reference_sequences_checkbox):
            self.distinct_reference_sequences_checkbox.setChecked(distinct_reference_sequences)

    def on_method_changed(self, text):
        is_range = text == "Range"
        self.range_label.setVisible(is_range)
        self.range_spin.setVisible(is_range)
        self.emit_settings()

    def on_value_changed(self, _val):
        self.emit_settings()

    def emit_settings(self):
        method = self.method_combo.currentText()
        range_val = self.range_spin.value()
        relative_rf = self.relative_rf_checkbox.isChecked()
        allow_missing_rf = self.allow_missing_rf_checkbox.isChecked()
        display_support_lines = self.display_support_lines_checkbox.isChecked()
        display_rf_classes = self.display_rf_classes_checkbox.isChecked()
        self.settingsChanged.emit(
            method,
            range_val,
            relative_rf,
            allow_missing_rf,
            display_rf_classes,
            display_support_lines,
        )

    def set_current_settings(self, method, range_val, relative_rf=True, allow_missing_rf=False, display_rf_classes=False, display_support_lines=False):
        self.method_combo.blockSignals(True)
        self.range_spin.blockSignals(True)
        self.relative_rf_checkbox.blockSignals(True)
        self.allow_missing_rf_checkbox.blockSignals(True)
        self.display_support_lines_checkbox.blockSignals(True)
        self.display_rf_classes_checkbox.blockSignals(True)

        index = self.method_combo.findText(method)
        if index >= 0:
            self.method_combo.setCurrentIndex(index)
        self.range_spin.setValue(range_val)
        self.relative_rf_checkbox.setChecked(relative_rf)
        self.allow_missing_rf_checkbox.setChecked(allow_missing_rf)
        self.display_support_lines_checkbox.setChecked(display_support_lines)
        self.display_rf_classes_checkbox.setChecked(display_rf_classes)

        self.method_combo.blockSignals(False)
        self.range_spin.blockSignals(False)
        self.relative_rf_checkbox.blockSignals(False)
        self.allow_missing_rf_checkbox.blockSignals(False)
        self.display_support_lines_checkbox.blockSignals(False)
        self.display_rf_classes_checkbox.blockSignals(False)

        # Keep range visibility in sync with method even when signals are blocked.
        is_range = self.method_combo.currentText() == "Range"
        self.range_label.setVisible(is_range)
        self.range_spin.setVisible(is_range)
