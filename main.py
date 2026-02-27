import sys
from PyQt6.QtWidgets import QApplication
from gui.mainwindow import MainWindow


def main():
    raw_args = sys.argv[1:]
    debug_mode = "--debug" in raw_args
    qt_args = [sys.argv[0]] + [arg for arg in raw_args if arg != "--debug"]

    app = QApplication(qt_args)
    window = MainWindow(debug_mode=debug_mode)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
