"""
pretty_schedule_xlsx.py

Create a nicely formatted XLSX from a Schedule instance (single sheet).
- Expects a `schedule` module in the same directory that defines:
    - Schedule: with .days: Dict[DayOfWeek, DayAssignment]
    - DayOfWeek: Enum with ordered days (MONDAY..SUNDAY) and readable .value (e.g. "Mon")
    - DayAssignment.shift_to_people: Dict[str, List[Volunteer]]
    - Volunteer objects expose .name (or volunteers may be strings)

Requires:
    pip install openpyxl
"""

from typing import List, Dict, Any
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

# Local import of your types (adjust module name if needed)
# Assumes schedule.py is next to this file
from .schedule import Schedule, DayOfWeek  # type: ignore

# Styling constants
HEADER_FILL = PatternFill("solid", fgColor="FFD3D3D3")  # light gray
ALT_FILL_1 = PatternFill("solid", fgColor="FFFFFFFF")   # white
ALT_FILL_2 = PatternFill("solid", fgColor="FFF7FBFF")   # very light blue
BORDER_SIDE = Side(style="thin", color="FFCCCCCC")
CELL_BORDER = Border(left=BORDER_SIDE, right=BORDER_SIDE, top=BORDER_SIDE, bottom=BORDER_SIDE)
HEADER_FONT = Font(bold=True, size=12)
SHIFT_FONT = Font(bold=True, size=11)
BASE_FONT_SIZE = 11

def _vol_name(v: Any) -> str:
    """Return volunteer's name from object or string."""
    if v is None:
        return ""
    name = getattr(v, "name", None)
    if isinstance(name, str):
        return name
    return str(v)

def _collect_shift_names(schedule: Schedule) -> List[str]:
    """Collect distinct shift names across the week in stable order (first appearance)."""
    shift_names: List[str] = []
    for d in list(DayOfWeek):
        assignment = schedule.days.get(d)
        if not assignment:
            continue
        for sname in assignment.shift_to_people.keys():
            if sname not in shift_names:
                shift_names.append(sname)
    return shift_names

def _build_grid(schedule: Schedule) -> List[List[str]]:
    """Return rows (list of lists) ready to be written: header + rows per shift."""
    shift_names = _collect_shift_names(schedule)
    header = ["Shift / Day"] + [d.value for d in list(DayOfWeek)]
    rows: List[List[str]] = [header]

    # Build day->shift->names map
    day_shift_map: Dict[str, Dict[str, List[str]]] = {}
    for d in list(DayOfWeek):
        assignment = schedule.days.get(d)
        mapping: Dict[str, List[str]] = {}
        if assignment:
            for sname, vols in assignment.shift_to_people.items():
                mapping[sname] = [_vol_name(v) for v in vols]
        day_shift_map[d.value] = mapping

    for s in shift_names:
        row = [s]
        for d in list(DayOfWeek):
            names = day_shift_map.get(d.value, {}).get(s, [])
            # join with newline for nicer wrapping in Excel
            cell = "\n".join(n for n in names if n)
            row.append(cell)
        rows.append(row)
    return rows

def _apply_sheet_styles(ws: Worksheet, rows: List[List[str]]):
    """Apply formatting: headers, fonts, column widths, row heights, colors, borders, wrapping."""
    max_cols = max(len(r) for r in rows) if rows else 1
    # Column widths: first column wider (shift name), others comfortable for ~5 names
    col_widths = [35] + [22] * (max_cols - 1)
    for i, w in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # Write cells and style them
    for r_idx, row in enumerate(rows, start=1):
        # choose alternate fill for content rows (not header)
        alt_fill = ALT_FILL_1 if (r_idx % 2 == 0) else ALT_FILL_2
        for c_idx in range(1, max_cols + 1):
            cell = ws.cell(row=r_idx, column=c_idx)
            value = row[c_idx - 1] if c_idx - 1 < len(row) else ""
            cell.value = value

            # header row styling
            if r_idx == 1:
                cell.fill = HEADER_FILL
                cell.font = HEADER_FONT
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                cell.border = CELL_BORDER
            else:
                # first column is shift name
                if c_idx == 1:
                    cell.font = SHIFT_FONT
                    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
                else:
                    # body cells: adjust font size depending on number of lines (names)
                    lines = (str(value).count("\n") + 1) if value else 0
                    if lines <= 1:
                        fsize = BASE_FONT_SIZE
                    elif lines <= 3:
                        fsize = BASE_FONT_SIZE - 1
                    elif lines <= 5:
                        fsize = BASE_FONT_SIZE - 2
                    else:
                        fsize = BASE_FONT_SIZE - 3
                    # set font
                    cell.font = Font(size=fsize)
                    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
                cell.fill = alt_fill
                cell.border = CELL_BORDER

        # Row height: base plus increments per number of lines in the widest cell of the row (excluding shift column)
        if r_idx == 1:
            ws.row_dimensions[r_idx].height = 28
        else:
            max_lines = 1
            for c_idx in range(2, max_cols + 1):
                cell_val = str(row[c_idx - 1]) if c_idx - 1 < len(row) else ""
                lines = cell_val.count("\n") + 1 if cell_val else 1
                if lines > max_lines:
                    max_lines = lines
            # estimate: 15-18 pixels per line, add padding
            height = 18 + (max_lines * 14)
            # clamp to a reasonable max to avoid enormous rows
            height = max(18, min(height, 200))
            ws.row_dimensions[r_idx].height = height

    # Freeze header row and first column
    ws.freeze_panes = "B2"

def write_pretty_schedule_xlsx(schedule: Schedule, out_path: str = "schedule_pretty.xlsx", sheet_title: str = "Weekly Schedule"):
    """
    Main entrypoint.
    - schedule: Schedule instance
    - out_path: path to write .xlsx
    - sheet_title: worksheet name
    """
    rows = _build_grid(schedule)

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title

    # write data and apply styles
    _apply_sheet_styles(ws, rows)

    # Save file
    wb.save(out_path)
    print(f"Wrote schedule to: {out_path}")

# -------------------------
# Example usage (optional)
# -------------------------
if __name__ == "__main__":
    # Attempt to obtain a Schedule instance from your schedule module.
    # Replace this with whatever you already have (e.g., call generate_schedule()).
    try:
        from schedule import generate_schedule  # type: ignore
        schedule_obj = generate_schedule([], [])  # adapt as needed in your project
    except Exception:
        raise RuntimeError("Please construct a Schedule instance and call write_pretty_schedule_xlsx(schedule_obj, out_path).")

    write_pretty_schedule_xlsx(schedule_obj, "schedule_pretty.xlsx")
