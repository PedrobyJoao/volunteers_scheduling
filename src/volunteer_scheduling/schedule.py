"""
[] consider that one of the day phases might be required for everyone
(as now it's considered early morning required)
[] use pydantic
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple
from datetime import time
from enum import Enum 
import random
from pydantic import BaseModel, ConfigDict

class DayOfWeek(Enum):
    MONDAY = "Mon"
    TUESDAY = "Tue"
    WEDNESDAY = "Wed"
    THURSDAY = "Thu"
    FRIDAY = "Fri"
    SATURDAY = "Sat"
    SUNDAY = "Sun"

class TimePeriod(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    start: time
    end: time

class Shift(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    time_period: TimePeriod
    min_people: int
    max_people: int
    importance: int # todo: change from importance to required?
    unoperational_days: tuple[str, ...]


class Volunteer(BaseModel):
    name: str
    days_off: List[str]
    fixed_shift: str = "" # for people only working on the same thing (e.g.: construction, agriculture)
    desired_shifts: List[str]
    # todo: how many shifts to be worked (default = 2)
    # todo: how many days off (default = 2)

class ShiftsVolunteersYAML(BaseModel):
    time_periods: List[TimePeriod]
    shifts: List[Shift]
    volunteers: List[Volunteer]

@dataclass
class DayAssignment():
    shift_to_people: Dict[Shift, List[Volunteer]]

@dataclass
class Schedule:
    def __init__(self, shifts: List[Shift]):
        self.days: Dict[DayOfWeek, DayAssignment] = {
                d: DayAssignment({s: [] for s in shifts}) 
                for d in DayOfWeek
                }


    # --------- helpers ----------
    @staticmethod
    def _shift_operational_on_day(shift: Shift, day: DayOfWeek) -> bool:
        for u in shift.unoperational_days:
            if isinstance(u, DayOfWeek):
                if u == day:
                    return False
            else:
                # compare by name or value (case-insensitive)
                s = str(u).lower()
                if s == day.name.lower() or s == day.value.lower():
                    return False
        return True

    def _vol_shifts_of_day(self, volunteer: Volunteer, day: DayOfWeek) -> List[Shift]:
        da = self.days[day]
        return [s for s, vols in da.shift_to_people.items() if volunteer in vols]

    def _vol_has_time_period(self, volunteer: Volunteer, day: DayOfWeek, tp: TimePeriod) -> bool:
        da = self.days[day]
        for shift, vols in da.shift_to_people.items():
            if shift.time_period == tp and volunteer in vols:
                return True
        return False

    def _count_vol_shifts_on_day(self, volunteer: 'Volunteer', day: DayOfWeek) -> int:
        return len(self._vol_shifts_of_day(volunteer, day))

    # --------- inspection / snapshots ----------
    def get_day_assignment(self, day: DayOfWeek) -> DayAssignment:
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
        if volunteer.fixed_shift and volunteer.fixed_shift != shift.name:
            return False, f"Volunteer {volunteer.name!r} fixed to {volunteer.fixed_shift!r}"

        # can not be assigned twice to the same time period
        if self._vol_has_time_period(volunteer, day, shift.time_period):
            return False, f"Volunteer {volunteer.name!r} already has a shift in time period {shift.time_period.name!r} on {day.name}"

        # max 2 shifts/day
        # todo: this should come from volunteer.num_days_offs
        if self._count_vol_shifts_on_day(volunteer, day) >= 2:
            return False, f"Volunteer {volunteer.name!r} already has 2 shifts on {day.name}"

        # shift max capacity
        current = self.days[day].shift_to_people.get(shift, [])
        if shift.max_people is not None and len(current) >= shift.max_people:
            return False, f"Shift {shift.name!r} on {day.name} at max capacity ({shift.max_people})"

        return True, ""

    # --------- mutations ----------
    def assign(self, volunteer: Volunteer, day: DayOfWeek, shift: Shift, raise_on_error: bool = False) -> bool:
        ok, reason = self.can_assign(volunteer, day, shift)
        if not ok:
            if raise_on_error:
                raise AssignmentError(reason)
            return False

        da = self.days[day]
        if shift not in da.shift_to_people:
            da.shift_to_people[shift] = [volunteer]
        else:
            if volunteer in da.shift_to_people[shift]:
                return True 
            da.shift_to_people[shift].append(volunteer)
        return True

    # --------- audits ----------

    def validate_minima(self) -> List[str]:
        problems: List[str] = []
        for day, da in self.days.items():
            for shift, vols in da.shift_to_people.items():
                if day.value in shift.unoperational_days:
                    continue
                if shift.min_people is not None and len(vols) < shift.min_people:
                    problems.append(f"Day {day.name}: shift {shift.name} needs {shift.min_people} but has {len(vols)}")
        return problems

    # --------- lookup ----------

    def find_volunteer_assignments(self, volunteer: Volunteer) -> Dict[DayOfWeek, List[Shift]]:
        result: Dict[DayOfWeek, List[Shift]] = {}
        for day, da in self.days.items():
            assigned = [s for s, vols in da.shift_to_people.items() if volunteer in vols]
            if assigned:
                result[day] = list(assigned)
        return result

"""
Consider:
- [x] Shift operational days
- [x] assign days off if not assigned yet
- [] for remaining volunteers without shifts assigned, assign them to shift Others
- [] consider people with fixed shifts ("Misc: Construction, Arts and others..." shift also) that
    will do the same all the work days
