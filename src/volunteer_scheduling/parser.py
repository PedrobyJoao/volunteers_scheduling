"""
YAML parser
"""

import yaml
from pydantic import TypeAdapter
from . import schedule

def parse(path: str) -> schedule.ShiftsVolunteersYAML:
    with open(path) as f:
        data = yaml.safe_load(f)

    periods = [schedule.TimePeriod(**p) for p in data.get('time_periods', [])]
    period_map = {p.name.strip().lower(): p for p in periods}

    shifts = []
    for s in data.get('shifts', []):
        tp_name = s['time_period']
        tp_name_clean = tp_name.strip().lower()
        if tp_name_clean not in period_map:
            raise ValueError(f"Unknown time_period: {tp_name}")
        shifts.append(schedule.Shift(
            name=s['name'],
            time_period=period_map[tp_name_clean],
            min_people=s['min_people'],
            max_people=s['max_people'],
            importance=s['importance'],
            unoperational_days=s.get('unoperational_days', ())
        ))

    volunteers = [schedule.Volunteer(**v) for v in data.get('volunteers', [])]

    return schedule.ShiftsVolunteersYAML(time_periods=periods, shifts=shifts, volunteers=volunteers)

from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from copy import deepcopy
from enum import Enum


class DayOfWeek(Enum):
    MONDAY = "Mon"
    TUESDAY = "Tue"
    WEDNESDAY = "Wed"
    THURSDAY = "Thu"
    FRIDAY = "Fri"
    SATURDAY = "Sat"
    SUNDAY = "Sun"


class AssignmentError(RuntimeError):
    """Raised when an assignment cannot be performed because of business rules."""


@dataclass
class DayAssignment:
    # shift -> list of volunteers
    shift_to_people: Dict['Shift', List['Volunteer']] = field(default_factory=dict)


@dataclass
class Schedule:
    """
    Simple schedule: DayOfWeek -> DayAssignment (shift -> [Volunteer]).
    All state changes must go through assign/unassign/replace_day_assignment.
    Public readers return deep copies to avoid side-effects.
    """
    days: Dict[DayOfWeek, DayAssignment] = field(
        default_factory=lambda: {d: DayAssignment() for d in DayOfWeek}
    )

    # --------- helpers ----------
    @staticmethod
    def _shift_operational_on_day(shift: 'Shift', day: DayOfWeek) -> bool:
        for u in shift.unoperational_days:
            # if stored DayOfWeek values:
            if isinstance(u, DayOfWeek):
                if u == day:
                    return False
            else:
                # compare by name or value (case-insensitive)
                s = str(u).lower()
                if s == day.name.lower() or s == day.value.lower():
                    return False
        return True

    def _ensure_day(self, day: DayOfWeek):
        if day not in self.days:
            self.days[day] = DayAssignment()

    def _vol_shifts_of_day(self, volunteer: 'Volunteer', day: DayOfWeek) -> List['Shift']:
        self._ensure_day(day)
        da = self.days[day]
        return [s for s, vols in da.shift_to_people.items() if volunteer in vols]

    def _vol_has_time_period(self, volunteer: 'Volunteer', day: DayOfWeek, tp: 'TimePeriod') -> bool:
        self._ensure_day(day)
        da = self.days[day]
        for shift, vols in da.shift_to_people.items():
            if shift.time_period == tp and volunteer in vols:
                return True
        return False

    def _count_vol_shifts_on_day(self, volunteer: 'Volunteer', day: DayOfWeek) -> int:
        return len(self._vol_shifts_of_day(volunteer, day))

    # --------- inspection / snapshots ----------
    def get_day_assignment(self, day: DayOfWeek) -> DayAssignment:
        self._ensure_day(day)
        return deepcopy(self.days[day])

    def snapshot(self) -> Dict[DayOfWeek, DayAssignment]:
        return deepcopy(self.days)

    def iter_assignments(self):
        for day, da in self.days.items():
            for shift, vols in da.shift_to_people.items():
                yield day, shift, tuple(vols)

    # --------- validation / can_assign ----------
    def can_assign(self, volunteer: 'Volunteer', day: DayOfWeek, shift: 'Shift') -> Tuple[bool, str]:
        """
        Return (True, "") when ok, else (False, reason).
        Does not mutate.
        """
        # operational day
        if not self._shift_operational_on_day(shift, day):
            return False, f"Shift {shift.name!r} not operational on {day.name}"

        # day off
        if day.value in volunteer.days_off:
            return False, f"Volunteer {volunteer.name!r} has {day.name} as day off"

        # fixed shift constraint
        if volunteer.fixed_shift:
            if volunteer.fixed_shift != shift.name:
                return False, f"Volunteer {volunteer.name!r} fixed to {volunteer.fixed_shift!r}"

        # time period exclusivity
        if self._vol_has_time_period(volunteer, day, shift.time_period):
            return False, f"Volunteer {volunteer.name!r} already has a shift in time period {shift.time_period.name!r} on {day.name}"

        # max 2 shifts/day
        if self._count_vol_shifts_on_day(volunteer, day) >= 2:
            return False, f"Volunteer {volunteer.name!r} already has 2 shifts on {day.name}"

        # shift capacity
        self._ensure_day(day)
        current = self.days[day].shift_to_people.get(shift, [])
        if shift.max_people is not None and len(current) >= shift.max_people:
            return False, f"Shift {shift.name!r} on {day.name} at max capacity ({shift.max_people})"

        return True, ""

    # --------- mutations ----------
    def assign(self, volunteer: 'Volunteer', day: DayOfWeek, shift: 'Shift', raise_on_error: bool = True) -> bool:
        ok, reason = self.can_assign(volunteer, day, shift)
        if not ok:
            if raise_on_error:
                raise AssignmentError(reason)
            return False

        self._ensure_day(day)
        da = self.days[day]
        if shift not in da.shift_to_people:
            da.shift_to_people[shift] = [volunteer]
        else:
            if volunteer in da.shift_to_people[shift]:
                return True  # idempotent
            da.shift_to_people[shift].append(volunteer)
        return True

    # --------- audits ----------
    # todo

    # --------- audits ----------

    def find_volunteer_assignments(self, volunteer: 'Volunteer') -> Dict[DayOfWeek, List['Shift']]:
        result: Dict[DayOfWeek, List['Shift']] = {}
        for day, da in self.days.items():
            assigned = [s for s, vols in da.shift_to_people.items() if volunteer in vols]
            if assigned:
                result[day] = list(assigned)
        return result
