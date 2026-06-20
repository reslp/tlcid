from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                             QLabel, QPushButton, QFileDialog, QSizePolicy,
                             QTableWidget, QHeaderView, QColorDialog,
                             QMessageBox, QDoubleSpinBox, QDialog, QMenu, QToolButton,
                             QSplitter)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer, QRect
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QCloseEvent, QIcon
from urllib.parse import unquote
from pathlib import Path

from gui.analysis_io import AnalysisSerializer
from gui.calibration import (
    CALIBRATION_MODE_LINEAR,
    CALIBRATION_MODE_NEAREST,
    correct_rf,
    normalize_calibration_mode as _normalize_calibration_mode,
    support_line_raw_rf,
)
from gui.prediction_service import PredictionService
from gui.reference_repository import ReferenceRepository
from gui.report_generator import PDFReportGenerator
from gui.results_table_renderer import ResultsTableRenderer
from gui.reference_standards import (
    REFERENCE_STANDARDS,
    get_reference_standard,
    predefined_reference_rf_values,
    reference_standard_name_for_rf_value,
)


ICON_DIR = Path(__file__).resolve().parent / "icons"
CUSTOM_HORIZONTAL_LINE_COLOR = "#0065C1"
CUSTOM_VERTICAL_LINE_COLOR = "#990000"
CUSTOM_LINE_BASE_WIDTH = 1.5
START_LINE_HINT_TEXT = "For best results, adjust start line position."


