"""
TODO: add 1 additional first row right below the days of the week,
with the name of people with day off for the day
"""
from pathlib import Path
from typing import Dict, List

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .schedule import (
    DayOfWeek,
    TimePeriod,
    Schedule,
    Shift,
    Volunteer,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SHIFT_COLUMN_WIDTH = 30
DAY_COLUMN_WIDTH = 22

HEADER_ROW_HEIGHT = 30
PHASE_ROW_HEIGHT = 24

MIN_SHIFT_ROW_HEIGHT = 30
LINE_HEIGHT = 15
MAX_SHIFT_ROW_HEIGHT = 110

NORMAL_FONT_SIZE = 11
COMPACT_FONT_SIZE = 10

HEADER_FILL = PatternFill("solid", fgColor="4472C4")
PHASE_FILL = PatternFill("solid", fgColor="D9EAF7")
SHIFT_FILL = PatternFill("solid", fgColor="F2F2F2")
CELL_FILL = PatternFill("solid", fgColor="FFFFFF")

WHITE_FONT = Font(
    name="Calibri",
    size=12,
    bold=True,
    color="FFFFFF",
)

PHASE_FONT = Font(
    name="Calibri",
    size=12,
    bold=True,
)

SHIFT_FONT = Font(
    name="Calibri",
    size=11,
    bold=True,
)

CELL_FONT = Font(
    name="Calibri",
    size=NORMAL_FONT_SIZE,
)

COMPACT_CELL_FONT = Font(
    name="Calibri",
    size=COMPACT_FONT_SIZE,
)

BORDER_SIDE = Side(
    style="thin",
    color="D9D9D9",
)

CELL_BORDER = Border(
    left=BORDER_SIDE,
    right=BORDER_SIDE,
    top=BORDER_SIDE,
    bottom=BORDER_SIDE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _volunteer_names(volunteers: List[Volunteer]) -> str:
    """Return volunteer names separated by newlines for display in Excel."""
    return "\n".join(volunteer.name for volunteer in volunteers)


def _collect_shifts(schedule: Schedule) -> List[Shift]:
    """
    Collect all distinct Shift objects used by the schedule.

    Shifts are returned in their first-seen order. Since Shift is frozen and
    therefore hashable, the objects themselves are used for identity.
    """
    shifts: List[Shift] = []

    for day in DayOfWeek:
        assignment = schedule.days.get(day)

        if assignment is None:
            continue

        for shift in assignment.shift_to_people:
            if shift not in shifts:
                shifts.append(shift)

    return shifts


def _group_shifts_by_phase(schedule: Schedule) -> Dict[TimePeriod, List[Shift]]:
    """Group shifts by their Shift.day_phase."""
    groups: Dict[TimePeriod, List[Shift]] = {}

    for shift in _collect_shifts(schedule):
        groups[shift.time_period].append(shift)

    return groups


def _build_assignment_map(
    schedule: Schedule,
) -> Dict[DayOfWeek, Dict[Shift, List[Volunteer]]]:
    """Return the schedule assignments keyed by day and Shift object."""
    return {
        day: (
            schedule.days[day].shift_to_people
            if day in schedule.days
            else {}
        )
        for day in DayOfWeek
    }


def _calculate_row_height(value: str) -> float:
    """Calculate a suitable row height based on the number of volunteer names."""
    if not value:
        return MIN_SHIFT_ROW_HEIGHT

    number_of_lines = value.count("\n") + 1

    height = max(
        MIN_SHIFT_ROW_HEIGHT,
        number_of_lines * LINE_HEIGHT + 10,
    )

    return min(height, MAX_SHIFT_ROW_HEIGHT)


# ---------------------------------------------------------------------------
# Worksheet styling
# ---------------------------------------------------------------------------

def _setup_columns(ws: Worksheet) -> None:
    """Configure column widths for the schedule."""
    ws.column_dimensions["A"].width = SHIFT_COLUMN_WIDTH

    for column_index, _day in enumerate(DayOfWeek, start=2):
        column_letter = get_column_letter(column_index)
        ws.column_dimensions[column_letter].width = DAY_COLUMN_WIDTH


def _write_header(ws: Worksheet) -> None:
    """Write the spreadsheet header row."""
    ws.cell(row=1, column=1, value="Shift")

    for column_index, day in enumerate(DayOfWeek, start=2):
        ws.cell(
            row=1,
            column=column_index,
            value=day.value,
        )

    for column_index in range(1, len(DayOfWeek) + 2):
        cell = ws.cell(row=1, column=column_index)

        cell.fill = HEADER_FILL
        cell.font = WHITE_FONT
        cell.border = CELL_BORDER
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

    ws.row_dimensions[1].height = HEADER_ROW_HEIGHT


def _write_phase_row(
    ws: Worksheet,
    row_number: int,
    time_period: TimePeriod,
) -> None:
    """Write and style a phase separator row."""
    last_column = len(DayOfWeek) + 1

    ws.merge_cells(
        start_row=row_number,
        start_column=1,
        end_row=row_number,
        end_column=last_column,
    )

    cell = ws.cell(
        row=row_number,
        column=1,
        value=time_period.name,
    )

    cell.fill = PHASE_FILL
    cell.font = PHASE_FONT
    cell.border = CELL_BORDER
    cell.alignment = Alignment(
        horizontal="left",
        vertical="center",
    )

    ws.row_dimensions[row_number].height = PHASE_ROW_HEIGHT


def _write_shift_row(
    ws: Worksheet,
    row_number: int,
    shift: Shift,
    assignments: Dict[DayOfWeek, Dict[Shift, List[Volunteer]]],
) -> None:
    """Write one Shift row and its volunteer assignments."""
    shift_cell = ws.cell(
        row=row_number,
        column=1,
        value=shift.name,
    )

    shift_cell.fill = SHIFT_FILL
    shift_cell.font = SHIFT_FONT
    shift_cell.border = CELL_BORDER
    shift_cell.alignment = Alignment(
        horizontal="left",
        vertical="center",
        wrap_text=True,
    )

    max_lines = 1

    for column_index, day in enumerate(DayOfWeek, start=2):
        volunteers = assignments[day].get(shift, [])
        names = _volunteer_names(volunteers)

        cell = ws.cell(
            row=row_number,
            column=column_index,
            value=names,
        )

        cell.fill = CELL_FILL
        cell.border = CELL_BORDER
        cell.alignment = Alignment(
            horizontal="left",
            vertical="center",
            wrap_text=True,
        )

        line_count = names.count("\n") + 1 if names else 1
        max_lines = max(max_lines, line_count)

        if len(volunteers) > 5:
            cell.font = COMPACT_CELL_FONT
        else:
            cell.font = CELL_FONT

    ws.row_dimensions[row_number].height = min(
        MAX_SHIFT_ROW_HEIGHT,
        max(MIN_SHIFT_ROW_HEIGHT, max_lines * LINE_HEIGHT + 10),
    )


# ---------------------------------------------------------------------------
# Main exporter
# ---------------------------------------------------------------------------

def write_pretty_schedule_xlsx(
    schedule: Schedule,
    time_periods: list[TimePeriod],
    output_path: str | Path = "schedule.xlsx",
    sheet_title: str = "Weekly Schedule",
) -> None:
    """
    Generate a formatted XLSX file from a Schedule.

    The spreadsheet is organized as:

        Shift | Mon | Tue | Wed | Thu | Fri | Sat | Sun

        Early morning
        Shift A
        Shift B

        Late morning
        Shift C
        Shift D

        Afternoon
        ...

        Evening
        ...

    Volunteer names inside a cell are separated by newlines.
    """
    output_path = Path(output_path)

    workbook = Workbook()
    worksheet = workbook.create_sheet(title=sheet_title)

    _setup_columns(worksheet)
    _write_header(worksheet)

    assignments = _build_assignment_map(schedule)
    shifts_by_phase = _group_shifts_by_phase(schedule)

    current_row = 2

    for time_period in time_periods:
        shifts = shifts_by_phase[time_period]

        # Don't display an empty phase.
        if not shifts:
            continue

        _write_phase_row(
            worksheet,
            current_row,
            time_period,
        )
        current_row += 1

        for shift in shifts:
            _write_shift_row(
                worksheet,
                current_row,
                shift,
                assignments,
            )
            current_row += 1

    worksheet.freeze_panes = "B2"
    worksheet.sheet_view.showGridLines = False

    workbook.save(output_path)
