"""Export result sets to CSV / Excel / PDF.

Hardening notes:
  * cells starting with = + - @ are prefixed with ' so spreadsheet apps do not
    execute attacker-controlled formulas (CSV/Excel injection);
  * filenames are sanitised; files live in a private temp dir and are removed
    after the response is sent (plus an age-based sweep as a safety net);
  * column order comes from the query, not from the first row's dict.
"""

from __future__ import annotations

import os
import re
import tempfile
import time
from datetime import datetime
from typing import Any, Dict, List, Sequence, Tuple
from xml.sax.saxutils import escape

from services.errors import BadRequestError

FORMATS: Dict[str, Tuple[str, str]] = {
    "csv": ("text/csv", "csv"),
    "excel": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
    "pdf": ("application/pdf", "pdf"),
}
PDF_MAX_ROWS = 300
PDF_MAX_COLS = 12
_FORMULA_PREFIX = ("=", "+", "-", "@", "\t", "\r")


def safe_name(name: str, fallback: str = "export") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", (name or "").strip()).strip("._")
    return (cleaned or fallback)[:60]


def _cell(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIX):
        return "'" + value
    return value


class ExportService:
    def __init__(self) -> None:
        self.export_dir = os.path.join(tempfile.gettempdir(), "askdb_exports")
        os.makedirs(self.export_dir, exist_ok=True)

    def _sweep(self, max_age_seconds: int = 3600) -> None:
        cutoff = time.time() - max_age_seconds
        for entry in os.scandir(self.export_dir):
            try:
                if entry.is_file() and entry.stat().st_mtime < cutoff:
                    os.remove(entry.path)
            except OSError:
                pass

    def export(self, columns: Sequence[str], rows: List[Dict[str, Any]], fmt: str, name: str) -> Tuple[str, str, str]:
        """Return (filepath, media_type, download_filename)."""
        fmt = (fmt or "").lower()
        if fmt not in FORMATS:
            raise BadRequestError(f"Unsupported export format '{fmt}'. Use csv, excel or pdf.")
        self._sweep()
        media_type, ext = FORMATS[fmt]
        base = safe_name(name)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        download = f"{base}_{stamp}.{ext}"
        path = os.path.join(self.export_dir, f"{os.urandom(4).hex()}_{download}")
        cols = list(columns)
        clean_rows = [[_cell(r.get(c)) for c in cols] for r in rows]

        if fmt == "csv":
            self._csv(path, cols, clean_rows)
        elif fmt == "excel":
            self._excel(path, cols, clean_rows, base)
        else:
            self._pdf(path, cols, clean_rows, base)
        return path, media_type, download

    
    @staticmethod
    def _csv(path: str, cols: List[str], rows: List[List[Any]]) -> None:
        import csv

        with open(path, "w", newline="", encoding="utf-8-sig") as fh:  
            writer = csv.writer(fh)
            writer.writerow(cols)
            writer.writerows(rows)

    @staticmethod
    def _excel(path: str, cols: List[str], rows: List[List[Any]], title: str) -> None:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter

        wb = Workbook()
        ws = wb.active
        ws.title = re.sub(r"[\[\]:*?/\\]", "_", title)[:31] or "Results"
        ws.append(cols)
        for row in rows:
            ws.append(row)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F2A37")
        ws.freeze_panes = "A2"
        for idx, col in enumerate(cols, start=1):
            longest = max([len(str(col))] + [len(str(r[idx - 1])) for r in rows[:200] if r[idx - 1] is not None])
            ws.column_dimensions[get_column_letter(idx)].width = min(longest + 2, 50)
        wb.save(path)

    @staticmethod
    def _pdf(path: str, cols: List[str], rows: List[List[Any]], title: str) -> None:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        shown_cols = cols[:PDF_MAX_COLS]
        shown_rows = rows[:PDF_MAX_ROWS]
        styles = getSampleStyleSheet()
        cell_style = ParagraphStyle("cell", parent=styles["Normal"], fontSize=7, leading=9)
        head_style = ParagraphStyle("head", parent=cell_style, textColor=colors.white, fontName="Helvetica-Bold")

        doc = SimpleDocTemplate(path, pagesize=landscape(A4), leftMargin=0.4 * inch, rightMargin=0.4 * inch,
                                topMargin=0.5 * inch, bottomMargin=0.5 * inch)
        story: List[Any] = [
            Paragraph(escape(title), styles["Heading2"]),
            Paragraph(f"Generated {datetime.now():%Y-%m-%d %H:%M} · {len(rows):,} rows", styles["Normal"]),
        ]
        notes = []
        if len(rows) > PDF_MAX_ROWS:
            notes.append(f"first {PDF_MAX_ROWS} of {len(rows):,} rows")
        if len(cols) > PDF_MAX_COLS:
            notes.append(f"first {PDF_MAX_COLS} of {len(cols)} columns")
        if notes:
            story.append(Paragraph("Note: showing " + " and ".join(notes) + ". Use CSV or Excel for the full data.", styles["Italic"]))
        story.append(Spacer(1, 0.15 * inch))

        if not shown_rows:
            story.append(Paragraph("No rows.", styles["Normal"]))
        else:
            data = [[Paragraph(escape(str(c)), head_style) for c in shown_cols]]
            for row in shown_rows:
                data.append([Paragraph(escape("" if v is None else str(v))[:300], cell_style) for v in row[:PDF_MAX_COLS]])
            table = Table(data, repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2A37")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(table)
        doc.build(story)