def _make_icon_button(icon_filename, tooltip_text, fallback_text):
    button = QPushButton()
    button.setToolTip(tooltip_text)
    button.setAccessibleName(tooltip_text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)

    icon = QIcon(str(ICON_DIR / icon_filename))
    if icon.isNull():
        # Fallback for environments without SVG icon support
        button.setText(fallback_text)
        button.setMinimumWidth(40)
        button.setIconSize(QSize(24, 24))
    else:
        # Icon-only modern button (no default rectangular frame)
        button.setIcon(icon)
        button.setText("")
        button.setFixedSize(40, 40)
        button.setIconSize(QSize(38, 38))
        button.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                border-radius: 5px;
                padding: 2px;
            }
            QPushButton:hover {
                background: rgba(0, 0, 0, 0.5);
            }
            QPushButton:pressed {
                background: rgba(0, 0, 0, 1);
            }
        """)
    return button


def _make_custom_line_pen(orientation, width):
    if orientation == "horizontal":
        color = QColor(CUSTOM_HORIZONTAL_LINE_COLOR)
    elif orientation == "vertical":
        color = QColor(CUSTOM_VERTICAL_LINE_COLOR)
    else:
        raise ValueError(f"Unsupported line orientation: {orientation}")

    pen = QPen(color)
    pen.setWidthF(width)
    pen.setStyle(Qt.PenStyle.DashLine)
    return pen


class SquareLabel(QLabel):
    linesMoved = pyqtSignal(float, float) # Signal emitting (start_y, front_y)
    spotsChanged = pyqtSignal(list) # Signal emitting list of spots data

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(100, 100)
        self._original_pixmap = None
        self.setText("No Image Loaded")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("border: 1px solid #ccc; background-color: #f0f0f0;")
        size_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        size_policy.setHeightForWidth(True)
        self.setSizePolicy(size_policy)
        self.setMouseTracking(True) # Enable mouse tracking for hover effects

        # Line positions
        self.start_line_y = 0.9
        self.front_line_y = 0.1
        self.show_lines = False

        # Spot Handling
        # list of {'sample_id': int, 'x': float, 'y': float}
        self.spots = []
        self.spot_radius = 8
        self.adding_sample_mode = False
        self.current_sample_id = None
        self.dragged_spot_index = None
        self.global_colors = {}
        self.global_names = {}
        self.global_font_sizes = {}  # Map: sample_id -> font_size for on-plate labels
        self.highlighted_samples = set()  # Set of sample IDs that should be highlighted

        # Line Dragging State
        self.dragged_line = None # "Start" or "Front"
        self.show_support_lines = False
        self.support_line_y_mapper = None
        self.support_line_specs_provider = None
        self.custom_line_rf_label_provider = None
        self.custom_lines = []  # list of {'orientation': 'horizontal'|'vertical', 'position': float}
        self.dragged_custom_line_index = None
        self.show_start_line_adjust_hint = False

    def set_global_colors(self, colors):
        self.global_colors = colors

    def set_global_names(self, names):
        self.global_names = names
        self.update()

    def set_global_font_sizes(self, font_sizes):
        self.global_font_sizes = font_sizes
        self.update()

    def set_highlighted_samples(self, highlighted_sids):
        self.highlighted_samples = set(highlighted_sids)
        self.update()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return width

    def set_add_sample_mode(self, enabled, sample_id=None):
        self.adding_sample_mode = enabled
        self.current_sample_id = sample_id
        if enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def add_custom_line(self, orientation):
        if orientation not in {"horizontal", "vertical"}:
            raise ValueError(f"Unsupported line orientation: {orientation}")
        self.custom_lines.append({
            "orientation": orientation,
            "position": 0.5,
        })
        self.update()

    def _find_custom_line_index(self, click_x, click_y):
        if not self.show_lines:
            return None

        hit_threshold = 8
        closest_index = None
        closest_distance = float('inf')

        for idx, line in enumerate(self.custom_lines):
            position = float(line.get("position", 0.5))
            if line.get("orientation") == "horizontal":
                distance = abs(click_y - (position * self.height()))
            elif line.get("orientation") == "vertical":
                distance = abs(click_x - (position * self.width()))
            else:
                continue

            if distance <= hit_threshold and distance < closest_distance:
                closest_distance = distance
                closest_index = idx

        return closest_index

    def _custom_line_cursor(self, line):
        if line.get("orientation") == "vertical":
            return Qt.CursorShape.SplitHCursor
        return Qt.CursorShape.SplitVCursor

    def set_image(self, pixmap, show_start_line_adjust_hint=True):
        self._original_pixmap = pixmap
        self.show_lines = True
        self.show_start_line_adjust_hint = bool(show_start_line_adjust_hint)
        self.setText("")
        self.update_display()
        self.linesMoved.emit(1.0 - self.start_line_y, 1.0 - self.front_line_y)

    def resizeEvent(self, event):
        self.update_display()
        super().resizeEvent(event)

    def mouseMoveEvent(self, event):
        x_norm = event.position().x() / self.width()
        y_norm = event.position().y() / self.height()
        x_norm = max(0.0, min(1.0, x_norm))
        y_norm = max(0.0, min(1.0, y_norm))

        # Cursor feedback for lines (only when show_lines is True)
        if (
            not self.adding_sample_mode
            and self.dragged_spot_index is None
            and self.dragged_line is None
            and self.dragged_custom_line_index is None
        ):
            custom_line_index = self._find_custom_line_index(event.position().x(), event.position().y())
            if custom_line_index is not None:
                self.setCursor(self._custom_line_cursor(self.custom_lines[custom_line_index]))
            elif self.show_lines:
                start_px = self.start_line_y * self.height()
                front_px = self.front_line_y * self.height()
                click_y = event.position().y()

                if abs(click_y - start_px) < 10 or abs(click_y - front_px) < 10:
                    self.setCursor(Qt.CursorShape.SplitVCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)

        if self.dragged_custom_line_index is not None:
            line = self.custom_lines[self.dragged_custom_line_index]
            if line.get("orientation") == "horizontal":
                line["position"] = y_norm
            else:
                line["position"] = x_norm
            self.update()

        elif self.dragged_spot_index is not None:
            self.spots[self.dragged_spot_index]['x'] = x_norm
            self.spots[self.dragged_spot_index]['y'] = y_norm
            self.update()
            self.spotsChanged.emit(self.spots)

        elif self.dragged_line is not None:
             # Dragging a line (only when show_lines is True)
            if self.show_lines:
                if self.dragged_line == "Start":
                    if self.show_start_line_adjust_hint and abs(self.start_line_y - y_norm) > 1e-6:
                        self.show_start_line_adjust_hint = False
                    self.start_line_y = y_norm
                elif self.dragged_line == "Front":
                    self.front_line_y = y_norm
                self.update()
                self.linesMoved.emit(1.0 - self.start_line_y, 1.0 - self.front_line_y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # Right click to remove
            click_x = event.position().x()
            click_y = event.position().y()

            for i, spot in enumerate(self.spots):
                px = spot['x'] * self.width()
                py = spot['y'] * self.height()
                dist = ((click_x - px)**2 + (click_y - py)**2)**0.5
                if dist < self.spot_radius + 5:
                    self.spots.pop(i)
                    self.update()
                    self.spotsChanged.emit(self.spots)
                    return

            custom_line_index = self._find_custom_line_index(click_x, click_y)
            if custom_line_index is not None:
                self.custom_lines.pop(custom_line_index)
                self.update()
                return
            return

        x_norm = event.position().x() / self.width()
        y_norm = event.position().y() / self.height()
        x_norm = max(0.0, min(1.0, x_norm))
        y_norm = max(0.0, min(1.0, y_norm))

        if self.adding_sample_mode:
            if self.current_sample_id is not None:
                # Enforce single spot per substance: check if spot exists
                existing_index = None
                for i, spot in enumerate(self.spots):
                    if spot['sample_id'] == self.current_sample_id:
                        existing_index = i
                        break

                if existing_index is not None:
                    # Update existing spot
                    self.spots[existing_index]['x'] = x_norm
                    self.spots[existing_index]['y'] = y_norm
                else:
                    # Create new spot
                    self.spots.append({
                        'sample_id': self.current_sample_id,
                        'x': x_norm,
                        'y': y_norm
                    })

                self.update()
                self.spotsChanged.emit(self.spots)
        else:
            # Check for line hit first (priority over general click, but maybe spots priority?)
            # Let's say Spots > Lines > Background

            # 1. Spot Hit
            click_x = event.position().x()
            click_y = event.position().y()

            clicked_idx = None
            closest_dist = float('inf')

            for i, spot in enumerate(self.spots):
                px = spot['x'] * self.width()
                py = spot['y'] * self.height()
                dist = ((click_x - px)**2 + (click_y - py)**2)**0.5
                if dist < self.spot_radius + 5:
                    if dist < closest_dist:
                        closest_dist = dist
                        clicked_idx = i

            if clicked_idx is not None:
                self.dragged_spot_index = clicked_idx
            else:
                custom_line_index = self._find_custom_line_index(click_x, click_y)
                if custom_line_index is not None:
                    self.dragged_custom_line_index = custom_line_index
                    self.setCursor(self._custom_line_cursor(self.custom_lines[custom_line_index]))
                    return

            if clicked_idx is None and self.show_lines:
                # 2. Calibration Line Hit (only when show_lines is True)
                start_px = self.start_line_y * self.height()
                front_px = self.front_line_y * self.height()

                if abs(click_y - start_px) < 10:
                    self.dragged_line = "Start"
                    self.setCursor(Qt.CursorShape.SplitVCursor)
                    return
                elif abs(click_y - front_px) < 10:
                    self.dragged_line = "Front"
                    self.setCursor(Qt.CursorShape.SplitVCursor)
                    return

    def mouseReleaseEvent(self, event):
        self.dragged_spot_index = None
        self.dragged_line = None
        self.dragged_custom_line_index = None
        if not self.adding_sample_mode:
             self.setCursor(Qt.CursorShape.ArrowCursor)

    def rf_to_widget_y(self, rf_value):
        if self.support_line_y_mapper is not None:
            mapped_y = self.support_line_y_mapper(rf_value)
            if mapped_y is not None:
                return mapped_y
        return self.start_line_y + (rf_value * (self.front_line_y - self.start_line_y))

    def get_support_line_specs(self):
        if self.support_line_specs_provider is not None:
            specs = self.support_line_specs_provider()
            if specs:
                return specs
        return [
            (self.rf_to_widget_y(rf_tenths / 100.0), str(rf_tenths))
            for rf_tenths in range(10, 81, 10)
        ]

    def get_custom_line_annotations(self):
        annotations = []
        for line in self.custom_lines:
            position = float(line.get("position", 0.5))
            orientation = line.get("orientation")
            label = None
            if orientation == "horizontal" and self.custom_line_rf_label_provider is not None:
                label = self.custom_line_rf_label_provider(position)
            annotations.append({
                "orientation": orientation,
                "position": position,
                "label": label,
            })
        return annotations

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)

        # Draw Lines (conditional)
        if self.show_lines:
            painter.setPen(QPen(QColor("green"), 2))
            start_y = int(self.start_line_y * self.height())
            painter.drawLine(0, start_y, self.width(), start_y)

            if self.show_start_line_adjust_hint:
                font = painter.font()
                font.setPointSize(max(9, font.pointSize()))
                painter.setFont(font)
                metrics = painter.fontMetrics()
                text_height = metrics.height()
                text_top = max(0, min(self.height() - text_height, start_y - text_height - 6))
                painter.setPen(QPen(QColor("green"), 1))
                painter.drawText(
                    QRect(0, text_top, self.width(), text_height),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                    START_LINE_HINT_TEXT,
                )

            painter.setPen(QPen(QColor("red"), 2))
            front_y = int(self.front_line_y * self.height())
            painter.drawLine(0, front_y, self.width(), front_y)

            if self.show_support_lines or self.support_line_specs_provider is not None:
                support_color = QColor("gray")
                painter.setPen(QPen(support_color, 1))
                font = painter.font()
                font.setPointSize(max(8, font.pointSize()))
                painter.setFont(font)
                for y_norm, label in self.get_support_line_specs():
                    y = int(y_norm * self.height())
                    painter.drawLine(0, y, self.width(), y)
                    painter.drawText(4, y - 4, str(label))

            for line in self.get_custom_line_annotations():
                position = line["position"]
                orientation = line["orientation"]
                painter.setPen(_make_custom_line_pen(orientation, CUSTOM_LINE_BASE_WIDTH))
                if orientation == "horizontal":
                    y = int(position * self.height())
                    painter.drawLine(0, y, self.width(), y)
                    label = line.get("label")
                    if label:
                        font = painter.font()
                        font.setPointSize(max(8, font.pointSize()))
                        painter.setFont(font)
                        metrics = painter.fontMetrics()
                        text_x = max(6, self.width() - metrics.horizontalAdvance(label) - 6)
                        text_y = max(metrics.ascent() + 2, y - 4)
                        painter.drawText(text_x, text_y, label)
                elif orientation == "vertical":
                    x = int(position * self.width())
                    painter.drawLine(x, 0, x, self.height())

        # Draw Spots (unconditional)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for spot in self.spots:
            sid = spot['sample_id']
            color = self.global_colors.get(sid, QColor("white"))

            # Check if this sample is highlighted (characteristics window is open)
            is_highlighted = sid in self.highlighted_samples

            # Draw highlighted spots with a thicker border and different style
            if is_highlighted:
                # Draw outer highlight ring (dashed, wider)
                print(f"DEBUG: Highlight: {spot}")
                highlight_pen = QPen(QColor("white"), 4)
                highlight_pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(highlight_pen)
                px = int(spot['x'] * self.width())
                py = int(spot['y'] * self.height())
                painter.drawEllipse(px - self.spot_radius - 4 , py - self.spot_radius - 4,
                                    (self.spot_radius + 4) * 2, (self.spot_radius + 4) * 2)

            # Draw the main spot circle
            painter.setPen(QPen(color, 2 if not is_highlighted else 3))
            px = int(spot['x'] * self.width())
            py = int(spot['y'] * self.height())
            painter.drawEllipse(px - self.spot_radius, py - self.spot_radius,
                                self.spot_radius * 2, self.spot_radius * 2)

            name = self.global_names.get(sid)
            if name:
                font = painter.font()
                # Use per-sample font size if available, otherwise default to 8
                font_size = self.global_font_sizes.get(sid, 8)
                font.setPointSize(font_size)
                painter.setFont(font)
                painter.drawText(px + self.spot_radius + 5, py - 5, name)

    def update_display(self):
        if self._original_pixmap and not self._original_pixmap.isNull():
            scaled = self._original_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            super().setPixmap(scaled)
        elif self.text() == "":
             self.setText("No Image Loaded")


class SquareImageContainer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label = SquareLabel(self)

    def resizeEvent(self, event):
        side = max(0, min(self.width(), self.height()))
        x = max(0, (self.width() - side) // 2)
        self.image_label.setGeometry(x, 0, side, side)
        super().resizeEvent(event)


class PlateSlotsWidget(QWidget):
    def __init__(self, slot_count, parent=None):
        super().__init__(parent)
        self.slot_count = max(1, slot_count)
        self.slots_layout = QHBoxLayout()
        self.slots_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.slots_layout)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        margins = self.slots_layout.contentsMargins()
        spacing = self.slots_layout.spacing()
        available_width = max(
            0,
            width - margins.left() - margins.right() - spacing * (self.slot_count - 1),
        )
        slot_width = max(0, available_width // self.slot_count)

        slot_heights = []
        for i in range(self.slots_layout.count()):
            widget = self.slots_layout.itemAt(i).widget()
            if widget is None:
                continue
            if widget.hasHeightForWidth():
                slot_heights.append(widget.heightForWidth(slot_width))
            else:
                slot_heights.append(widget.sizeHint().height())

        return margins.top() + margins.bottom() + max(slot_heights, default=0)

    def sizeHint(self):
        return QSize(600, self.heightForWidth(600))


class ImageSlot(QWidget):
    # Signal emitted when the per-plate range changes
    rangeChanged = pyqtSignal(int, float)  # (plate_index, range_value)
    calibrationModeChanged = pyqtSignal(int, str)  # (plate_index, calibration_mode)

    def __init__(self, title, plate_index):
        super().__init__()
        self.plate_index = plate_index
        self.image_path = None # Store loaded image path
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.layout = QVBoxLayout()
        self.layout.setSpacing(2)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)

        # Title with Range SpinBox
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.addStretch()

        # Title label
        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.title_label.font()
        font.setPointSize(14)
        font.setBold(True)
        self.title_label.setFont(font)
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()

        self.layout.addLayout(title_layout)

        # Image Area
        self.image_container = SquareImageContainer()
        self.image_label = self.image_container.image_label
        self.layout.addWidget(self.image_container, 1)

        # Controls
        self.controls_layout = QHBoxLayout()
        self.controls_layout.setContentsMargins(0, 0, 0, 0)
        self.controls_layout.setSpacing(0) # reduce space between elements to 0
        self.controls_layout.setAlignment(Qt.AlignmentFlag.AlignCenter) # center whole group
        self.layout.addLayout(self.controls_layout)

        # Load Button
        self.load_button = _make_icon_button("load_image.svg", "Load Image", "Load Image")
        self.load_button.clicked.connect(self.load_image)
        self.controls_layout.addWidget(self.load_button)

        # Export Button
        self.export_button = _make_icon_button("export_image.svg", "Export Image", "Export Image")
        self.export_button.clicked.connect(self.export_marked_image)
        self.controls_layout.addWidget(self.export_button)

        self.horizontal_line_button = _make_icon_button("horizontal_line.svg", "Add Horizontal Line", "Add H Line")
        self.horizontal_line_button.clicked.connect(self.add_horizontal_line)
        self.controls_layout.addWidget(self.horizontal_line_button)

        self.vertical_line_button = _make_icon_button("vertical_line.svg", "Add Vertical Line", "Add V Line")
        self.vertical_line_button.clicked.connect(self.add_vertical_line)
        self.controls_layout.addWidget(self.vertical_line_button)

        # Range SpinBox (per-plate)
        self.relative_rf_display = True
        self.range_spin = QDoubleSpinBox()
        self.range_spin.setPrefix("±")
        self.range_spin.setToolTip(f"Range tolerance for plate {title}")
        self.range_spin.setMaximumWidth(80)
        self.range_spin.valueChanged.connect(self._on_range_changed)
        self.set_relative_rf_display(True)
        self.set_range(0.05)
        self.controls_layout.addWidget(self.range_spin)

        # View dropdown (Support Lines + Show Rf classes)
        self.controls_layout.addSpacing(12)
        self._view_button = QToolButton()
        self._view_button.setStyleSheet("""
        QToolButton::menu-indicator { width: 0px; }
        """)
        self._view_button.setText("Options ▼")
        self._view_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._view_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._view_button.setToolTip("Toggle plate overlays")
        _view_menu = QMenu(self._view_button)
        self._action_support_lines = QAction("Support Lines", self)
        self._action_support_lines.setCheckable(True)
        self._action_support_lines.triggered.connect(self._on_support_lines_action_toggled)
        _view_menu.addAction(self._action_support_lines)
        self._action_rf_classes = QAction("Show Rf classes", self)
        self._action_rf_classes.setCheckable(True)
        self._action_rf_classes.triggered.connect(self._on_rf_classes_action_toggled)
        _view_menu.addAction(self._action_rf_classes)
        _view_menu.addSeparator()
        _action_clear = QAction("Clear", self)
        _action_clear.triggered.connect(self._on_view_clear)
        _view_menu.addAction(_action_clear)
        self._view_button.setMenu(_view_menu)
        self.controls_layout.addWidget(self._view_button)

        self.controls_layout.addSpacing(8)
        self._calibration_button = QToolButton()
        self._calibration_button.setStyleSheet("""
        QToolButton::menu-indicator { width: 0px; }
        """)
        self._calibration_button.setText("Calibration ▼")
        self._calibration_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._calibration_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._calibration_button.setToolTip(
            "Choose the calibration mode for this plate"
        )
        _calibration_menu = QMenu(self._calibration_button)
        self._action_calibration_linear = QAction(CALIBRATION_MODE_LINEAR, self)
        self._action_calibration_linear.setCheckable(True)
        self._action_calibration_linear.triggered.connect(
            lambda checked: self._on_calibration_action_triggered(
                CALIBRATION_MODE_LINEAR, checked
            )
        )
        _calibration_menu.addAction(self._action_calibration_linear)
        self._action_calibration_nearest = QAction(CALIBRATION_MODE_NEAREST, self)
        self._action_calibration_nearest.setCheckable(True)
        self._action_calibration_nearest.triggered.connect(
            lambda checked: self._on_calibration_action_triggered(
                CALIBRATION_MODE_NEAREST, checked
            )
        )
        _calibration_menu.addAction(self._action_calibration_nearest)
        self._calibration_button.setMenu(_calibration_menu)
        self.controls_layout.addWidget(self._calibration_button)
        self.set_calibration_mode(CALIBRATION_MODE_LINEAR)

        self.set_custom_line_controls_enabled(False)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        margins = self.layout.contentsMargins()
        spacing = self.layout.spacing()
        title_height = self.title_label.sizeHint().height()
        controls_height = max(
            self.load_button.sizeHint().height(),
            self.export_button.sizeHint().height(),
            self.horizontal_line_button.sizeHint().height(),
            self.vertical_line_button.sizeHint().height(),
            self.range_spin.sizeHint().height(),
            self._view_button.sizeHint().height(),
            self._calibration_button.sizeHint().height(),
        )
        image_height = self.image_label.heightForWidth(width)
        return (
            margins.top()
            + margins.bottom()
            + title_height
            + controls_height
            + image_height
            + spacing * 2
        )

    def sizeHint(self):
        return QSize(220, self.heightForWidth(220))

    def _on_range_changed(self, value):
        """Emit signal when the per-plate range changes (normalized 0.0-1.0)."""
        normalized = value / 100.0 if self.relative_rf_display else value
        self.rangeChanged.emit(self.plate_index, normalized)

    def set_relative_rf_display(self, enabled):
        """Switch per-plate range control between 0.0-1.0 and 0-100 display."""
        current = self.get_range()
        self.relative_rf_display = enabled
        self.range_spin.blockSignals(True)
        if enabled:
            self.range_spin.setRange(0.0, 100.0)
            self.range_spin.setSingleStep(1.0)
            self.range_spin.setDecimals(0)
            self.range_spin.setSuffix(" %")
        else:
            self.range_spin.setRange(0.0, 1.0)
            self.range_spin.setSingleStep(0.01)
            self.range_spin.setDecimals(2)
            self.range_spin.setSuffix(" Rf")
        self.range_spin.blockSignals(False)
        self.set_range(current)

    def set_range(self, value):
        """Set the range spinbox value without triggering the signal (input: 0.0-1.0)."""
        display_value = (value * 100.0) if self.relative_rf_display else value
        self.range_spin.blockSignals(True)
        self.range_spin.setValue(display_value)
        self.range_spin.blockSignals(False)

    def get_range(self):
        """Get current normalized range value (0.0-1.0)."""
        value = self.range_spin.value()
        return value / 100.0 if self.relative_rf_display else value

    def _on_support_lines_action_toggled(self, checked):
        """Toggle support lines for this plate only."""
        self.image_label.show_support_lines = checked
        main_window = self.window()
        if hasattr(main_window, 'update_results_display'):
            main_window.update_results_display()
        else:
            self.image_label.update()

    def _on_rf_classes_action_toggled(self, checked):
        """Toggle Rf classes for this plate only."""
        main_window = self.window()
        if hasattr(main_window, 'update_results_display'):
            main_window.update_results_display()
        else:
            self.image_label.update()

    def _on_view_clear(self):
        self._action_support_lines.setChecked(False)
        self._action_rf_classes.setChecked(False)
        self._on_support_lines_action_toggled(False)
        self._on_rf_classes_action_toggled(False)

    def _on_calibration_action_triggered(self, mode, checked):
        mode = _normalize_calibration_mode(mode)
        if not checked:
            # Keep exactly one calibration mode selected.
            self.set_calibration_mode(mode)
            return
        self.set_calibration_mode(mode)
        self.calibrationModeChanged.emit(self.plate_index, mode)

    def set_calibration_mode(self, mode):
        mode = _normalize_calibration_mode(mode)
        is_linear = mode == CALIBRATION_MODE_LINEAR
        self._action_calibration_linear.blockSignals(True)
        self._action_calibration_nearest.blockSignals(True)
        self._action_calibration_linear.setChecked(is_linear)
        self._action_calibration_nearest.setChecked(not is_linear)
        self._action_calibration_linear.blockSignals(False)
        self._action_calibration_nearest.blockSignals(False)

    def get_calibration_mode(self):
        return (
            CALIBRATION_MODE_LINEAR
            if self._action_calibration_linear.isChecked()
            else CALIBRATION_MODE_NEAREST
        )

    def set_support_lines_checked(self, checked):
        """Set support lines checked state and apply side effects."""
        self._action_support_lines.setChecked(checked)
        self._on_support_lines_action_toggled(checked)

    def set_support_lines_action_checked(self, checked):
        """Update the support-lines action checked state without triggering the handler."""
        self._action_support_lines.blockSignals(True)
        self._action_support_lines.setChecked(checked)
        self._action_support_lines.blockSignals(False)

    def set_rf_classes_action_checked(self, checked):
        """Update the Rf-classes action checked state without triggering the handler."""
        self._action_rf_classes.blockSignals(True)
        self._action_rf_classes.setChecked(checked)
        self._action_rf_classes.blockSignals(False)

    def rf_classes_checked(self):
        """Return whether Rf classes are enabled for this plate."""
        return self._action_rf_classes.isChecked()

    def set_custom_line_controls_enabled(self, enabled):
        self.export_button.setEnabled(enabled)
        self.horizontal_line_button.setEnabled(enabled)
        self.vertical_line_button.setEnabled(enabled)

    def set_loaded_image(self, pixmap, image_path=None, show_start_line_adjust_hint=True):
        if image_path is not None:
            self.image_path = image_path
        self.image_label.set_image(pixmap, show_start_line_adjust_hint=show_start_line_adjust_hint)
        self.set_custom_line_controls_enabled(True)

    def add_horizontal_line(self):
        self.image_label.add_custom_line("horizontal")

    def add_vertical_line(self):
        self.image_label.add_custom_line("vertical")

    def load_image(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "", "Images (*.png *.xpm *.jpg *.jpeg *.bmp *.tif *.tiff)"
        )
        if file_name:
            pixmap = QPixmap(file_name)
            if not pixmap.isNull():
                self.set_loaded_image(pixmap, file_name)

    def get_marked_pixmap(self, label_font_size_delta=0):
        """Return a QPixmap of the original image with all annotations drawn on it,
        or None if no image is loaded."""
        if self.image_label._original_pixmap is None:
            return None

        # Create a mutable copy of the original pixmap
        export_pixmap = self.image_label._original_pixmap.copy()

        painter = QPainter(export_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dimensions of original image
        img_w = export_pixmap.width()
        img_h = export_pixmap.height()

        # Widget Dimensions and Scaling Logic (matching SquareLabel.update_display)
        label_w = self.image_label.width()
        label_h = self.image_label.height()

        if img_w <= 0 or img_h <= 0:
            painter.end()
            return None

        # Calculate scale factor used by Qt's KeepAspectRatio
        scale_w = label_w / img_w
        scale_h = label_h / img_h
        scale = min(scale_w, scale_h)

        drawn_w = int(img_w * scale)
        drawn_h = int(img_h * scale)

        # Calculate offsets (centering)
        offset_x = (label_w - drawn_w) // 2
        offset_y = (label_h - drawn_h) // 2

        # Coordinate Transformation Function: Widget Normalized -> Image Pixel
        def widget_norm_to_image_px(norm_val, is_y=True):
            if is_y:
                widget_px = norm_val * label_h
                rel_px = widget_px - offset_y
                rel_norm = rel_px / drawn_h
                return int(rel_norm * img_h)
            else:
                widget_px = norm_val * label_w
                rel_px = widget_px - offset_x
                rel_norm = rel_px / drawn_w
                return int(rel_norm * img_w)

        # Scale for drawing elements (assume 800px is standard view for relative sizing)
        scale_factor = max(1.0, img_w / 800.0)
        line_width = int(4 * scale_factor)
        spot_radius = int(self.image_label.spot_radius * scale_factor)
        spot_pen_width = int(2 * scale_factor)

        # Draw Start Line (Green)
        start_y = widget_norm_to_image_px(self.image_label.start_line_y, is_y=True)
        pen = QPen(QColor("green"), line_width)
        painter.setPen(pen)
        painter.drawLine(0, start_y, img_w, start_y)

        # Draw Front Line (Red)
        front_y = widget_norm_to_image_px(self.image_label.front_line_y, is_y=True)
        pen = QPen(QColor("red"), line_width)
        painter.setPen(pen)
        painter.drawLine(0, front_y, img_w, front_y)

        if self.image_label.show_support_lines:
            support_color = QColor("gray")
            painter.setPen(QPen(support_color, max(1, int(2 * scale_factor))))
            font = painter.font()
            font.setPointSize(max(8, int(10 * scale_factor)))
            painter.setFont(font)
            for y_norm, label in self.image_label.get_support_line_specs():
                support_y = widget_norm_to_image_px(y_norm, is_y=True)
                painter.drawLine(0, support_y, img_w, support_y)
                painter.drawText(int(6 * scale_factor), support_y - int(4 * scale_factor), str(label))

        for line in self.image_label.get_custom_line_annotations():
            position = line["position"]
            orientation = line["orientation"]
            painter.setPen(_make_custom_line_pen(orientation, max(1.0, CUSTOM_LINE_BASE_WIDTH * scale_factor)))
            if orientation == "horizontal":
                custom_y = widget_norm_to_image_px(position, is_y=True)
                painter.drawLine(0, custom_y, img_w, custom_y)
                label = line.get("label")
                if label:
                    font = painter.font()
                    font.setPointSize(max(8, int(10 * scale_factor)))
                    painter.setFont(font)
                    metrics = painter.fontMetrics()
                    text_x = max(int(6 * scale_factor), img_w - metrics.horizontalAdvance(label) - int(6 * scale_factor))
                    text_y = max(metrics.ascent() + int(2 * scale_factor), custom_y - int(4 * scale_factor))
                    painter.drawText(text_x, text_y, label)
            elif orientation == "vertical":
                custom_x = widget_norm_to_image_px(position, is_y=False)
                painter.drawLine(custom_x, 0, custom_x, img_h)

        # Draw Spots
        spots = self.image_label.spots
        colors = self.image_label.global_colors

        painter.setBrush(Qt.BrushStyle.NoBrush)

        for spot in spots:
            sid = spot['sample_id']
            color = colors.get(sid, QColor("black"))
            painter.setPen(QPen(color, spot_pen_width))

            px = widget_norm_to_image_px(spot['x'], is_y=False)
            py = widget_norm_to_image_px(spot['y'], is_y=True)

            painter.drawEllipse(px - spot_radius, py - spot_radius, spot_radius * 2, spot_radius * 2)

            name = self.image_label.global_names.get(sid)
            if name:
                font = painter.font()
                # Use per-sample font size if available, otherwise default
                font_size = self.image_label.global_font_sizes.get(sid, 9)
                effective_font_size = max(1, font_size + label_font_size_delta)
                font.setPointSize(int(effective_font_size * scale_factor))
                painter.setFont(font)
                painter.drawText(px + spot_radius + int(5 * scale_factor), py - int(5 * scale_factor), name)

        painter.end()

        return export_pixmap

    def export_marked_image(self):
        export_pixmap = self.get_marked_pixmap()
        if export_pixmap is None:
            return

        file_name, _ = QFileDialog.getSaveFileName(
            self, "Export Marked Image", "", "PNG Images (*.png);;JPEG Images (*.jpg)"
        )
        if not file_name:
            return

        export_pixmap.save(file_name)

class MainWindow(QMainWindow):
    RESULTS_COL_COLOR = 0
    RESULTS_COL_REFERENCE = 1
    RESULTS_COL_SUBSTANCE = 2
    RESULTS_COL_PLATE_A = 3
    RESULTS_COL_PLATE_B = 4
    RESULTS_COL_PLATE_C = 5
    RESULTS_COL_PREDICTIONS = 6
    RESULTS_COL_ALL_RESULTS = 7

    def __init__(self, parent=None, debug_mode=False):
        super().__init__(parent)
        self.setWindowTitle("TLCid")
        self.resize(1200, 700)

        import os
        self.base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.db_path = os.path.join(self.base_path, "tlcid_database.db")
        self.debug_mode = debug_mode
        self.analysis_file_path = None  # Last loaded/saved analysis JSON path

        # State
        self.samples = {} # {id: {'color': QColor, 'name': str}}
        self.reference_repository = ReferenceRepository(self.db_path)
        self.prediction_service = PredictionService()
        self.reference_data = [] # Compatibility cache for prediction
        self.reference_rf_by_name = {}
        self.genus_to_substances = {} # Compatibility cache for genus-specific substance filtering
        self.family_to_substances = {}
        self.next_sample_id = 1
        self.active_regular_marking_sid = None
        self.colors = [
            QColor("cyan"), QColor("magenta"), QColor("yellow"),
            QColor("blue"), QColor("orange"), QColor("purple"),
            QColor("lime"), QColor("pink")
        ]

        self.char_windows = {}    # {sid: SubstanceCharacteristicsWindow}
        self.detail_windows = {}  # {name: SubstanceDetailWindow}

        self._ensure_default_db_connection()
        self.load_reference_data() # Load DB data on startup

        # Compatibility aliases for code/tests that still access named standards directly.
        # Source of truth is gui.reference_standards.REFERENCE_STANDARDS.
        self.atranorin_standards = REFERENCE_STANDARDS[0].rf_by_plate
        self.norstictic_standards = REFERENCE_STANDARDS[-1].rf_by_plate
        self.rhizocarpic_standards = REFERENCE_STANDARDS[-2].rf_by_plate
        self.lecanoric_standards = REFERENCE_STANDARDS[-3].rf_by_plate
        self.evernic_standards = REFERENCE_STANDARDS[-4].rf_by_plate


        # Detection Settings
        self.detection_method = "Range"
        self.detection_range = 0.05  # Global default (used as initial value for plates)
        self.relative_rf_display = True
        self.allow_missing_rf_values = False
        self.display_support_lines = False
        self.display_rf_classes = False
        self._rf_classes_missing_popup_shown = False

        # Per-plate range settings: {plate_index: range_value}
        self.plate_ranges = {0: 0.05, 1: 0.05, 2: 0.05}

        # Per-plate calibration mode
        self.calibration_mode = CALIBRATION_MODE_LINEAR  # legacy fallback for old analysis files/tests
        self.plate_calibration_modes = {
            0: CALIBRATION_MODE_LINEAR,
            1: CALIBRATION_MODE_LINEAR,
            2: CALIBRATION_MODE_LINEAR,
        }


        # Main Layout Construction
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # Toolbar Area - Main horizontal layout with two columns
        toolbar_hlayout = QHBoxLayout()

        # Left column: toolbar controls in three rows
        toolbar_left_col = QVBoxLayout()
        toolbar_left_col.setSpacing(0)

        # Row 1: Label for Reference Substances
        row1_layout = QHBoxLayout()
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(0)

        self.reference_substances_label = QLabel()
        self.reference_substances_label.setStyleSheet("color: gray; padding: 0px; margin: 0px;")
        self.reference_substances_label.setText("<b>Mark known substances as references:</b>")
        row1_layout.addWidget(self.reference_substances_label)
        row1_layout.addStretch()
        toolbar_left_col.addLayout(row1_layout)

        # Row 2: All buttons for marking reference substances
        row2_layout = QHBoxLayout()
        row2_layout.setSpacing(5)
        row2_layout.setContentsMargins(0, 0, 0, 0)


        self.reference_buttons = {}
        for standard in REFERENCE_STANDARDS.values():
            button = QPushButton(standard.button_text)
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked, sid=standard.sample_id: self.toggle_mark_reference(sid, checked)
            )
            setattr(self, standard.button_attr, button)
            self.reference_buttons[standard.sample_id] = button
            row2_layout.addWidget(button)

        row2_layout.addStretch()
        toolbar_left_col.addLayout(row2_layout)

        # Row 5: Label for Reference Substances
        row3_layout = QHBoxLayout()
        row3_layout.setSpacing(0)
        row3_layout.setContentsMargins(0, 0, 0, 0)

        self.reference_substances_label = QLabel()
        self.reference_substances_label.setStyleSheet("color: gray; padding: 0px; margin: 0px;")
        self.reference_substances_label.setText("<b>Mark unknown substances:</b>")
        row3_layout.addWidget(self.reference_substances_label)
        row3_layout.addStretch()
        toolbar_left_col.addLayout(row3_layout)

        # Row 4: "Mark Substance" button
        row4_layout = QHBoxLayout()
        row4_layout.setSpacing(0)
        row4_layout.setContentsMargins(0, 0, 0, 0)

        self.mark_substance_button = QPushButton("New Substance")
        self.mark_substance_button.setCheckable(True)
        self.mark_substance_button.clicked.connect(self.toggle_mark_substance)
        row4_layout.addWidget(self.mark_substance_button)

        row4_layout.addStretch()
        toolbar_left_col.addLayout(row4_layout)

        # Row 5: Additional inline controls
        row5_layout = QHBoxLayout()
        row5_layout.setSpacing(0)
        row5_layout.setContentsMargins(0, 0, 0, 0)

        # Inline Range control in Main Window
        self.range_main = QDoubleSpinBox()
        self.range_main.setRange(0.0, 1.0)
        self.range_main.setSingleStep(0.01)
        self.range_main.setValue(self.detection_range)
        self.range_main.valueChanged.connect(self.on_main_range_changed)
        row5_layout.addWidget(self.range_main)

        self.update_detection_status_label()

        row5_layout.addStretch()
        toolbar_left_col.addLayout(row5_layout)

        # Add left column to main toolbar layout
        toolbar_hlayout.addLayout(toolbar_left_col)

        # Right column: App icon with TLCid text below (spans all three rows)
        import os
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_path, "icon.png")
        if os.path.exists(icon_path):
            # Create a vertical layout for icon + text
            icon_column = QVBoxLayout()
            icon_column.setSpacing(0)
            icon_column.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

            # Icon
            self.icon_label = QLabel()
            icon_pixmap = QPixmap(icon_path)
            if not icon_pixmap.isNull():
                self.icon_label.setPixmap(icon_pixmap.scaled(75, 75, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                icon_column.addWidget(self.icon_label)

            # TLCid text below icon
            self.tlcid_label = QLabel()
            self.tlcid_label.setText("TLCid")
            self.tlcid_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_column.addWidget(self.tlcid_label)

            icon_column.addStretch()  # Push content to top
            toolbar_hlayout.addLayout(icon_column)

        main_layout.addLayout(toolbar_hlayout, 0)

        # Vertical splitter: plates on top, results table on bottom
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setHandleWidth(4)
        self.main_splitter.setStyleSheet("""
            QSplitter::handle:vertical {
                background: #b0b0b0;
                margin: 0 4px;
            }
            QSplitter::handle:vertical:hover {
                background: #8f8f8f;
            }
        """)

        # Slots Area - wrap in a container widget for the splitter
        self.slots = []
        self.plate_labels = ['A', "B'", 'C']
        slots_widget = PlateSlotsWidget(len(self.plate_labels))
        slots_layout = slots_widget.slots_layout
        for plate_idx, label in enumerate(self.plate_labels):
            slot = ImageSlot(label, plate_idx)
            # Connect spot changes to aggregation logic
            slot.image_label.spotsChanged.connect(self.update_results_display)
            # Also connect line moves to aggregation logic
            slot.image_label.linesMoved.connect(lambda s, f: self.update_results_display())
            # Connect per-plate range changes
            slot.rangeChanged.connect(self.on_plate_range_changed)
            slot.calibrationModeChanged.connect(self.on_plate_calibration_mode_changed)
            self.slots.append(slot)
            slots_layout.addWidget(slot)
        self.main_splitter.addWidget(slots_widget)

        # Results Display
        # Results Display using QTableWidget
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(8)
        self.results_table.setHorizontalHeaderLabels(["Color", "Reference", "Substance", "Plate A", "Plate B'", "Plate C", "Predictions", "All Results"])

        # Column Resizing Logic
        header = self.results_table.horizontalHeader()

        # 0: Color (Fixed, Small)
        header.setSectionResizeMode(self.RESULTS_COL_COLOR, QHeaderView.ResizeMode.Fixed)
        self.results_table.setColumnWidth(self.RESULTS_COL_COLOR, 50)

        # 1: Reference (Fixed, Small)
        header.setSectionResizeMode(self.RESULTS_COL_REFERENCE, QHeaderView.ResizeMode.Fixed)
        self.results_table.setColumnWidth(self.RESULTS_COL_REFERENCE, 70)

        # 2: Substance
        header.setSectionResizeMode(self.RESULTS_COL_SUBSTANCE, QHeaderView.ResizeMode.Interactive)
        self.results_table.setColumnWidth(self.RESULTS_COL_SUBSTANCE, 150)

        # 3, 4, 5: Plates
        for i in [self.RESULTS_COL_PLATE_A, self.RESULTS_COL_PLATE_B, self.RESULTS_COL_PLATE_C]:
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.results_table.setColumnWidth(i, 60)

        # 6: Predictions (Fill remaining space)
        header.setSectionResizeMode(self.RESULTS_COL_PREDICTIONS, QHeaderView.ResizeMode.Stretch)

        # 7: All Results button (Fixed, Small)
        header.setSectionResizeMode(self.RESULTS_COL_ALL_RESULTS, QHeaderView.ResizeMode.Fixed)
        self.results_table.setColumnWidth(self.RESULTS_COL_ALL_RESULTS, 90)

        # Ensure horizontal scrolling is possible
        self.results_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.results_table.setSortingEnabled(True)
        self.results_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self.show_results_table_context_menu)

        # Row Height
        # Connect Cell Click
        self.results_table.cellClicked.connect(self.handle_table_click)
        self.results_renderer = ResultsTableRenderer(self.results_table, self)

        self.main_splitter.addWidget(self.results_table)

        # Keep the plate area at its natural height; extra window height goes to the table.
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setChildrenCollapsible(False)

        main_layout.addWidget(self.main_splitter, 1)
        main_layout.setStretch(0, 0)
        main_layout.setStretch(1, 1)

        self.create_menu()
        QTimer.singleShot(0, self.initialize_main_splitter_sizes)

    def initialize_main_splitter_sizes(self):
        slots_widget = self.main_splitter.widget(0)
        total_height = self.main_splitter.size().height()
        if slots_widget is None or total_height <= 0:
            return

        if slots_widget.hasHeightForWidth():
            preferred_top_height = slots_widget.heightForWidth(slots_widget.width())
        else:
            preferred_top_height = slots_widget.sizeHint().height()

        handle_height = self.main_splitter.handleWidth()
        minimum_bottom_height = 80
        available_top_height = max(0, total_height - handle_height - minimum_bottom_height)
        top_height = max(0, min(preferred_top_height, available_top_height))
        bottom_height = max(minimum_bottom_height, total_height - top_height - handle_height)
        self.main_splitter.setSizes([top_height, bottom_height])

    def handle_table_click(self, row, col):
        if col == self.RESULTS_COL_COLOR:
            # Color Column Clicked
            item = self.results_table.item(row, col)
            if item:
                sid = item.data(Qt.ItemDataRole.UserRole)
                if sid is not None:
                    self.change_sample_color(sid)
        elif col == self.RESULTS_COL_SUBSTANCE:
            item = self.results_table.item(row, col)
            if item:
                sid = item.data(Qt.ItemDataRole.UserRole + 1)
                if sid is not None:
                    self.open_characteristics_window(sid)

    def show_results_table_context_menu(self, pos):
        """Show context menu for sortable item-based cells in the results table."""
        item = self.results_table.itemAt(pos)
        if item is None or item.column() != self.RESULTS_COL_SUBSTANCE:
            return

        sid = item.data(Qt.ItemDataRole.UserRole + 1)
        if sid is None:
            return

        self.show_substance_context_menu(sid, self.results_table.viewport(), pos)

    def handle_reference_checkbox(self, state, sid):
        """Handle when the reference checkbox is toggled."""
        if sid not in self.samples:
            return

        # Update the sample data
        self.samples[sid]['is_reference'] = (state == 2)  # Qt.CheckState.Checked == 2

        # Predefined reference standards can use configured Rf values directly
        predefined_reference_rf = predefined_reference_rf_values()

        # If checked, load reference Rf values
        if self.samples[sid]['is_reference']:
            if sid in predefined_reference_rf:
                self.samples[sid]['reference_rf'] = predefined_reference_rf[sid]
                print(f"DEBUG: Predefined reference {sid} marked with Rf: {predefined_reference_rf[sid]}")
            else:
                assigned_name = self.samples[sid].get('assigned_name')
                if not assigned_name:
                    # Use first predicted match if no assigned name
                    matches = self.samples[sid].get('last_matches', [])
                    if matches:
                        assigned_name = matches[0][1]  # Extract name from (score, name) tuple

                if assigned_name:
                    ref_rf = self.get_substance_rf_from_db(assigned_name)
                    if ref_rf:
                        self.samples[sid]['reference_rf'] = ref_rf
                        print(f"DEBUG: Substance {sid} marked as reference with name '{assigned_name}' and Rf: {ref_rf}")
                    else:
                        print(f"DEBUG: Could not find Rf values for '{assigned_name}' in database")
                        self.samples[sid]['reference_rf'] = None
                else:
                    print(f"DEBUG: Substance {sid} has no assigned name, cannot be reference")
                    self.samples[sid]['is_reference'] = False
                    self.samples[sid]['reference_rf'] = None
        else:
            self.samples[sid]['reference_rf'] = None
            print(f"DEBUG: Substance {sid} unmarked as reference")

        # Update calibration and results
        self.update_results_display()

    def get_substance_rf_from_db(self, name):
        """Look up Rf values from the configured reference repository."""
        cached = self.reference_rf_by_name.get(name)
        if cached is not None:
            return cached
        return self.reference_repository.get_substance_rf(name)

    def change_sample_color(self, sid):
        if sid not in self.samples:
            return

        current_color = self.samples[sid]['color']
        new_color = QColorDialog.getColor(current_color, self, "Select Spot Color")

        if new_color.isValid():
            self.samples[sid]['color'] = new_color

            # Update Slots
            colors = {s: d['color'] for s, d in self.samples.items()}
            # Update standard references if needed?
            # Standards map to 0 and -1 which reuse these colors if they are in samples.

            for slot in self.slots:
                slot.image_label.set_global_colors(colors)
                slot.image_label.update()

            self.update_results_display()

    def _ensure_default_db_connection(self):
        from PyQt6.QtSql import QSqlDatabase

        if QSqlDatabase.contains("qt_sql_default_connection"):
            db = QSqlDatabase.database("qt_sql_default_connection")
        else:
            db = QSqlDatabase.addDatabase("QSQLITE")

        db.setDatabaseName(self.db_path)
        if not db.isOpen():
            if not db.open():
                print(f"Error: Could not open database: {self.db_path}")
        return db

    def select_database_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select SQLite Database", self.db_path, "SQLite Database (*.db *.sqlite *.sqlite3);;All Files (*)"
        )
        if file_name:
            self.set_database_path(file_name)

    def set_database_path(self, db_path):
        import os
        from PyQt6.QtSql import QSqlDatabase

        if not db_path or not os.path.exists(db_path):
            QMessageBox.warning(self, "Invalid database", f"Database file not found:\n{db_path}")
            return

        self.db_path = db_path
        self.reference_repository.set_database_path(db_path)

        for connection_name in ["qt_sql_default_connection", "main_ref_connection", "substances_connection"]:
            if QSqlDatabase.contains(connection_name):
                db = QSqlDatabase.database(connection_name)
                if db.isOpen():
                    db.close()
                db.setDatabaseName(self.db_path)

        self._ensure_default_db_connection()
        self.load_reference_data()

        if hasattr(self, "table_windows"):
            for win in self.table_windows.values():
                if win is not None:
                    win.close()
            self.table_windows = {}

        self.update_results_display()
        self.statusBar().showMessage(f"Using database: {self.db_path}", 5000)

    def create_menu(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        about_action = QAction("About", self)
        about_action.setMenuRole(QAction.MenuRole.NoRole)
        about_action.triggered.connect(self.show_about_dialog)
        file_menu.addAction(about_action)

        new_analysis_action = QAction("New Analysis", self)
        new_analysis_action.triggered.connect(self.new_analysis)
        file_menu.addAction(new_analysis_action)

        save_analysis_action = QAction("Save Analysis", self)
        save_analysis_action.triggered.connect(self.save_analysis)
        file_menu.addAction(save_analysis_action)

        load_analysis_action = QAction("Load Analysis", self)
        load_analysis_action.triggered.connect(self.load_analysis)
        file_menu.addAction(load_analysis_action)

        load_examples_action = QAction("Load Examples", self)
        load_examples_action.triggered.connect(self.load_examples)
        file_menu.addAction(load_examples_action)


        # Analysis Menu
        analysis_menu = menu_bar.addMenu("Analysis")

        predict_species_action = QAction("Predict species", self)
        predict_species_action.triggered.connect(self.show_species_prediction_window)
        analysis_menu.addAction(predict_species_action)

        export_combined_action = QAction("Export Combined Image", self)
        export_combined_action.triggered.connect(self.export_combined_image)
        analysis_menu.addAction(export_combined_action)

        generate_report_action = QAction("Generate Report", self)
        generate_report_action.triggered.connect(self.generate_report)
        analysis_menu.addAction(generate_report_action)

        # Settings Menu
        settings_menu = menu_bar.addMenu("Settings")
        application_settings_action = QAction("Application Settings", self)
        application_settings_action.setMenuRole(QAction.MenuRole.NoRole)
        application_settings_action.triggered.connect(self.show_settings_window)
        settings_menu.addAction(application_settings_action)

        # Reference Menu
        ref_menu = menu_bar.addMenu("Databases")

        tables = ["Lichens", "Substances"]
        for table in tables:
            action = QAction(table, self)
            # Use default arg to capture loop variable
            action.triggered.connect(lambda checked, t=table: self.show_table(t))
            ref_menu.addAction(action)

        if self.debug_mode:
            debug_menu = menu_bar.addMenu("Debug")
            select_db_action = QAction("Select database file...", self)
            select_db_action.triggered.connect(self.select_database_file)
            debug_menu.addAction(select_db_action)

    def show_table(self, table_name):
        from gui.database_window import DatabaseTableWindow

        # Store windows in a dict to prevent GC and allow multiple open
        if not hasattr(self, 'table_windows'):
            self.table_windows = {}

        # Create logic: bring to front if open, else create
        if table_name not in self.table_windows or self.table_windows[table_name] is None:
             self.table_windows[table_name] = DatabaseTableWindow(table_name, self.db_path)

        window = self.table_windows[table_name]
        window.show()
        window.raise_()
        window.activateWindow()

    def handle_link_click(self, link):
        if link.startswith("substance:"):
            name = unquote(link.split(":", 1)[1])
            from gui.substance_detail_window import SubstanceDetailWindow
            from PyQt6.QtSql import QSqlDatabase

            # Ensure DB connection exists (should be established by load_reference_data or show_table)
            # Check default connection
            if not QSqlDatabase.contains("qt_sql_default_connection"):
                db = self._ensure_default_db_connection()
                if not db.isOpen():
                    print("Error: Could not open database")
                    return
            else:
                db = QSqlDatabase.database()



            # Manage window instance to prevent GC
            # (initialized in __init__)

            # Close existing if same? Or allow multiple?
            # Let's allow multiple distinct, bring to front if same
            if name in self.detail_windows and self.detail_windows[name].isVisible():
                self.detail_windows[name].raise_()
                self.detail_windows[name].activateWindow()
                return

            window = SubstanceDetailWindow(name, db)
            self.detail_windows[name] = window
            window.show()

        elif link.startswith("edit_sample:"):
            sid = int(link.split(":", 1)[1])
            self.open_characteristics_window(sid)
        # The code for showing the substances inside a QMessageBox is commented out, since there is a different solution.
        # It will be kept as reference though.
        #elif link.startswith("show_more:"):
        #    sid = int(link.split(":", 1)[1])
        #    matches = self.samples.get(sid, {}).get('last_matches', [])
        #    if matches:
        #         # Format matches with scores: "name (score: X.XXXXXX)"
        #         match_lines = [f"{name} (score: {score:.6f})" for score, name in matches]
        #         text = "\n".join(match_lines)
        #         QMessageBox.information(self, f"All Matches for {self.samples[sid]['name']}", text)

    def show_prediction_results(self, substance_id, matches, plate_data, substance_name):
        """Show all prediction results in a table dialog."""
        from gui.prediction_results_window import PredictionResultsWindow

        # Create and show the prediction results window
        window = PredictionResultsWindow(substance_name, substance_id, matches, plate_data, self)

        # Position window slightly to the right of the main window
        parent_pos = self.pos()
        window.move(parent_pos.x() + 140, parent_pos.y() + 40)

        window.exec()

    def assign_predicted_name_to_sample(self, sid, name):
        """Assign a predicted substance name to a sample (same logic as characteristics window assignment)."""
        if sid not in self.samples:
            return

        self.samples[sid]['assigned_name'] = name

        # If characteristics window is open, keep dropdown in sync
        if sid in self.char_windows and self.char_windows[sid] and self.char_windows[sid].isVisible():
            win = self.char_windows[sid]
            win.combo_assigned.blockSignals(True)
            win.combo_assigned.setEditText(name)
            win.combo_assigned.blockSignals(False)

        self.update_results_display()

    def set_sample_show_on_plate(self, sid, show_on_plate):
        """Toggle whether the sample name is displayed on the plate."""
        if sid not in self.samples:
            return

        self.samples[sid]['show_on_plate'] = bool(show_on_plate)

        # Keep characteristics window checkbox in sync when open
        if sid in self.char_windows and self.char_windows[sid] and self.char_windows[sid].isVisible():
            win = self.char_windows[sid]
            win.check_show_name.blockSignals(True)
            win.check_show_name.setChecked(bool(show_on_plate))
            win.check_show_name.blockSignals(False)

        self.update_results_display()

    def show_prediction_context_menu(self, sid, label_widget, pos):
        """Show context menu for the exact predicted substance currently hovered/clicked."""
        if sid not in self.samples:
            return

        hovered_link = None
        if hasattr(self, '_prediction_hover_link_by_sid'):
            hovered_link = self._prediction_hover_link_by_sid.get(sid)

        menu = QMenu(self)

        clicked_name = None
        # Only offer assignment for the exact hovered prediction link
        if hovered_link and hovered_link.startswith("substance:"):
            clicked_name = unquote(hovered_link.split(":", 1)[1])
            assign_action = menu.addAction(f"Assign substance name: {clicked_name}")
            assign_action.triggered.connect(
                lambda checked=False, s=sid, n=clicked_name: self.assign_predicted_name_to_sample(s, n)
            )
        else:
            disabled = menu.addAction("Assign substance name")
            disabled.setEnabled(False)

        # Display name on plate (same behavior as characteristics window checkbox)
        display_action = menu.addAction("Display name on plate")
        display_action.setCheckable(True)
        display_action.setChecked(bool(self.samples.get(sid, {}).get('show_on_plate', False)))
        display_action.triggered.connect(
            lambda checked=False, s=sid, n=clicked_name: (
                self.assign_predicted_name_to_sample(s, n) if (checked and n) else None,
                self.set_sample_show_on_plate(s, checked)
            )
        )

        menu.exec(label_widget.mapToGlobal(pos))

    def show_substance_context_menu(self, sid, label_widget, pos):
        """Right-click context menu for entries in the Substance column."""
        if sid not in self.samples:
            return

        menu = QMenu(self)
        remark_action = menu.addAction("Remark substance")
        remark_action.triggered.connect(lambda checked=False, s=sid: self.remark_substance(s))
        remove_action = menu.addAction("Remove substance")
        remove_action.triggered.connect(lambda checked=False, s=sid: self.remove_substance(s))
        menu.exec(label_widget.mapToGlobal(pos))

    def get_marked_plate_indices(self, sid):
        """Return sorted plate indices that already contain a spot for this substance."""
        marked = []
        for plate_idx, slot in enumerate(self.slots):
            if any(spot.get('sample_id') == sid for spot in slot.image_label.spots):
                marked.append(plate_idx)
        return marked

    def current_marking_sid(self):
        """Return the sample ID currently being marked, if any."""
        if self.mark_substance_button.isChecked():
            return self.active_regular_marking_sid
        for sid, button in self.reference_buttons.items():
            if button.isChecked():
                return sid
        return None

    def remark_substance(self, sid):
        """Re-enter marking mode for a regular substance that is missing plate spots."""
        if sid not in self.samples or sid <= 0:
            return

        if len(self.get_marked_plate_indices(sid)) >= len(self.slots):
            return

        self.active_regular_marking_sid = sid
        if self.mark_substance_button.isChecked():
            self.toggle_mark_substance(True)
            return

        self.mark_substance_button.setChecked(True)
        self.toggle_mark_substance(True)

    def remove_substance(self, sid):
        """Remove a substance from result state and from all plate spots."""
        if sid not in self.samples:
            return

        # If this substance is currently in an active marking mode, stop that mode first.
        if sid > 0 and self.mark_substance_button.isChecked() and sid == self.active_regular_marking_sid:
            self.mark_substance_button.click()
        elif sid in self.reference_buttons and self.reference_buttons[sid].isChecked():
            self.reference_buttons[sid].click()

        # Remove all matching spots from all plates.
        for slot in self.slots:
            slot.image_label.spots = [spot for spot in slot.image_label.spots if spot.get('sample_id') != sid]
            slot.image_label.update()

        # Close characteristics window, if open.
        if sid in self.char_windows:
            try:
                if self.char_windows[sid] is not None:
                    self.char_windows[sid].close()
                    self.char_windows[sid].deleteLater()
            finally:
                self.char_windows.pop(sid, None)

        # Remove sample state from memory.
        self.samples.pop(sid, None)

        if hasattr(self, '_prediction_hover_link_by_sid'):
            self._prediction_hover_link_by_sid.pop(sid, None)

        self.update_results_display()

    def open_characteristics_window(self, sid):
        if sid not in self.samples:
            return

        from gui.substance_characteristics_window import SubstanceCharacteristicsWindow
        from PyQt6.QtSql import QSqlDatabase

        # Ensure DB connection
        if QSqlDatabase.contains("qt_sql_default_connection"):
            db = QSqlDatabase.database()
        else:
             db = self._ensure_default_db_connection()
             if not db.isOpen():
                 return

        # Manage window (initialized in __init__)
        sample_name = self.samples[sid]['name']
        current_group = self.samples[sid].get('filter_group')
        current_genus = self.samples[sid].get('filter_genus')
        current_family = self.samples[sid].get('filter_family')

        current_vis = self.samples[sid].get('filter_vis', False)
        current_uvs = self.samples[sid].get('filter_uvs', False)
        current_uvl = self.samples[sid].get('filter_uvl', False)
        current_aft_vis = self.samples[sid].get('filter_aft_vis')
        current_aft_uv = self.samples[sid].get('filter_aft_uv')

        assigned_name = self.samples[sid].get('assigned_name')
        candidates = self.samples[sid].get('last_matches', [])
        show_on_plate = self.samples[sid].get('show_on_plate', False)
        font_size = self.samples[sid].get('font_size', 8)
        current_color = self.samples[sid].get('color', QColor("white"))

        # Unique key? sid is unique.
        if sid in self.char_windows and self.char_windows[sid].isVisible():
            self.char_windows[sid].raise_()
            self.char_windows[sid].activateWindow()
            return

        window = SubstanceCharacteristicsWindow(sid, sample_name, current_group, current_genus, current_family,
                                                current_vis, current_uvs, current_uvl,
                                                current_aft_vis, current_aft_uv,
                                                assigned_name, candidates, show_on_plate, font_size, current_color, db)
        window.filterChanged.connect(self.set_sample_filter)
        window.finished.connect(lambda: self.on_characteristics_window_closed(sid))
        self.char_windows[sid] = window
        window.show()
        self.update_highlighting()  # Update highlighting when window is open

    def on_characteristics_window_closed(self, sid):
        """Called when a characteristics window is closed."""
        self.update_highlighting()  # Update highlighting when window closes

    def update_highlighting(self):
        """Update the highlighting state for all spots based on open characteristics windows."""
        # Collect all open window SIDs
        open_sids = set()
        for sid, win in self.char_windows.items():
            print(f"DEBUG: {sid}, {win}")
            print(f"DEBUG: {win.isVisible()}")
            if win and win.isVisible():
                open_sids.add(sid)
        print(f"DEBUG: OPEN_SIDS:{open_sids}")

        # Update each slot's highlighted samples
        for slot in self.slots:
            slot.image_label.set_highlighted_samples(open_sids)

    def set_sample_filter(self, sid, group_name, genus, family, is_vis, is_uvs, is_uvl, aft_vis, aft_uv, assigned_name, show_on_plate, font_size, spot_color):
        if sid in self.samples:
            self.samples[sid]['filter_group'] = group_name
            self.samples[sid]['filter_genus'] = genus
            self.samples[sid]['filter_family'] = family
            self.samples[sid]['filter_vis'] = is_vis
            self.samples[sid]['filter_uvs'] = is_uvs
            self.samples[sid]['filter_uvl'] = is_uvl
            self.samples[sid]['filter_aft_vis'] = aft_vis
            self.samples[sid]['filter_aft_uv'] = aft_uv
            self.samples[sid]['assigned_name'] = assigned_name
            self.samples[sid]['show_on_plate'] = show_on_plate
            self.samples[sid]['font_size'] = font_size

            color = QColor(spot_color)
            if color.isValid():
                self.samples[sid]['color'] = color
                color_map = {sample_id: data['color'] for sample_id, data in self.samples.items() if data.get('color') is not None}
                for slot in self.slots:
                    slot.image_label.set_global_colors(color_map)
                    slot.image_label.update()

            self.update_results_display()

    def ensure_single_mode(self, active_btn):
        # Helper to uncheck other buttons
        buttons = [self.mark_substance_button, *self.reference_buttons.values()]
        for btn in buttons:
            if btn != active_btn and btn.isChecked():
                btn.click() # This triggers its toggle handler to clean up

    def activate_marking_mode(self, sid, color, name):
        if sid not in self.samples:
             self.samples[sid] = {'color': color, 'name': name}

        color_map = {k: v['color'] for k, v in self.samples.items()}
        for slot in self.slots:
            slot.image_label.set_global_colors(color_map)
            slot.image_label.set_add_sample_mode(True, sid)

    def _read_database_created_text(self, cur):
        """Read DB creation timestamp text from metadata table (if available)."""
        import sqlite3
        from datetime import datetime

        try:
            cur.execute("PRAGMA table_info(metadata)")
            cols = [row[1] for row in cur.fetchall()]
            created_col = None
            for candidate in ("created_at", "created", "creation_date", "created_on", "date_created"):
                if candidate in cols:
                    created_col = candidate
                    break

            if not created_col:
                return None

            cur.execute(f'SELECT "{created_col}" FROM metadata WHERE "{created_col}" IS NOT NULL LIMIT 1')
            row = cur.fetchone()
            if not row or row[0] is None:
                return None

            raw_value = str(row[0]).strip()
            if not raw_value:
                return None

            if raw_value.isdigit():
                try:
                    return datetime.fromtimestamp(int(raw_value)).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass

            return raw_value
        except sqlite3.Error:
            return None

    def _collect_database_about_info(self):
        """Collect lightweight database info for display in the About dialog."""
        import os
        import sqlite3

        info_lines = []
        db_path = getattr(self, 'db_path', None)
        if not db_path or not os.path.exists(db_path):
            return info_lines

        try:
            file_size_mb = os.path.getsize(db_path) / (1024 * 1024)
            info_lines.append(f"Database file: {os.path.basename(db_path)} ({file_size_mb:.2f} MB)")
        except OSError:
            info_lines.append(f"Database file: {os.path.basename(db_path)}")

        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()

            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
            table_names = [row[0] for row in cur.fetchall()]
            info_lines.append(f"Database tables: {len(table_names)}")

            for table in ("Substances", "Lichens"):
                if table in table_names:
                    cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                    row_count = cur.fetchone()[0]
                    info_lines.append(f"{table} rows: {row_count}")

            if "metadata" in table_names:
                metadata_created = self._read_database_created_text(cur)
                if metadata_created:
                    info_lines.append(f"Database created: {metadata_created}")
                else:
                    info_lines.append("Database created: available in metadata table")

            conn.close()
        except sqlite3.Error:
            info_lines.append("Database statistics unavailable")

        return info_lines

    def show_about_dialog(self):
        import os
        version = "Unknown"
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        version_path = os.path.join(base_path, "VERSION")
        if os.path.exists(version_path):
            with open(version_path, 'r') as f:
                version = f.read().strip()

        dialog = QDialog(self)
        dialog.setWindowTitle("About TLCid")
        dialog.setMinimumWidth(460)

        layout = QVBoxLayout()
        dialog.setLayout(layout)

        icon_path = os.path.join(base_path, "icon.png")
        if os.path.exists(icon_path):
            icon_label = QLabel()
            icon_pixmap = QPixmap(icon_path)
            if not icon_pixmap.isNull():
                icon_label.setPixmap(icon_pixmap.scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(icon_label)

        about_lines = [
            f"TLCid v{version}",
            "",
            "Copyright by Philipp Resl 2026"
        ]

        db_info_lines = self._collect_database_about_info()
        if db_info_lines:
            about_lines.extend(["", "Database statistics:"])
            about_lines.extend(db_info_lines)

        text_label = QLabel()
        text_label.setText("\n".join(about_lines))
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text_label)

        attribution_text = (
            'Chemical substance data is based on Elix 2022 - A catalogue of standardized '
            'chromatographic data and biosynthetic relationships for lichen substances '
            '(6th edition). \n\nOccurrence data of substances in lichens is based on:\n '
            'Nimis P.L., 2026. ITALIC - The Information System on Italian Lichens. '
            'Version 8.0. University of Trieste, Dept. of Biology, '
            '(https://dryades.units.it/italic) and \nLIAS 1995–2026. A Global Information '
            'System for Lichenized and Non-Lichenized Ascomycetes: www.lias.net.\n\n '
            'Lichen taxonomy is based on: \nGBIF Secretariat (2023). GBIF Backbone '
            'Taxonomy. Checklist dataset https://doi.org/10.15468/39omei accessed via '
            'GBIF.org.'
        )
        attribution_label = QLabel(attribution_text)
        attribution_label.setWordWrap(True)
        attribution_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        attribution_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(attribution_label)

        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_layout.addWidget(close_button)
        close_layout.addStretch()
        layout.addLayout(close_layout)

        dialog.exec()

    def show_settings_window(self):
        from gui.settings_window import SettingsWindow
        if not hasattr(self, 'settings_window') or self.settings_window is None:
            self.settings_window = SettingsWindow()
            self.settings_window.settingsChanged.connect(self.update_detection_settings)

        self.settings_window.set_current_settings(
            self.detection_method,
            self.detection_range,
            self.relative_rf_display,
            self.allow_missing_rf_values,
            self.display_rf_classes,
            self.display_support_lines,
        )
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def show_species_prediction_window(self):
        from gui.species_prediction_window import SpeciesPredictionWindow
        from PyQt6.QtSql import QSqlDatabase

        # Gather all current predicted substances with their sample info
        prediction_data = []
        # Sort samples by ID to keep the list ordered
        sorted_sample_ids = sorted(self.samples.keys())

        for sid in sorted_sample_ids:
            if sid > 0: # Skip reference markers
                sdata = self.samples[sid]

                assigned = sdata.get('assigned_name')
                if assigned:
                    # If manually named, only use that name for species prediction
                    prediction_data.append({
                        'name': assigned,
                        'sample_name': assigned,
                        'color': sdata['color']
                    })
                else:
                    # Otherwise, use all predicted candidates for this spot
                    display_name = sdata['name']
                    matches = sdata.get('last_matches', [])
                    for score, name in matches:
                        prediction_data.append({
                            'name': name,
                            'sample_name': display_name,
                            'color': sdata['color']
                        })

        if not prediction_data:
            QMessageBox.warning(self, "No Predictions", "No substances have been predicted yet. Please mark spots on the plates first.")
            return

        # Ensure DB connection
        if QSqlDatabase.contains("qt_sql_default_connection"):
            db = QSqlDatabase.database()
        else:
             db = self._ensure_default_db_connection()
             if not db.isOpen():
                 return

        self.species_window = SpeciesPredictionWindow(prediction_data, db)
        self.species_window.show()

    def _build_combined_export_image(self, label_font_size_delta=10):
        """Build combined plate image used by export/report. Returns QImage or None."""
        from PyQt6.QtGui import QImage, QFont

        pixmaps = []
        labels = []
        for i, slot in enumerate(self.slots):
            pm = slot.get_marked_pixmap(label_font_size_delta=label_font_size_delta)
            if pm is not None:
                pixmaps.append(pm)
                labels.append(self.plate_labels[i])

        if not pixmaps:
            return None

        padding = 20
        label_height = 40
        max_h = max(pm.height() for pm in pixmaps)

        scaled_pixmaps = []
        for pm in pixmaps:
            if pm.height() != max_h:
                scaled = pm.scaledToHeight(max_h, Qt.TransformationMode.SmoothTransformation)
            else:
                scaled = pm
            scaled_pixmaps.append(scaled)

        total_w = sum(pm.width() for pm in scaled_pixmaps) + padding * (len(scaled_pixmaps) - 1)
        total_h = max_h + label_height

        combined = QImage(total_w, total_h, QImage.Format.Format_RGB32)
        combined.fill(QColor("white"))

        painter = QPainter(combined)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        x_offset = 0
        label_font = QFont()
        label_font_size = max(14, int(max_h / 40))
        label_font.setPointSize(label_font_size)
        label_font.setBold(True)

        for pm, label in zip(scaled_pixmaps, labels):
            painter.setFont(label_font)
            painter.setPen(QColor("black"))
            text_rect = painter.fontMetrics().boundingRect(label)
            text_x = x_offset + (pm.width() - text_rect.width()) // 2
            text_y = label_height - 8
            painter.drawText(text_x, text_y, label)
            painter.drawPixmap(x_offset, label_height, pm)
            x_offset += pm.width() + padding

        painter.end()
        return combined

    def get_database_version_text(self):
        """Best-effort database version text for reports (align with About dialog)."""
        import os
        import sqlite3

        db_path = getattr(self, 'db_path', None)
        if not db_path or not os.path.exists(db_path):
            return "unknown"

        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'")
            has_meta = cur.fetchone() is not None

            if has_meta:
                metadata_created = self._read_database_created_text(cur)
                if metadata_created:
                    conn.close()
                    return metadata_created

            cur.execute("PRAGMA user_version")
            row = cur.fetchone()
            conn.close()
            if row and int(row[0]) > 0:
                return f"user_version={int(row[0])}"
        except Exception:
            pass

        return "unknown"

    def generate_report(self):
        """Generate PDF report with combined image, top predictions table, and metadata."""
        PDFReportGenerator(self).generate()

    def _find_row_by_sid(self, sid):
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == sid:
                return row
        return None

    def export_combined_image(self):
        """Export a combined image of all loaded plates with markings."""
        combined = self._build_combined_export_image(label_font_size_delta=10)
        if combined is None:
            QMessageBox.warning(self, "No Images", "No plate images are loaded. Please load at least one image before exporting.")
            return

        file_name, _ = QFileDialog.getSaveFileName(
            self, "Export Combined Image", "", "PNG Images (*.png);;JPEG Images (*.jpg)"
        )
        if not file_name:
            return

        combined.save(file_name)

    def format_rf_value(self, value):
        if value is None:
            return "-"
        if self.relative_rf_display:
            return f"{value * 100:.0f}"
        return f"{value:.2f}"

    def update_detection_settings(self, method, range_val, relative_rf=True, allow_missing_rf_values=False, display_rf_classes=False, display_support_lines=None):
        self.detection_method = method
        self.detection_range = range_val
        self.relative_rf_display = relative_rf
        if display_support_lines is None:
            display_support_lines = self.display_support_lines
        self.allow_missing_rf_values = allow_missing_rf_values
        self.display_support_lines = display_support_lines
        self.display_rf_classes = display_rf_classes
        if not display_rf_classes:
            self._rf_classes_missing_popup_shown = False
        for slot in self.slots:
            slot.set_relative_rf_display(relative_rf)
            slot.image_label.show_support_lines = display_support_lines
            slot.set_support_lines_action_checked(display_support_lines)
            slot.set_rf_classes_action_checked(display_rf_classes)
        self.update_detection_status_label()

        # Keep settings window controls synchronized when open
        if hasattr(self, 'settings_window') and self.settings_window is not None:
            self.settings_window.set_current_settings(
                method,
                range_val,
                relative_rf,
                allow_missing_rf_values,
                display_rf_classes,
                display_support_lines,
            )

        self.update_results_display()

    def set_display_support_lines(self, checked):
        """Apply the application-level support-lines switch to all plates."""
        self.display_support_lines = checked
        if hasattr(self, 'settings_window') and self.settings_window is not None:
            self.settings_window.display_support_lines_checkbox.blockSignals(True)
            self.settings_window.display_support_lines_checkbox.setChecked(checked)
            self.settings_window.display_support_lines_checkbox.blockSignals(False)
        for slot in self.slots:
            slot.image_label.show_support_lines = checked
            slot.set_support_lines_action_checked(checked)
        self.update_results_display()

    def set_display_rf_classes(self, checked):
        """Apply the application-level Rf-classes switch to all plates."""
        self.display_rf_classes = checked
        if not checked:
            self._rf_classes_missing_popup_shown = False
        if hasattr(self, 'settings_window') and self.settings_window is not None:
            self.settings_window.display_rf_classes_checkbox.blockSignals(True)
            self.settings_window.display_rf_classes_checkbox.setChecked(checked)
            self.settings_window.display_rf_classes_checkbox.blockSignals(False)
        for slot in self.slots:
            slot.set_rf_classes_action_checked(checked)
        self.update_results_display()

    def sample_allows_missing_rf_values(self, sid):
        if self.allow_missing_rf_values:
            return True
        return bool(self.samples.get(sid, {}).get('allow_missing_rf_values', False))

    def set_sample_allow_missing_rf_values(self, sid, allow_missing_rf_values):
        if sid not in self.samples:
            return
        self.samples[sid]['allow_missing_rf_values'] = bool(allow_missing_rf_values)
        self.update_results_display()

    def on_main_range_changed(self, val):
        self.detection_range = val
        self.update_detection_status_label()
        # Sync to all plates
        for i, slot in enumerate(self.slots):
            slot.set_range(val)
            self.plate_ranges[i] = val
        self.update_results_display()
        # Sync Settings Window if open
        if hasattr(self, 'settings_window') and self.settings_window is not None:
            self.settings_window.range_spin.blockSignals(True)
            self.settings_window.range_spin.setValue(val)
            self.settings_window.range_spin.blockSignals(False)

    def on_plate_range_changed(self, plate_idx, range_val):
        """Handle per-plate range changes."""
        self.plate_ranges[plate_idx] = range_val
        self.update_results_display()

    def get_plate_calibration_mode(self, plate_idx):
        return _normalize_calibration_mode(
            self.plate_calibration_modes.get(plate_idx, self.calibration_mode)
        )

    def set_plate_calibration_mode(self, plate_idx, mode, update_results=True):
        normalized_mode = _normalize_calibration_mode(mode)
        self.plate_calibration_modes[plate_idx] = normalized_mode
        if 0 <= plate_idx < len(self.slots):
            self.slots[plate_idx].set_calibration_mode(normalized_mode)
        if update_results:
            self.update_results_display()

    def on_plate_calibration_mode_changed(self, plate_idx, mode):
        self.set_plate_calibration_mode(plate_idx, mode, update_results=True)

    def update_detection_status_label(self):
        # Keep the legacy helper as the central place for synchronizing
        # inline detection-related controls.
        if hasattr(self, 'range_main'):
            self.range_main.setVisible(False)  # Hide global range, use per-plate instead
            # Sync spinbox value without triggering valueChanged
            self.range_main.blockSignals(True)
            self.range_main.setValue(self.detection_range)
            self.range_main.blockSignals(False)

    def deactivate_marking_mode(self):
        self.active_regular_marking_sid = None
        for slot in self.slots:
            slot.image_label.set_add_sample_mode(False)

    def toggle_mark_substance(self, checked):
        if checked:
            self.ensure_single_mode(self.mark_substance_button)

            # Entering Add Mode
            self.mark_substance_button.setText("Stop Marking")
            sid = self.active_regular_marking_sid
            if sid is None:
                sid = self.next_sample_id
                self.next_sample_id += 1
                self.active_regular_marking_sid = sid
            color = self.colors[(sid - 1) % len(self.colors)]
            self.activate_marking_mode(sid, color, f"Substance {sid}")
        else:
            self.mark_substance_button.setText("New Substance")
            self.deactivate_marking_mode()

    def toggle_mark_reference(self, sid, checked):
        standard = get_reference_standard(sid)
        if standard is None:
            return

        button = self.reference_buttons.get(sid, getattr(self, standard.button_attr, None))
        if button is None:
            return

        if checked:
            self.ensure_single_mode(button)
            button.setText(standard.active_text)
            self.activate_marking_mode(sid, standard.color(), standard.sample_name)
        else:
            button.setText(standard.inactive_text)
            self.deactivate_marking_mode()

    def toggle_mark_atranorin(self, checked):
        self.toggle_mark_reference(0, checked)

    def toggle_mark_norstictic(self, checked):
        self.toggle_mark_reference(-1, checked)

    def toggle_mark_rhizocarpic(self, checked):
        self.toggle_mark_reference(-2, checked)

    def toggle_mark_lecanoric(self, checked):
        self.toggle_mark_reference(-3, checked)

    def toggle_mark_evernic(self, checked):
        self.toggle_mark_reference(-4, checked)

    def _raw_rf_from_slot_y(self, slot, raw_y):
        raw_start = slot.image_label.start_line_y
        raw_front = slot.image_label.front_line_y

        u_start = 1.0 - raw_start
        u_front = 1.0 - raw_front
        u_spot = 1.0 - raw_y
        denom = u_front - u_start

        if abs(denom) < 1e-6:
            return 0.0
        return (u_spot - u_start) / denom

    def _correct_plate_rf(self, raw_rf, standards, mode=None):
        return correct_rf(raw_rf, standards, mode or self.calibration_mode)

    def _support_line_raw_rf(self, corrected_rf, standards, mode=None):
        return support_line_raw_rf(corrected_rf, standards, mode or self.calibration_mode)

    def _support_line_widget_y(self, slot, corrected_rf, standards, mode=None):
        raw_rf = self._support_line_raw_rf(corrected_rf, standards, mode)
        return slot.image_label.start_line_y + (raw_rf * (slot.image_label.front_line_y - slot.image_label.start_line_y))

    def _custom_line_rf_label(self, slot, raw_y, standards, mode=None):
        raw_rf = self._raw_rf_from_slot_y(slot, raw_y)
        corrected_rf = self._correct_plate_rf(raw_rf, standards, mode)
        return self.format_rf_value(corrected_rf)

    def _reference_name_for_standard_value(self, plate_idx, rf_value):
        std_name = reference_standard_name_for_rf_value(rf_value)
        if std_name is not None:
            return std_name

        for ref_sid, sdata in self.samples.items():
            if sdata.get('is_reference', False) and sdata.get('reference_rf'):
                ref_rf = sdata['reference_rf']
                if plate_idx < len(ref_rf) and ref_rf[plate_idx] == rf_value:
                    return sdata.get('assigned_name', f"Substance {ref_sid}")
        return "Unknown"

    def _rf_class_support_line_specs(self, slot, atranorin_y, norstictic_y):
        anchor_points = [
            (1.0, slot.image_label.start_line_y),
            (4.0, norstictic_y),
            (7.0, atranorin_y),
            (8.0, slot.image_label.front_line_y),
        ]
        specs = []
        for class_idx in range(1, 9):
            y_norm = slot.image_label.start_line_y
            for (x1, y1), (x2, y2) in zip(anchor_points, anchor_points[1:]):
                if x1 <= class_idx <= x2:
                    if abs(x2 - x1) > 1e-7:
                        y_norm = y1 + ((class_idx - x1) * (y2 - y1) / (x2 - x1))
                    else:
                        y_norm = y1
                    break
            specs.append((y_norm, str(class_idx)))
        return specs

    def _show_rf_classes_missing_popup(self):
        if self._rf_classes_missing_popup_shown:
            return
        self._rf_classes_missing_popup_shown = True
        QMessageBox.information(
            self,
            "Rf classes unavailable",
            "Atranorin and Norstictic Acid have to be references to use Rf classes.",
        )

    def _apply_support_line_mapping(self, active_standards, rf_class_reference_positions=None):
        rf_class_reference_positions = rf_class_reference_positions or {}
        missing_rf_class_requirements = False
        for plate_idx, slot in enumerate(self.slots):
            standards = list(active_standards.get(plate_idx, []))
            calibration_mode = self.get_plate_calibration_mode(plate_idx)
            if standards:
                slot.image_label.support_line_y_mapper = (
                    lambda rf_value, slot=slot, standards=standards, calibration_mode=calibration_mode: self._support_line_widget_y(slot, rf_value, standards, calibration_mode)
                )
            else:
                slot.image_label.support_line_y_mapper = None
            slot.image_label.custom_line_rf_label_provider = (
                lambda raw_y, slot=slot, standards=standards, calibration_mode=calibration_mode: self._custom_line_rf_label(slot, raw_y, standards, calibration_mode)
            )

            slot.image_label.support_line_specs_provider = None
            slot_rf_classes_enabled = slot.rf_classes_checked() if hasattr(slot, 'rf_classes_checked') else self.display_rf_classes
            if slot_rf_classes_enabled:
                refs = rf_class_reference_positions.get(plate_idx)
                if refs is not None:
                    atranorin_y, norstictic_y = refs
                    slot.image_label.support_line_specs_provider = (
                        lambda slot=slot, atranorin_y=atranorin_y, norstictic_y=norstictic_y: self._rf_class_support_line_specs(slot, atranorin_y, norstictic_y)
                    )
                elif slot.image_label.show_lines or slot.image_label.spots:
                    missing_rf_class_requirements = True

            if slot.image_label.show_lines:
                slot.image_label.update()

        if missing_rf_class_requirements:
            self._show_rf_classes_missing_popup()
        elif not missing_rf_class_requirements:
            self._rf_classes_missing_popup_shown = False

    def _safe_print(self, *args, **kwargs):
        import sys

        try:
            print(*args, **kwargs)
        except UnicodeEncodeError:
            sep = kwargs.get("sep", " ")
            end = kwargs.get("end", "\n")
            text = sep.join(str(a) for a in args)
            enc = (getattr(sys.stdout, "encoding", None) or "utf-8")
            safe = text.encode(enc, errors="backslashreplace").decode(enc, errors="replace")
            print(safe, end=end)

    def _aggregate_spots(self):
        """Return sample id -> plate index -> raw Rf values aggregated from all image slots."""
        aggregated = {}
        for i, slot in enumerate(self.slots):
            spots = slot.image_label.spots
            for spot in spots:
                self._safe_print(f"DEBUG: Spot on Plate {i}: {spot}")
                sid = spot['sample_id']
                raw_y = spot['y']
                rf_val = self._raw_rf_from_slot_y(slot, raw_y)
                aggregated.setdefault(sid, {}).setdefault(i, []).append(rf_val)
        return aggregated

    def _sync_samples_with_aggregated_spots(self, aggregated):
        """Remove regular samples with no plate spots and clear stale prediction matches."""
        ids_to_remove = [sid for sid in self.samples if sid > 0 and sid not in aggregated]

        if ids_to_remove:
            self._safe_print(f"DEBUG: Removing substances {ids_to_remove} (no spots remaining)")
        else:
            self._safe_print(
                f"DEBUG: No substances to remove. aggregated={sorted(aggregated.keys())}, "
                f"samples={sorted(self.samples.keys())}"
            )

        for sid in ids_to_remove:
            self._safe_print(f"DEBUG: Removing substance ID {sid}")
            self.samples.pop(sid)
            if sid in self.char_windows:
                try:
                    self.char_windows[sid].close()
                    self.char_windows[sid].deleteLater()
                except RuntimeError:
                    pass
                self.char_windows.pop(sid, None)

        if ids_to_remove:
            color_map = {k: v['color'] for k, v in self.samples.items()}
            for slot in self.slots:
                slot.image_label.set_global_colors(color_map)

        for _sid, sdata in self.samples.items():
            sdata['last_matches'] = []

        self._safe_print(f"DEBUG: Aggregated Rf values: {aggregated}")

    def _auto_stop_completed_marking(self, aggregated):
        """Leave marking mode once the active substance has spots on all plates."""
        if self.mark_substance_button.isChecked():
            current_sid = self.active_regular_marking_sid
            if current_sid in aggregated and len(aggregated[current_sid]) == 3:
                self.mark_substance_button.click()
            return

        for current_sid, button in self.reference_buttons.items():
            if button.isChecked() and current_sid in aggregated and len(aggregated[current_sid]) == 3:
                button.click()
                break

    def _ensure_predefined_reference_state(self, aggregated):
        """Enable configured predefined references when they are newly marked on a plate."""
        for ref_sid, ref_rf in predefined_reference_rf_values().items():
            if ref_sid in aggregated and ref_sid in self.samples:
                if 'is_reference' not in self.samples[ref_sid]:
                    self.samples[ref_sid]['is_reference'] = True
                    self.samples[ref_sid]['reference_rf'] = ref_rf

    def _build_active_standards(self, aggregated):
        """Return active calibration points per plate as observed Rf -> standard Rf pairs."""
        active_standards = {0: [], 1: [], 2: []}

        for ref_sid, standard in REFERENCE_STANDARDS.items():
            if ref_sid in aggregated and self.samples.get(ref_sid, {}).get('is_reference', False):
                for idx, vals in aggregated[ref_sid].items():
                    if vals and idx in standard.rf_by_plate:
                        active_standards[idx].append((vals[0], standard.rf_by_plate[idx]))

        for sid, sdata in self.samples.items():
            if sid > 0 and sdata.get('is_reference', False) and sid in aggregated:
                ref_rf = sdata.get('reference_rf')
                if ref_rf:
                    for idx, vals in aggregated[sid].items():
                        if vals and idx < len(ref_rf) and ref_rf[idx] is not None:
                            active_standards[idx].append((vals[0], ref_rf[idx]))
                            self._safe_print(
                                f"DEBUG: Added reference substance {sid} (name: {sdata.get('assigned_name')}) "
                                f"to plate {idx} calibration: observed={vals[0]:.3f}, std={ref_rf[idx]:.3f}"
                            )

        for idx in active_standards:
            active_standards[idx].sort(key=lambda x: x[0])
        return active_standards

    def _build_rf_class_reference_positions(self):
        rf_class_reference_positions = {}
        if self.samples.get(0, {}).get('is_reference', False) and self.samples.get(-1, {}).get('is_reference', False):
            for plate_idx, slot in enumerate(self.slots):
                atranorin_spot = next((spot for spot in slot.image_label.spots if spot['sample_id'] == 0), None)
                norstictic_spot = next((spot for spot in slot.image_label.spots if spot['sample_id'] == -1), None)
                if atranorin_spot is not None and norstictic_spot is not None:
                    rf_class_reference_positions[plate_idx] = (atranorin_spot['y'], norstictic_spot['y'])
        return rf_class_reference_positions

    def _debug_print_calibration(self, active_standards):
        self._safe_print("=" * 80)
        self._safe_print("CALIBRATION REFERENCE SUBSTANCES PER PLATE")
        self._safe_print("=" * 80)
        for idx in [0, 1, 2]:
            standards = active_standards[idx]
            self._safe_print(f"\nPlate {['A', 'B', 'C'][idx]}:")
            if not standards:
                self._safe_print("  No reference standards active - using raw Rf values")
            else:
                self._safe_print("  Calibration points (observed Rf -> standard Rf):")
                for obs, std in standards:
                    std_name = self._reference_name_for_standard_value(idx, std)
                    self._safe_print(f"    {std_name}: {obs:.3f} -> {std:.3f}")
        self._safe_print("=" * 80)

    def _update_plate_name_and_font_maps(self):
        name_map = {}
        font_size_map = {}
        for sid, sdata in self.samples.items():
            if sdata.get('show_on_plate', False):
                assigned = sdata.get('assigned_name')
                name_map[sid] = assigned if assigned else sdata['name']
                font_size_map[sid] = sdata.get('font_size', 8)

        for slot in self.slots:
            slot.image_label.set_global_names(name_map)
            slot.image_label.set_global_font_sizes(font_size_map)

    def _render_result_rows(self, aggregated, active_standards):
        self.results_renderer.render(aggregated, active_standards)

    def update_results_display(self):
        aggregated = self._aggregate_spots()
        self._sync_samples_with_aggregated_spots(aggregated)
        self._auto_stop_completed_marking(aggregated)
        self._ensure_predefined_reference_state(aggregated)
        active_standards = self._build_active_standards(aggregated)
        rf_class_refs = self._build_rf_class_reference_positions()
        self._apply_support_line_mapping(active_standards, rf_class_refs)
        self._debug_print_calibration(active_standards)
        self._render_result_rows(aggregated, active_standards)
        self._update_plate_name_and_font_maps()
        self._update_reference_button_colors(aggregated)

    def _update_reference_button_colors(self, aggregated):
        """Update the text color of reference substance buttons when marked on all three plates."""
        ref_button_config = [
            (sid, self.reference_buttons[sid], standard.color_name)
            for sid, standard in REFERENCE_STANDARDS.items()
        ]

        for sid, button, color in ref_button_config:
            # Check if this reference substance is marked on all three plates
            if sid in aggregated and len(aggregated[sid]) == 3:
                # Marked on all three plates - apply color to button text
                button.setStyleSheet(f"color: {color}; font-weight: bold;")
            else:
                # Not marked on all plates - reset to default
                button.setStyleSheet("")

    def load_examples(self):
        import os
        base_path = os.path.dirname(os.path.abspath(__file__))
        root_path = os.path.dirname(base_path)
        examples_dir = os.path.join(root_path, "examples")
        example_files = ["A.jpeg", "B.jpeg", "C.jpeg"]

        for i, filename in enumerate(example_files):
            if i < len(self.slots):
                full_path = os.path.join(examples_dir, filename)
                if os.path.exists(full_path):
                    pixmap = QPixmap(full_path)
                    if not pixmap.isNull():
                        self.slots[i].set_loaded_image(pixmap, full_path)

    def save_analysis(self):
        suggested_path = self.analysis_file_path or ""
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Save Analysis", suggested_path, "JSON Files (*.json)"
        )
        if not file_name:
            return False

        try:
            AnalysisSerializer.save_to_path(file_name, AnalysisSerializer.from_window_state(self))
            self.analysis_file_path = file_name
            return True
        except Exception as e:
            print(f"Error saving file: {e}")
            QMessageBox.warning(self, "Save Error", f"Could not save analysis:\n{e}")
            return False

    def load_analysis(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Load Analysis", "", "JSON Files (*.json)"
        )
        if not file_name:
            return

        try:
            data = AnalysisSerializer.load_from_path(file_name)
            self.analysis_file_path = file_name
            AnalysisSerializer.apply_to_window(self, data)
        except Exception as e:
            print(f"Error loading file: {e}")

    def _has_analysis_data(self):
        """Return True if plates are loaded and/or spots/substances exist."""
        if self.samples:
            return True

        for slot in self.slots:
            if slot.image_path or slot.image_label._original_pixmap is not None:
                return True
            if slot.image_label.spots:
                return True
            if slot.image_label.custom_lines:
                return True

        return False

    def _close_child_windows(self):
        """Close all known child/top-level windows opened from the main window."""
        for sid, win in list(self.char_windows.items()):
            try:
                if win is not None:
                    win.close()
            except RuntimeError:
                pass
        self.char_windows.clear()

        for name, win in list(self.detail_windows.items()):
            try:
                if win is not None:
                    win.close()
            except RuntimeError:
                pass
        self.detail_windows.clear()

        if hasattr(self, 'table_windows'):
            for _, win in list(self.table_windows.items()):
                try:
                    if win is not None:
                        win.close()
                except RuntimeError:
                    pass
            self.table_windows = {}

        if hasattr(self, 'settings_window') and self.settings_window is not None:
            try:
                self.settings_window.close()
            except RuntimeError:
                pass
            self.settings_window = None

        if hasattr(self, 'species_window') and self.species_window is not None:
            try:
                self.species_window.close()
            except RuntimeError:
                pass
            self.species_window = None

    def closeEvent(self, event: QCloseEvent):
        if self._has_analysis_data():
            choice = QMessageBox.question(
                self,
                "Save Analysis?",
                "Current analysis has loaded plates and/or marked substances. Save before closing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )

            if choice == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return

            if choice == QMessageBox.StandardButton.Save:
                if not self.save_analysis():
                    event.ignore()
                    return

        self._close_child_windows()
        super().closeEvent(event)

    def new_analysis(self):
        # Reset Global State
        self.samples = {}
        self.next_sample_id = 1
        self.active_regular_marking_sid = None
        self.analysis_file_path = None

        # Reset per-plate ranges to default
        self.plate_ranges = {0: 0.05, 1: 0.05, 2: 0.05}
        self.display_support_lines = False
        self.display_rf_classes = False
        self._rf_classes_missing_popup_shown = False
        for i, slot in enumerate(self.slots):
            slot.set_range(0.05)

        # Reset per-plate calibration modes to default
        self.calibration_mode = CALIBRATION_MODE_LINEAR
        self.plate_calibration_modes = {
            0: CALIBRATION_MODE_LINEAR,
            1: CALIBRATION_MODE_LINEAR,
            2: CALIBRATION_MODE_LINEAR,
        }

        # Reset Controls
        if self.mark_substance_button.isChecked():
            self.mark_substance_button.click() # This will toggle it off and reset cursors
        for button in self.reference_buttons.values():
            if button.isChecked():
                button.click()

        # Reset reference button colors
        for button in self.reference_buttons.values():
            button.setStyleSheet("")

        # Close and clear all open characteristics windows
        for sid, win in list(self.char_windows.items()):
            try:
                win.close()
            except RuntimeError:
                pass  # Widget already deleted by Qt
            try:
                win.deleteLater()
            except RuntimeError:
                pass
        self.char_windows.clear()

        # Close and clear all open detail windows
        for name, win in list(self.detail_windows.items()):
            try:
                win.close()
            except RuntimeError:
                pass
            try:
                win.deleteLater()
            except RuntimeError:
                pass
        self.detail_windows.clear()

        # Reset Slots
        for slot in self.slots:
            slot.image_path = None
            slot.image_label._original_pixmap = None
            slot.image_label.setText("No Image Loaded")
            slot.image_label.setPixmap(QPixmap()) # Clear displayed pixmap
            slot.image_label.spots = []
            slot.image_label.custom_lines = []
            slot.image_label.start_line_y = 0.9
            slot.image_label.front_line_y = 0.1
            slot.image_label.show_lines = False
            slot.image_label.show_support_lines = False
            slot.image_label.show_start_line_adjust_hint = False
            slot.image_label.support_line_y_mapper = None
            slot.image_label.support_line_specs_provider = None
            slot.set_custom_line_controls_enabled(False)
            slot._action_support_lines.setChecked(False)
            slot._action_rf_classes.setChecked(False)
            slot.set_calibration_mode(CALIBRATION_MODE_LINEAR)
            slot.image_label.set_global_colors({})
            # Signal won't fire if lines aren't moved/set via setter that emits.
            # Let's forcefully emit or set text.
            slot.image_label.linesMoved.emit(0.1, 0.9) # Inverted: 1-0.9=0.1 start, 1-0.1=0.9 front
            slot.image_label.spotsChanged.emit([])
            slot.image_label.update()

        self.update_results_display()

    def load_reference_data(self):
        bundle = self.reference_repository.load_reference_data()
        self.prediction_service.load_bundle(bundle)
        self.reference_data = self.prediction_service.reference_data
        self.genus_to_substances = self.prediction_service.genus_to_substances
        self.family_to_substances = self.prediction_service.family_to_substances
        self.reference_rf_by_name = self.prediction_service.reference_rf_by_name

    def predict_matches(self, input_data, filter_group=None, filter_genus=None, filter_family=None,
                        filter_vis=False, filter_uvs=False, filter_uvl=False,
                        filter_aft_vis=None, filter_aft_uv=None,
                        allow_missing_rf_values=False):
        # Keep compatibility with tests/extensions that mutate these public caches directly.
        self.prediction_service.reference_data = self.reference_data
        self.prediction_service.genus_to_substances = self.genus_to_substances
        self.prediction_service.family_to_substances = self.family_to_substances
        self.prediction_service.reference_rf_by_name = self.reference_rf_by_name

        return self.prediction_service.predict(
            input_data,
            detection_method=self.detection_method,
            detection_range=self.detection_range,
            plate_ranges=self.plate_ranges,
            filter_group=filter_group,
            filter_genus=filter_genus,
            filter_family=filter_family,
            filter_vis=filter_vis,
            filter_uvs=filter_uvs,
            filter_uvl=filter_uvl,
            filter_aft_vis=filter_aft_vis,
            filter_aft_uv=filter_aft_uv,
            allow_missing_rf_values=allow_missing_rf_values,
        )
