from dataclasses import dataclass, field
from typing import List, Dict
from enum import Enum
import random

class DayOfWeek(Enum):
    MONDAY = "Mon"
    TUESDAY = "Tue"
    WEDNESDAY = "Wed"
    THURSDAY = "Thu"
    FRIDAY = "Fri"
    SATURDAY = "Sat"
    SUNDAY = "Sun"

class PhaseOfDay(Enum):
    EARLY_MORNING = "Early Morning"
    LATE_MORNING = "Late Morning"
    AFTERNOON = "Afternoon"
    EVENING = "Evening"

@dataclass(frozen=True)
class Shift:
    name: str
    day_phase: PhaseOfDay
    min_people: int
    max_people: int
    importance: int
    unoperational_days: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        # 1. unoperational days as a tuple instead of list
        if isinstance(self.unoperational_days, list):
            object.__setattr__(self, 'unoperational_days', tuple(self.unoperational_days))

        # 2. Enforce Enum conversion
        if isinstance(self.day_phase, str):
            # todo: smarter check (or smarter values of PhaseOfDay)
            valid_enum = PhaseOfDay(self.day_phase)
            object.__setattr__(self, 'day_phase', valid_enum)

@dataclass
class Volunteer:
    name: str
    days_off: List[str]
    desired_shifts: List[str] = field(default_factory=list)

@dataclass
class DayAssignment:
    shift_to_people: Dict[Shift, List[Volunteer]]

@dataclass
class Schedule:
    days: Dict[DayOfWeek, DayAssignment]

"""
Consider:
- [x] Shift operational days
- [x] if no 2 days off are assigned to volunteer, we must assign randomly
    with a preference of assigning everyone to Sunday after assigning all people
    to number 3 importance shifts of Sunday. And then assign volunteers days off
    to random days of the week (all volunteers hsould have 2 days off)
- [x] handle error if no volunteers fitted
- [] for remaining volunteers without shifts assigned, assign them to shift Others
- [] consider people with fixed shifts ("Misc: Construction, Arts and others..." shift also) that
    will do the same all the work days
- [] verify if all shifts were filled
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

            if len(eligible) < shift.min_people:
                raise ValueError(f"Shift {shift.name} needs {shift.min_people} people, but only {len(eligible)} were found")

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
        raise RuntimeError(f"Shift {shift.name} needs {shift.min_people} people, but only {n} were found")

    return eligible

def assign_volunteer_to_shift(schedule: Schedule, day: DayOfWeek, shift: Shift, vol: Volunteer):
    if shift.name not in schedule.days[day].shift_to_people:
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

Next versions:

[] Volunteers with fixed shifts

Todo: test all requirements
"""
def volunteer_satisfies(schedule: Schedule, volunteer: Volunteer, shift: Shift, day: DayOfWeek) -> bool:
    if day.value in volunteer.days_off:
        return False
    
    vol_shifts = vol_shifts_of_day(schedule, volunteer, day)
    for vol_shift in vol_shifts:
        if vol_shift.day_phase == shift.day_phase:
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
            shifts.sort(key=lambda kv: (-kv[0].importance, kv[0].day_phase.value, kv[0].name))

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

            lines.append(f"{indent}{status} {shift.name} — {shift.day_phase.value} "
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