- [] ignore preferences when minimum quote is not reached for level 3 shifts
- [x] verify if all shifts were filled
- [] verify if all volunteers were assigned

Test cases to cover:
1. enough volunteers for shifts level 3 (considering min)
2. assert all volunteers get 2 days off
"""
def generate_schedule(shifts: List[Shift], volunteers: List[Volunteer]) -> Schedule:
    # 0. check if we have enough volunteers to cover required shifts
    for day in list(DayOfWeek):
        min_day = min_needed_level3(shifts, day)
        if min_day > len(volunteers):
            raise ValueError(
                    f"""
                    Day {day.name} needs {min_day} volunteers,
                    but only {len(volunteers)} were found"
                    """)

    shifts_by_importance = sorted(shifts, key=lambda s: s.importance, reverse=True)
    schedule = Schedule({day: DayAssignment({}) for day in list(DayOfWeek)})
    random.shuffle(volunteers)

    # 1. assign days off randomly, all must have 2 days off
    assign_days_offs(shifts, volunteers)

    for day in list(DayOfWeek):
        for shift in shifts_by_importance:
            if day.name in shift.unoperational_days:
                continue

            eligible =  eligible_vols_for_shift(schedule, shift, volunteers, day) 

            for vol in eligible: 
                assign_volunteer_to_shift(schedule, day, shift, vol)

            # check if shifts min people were assigned
            if shift.min_people > len(schedule.days[day].shift_to_people.get(shift, [])):
                msg = f"""
                    Shift {shift.name} needed {shift.min_people} people,
                    but only {len(schedule.days[day].shift_to_people.get(shift, []))} were assigned
                    """
                if shift.importance == 3:
                    raise ValueError(msg)
                else:
                    print(f"WARNING: {msg}")




    return schedule

"""
[x] Min people needed for the shift
[x] return error if no volunteers were filled
"""
def eligible_vols_for_shift(schedule: Schedule,
    shift: Shift, volunteers: List[Volunteer], 
    day: DayOfWeek) -> List[Volunteer]:

    n = 0
    eligible : List[Volunteer] = []
    for vol in volunteers:
        if volunteer_satisfies(schedule, vol, shift, day):
            n += 1
            eligible.append(vol)

        if n >= shift.min_people:
            break

    if n < shift.min_people:
        msg = f"Shift {shift.name} needs {shift.min_people} people, but only {n} were found"
        if shift.importance == 3:
            raise ValueError(msg)
        else:
            print(f"WARNING: {msg}")

    return eligible

def assign_volunteer_to_shift(schedule: Schedule, day: DayOfWeek, shift: Shift, vol: Volunteer):
    if shift not in schedule.days[day].shift_to_people:
        schedule.days[day].shift_to_people[shift] = [vol]
    else:
        schedule.days[day].shift_to_people[shift].append(vol)

"""
Requirements:

[x] Check volunteers' days off
[x] only one shift per phase of day
[x] two shifts per day per volunteer
[] volunteer preferences of days phase
[] Preferences of shifts
[] Volunteers with fixed shifts

