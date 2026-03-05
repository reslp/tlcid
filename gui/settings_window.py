from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QDoubleSpinBox,
    QCheckBox,
)
from PyQt6.QtCore import pyqtSignal


class SettingsWindow(QWidget):
    settingsChanged = pyqtSignal(str, float, bool)

    def __init__(self, parent=None):
        super().__init__()
        self.setWindowTitle("Substance Detection Settings")
        self.resize(300, 220)

        layout = QVBoxLayout()
        self.setLayout(layout)

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

        # Relative Rf display toggle
        self.relative_rf_checkbox = QCheckBox("Toggle absolute Rf")
        self.relative_rf_checkbox.stateChanged.connect(self.on_value_changed)
        layout.addWidget(self.relative_rf_checkbox)

        layout.addStretch()

        # Close Button
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        layout.addWidget(self.close_button)

        # Initial State
        self.on_method_changed(self.method_combo.currentText())

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
        self.settingsChanged.emit(method, range_val, relative_rf)

    def set_current_settings(self, method, range_val, relative_rf=False):
        index = self.method_combo.findText(method)
        if index >= 0:
            self.method_combo.setCurrentIndex(index)
        self.range_spin.setValue(range_val)
        self.relative_rf_checkbox.setChecked(relative_rf)
