"""Small plain-text editor for a plate spot's note."""

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout


class SubstanceNoteWindow(QDialog):
    def __init__(self, sample_name, note, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Note: {sample_name}")
        self.resize(380, 240)

        layout = QVBoxLayout(self)
        self.textbox = QPlainTextEdit()
        self.textbox.setPlaceholderText("Enter a note about this spot. Saved when closed.")
        self.textbox.setPlainText(note)
        layout.addWidget(self.textbox)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self.textbox.setFocus()