Todo: test all requirements
"""
def volunteer_satisfies(schedule: Schedule, volunteer: Volunteer, shift: Shift, day: DayOfWeek) -> bool:
    if day.value in volunteer.days_off:
        return False
    
    vol_shifts = vol_shifts_of_day(schedule, volunteer, day)
    for vol_shift in vol_shifts:
        if vol_shift.time_period == shift.time_period:
            return False

    if len(vol_shifts) == 2:
        return False

    return True

def vol_shifts_of_day(schedule: Schedule, volunteer: Volunteer, day: DayOfWeek) -> List[Shift]:
    return [shift 
            for shift in schedule.days[day].shift_to_people
            if volunteer in schedule.days[day].shift_to_people[shift]
            ]


def assign_days_offs(shifts: List[Shift], volunteers: List[Volunteer]):
    """
    TODO: days off are being concentrated in a few days which is ok for Saturday and Sunday
    but for weekdays, we need to distribute them randomly
    """
    random.shuffle(volunteers)

    # Sunday first
    assign_weekend_day_off(shifts, DayOfWeek.SUNDAY, volunteers)

    # Saturday
    assign_weekend_day_off(shifts, DayOfWeek.SATURDAY, volunteers)

    # weekdays (todo randomize)
    days: List[DayOfWeek] = [DayOfWeek.MONDAY, DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY, DayOfWeek.THURSDAY, DayOfWeek.FRIDAY]
    random.shuffle(days)
    for day in days:
        assign_weekend_day_off(shifts, day, volunteers)

    for v in volunteers:
        if len(v.days_off) != 2:
            raise RuntimeError(f"{v.name} ended with {len(v.days_off)} days off (expected 2)")

def assign_weekend_day_off(shifts: List[Shift], day: DayOfWeek, volunteers: List[Volunteer]):
    off_count = 0
    max_off_day = max(0, max_vols_off(shifts, day, len(volunteers)))

    for vol in volunteers:
        if len(vol.days_off) == 2:
            continue

        if day.name not in vol.days_off:
            vol.days_off.append(day.name)

        off_count += 1

        if off_count >= max_off_day:
            break
    pass

def min_needed_level3(shifts: List[Shift], day: DayOfWeek) -> int:
    """min number of volunteers for level3 shifts"""
    n = 0
    for shift in shifts:
        if day.name in shift.unoperational_days:
            continue
        if shift.importance == 3:
            n += shift.min_people
    return n

def max_vols_off(shifts: List[Shift], day: DayOfWeek, total_vols: int) -> int:
    """how many volunteers can get day off this day"""
    return total_vols - min_needed_level3(shifts, day)

# PRINTING

def _shift_operational_on_day(shift: 'Shift', day: 'DayOfWeek') -> bool:
    """Return False if shift.unoperational_days lists this day (supports DayOfWeek or string values)."""
    for u in shift.unoperational_days:
        if isinstance(u, DayOfWeek):
            if u == day:
                return False
        else:
            # compare by name or value (case-insensitive)
            if u.lower() == day.name.lower() or u.lower() == day.value.lower():
                return False
    return True

def pretty_schedule(schedule: 'Schedule',
                    show_empty_shifts: bool = True,
                    sort_shifts_by_importance: bool = True,
                    indent: str = "  ") -> str:
    lines: List[str] = []
    for day in DayOfWeek:  # iterate in enum order
        lines.append(f"{day.name} ({day.value})")
        day_assignment = schedule.days.get(day)
        if not day_assignment or not day_assignment.shift_to_people:
            lines.append(f"{indent}<no shifts assigned>")
            lines.append("")  # blank line between days
            continue

        shifts = list(day_assignment.shift_to_people.items())  # list of (Shift, [Volunteer])
        if sort_shifts_by_importance:
            # sort by importance desc, then by phase, then by shift name
            shifts.sort(key=lambda kv: (-kv[0].importance, kv[0].time_period.start, kv[0].name))

        for shift, people in shifts:
            operational = _shift_operational_on_day(shift, day)
            count = len(people)
            # status icon:
            if not operational:
                status = "🔴"  # not operational today
            elif count < shift.min_people:
                status = "UNSAT"  # understaffed
            elif count > shift.max_people:
                status = "OVER"  # overstaffed
            else:
                status = "OK"  # OK

            lines.append(f"{indent}{status} {shift.name} — {shift.time_period.start} "
                         f"(importance={shift.importance}) [{count}/{shift.min_people}-{shift.max_people}]")

            if shift.unoperational_days:
                lines.append(f"{indent*2}unoperational_days: {shift.unoperational_days}")

            if people:
                # sort volunteers by name for deterministic output
                for vol in sorted(people, key=lambda v: v.name):
                    desired = f" desired={vol.desired_shifts}" if getattr(vol, "desired_shifts", None) else ""
                    lines.append(f"{indent*2}- {vol.name} (days_off={vol.days_off}){desired}")
            else:
                if show_empty_shifts:
                    lines.append(f"{indent*2}- <no volunteers>")

        lines.append("")  # blank line after each day

    return "\n".join(lines)
