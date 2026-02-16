from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
                             QLabel, QPushButton, QFileDialog, QSizePolicy, QComboBox,
                             QTableWidget, QTableWidgetItem, QHeaderView, QColorDialog,
                             QMessageBox, QDoubleSpinBox)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor

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
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
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
        
        # Line Dragging State
        self.dragged_line = None # "Start" or "Front"

    def set_global_colors(self, colors):
        self.global_colors = colors

    def set_global_names(self, names):
        self.global_names = names
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

    def set_image(self, pixmap):
        self._original_pixmap = pixmap
        self.show_lines = True
        self.setText("") 
        self.update_display()
        self.linesMoved.emit(1.0 - self.start_line_y, 1.0 - self.front_line_y)
        self.spotsChanged.emit(self.spots)
        
    def resizeEvent(self, event):
        self.update_display()
        super().resizeEvent(event)
        
    def mouseMoveEvent(self, event):
        if not self.show_lines:
            return

        x_norm = event.position().x() / self.width()
        y_norm = event.position().y() / self.height()
        x_norm = max(0.0, min(1.0, x_norm))
        y_norm = max(0.0, min(1.0, y_norm))
        
        # Cursor feedback for lines
        if not self.adding_sample_mode and self.dragged_spot_index is None and self.dragged_line is None:
            start_px = self.start_line_y * self.height()
            front_px = self.front_line_y * self.height()
            click_y = event.position().y()
            
            if abs(click_y - start_px) < 10 or abs(click_y - front_px) < 10:
                self.setCursor(Qt.CursorShape.SplitVCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

        if self.dragged_spot_index is not None:
            self.spots[self.dragged_spot_index]['x'] = x_norm
            self.spots[self.dragged_spot_index]['y'] = y_norm
            self.update()
            self.spotsChanged.emit(self.spots)
            
        elif self.dragged_line is not None:
             # Dragging a line
            if self.dragged_line == "Start":
                self.start_line_y = y_norm
            elif self.dragged_line == "Front":
                self.front_line_y = y_norm
            self.update() 
            self.linesMoved.emit(1.0 - self.start_line_y, 1.0 - self.front_line_y)

    def mousePressEvent(self, event):
        if not self.show_lines:
            return

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
            return

        x_norm = event.position().x() / self.width()
        y_norm = event.position().y() / self.height()

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
                 # 2. Line Hit
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
        if not self.adding_sample_mode:
             self.setCursor(Qt.CursorShape.ArrowCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.show_lines:
            painter = QPainter(self)
            
            # Draw Lines
            painter.setPen(QPen(QColor("green"), 2))
            start_y = int(self.start_line_y * self.height())
            painter.drawLine(0, start_y, self.width(), start_y)
            
            painter.setPen(QPen(QColor("red"), 2))
            front_y = int(self.front_line_y * self.height())
            painter.drawLine(0, front_y, self.width(), front_y)
            
            # Draw Spots
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for spot in self.spots:
                sid = spot['sample_id']
                color = self.global_colors.get(sid, QColor("black"))
                painter.setPen(QPen(color, 2))
                
                px = int(spot['x'] * self.width())
                py = int(spot['y'] * self.height())
                painter.drawEllipse(px - self.spot_radius, py - self.spot_radius, 
                                    self.spot_radius * 2, self.spot_radius * 2)
                
                name = self.global_names.get(sid)
                if name:
                    font = painter.font()
                    font.setPointSize(8)
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

class ImageSlot(QWidget):
    def __init__(self, title):
        super().__init__()
        self.image_path = None # Store loaded image path
        self.layout = QVBoxLayout()
        self.layout.setSpacing(2)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)
        
        # Title
        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.title_label.font()
        font.setPointSize(14)
        font.setBold(True)
        self.title_label.setFont(font)
        self.layout.addWidget(self.title_label)
        
        # Image Area
        self.image_label = SquareLabel()
        self.layout.addWidget(self.image_label)
        
        # Controls
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addLayout(controls_layout)

        # Load Button
        self.load_button = QPushButton("Load Image")
        self.load_button.clicked.connect(self.load_image)
        controls_layout.addWidget(self.load_button)
        
        # Export Button
        self.export_button = QPushButton("Export Image")
        self.export_button.clicked.connect(self.export_marked_image)
        controls_layout.addWidget(self.export_button)
        
    def load_image(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "", "Images (*.png *.xpm *.jpg *.jpeg *.bmp *.tif *.tiff)"
        )
        if file_name:
            self.image_path = file_name
            pixmap = QPixmap(file_name)
            if not pixmap.isNull():
                self.image_label.set_image(pixmap)

    def get_marked_pixmap(self):
        """Return a QPixmap of the original image with all annotations drawn on it,
        or None if no image is loaded."""
        if not self.image_path or not self.image_label._original_pixmap:
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
                font.setPointSize(int(9 * scale_factor))
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TLCid")
        self.resize(1200, 700) 
        
        # State
        self.samples = {} # {id: {'color': QColor, 'name': str}}
        self.genus_to_substances = {} # Cache for genus-specific substance filtering
        self.next_sample_id = 1
        self.colors = [
            QColor("cyan"), QColor("magenta"), QColor("yellow"), 
            QColor("blue"), QColor("orange"), QColor("purple"), 
            QColor("lime"), QColor("pink")
        ]
        
        self.char_windows = {}    # {sid: SubstanceCharacteristicsWindow}
        self.detail_windows = {}  # {name: SubstanceDetailWindow}
        
        self.reference_data = [] # Cache for prediction
        self.load_reference_data() # Load DB data on startup
        
        # Standards configuration (Values / 100.0)
        # ID 0: Atranorin
        self.atranorin_standards = {
            0: 0.76, # A
            1: 0.73, # Bprime
            2: 0.79  # C
        }
        # ID -1: Norstictic Acid (A=40, B=32, C=30)
        self.norstictic_standards = {
            0: 0.40, # A
            1: 0.32, # Bprime
            2: 0.30  # C
        }

        # Detection Settings
        self.detection_method = "Range"
        self.detection_range = 0.05

        
        # Main Layout Construction
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # Toolbar Area
        toolbar_layout = QHBoxLayout()
        
        self.mark_substance_button = QPushButton("Mark Substance")
        self.mark_substance_button.setCheckable(True)
        self.mark_substance_button.clicked.connect(self.toggle_mark_substance)
        toolbar_layout.addWidget(self.mark_substance_button)
        
        self.mark_atranorin_button = QPushButton("Mark Atranorin")
        self.mark_atranorin_button.setCheckable(True)
        self.mark_atranorin_button.clicked.connect(self.toggle_mark_atranorin)
        toolbar_layout.addWidget(self.mark_atranorin_button)
        
        self.mark_norstictic_button = QPushButton("Mark Norstictic")
        self.mark_norstictic_button.setCheckable(True)
        self.mark_norstictic_button.clicked.connect(self.toggle_mark_norstictic)
        toolbar_layout.addWidget(self.mark_norstictic_button)

        # Detection Status Label
        self.detection_status_label = QLabel()
        self.detection_status_label.setStyleSheet("color: gray; padding-left: 10px;")
        toolbar_layout.addWidget(self.detection_status_label)

        # Inline Range control in Main Window
        self.range_main = QDoubleSpinBox()
        self.range_main.setRange(0.0, 1.0)
        self.range_main.setSingleStep(0.01)
        self.range_main.setValue(self.detection_range)
        self.range_main.valueChanged.connect(self.on_main_range_changed)
        toolbar_layout.addWidget(self.range_main)

        self.update_detection_status_label()
        
        toolbar_layout.addStretch()
        
        # App Icon
        import os
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_path, "icon.png")
        if os.path.exists(icon_path):
            self.icon_label = QLabel()
            icon_pixmap = QPixmap(icon_path)
            if not icon_pixmap.isNull():
                self.icon_label.setPixmap(icon_pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                toolbar_layout.addWidget(self.icon_label)

        main_layout.addLayout(toolbar_layout)

        # Slots Area
        slots_layout = QHBoxLayout()
        self.slots = []
        self.plate_labels = ['A', "B'", 'C']
        for label in self.plate_labels:
            slot = ImageSlot(label)
            # Connect spot changes to aggregation logic
            slot.image_label.spotsChanged.connect(self.update_results_display)
            # Also connect line moves to aggregation logic
            slot.image_label.linesMoved.connect(lambda s, f: self.update_results_display())
            self.slots.append(slot)
            slots_layout.addWidget(slot)
        main_layout.addLayout(slots_layout)
        
        # Results Display
        # Results Display using QTableWidget
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(6)
        self.results_table.setHorizontalHeaderLabels(["Color", "Substance", "Plate A", "Plate B'", "Plate C", "Predictions"])
        
        # Column Resizing Logic
        header = self.results_table.horizontalHeader()
        
        # 0: Color (Fixed, Small)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.results_table.setColumnWidth(0, 50)
        
        # 1: Substance (Interactive/Stretch?) - Let's use Interactive defaults but set width
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.results_table.setColumnWidth(1, 150)
        
        # 2, 3, 4: Plates (Fixed, Small - ~1/5 of typical width)
        for i in [2, 3, 4]:
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.results_table.setColumnWidth(i, 60)
            
        # 5: Predictions (Fill remaining space)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        
        # Ensure horizontal scrolling is possible
        self.results_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Row Height
        # Connect Cell Click
        self.results_table.cellClicked.connect(self.handle_table_click)
        
        main_layout.addWidget(self.results_table)

        self.create_menu()

    def handle_table_click(self, row, col):
        if col == 0:
            # Color Column Clicked
            item = self.results_table.item(row, col)
            if item:
                sid = item.data(Qt.ItemDataRole.UserRole)
                if sid is not None:
                     self.change_sample_color(sid)

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

    def create_menu(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        
        about_action = QAction("About", self)
        about_action.setMenuRole(QAction.MenuRole.NoRole)
        about_action.triggered.connect(self.show_about_dialog)
        file_menu.addAction(about_action)

        load_examples_action = QAction("Load Examples", self)
        load_examples_action.triggered.connect(self.load_examples)
        file_menu.addAction(load_examples_action)
        
        save_analysis_action = QAction("Save Analysis", self)
        save_analysis_action.triggered.connect(self.save_analysis)
        file_menu.addAction(save_analysis_action)

        load_analysis_action = QAction("Load Analysis", self)
        load_analysis_action.triggered.connect(self.load_analysis)
        file_menu.addAction(load_analysis_action)
        
        new_analysis_action = QAction("New Analysis", self)
        new_analysis_action.triggered.connect(self.new_analysis)
        file_menu.addAction(new_analysis_action)



        # Analysis Menu
        analysis_menu = menu_bar.addMenu("Analysis")
        
        substance_detection_action = QAction("Substance Detection", self)
        substance_detection_action.triggered.connect(self.show_settings_window)
        analysis_menu.addAction(substance_detection_action)

        predict_species_action = QAction("Predict species", self)
        predict_species_action.triggered.connect(self.show_species_prediction_window)
        analysis_menu.addAction(predict_species_action)

        # Reference Menu
        ref_menu = menu_bar.addMenu("Reference")
        
        tables = ["Lichens", "LichensBackup", "Substances", "SubstancesBackup"]
        for table in tables:
            action = QAction(table, self)
            # Use default arg to capture loop variable
            action.triggered.connect(lambda checked, t=table: self.show_table(t))
            ref_menu.addAction(action)

    def show_table(self, table_name):
        from gui.database_window import DatabaseTableWindow
        
        # Store windows in a dict to prevent GC and allow multiple open
        if not hasattr(self, 'table_windows'):
            self.table_windows = {}
            
        # Create logic: bring to front if open, else create
        if table_name not in self.table_windows or self.table_windows[table_name] is None:
             import os
             base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
             db_path = os.path.join(base_path, "Mytabolites.db")
             self.table_windows[table_name] = DatabaseTableWindow(table_name, db_path)
        
        window = self.table_windows[table_name]
        window.show()
        window.raise_()
        window.activateWindow()

    def handle_link_click(self, link):
        if link.startswith("substance:"):
            name = link.split(":", 1)[1]
            from gui.substance_detail_window import SubstanceDetailWindow
            from PyQt6.QtSql import QSqlDatabase
            
            # Ensure DB connection exists (should be established by load_reference_data or show_table)
            # Check default connection
            if not QSqlDatabase.contains("qt_sql_default_connection"):
                # Re-establish if missing (reuse logic?)
                import os
                base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                db_path = os.path.join(base_path, "Mytabolites.db")
                db = QSqlDatabase.addDatabase("QSQLITE")
                db.setDatabaseName(db_path)
                if not db.open():
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
        elif link.startswith("show_more:"):
            sid = int(link.split(":", 1)[1])
            matches = self.samples.get(sid, {}).get('last_matches', [])
            if matches:
                 text = "\n".join(matches)
                 QMessageBox.information(self, f"All Matches for {self.samples[sid]['name']}", text)

    def open_characteristics_window(self, sid):
        if sid not in self.samples:
            return
            
        from gui.substance_characteristics_window import SubstanceCharacteristicsWindow
        from PyQt6.QtSql import QSqlDatabase
        
        # Ensure DB connection
        if QSqlDatabase.contains("qt_sql_default_connection"):
            db = QSqlDatabase.database()
        else:
             # Fallback if somehow missing
             import os
             base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
             db_path = os.path.join(base_path, "Mytabolites.db")
             db = QSqlDatabase.addDatabase("QSQLITE")
             db.setDatabaseName(db_path)
             if not db.open(): return

        # Manage window (initialized in __init__)
        sample_name = self.samples[sid]['name']
        current_group = self.samples[sid].get('filter_group')
        current_genus = self.samples[sid].get('filter_genus')
        
        current_vis = self.samples[sid].get('filter_vis', False)
        current_uvs = self.samples[sid].get('filter_uvs', False)
        current_uvl = self.samples[sid].get('filter_uvl', False)
        current_aft_vis = self.samples[sid].get('filter_aft_vis')
        current_aft_uv = self.samples[sid].get('filter_aft_uv')
        
        assigned_name = self.samples[sid].get('assigned_name')
        candidates = self.samples[sid].get('last_matches', [])
        show_on_plate = self.samples[sid].get('show_on_plate', False)

        # Unique key? sid is unique.
        if sid in self.char_windows and self.char_windows[sid].isVisible():
            self.char_windows[sid].raise_()
            self.char_windows[sid].activateWindow()
            return

        window = SubstanceCharacteristicsWindow(sid, sample_name, current_group, current_genus, 
                                                current_vis, current_uvs, current_uvl, 
                                                current_aft_vis, current_aft_uv, 
                                                assigned_name, candidates, show_on_plate, db)
        window.filterChanged.connect(self.set_sample_filter)
        self.char_windows[sid] = window
        window.show()

    def set_sample_filter(self, sid, group_name, genus, is_vis, is_uvs, is_uvl, aft_vis, aft_uv, assigned_name, show_on_plate):
        if sid in self.samples:
            self.samples[sid]['filter_group'] = group_name
            self.samples[sid]['filter_genus'] = genus
            self.samples[sid]['filter_vis'] = is_vis
            self.samples[sid]['filter_uvs'] = is_uvs
            self.samples[sid]['filter_uvl'] = is_uvl
            self.samples[sid]['filter_aft_vis'] = aft_vis
            self.samples[sid]['filter_aft_uv'] = aft_uv
            self.samples[sid]['assigned_name'] = assigned_name
            self.samples[sid]['show_on_plate'] = show_on_plate
            self.update_results_display()

    def ensure_single_mode(self, active_btn):
        # Helper to uncheck other buttons
        buttons = [self.mark_substance_button, self.mark_atranorin_button, self.mark_norstictic_button]
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

    def show_about_dialog(self):
        import os
        version = "Unknown"
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        version_path = os.path.join(base_path, "VERSION")
        if os.path.exists(version_path):
            with open(version_path, 'r') as f:
                version = f.read().strip()
        QMessageBox.about(self, "About TLCid", f"TLCid v{version}\nCopyright by Philipp Resl 2026")

    def show_settings_window(self):
        from gui.settings_window import SettingsWindow
        if not hasattr(self, 'settings_window') or self.settings_window is None:
            self.settings_window = SettingsWindow()
            self.settings_window.settingsChanged.connect(self.update_detection_settings)
            
        self.settings_window.set_current_settings(self.detection_method, self.detection_range)
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
                    for m in matches:
                        prediction_data.append({
                            'name': m,
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
             import os
             base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
             db_path = os.path.join(base_path, "Mytabolites.db")
             db = QSqlDatabase.addDatabase("QSQLITE")
             db.setDatabaseName(db_path)
             if not db.open(): return

        self.species_window = SpeciesPredictionWindow(prediction_data, db)
        self.species_window.show()

    def update_detection_settings(self, method, range_val):
        self.detection_method = method
        self.detection_range = range_val
        self.update_detection_status_label()
        self.update_results_display()

    def on_main_range_changed(self, val):
        self.detection_range = val
        self.update_detection_status_label()
        self.update_results_display()
        # Sync Settings Window if open
        if hasattr(self, 'settings_window') and self.settings_window is not None:
            self.settings_window.range_spin.blockSignals(True)
            self.settings_window.range_spin.setValue(val)
            self.settings_window.range_spin.blockSignals(False)

    def update_detection_status_label(self):
        is_range = (self.detection_method == "Range")
        text = f"Method: <b>{self.detection_method}</b>"
        if is_range:
            text += " (+/-)"
        self.detection_status_label.setText(text)
        # Show/hide the inline range spinbox based on detection method
        if hasattr(self, 'range_main'):
            self.range_main.setVisible(is_range)
            # Sync spinbox value without triggering valueChanged
            self.range_main.blockSignals(True)
            self.range_main.setValue(self.detection_range)
            self.range_main.blockSignals(False)

    def deactivate_marking_mode(self):
        for slot in self.slots:
            slot.image_label.set_add_sample_mode(False)

    def toggle_mark_substance(self, checked):
        if checked:
            self.ensure_single_mode(self.mark_substance_button)
                
            # Entering Add Mode
            self.mark_substance_button.setText("Stop Marking")
            sid = self.next_sample_id
            self.next_sample_id += 1
            color = self.colors[(sid - 1) % len(self.colors)]
            self.activate_marking_mode(sid, color, f"Substance {sid}")
        else:
            self.mark_substance_button.setText("Mark Substance")
            self.deactivate_marking_mode()

    def toggle_mark_atranorin(self, checked):
        if checked:
            self.ensure_single_mode(self.mark_atranorin_button)
            
            # Atranorin Mode (ID 0)
            self.mark_atranorin_button.setText("Stop Ref (Atr)")
            self.activate_marking_mode(0, QColor("red"), "Atranorin (Ref)")
        else:
            self.mark_atranorin_button.setText("Mark Atranorin")
            self.deactivate_marking_mode()

    def toggle_mark_norstictic(self, checked):
        if checked:
            self.ensure_single_mode(self.mark_norstictic_button)
            
            # Norstictic Mode (ID -1)
            self.mark_norstictic_button.setText("Stop Ref (Nor)")
            self.activate_marking_mode(-1, QColor("yellow"), "Norstictic Acid (Ref)")
        else:
            self.mark_norstictic_button.setText("Mark Norstictic")
            self.deactivate_marking_mode()
    
    def update_results_display(self):
        # Aggregate data from all slots
        # Map: Sample ID -> { Plate Index -> [rf1, rf2, ...] }
        aggregated = {}
        
        for i, slot in enumerate(self.slots):
            # Get Start and Front lines (raw normalized coords: 0=Top, 1=Bottom)
            # Invert them for logical calculation (0=Bottom, 1=Top)
            raw_start = slot.image_label.start_line_y
            raw_front = slot.image_label.front_line_y
            
            u_start = 1.0 - raw_start
            u_front = 1.0 - raw_front
            
            denom = u_front - u_start
            
            spots = slot.image_label.spots # list of dicts
            for spot in spots:
                # Debug print for spots
                print(f"DEBUG: Spot on Plate {i}: {spot}")
                sid = spot['sample_id']
                raw_y = spot['y']
                u_spot = 1.0 - raw_y
                
                # Calculate Rf
                if abs(denom) < 1e-6:
                    rf_val = 0.0 # Avoid div by zero
                else:
                    rf_val = (u_spot - u_start) / denom
                
                if sid not in aggregated:
                    aggregated[sid] = {}
                if i not in aggregated[sid]:
                    aggregated[sid][i] = []
                aggregated[sid][i].append(rf_val)
        
        # Sync self.samples with aggregated data:
        # If a sample ID is no longer in any of the plate spots (not in 'aggregated'),
        # remove it from self.samples to clear it from the results list.
        # We keep IDs <= 0 as they represent reference standards (Atranorin/Norstictic).
        # Determine which substance is currently being marked (if any)
        currently_marking_sid = None
        if self.mark_substance_button.isChecked():
            currently_marking_sid = self.next_sample_id - 1
        elif self.mark_atranorin_button.isChecked():
            currently_marking_sid = 0
        elif self.mark_norstictic_button.isChecked():
            currently_marking_sid = -1

        ids_to_remove = []
        for sid in self.samples:
            if sid > 0 and sid not in aggregated and sid != currently_marking_sid:
                ids_to_remove.append(sid)
        
        for sid in ids_to_remove:
            print(f"DEBUG: Removing substance ID {sid} (no spots remaining)")
            self.samples.pop(sid)
            # Close any open characteristics window for this sample
            if sid in self.char_windows:
                try:
                    self.char_windows[sid].close()
                except RuntimeError:
                    pass  # Widget already deleted by Qt
                self.char_windows[sid].deleteLater() if sid in self.char_windows else None
                self.char_windows.pop(sid, None)
        
        # Refresh global color map in slots after removal to keep synchronized
        if ids_to_remove:
            color_map = {k: v['color'] for k, v in self.samples.items()}
            for slot in self.slots:
                slot.image_label.set_global_colors(color_map)

        # Clear previous matches for remaining samples
        for sid, sdata in self.samples.items():
            sdata['last_matches'] = []
        
        # Debug print for aggregated data
        print(f"DEBUG: Aggregated Rf values: {aggregated}")

        # Check for auto-stop if currently marking
        if self.mark_substance_button.isChecked():
            current_sid = self.next_sample_id - 1
            # Check if this sample has entries for all 3 plates (indices 0, 1, 2)
            if current_sid in aggregated and len(aggregated[current_sid]) == 3:
                self.mark_substance_button.click()
        elif self.mark_atranorin_button.isChecked():
            current_sid = 0 # Atranorin ID
            if current_sid in aggregated and len(aggregated[current_sid]) == 3:
                self.mark_atranorin_button.click()
        elif self.mark_norstictic_button.isChecked():
            current_sid = -1 # Norstictic ID
            if current_sid in aggregated and len(aggregated[current_sid]) == 3:
                self.mark_norstictic_button.click()

        # Calibration Logic
        # Gather Active Standards per Plate
        active_standards = {0: [], 1: [], 2: []}
        
        # Check Atranorin (0)
        if 0 in aggregated:
             for idx, vals in aggregated[0].items():
                 if vals and idx in self.atranorin_standards:
                     active_standards[idx].append((vals[0], self.atranorin_standards[idx]))
                     
        # Check Norstictic (-1)
        if -1 in aggregated:
             for idx, vals in aggregated[-1].items():
                 if vals and idx in self.norstictic_standards:
                     active_standards[idx].append((vals[0], self.norstictic_standards[idx]))

        for idx in active_standards:
            active_standards[idx].sort(key=lambda x: x[0])

        # Store Scroll Position
        v_scroll = self.results_table.verticalScrollBar().value()
        h_scroll = self.results_table.horizontalScrollBar().value()

        # Render to Table
        self.results_table.setRowCount(0)
        sorted_ids = sorted(aggregated.keys())
        
        for sid in sorted_ids:
            if sid not in self.samples:
                continue 
                
            color = self.samples[sid]['color']
            
            # Prepare row data
            current_row = self.results_table.rowCount()
            self.results_table.insertRow(current_row)
            
            # 1. Color Column
            color_item = QTableWidgetItem()
            color_item.setBackground(color)
            color_item.setData(Qt.ItemDataRole.UserRole, sid) # Store SID
            color_item.setFlags(Qt.ItemFlag.NoItemFlags) # Non-editable/selectable
            self.results_table.setItem(current_row, 0, color_item)
            
            # 2. Substance Name (Clickable Link)
            name_label = QLabel()
            name_text = self.samples[sid].get('assigned_name')
            if not name_text:
                name_text = self.samples[sid]['name']
            
            hex_c = color.name()
            # Link style
            name_label.setText(f"<a href='edit_sample:{sid}' style='color:steelblue; text-decoration:none;'><b>{name_text}</b></a>")
            name_label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
            name_label.linkActivated.connect(self.handle_link_click)
            name_label.setContentsMargins(5, 0, 5, 0)
            self.results_table.setCellWidget(current_row, 1, name_label)

            # Columns for A, B, C
            plate_data = aggregated[sid]
            prediction_input = {}
            current_filter = None
            
            for plate_idx, label in enumerate(self.plate_labels):
                col_idx = 2 + plate_idx
                
                val_str = "-"
                if plate_idx in plate_data:
                    raw_val = plate_data[plate_idx][0]
                    
                    # Apply Linear Interpolation Calibration
                    standards = active_standards.get(plate_idx, [])
                    # Include boundary points (0,0) and (1,1)
                    points = [(0.0, 0.0)] + standards + [(1.0, 1.0)]
                    
                    corrected_val = raw_val # Default
                    for j in range(len(points) - 1):
                        x1, y1 = points[j]
                        x2, y2 = points[j+1]
                        if x1 <= raw_val <= x2:
                            if abs(x2 - x1) > 1e-7:
                                corrected_val = y1 + (raw_val - x1) * (y2 - y1) / (x2 - x1)
                            else:
                                corrected_val = y1
                            break
                    
                    prediction_input[plate_idx] = corrected_val
                    val_str = f"{corrected_val:.2f}"
                
                item = QTableWidgetItem(val_str)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.results_table.setItem(current_row, col_idx, item)
            
            # 3. Predictions
            matches = []
            if sid > 0 and prediction_input:
                current_filter = self.samples[sid].get('filter_group')
                current_genus = self.samples[sid].get('filter_genus')
                f_vis = self.samples[sid].get('filter_vis', False)
                f_uvs = self.samples[sid].get('filter_uvs', False)
                f_uvl = self.samples[sid].get('filter_uvl', False)
                f_aft_vis = self.samples[sid].get('filter_aft_vis')
                f_aft_uv = self.samples[sid].get('filter_aft_uv')
                
                matches = self.predict_matches(prediction_input, 
                                               filter_group=current_filter, 
                                               filter_genus=current_genus,
                                               filter_vis=f_vis,
                                               filter_uvs=f_uvs,
                                               filter_uvl=f_uvl,
                                               filter_aft_vis=f_aft_vis,
                                               filter_aft_uv=f_aft_uv)
            
            pred_label = QLabel()
            self.samples[sid]['last_matches'] = matches
            if matches:
                 display_matches = matches[:5]
                 match_links = []
                 for m in display_matches:
                     match_links.append(f"<a href='substance:{m}'>{m}</a>")
                 match_str = ", ".join(match_links)
                 
                 if len(matches) > 5:
                     more_count = len(matches) - 5
                     match_str += f" <a href='show_more:{sid}' style='color:blue;'>+{more_count} more</a>"

                 if current_filter:
                     match_str += f" <small style='color:gray'>[{current_filter}]</small>"
                     
                 pred_label.setText(match_str)
                 pred_label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
                 pred_label.linkActivated.connect(self.handle_link_click)
            else:
                pred_label.setText("-")
                
            pred_label.setContentsMargins(5, 0, 5, 0)
            self.results_table.setCellWidget(current_row, 5, pred_label)
            
        # Restore Scroll Position
        self.results_table.verticalScrollBar().setValue(v_scroll)
        self.results_table.horizontalScrollBar().setValue(h_scroll)

        # Update Name Mapping in slots
        name_map = {}
        for sid, sdata in self.samples.items():
            if sdata.get('show_on_plate', False):
                assigned = sdata.get('assigned_name')
                name_map[sid] = assigned if assigned else sdata['name']
        
        for slot in self.slots:
            slot.image_label.set_global_names(name_map)
            
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
                    self.slots[i].image_path = full_path # Store path
                    pixmap = QPixmap(full_path)
                    if not pixmap.isNull():
                        self.slots[i].image_label.set_image(pixmap)

    def save_analysis(self):
        import json
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Save Analysis", "", "JSON Files (*.json)"
        )
        if not file_name:
            return
            
        data = {
            "version": 1,
            "detection_method": self.detection_method,
            "detection_range": self.detection_range,
            "samples": {},
            "plates": []
        }
        
        # Save Samples (only need ID and name, color can be deterministic)
        for sid, sdata in self.samples.items():
            data["samples"][sid] = {
                "name": sdata["name"],
                "assigned_name": sdata.get('assigned_name'),
                "show_on_plate": sdata.get('show_on_plate', False),
                "filter_group": sdata.get('filter_group'),
                "filter_genus": sdata.get('filter_genus'),
                "filter_vis": sdata.get('filter_vis', False),
                "filter_uvs": sdata.get('filter_uvs', False),
                "filter_uvl": sdata.get('filter_uvl', False),
                "filter_aft_vis": sdata.get('filter_aft_vis'),
                "filter_aft_uv": sdata.get('filter_aft_uv')
            }
            
        # Save Plates
        for i, slot in enumerate(self.slots):
            plate_data = {
                "id": i,
                "image_path": slot.image_path,
                "start_line_y": slot.image_label.start_line_y,
                "front_line_y": slot.image_label.front_line_y,
                "spots": slot.image_label.spots
            }
            data["plates"].append(plate_data)
            
        try:
            with open(file_name, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving file: {e}")

    def load_analysis(self):
        import json
        import os
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Load Analysis", "", "JSON Files (*.json)"
        )
        if not file_name:
            return
            
        try:
            with open(file_name, 'r') as f:
                data = json.load(f)
            
            # Reset State
            self.samples = {} # Clear samples
            
            # Load Detection Settings
            if "detection_method" in data:
                 self.detection_method = data["detection_method"]
            if "detection_range" in data:
                 self.detection_range = float(data["detection_range"])
                 
            # Update UI for detection settings
            self.update_detection_status_label()
            
            # Block signals on all image labels during loading to prevent
            # premature update_results_display calls (which would remove
            # substances from self.samples before their spots are loaded)
            for slot in self.slots:
                slot.image_label.blockSignals(True)
            
            # Determine next sample id (max id + 1)
            max_sid = 0
            
            # Restore Samples
            for sid_str, sdata in data.get("samples", {}).items():
                sid = int(sid_str)
                if sid > max_sid:
                    max_sid = sid
                # Assign correct colors for reference standards vs substances
                if sid == 0:
                    color = QColor("red")       # Atranorin reference
                elif sid == -1:
                    color = QColor("yellow")    # Norstictic Acid reference
                else:
                    color = self.colors[(sid - 1) % len(self.colors)]
                self.samples[sid] = {
                    'color': color, 
                    'name': sdata['name'],
                    'assigned_name': sdata.get('assigned_name'),
                    'show_on_plate': sdata.get('show_on_plate', False),
                    'filter_group': sdata.get('filter_group'),
                    'filter_genus': sdata.get('filter_genus'),
                    'filter_vis': sdata.get('filter_vis', False),
                    'filter_uvs': sdata.get('filter_uvs', False),
                    'filter_uvl': sdata.get('filter_uvl', False),
                    'filter_aft_vis': sdata.get('filter_aft_vis'),
                    'filter_aft_uv': sdata.get('filter_aft_uv')
                }
            
            self.next_sample_id = max_sid + 1
            
            # Update Slots
            plates_data = data.get("plates", [])
            for plate_info in plates_data:
                idx = plate_info.get("id")
                if idx is not None and 0 <= idx < len(self.slots):
                    slot = self.slots[idx]
                    path = plate_info.get("image_path")
                    start_y = plate_info.get("start_line_y", 0.9)
                    front_y = plate_info.get("front_line_y", 0.1)
                    spots = plate_info.get("spots", [])
                    
                    if path and os.path.exists(path):
                        slot.image_path = path
                        pixmap = QPixmap(path)
                        if not pixmap.isNull():
                            slot.image_label.set_image(pixmap)
                    
                    # Set Lines
                    slot.image_label.start_line_y = start_y
                    slot.image_label.front_line_y = front_y
                    
                    # Set Spots
                    # Ensure spots have integer sample_id as saved
                    safe_spots = []
                    for s in spots:
                        safe_spots.append({
                            'sample_id': int(s['sample_id']),
                            'x': s['x'],
                            'y': s['y']
                        })
                    slot.image_label.spots = safe_spots
            
            # Unblock signals now that all data is loaded
            for slot in self.slots:
                slot.image_label.blockSignals(False)
            
            # Global Updates
            color_map = {k: v['color'] for k, v in self.samples.items()}
            for slot in self.slots:
                slot.image_label.set_global_colors(color_map)
                slot.image_label.update()
                
            self.update_results_display()
            
        except Exception as e:
            print(f"Error loading file: {e}")

    def new_analysis(self):
        # Reset Global State
        self.samples = {}
        self.next_sample_id = 1
        
        # Reset Controls
        if self.mark_substance_button.isChecked():
            self.mark_substance_button.click() # This will toggle it off and reset cursors
        
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
            slot.image_label.start_line_y = 0.9
            slot.image_label.front_line_y = 0.1
            slot.image_label.show_lines = False
            slot.image_label.set_global_colors({})
            # Signal won't fire if lines aren't moved/set via setter that emits.
            # Let's forcefully emit or set text.
            slot.image_label.linesMoved.emit(0.1, 0.9) # Inverted: 1-0.9=0.1 start, 1-0.1=0.9 front
            slot.image_label.spotsChanged.emit([])
            slot.image_label.update()
            
        self.update_results_display()
        
    def load_reference_data(self):
        self.reference_data = []
        self.genus_to_substances = {}
        import os
        from PyQt6.QtSql import QSqlDatabase, QSqlQuery
        
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(base_path, "Mytabolites.db")
        
        if QSqlDatabase.contains("main_ref_connection"):
            db = QSqlDatabase.database("main_ref_connection")
        else:
            db = QSqlDatabase.addDatabase("QSQLITE", "main_ref_connection")
            db.setDatabaseName(db_path)
            
        if db.open():
            # Populate Genus Cache
            gen_query = QSqlQuery(db)
            if gen_query.exec("SELECT DISTINCT Genus, Substance FROM Lichens"):
                while gen_query.next():
                    g = gen_query.value(0)
                    s = gen_query.value(1)
                    if g not in self.genus_to_substances:
                        self.genus_to_substances[g] = set()
                    self.genus_to_substances[g].add(s.lower())

            tables = ["Substances", "SubstancesBackup"]
            for table in tables:
                query = QSqlQuery(db)
                # Select name, A, Bprime, C, GroupName, Lichens, BefVis, BefUVS, BefUVL, AftVis, AftUV
                if query.exec(f"SELECT name, A, Bprime, C, GroupName, Lichens, BefVis, BefUVS, BefUVL, AftVis, AftUV FROM {table}"):
                    while query.next():
                        name = query.value(0)
                        
                        def parse_rf(val):
                            if val is None or val == "":
                                return None
                            try:
                                return float(val) / 100.0
                            except:
                                return None
                                
                        rf_a = parse_rf(query.value(1))
                        rf_b = parse_rf(query.value(2))
                        rf_c = parse_rf(query.value(3))
                        group_name = query.value(4)
                        lichens_str = query.value(5)
                        bef_vis = query.value(6)
                        bef_uvs = query.value(7)
                        bef_uvl = query.value(8)
                        aft_vis = query.value(9)
                        aft_uv = query.value(10)
                        
                        self.reference_data.append({
                            'name': name,
                            'rf': [rf_a, rf_b, rf_c], # Matching slots 0, 1, 2
                            'GroupName': group_name,
                            'BefVis': bef_vis,
                            'BefUVS': bef_uvs,
                            'BefUVL': bef_uvl,
                            'AftVis': aft_vis,
                            'AftUV': aft_uv
                        })
            db.close()
        
    def predict_matches(self, input_data, filter_group=None, filter_genus=None, 
                        filter_vis=False, filter_uvs=False, filter_uvl=False,
                        filter_aft_vis=None, filter_aft_uv=None):
        # input_data: {plate_idx: value}
        # Returns list of top names
        
        scores = []
        # Detection Setting: self.detection_method ("MSE" or "Range")
        # Detection Range: self.detection_range
        
        for item in self.reference_data:
            name = item['name']
            
            # Filter by Group
            if filter_group and item.get('GroupName') != filter_group:
                continue
                
            # Filter by Genus (Optimized using Lichens table mapping)
            if filter_genus:
                valid_subs = self.genus_to_substances.get(filter_genus, set())
                if name.lower() not in valid_subs:
                    continue

            # Filter by Visual Characteristics (only if checkbox is checked)
            # Database marks positive with '+'
            if filter_vis:
                if item.get('BefVis') != '+':
                    continue
            if filter_uvs:
                if item.get('BefUVS') != '+':
                    continue
            if filter_uvl:
                if item.get('BefUVL') != '+':
                    continue

            # Filter by After Treatment Characteristics
            # Exact match if filter is set
            if filter_aft_vis:
                if item.get('AftVis') != filter_aft_vis:
                    continue
            if filter_aft_uv:
                if item.get('AftUV') != filter_aft_uv:
                    continue

            if self.detection_method == "Range":
                # Range Logic: ALL present plates must be within range
                match = True
                dist = 0.0
                count = 0
                
                for plate_idx, obs_val in input_data.items():
                   if plate_idx < len(item['rf']):
                       ref_val = item['rf'][plate_idx]
                       if ref_val is None:
                           match = False
                           break
                       
                       error = abs(obs_val - ref_val)
                       if error > self.detection_range:
                           match = False
                           break
                       
                       dist += error ** 2
                       count += 1
                   else:
                       match = False
                       break
                
                if match and count > 0:
                    mse = dist / count
                    scores.append((mse, name))

            else:
                # MSE Logic
                dist = 0.0
                count = 0
                
                for plate_idx, obs_val in input_data.items():
                    if plate_idx < len(item['rf']): # Ensure index is valid
                        ref_val = item['rf'][plate_idx]
                        if ref_val is not None:
                            dist += (obs_val - ref_val) ** 2
                            count += 1
                
                if count > 0:
                    mse = dist / count
                    scores.append((mse, name))
        
        # Sort by score (lowest error first)
        scores.sort(key=lambda x: x[0])
        
        # Return all unique names sorted by score
        unique_names = []
        seen = set()
        for _, name in scores:
            if name not in seen:
                unique_names.append(name)
                seen.add(name)
                    
        return unique_names
