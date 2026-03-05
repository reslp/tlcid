from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QMarginsF, QRect, QSizeF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPageLayout, QPageSize, QPdfWriter
from PyQt6.QtWidgets import QFileDialog, QMessageBox


class PDFReportGenerator:
    """Generate TLCid PDF reports with robust spacing and pagination."""

    def __init__(self, window):
        self.window = window

    def generate(self) -> None:
        combined = self.window._build_combined_export_image(label_font_size_delta=10)
        if combined is None:
            QMessageBox.warning(
                self.window,
                "No Images",
                "No plate images are loaded. Please load at least one image before generating a report.",
            )
            return

        has_pred_rows = any(
            sid > 0 and self.window.samples.get(sid, {}).get("last_matches")
            for sid in self.window.samples
        )
        if not has_pred_rows:
            QMessageBox.warning(
                self.window,
                "No Predictions",
                "No predicted substances available. Please mark spots first.",
            )
            return

        file_name, _ = QFileDialog.getSaveFileName(
            self.window, "Generate Report", "", "PDF Files (*.pdf)"
        )
        if not file_name:
            return
        if not file_name.lower().endswith(".pdf"):
            file_name += ".pdf"

        writer = QPdfWriter(file_name)

        # Page 1: exact image-sized landscape canvas, zero margins, image only.
        # Convert image pixel dimensions to PDF points so the physical page size matches
        # image dimensions at writer DPI (and avoids tiny/huge rendering artifacts).
        dpi = max(1, writer.resolution())
        img_w_pt = (float(combined.width()) * 300.0) / float(dpi)
        img_h_pt = (float(combined.height()) * 300.0) / float(dpi)

        image_page_size = QPageSize(
            QSizeF(max(1.0, img_h_pt), max(1.0, img_w_pt)),
            QPageSize.Unit.Point,
            "Combined Plate",
            QPageSize.SizeMatchPolicy.ExactMatch,
        )
        image_layout = QPageLayout(
            image_page_size,
            QPageLayout.Orientation.Landscape,
            QMarginsF(0, 0, 0, 0),
            QPageLayout.Unit.Point,
        )
        writer.setPageLayout(image_layout)

        painter = QPainter(writer)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw only the combined image on page 1, filling the full page.
        first_page_rect = writer.pageLayout().fullRectPixels(writer.resolution())
        painter.drawImage(first_page_rect, combined)

        # Remaining pages: regular portrait A4 + current 15 mm margin settings.
        report_layout = QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Portrait,
            QMarginsF(15, 15, 15, 15),
            QPageLayout.Unit.Millimeter,
        )
        writer.setPageLayout(report_layout)
        writer.newPage()

        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)

        info_font = QFont()
        info_font.setPointSize(9)

        section_font = QFont()
        section_font.setPointSize(10)
        section_font.setBold(True)

        header_font = QFont()
        header_font.setPointSize(8)
        header_font.setBold(True)

        normal_font = QFont()
        normal_font.setPointSize(8)

        def page_metrics() -> tuple[int, int, int, int]:
            rect = writer.pageLayout().paintRectPixels(writer.resolution())
            return rect.left(), rect.top(), rect.width(), rect.bottom()

        left, top, width, bottom = page_metrics()

        def line_height(font: QFont, extra: int = 0) -> int:
            painter.setFont(font)
            return int(painter.fontMetrics().lineSpacing()) + extra

        def as_qcolor(value) -> QColor:
            if isinstance(value, QColor):
                return QColor(value)
            if isinstance(value, (tuple, list)) and len(value) >= 3:
                return QColor(int(value[0]), int(value[1]), int(value[2]))
            return QColor("lightgray")

        def text_color_for_bg(bg: QColor) -> QColor:
            luminance = (0.299 * bg.red()) + (0.587 * bg.green()) + (0.114 * bg.blue())
            return QColor("black") if luminance > 140 else QColor("white")

        def draw_page_header() -> int:
            y_local = top
            painter.setFont(title_font)
            title_h = line_height(title_font, extra=2)
            painter.setPen(QColor("black"))
            painter.drawText(left, y_local + title_h, "TLCid Analysis Report")
            y_local += title_h + 16

            painter.setFont(info_font)
            info_h = line_height(info_font)
            version = "Unknown"
            try:
                with open(f"{self.window.base_path}/VERSION", "r") as f:
                    version = f.read().strip()
            except Exception:
                pass

            report_date = datetime.now().strftime("%Y-%m-%d %H:%M")
            db_version = self.window.get_database_version_text()
            painter.drawText(left, y_local + info_h, f"Generated: {report_date}")
            y_local += info_h
            painter.drawText(left, y_local + info_h, f"TLCid version: {version}")
            y_local += info_h
            painter.drawText(left, y_local + info_h, f"Database version: {db_version}")
            y_local += info_h + 10
            return y_local

        y = draw_page_header()

        section_h = line_height(section_font)
        y += section_h + 8

        table_header_h = max(20, line_height(header_font, extra=6))
        row_h = max(18, line_height(normal_font, extra=5))
        block_gap = 10

        col_fracs = [0.10, 0.34, 0.14, 0.14, 0.14, 0.14]

        def get_col_widths(total_w: int) -> list[int]:
            raw = [int(total_w * frac) for frac in col_fracs]
            diff = total_w - sum(raw)
            raw[-1] += diff
            return raw

        def draw_table_header(table_x: int, table_y: int, table_w: int) -> None:
            headers = ["Rank", "Substance Name", "Rf value A", "Rf value B'", "Rf value C", "Score"]
            col_widths = get_col_widths(table_w)

            painter.save()
            painter.setFont(header_font)
            painter.setPen(QColor("black"))
            painter.setBrush(QColor(235, 235, 235))
            painter.drawRect(table_x, table_y, table_w, table_header_h)

            x = table_x
            for idx, text in enumerate(headers):
                w = col_widths[idx]
                if idx > 0:
                    painter.drawLine(x, table_y, x, table_y + table_header_h)
                rect = QRect(x + 4, table_y, max(1, w - 8), table_header_h)
                painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)
                x += w
            painter.restore()

        def draw_row(
            table_x: int,
            table_y: int,
            table_w: int,
            values: list[str],
            bg: QColor,
            fg: QColor,
            bold: bool = False,
        ) -> None:
            col_widths = get_col_widths(table_w)
            painter.save()
            painter.setPen(QColor("black"))
            painter.setBrush(bg)
            painter.drawRect(table_x, table_y, table_w, row_h)

            row_font = QFont(normal_font)
            row_font.setBold(bold)
            painter.setFont(row_font)
            painter.setPen(fg)

            x = table_x
            for idx, text in enumerate(values):
                w = col_widths[idx]
                if idx > 0:
                    painter.setPen(QColor("black"))
                    painter.drawLine(x, table_y, x, table_y + row_h)
                    painter.setPen(fg)

                rect = QRect(x + 4, table_y, max(1, w - 8), row_h)
                if idx == 1:
                    align = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                elif idx in (0, 5):
                    align = int(Qt.AlignmentFlag.AlignCenter)
                else:
                    align = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                painter.drawText(rect, align, text)
                x += w
            painter.restore()

        def ensure_space(needed: int) -> None:
            nonlocal y, left, top, width, bottom
            if y + needed <= bottom - 10:
                return
            writer.newPage()
            left, top, width, bottom = page_metrics()
            y = top
            y += section_h + 8

        table_x = left
        table_w = width - 1500 # important: modify width so that it fits on the page with a margin

        for sid in sorted(self.window.samples.keys()):
            if sid <= 0:
                continue

            sdata = self.window.samples[sid]
            matches = sdata.get("last_matches", [])[:5]
            if not matches:
                continue

            spot_name = sdata.get("assigned_name") or sdata.get("name", f"Substance {sid}")
            spot_color = as_qcolor(sdata.get("color", QColor("lightgray")))

            row = self.window._find_row_by_sid(sid)
            spot_rf = []
            for col in (2, 3, 4):
                txt = "-"
                item = self.window.results_table.item(row, col) if row is not None else None
                if item:
                    txt = item.text() or "-"
                spot_rf.append(txt)

            block_title_h = line_height(section_font)
            block_needed = block_title_h + 4 + table_header_h + (1 + len(matches)) * row_h + block_gap
            ensure_space(block_needed)

            painter.setFont(section_font)
            painter.setPen(QColor("black"))
            painter.drawText(left, y + block_title_h, f"Spot {sid}: {spot_name}")
            y += block_title_h + 50

            draw_table_header(table_x, y, table_w)
            y += table_header_h

            observed_row = [
                "-",
                "Observed (plate spot)",
                spot_rf[0],
                spot_rf[1],
                spot_rf[2],
                "-",
            ]
            draw_row(
                table_x,
                y,
                table_w,
                observed_row,
                bg=spot_color,
                fg=text_color_for_bg(spot_color),
                bold=True,
            )
            y += row_h

            for rank, (score, name) in enumerate(matches, start=1):
                rf_vals = self.window.get_substance_rf_from_db(name) or [None, None, None]
                rf_a = self.window.format_rf_value(rf_vals[0])
                rf_b = self.window.format_rf_value(rf_vals[1])
                rf_c = self.window.format_rf_value(rf_vals[2])
                row_values = [
                    str(rank),
                    str(name),
                    rf_a,
                    rf_b,
                    rf_c,
                    f"{score:.4f}",
                ]
                alt_bg = QColor(250, 250, 250) if rank % 2 == 1 else QColor(242, 242, 242)
                draw_row(table_x, y, table_w, row_values, bg=alt_bg, fg=QColor("black"))
                y += row_h

            painter.setPen(QColor("black"))
            painter.drawRect(
                table_x,
                y - (table_header_h + (1 + len(matches)) * row_h),
                table_w,
                table_header_h + (1 + len(matches)) * row_h,
            )
            y += block_gap

        painter.end()
