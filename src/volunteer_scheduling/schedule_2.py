"""
TODOs:
[] test prefered shifts
[] warning when typos, wrong fields in yaml


DONE:

Volunteer-wise:
[x] only one shift per time period
[x] at most 2 shifts per day for volunteer
[x] volunteer custom number of shifts
[x] Preferences of shifts
[x] assign days off if not assigned yet
[x] Check volunteers' days off
[x] volunteer available time periods

Shift-Wise
[x] shift capacity (max_people)
[x] Min people needed for the shift

Algorithm:
[x] return error if no volunteers were filled
[x] ignore preferences when minimum quote is not reached
[x] for remaining volunteers without shifts assigned, assign them to shift Others
[x] verify if all volunteers were assigned
""" 
from dataclasses import dataclass
from typing import Dict, List, Optional, Iterable
from pydantic import BaseModel, ConfigDict
from datetime import time
from copy import deepcopy
from enum import Enum
from copy import deepcopy
import random

class DayOfWeek(Enum):
    MONDAY = "Monday"
    TUESDAY = "Tuesday"
    WEDNESDAY = "Wednesday"
    THURSDAY = "Thursday"
    FRIDAY = "Friday"
    SATURDAY = "Saturday"
    SUNDAY = "Sunday"

# todo: this should be described by the yaml instead
class WorkType(Enum):
    kitchen = "kitchen"
    housekeeping = "housekeeping"
    others = "others"

class TimePeriod(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    start: time
    end: time

class Shift(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    time_period: TimePeriod
    work_type: WorkType = WorkType.others
    min_people: int
    max_people: int
    unoperational_days: tuple[str, ...]

class Volunteer(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    days_off: tuple[str, ...] = ()
    fixed_shift: str = "" # for people only working on the same thing (e.g.: construction, agriculture)
    desired_work: tuple[WorkType, ...] = ()
    unavailable_periods: tuple[TimePeriod, ...] = ()
    max_days_off: int = 2
    max_number_of_shifts: int = 2

class ShiftsVolunteersYAML(BaseModel):
    time_periods: List[TimePeriod]
    shifts: List[Shift]
    volunteers: List[Volunteer]

class AssignmentError(RuntimeError):
    """Raised when an assignment cannot be performed because of business rules."""

@dataclass
class Schedule:
    def __init__(self, shifts: List['Shift'], vols: List['Volunteer'], time_periods: List['TimePeriod']):
            self.vols_shifts : Dict[Volunteer, Dict[DayOfWeek, Dict[TimePeriod, Shift]]] = {}
            self.schedule : Dict[DayOfWeek, Dict['TimePeriod', Dict['Shift', List['Volunteer']]]] = {}
            for day in DayOfWeek:
                self.schedule[day] = {}
                for tp in time_periods:
                    self.schedule[day][tp] = {}
                for shift in shifts:
                    self._add_shift_for_day(day, shift)

            for vol in vols:
                self.vols_shifts[vol] = {}
                for day in DayOfWeek:
                    self.vols_shifts[vol][day] = {}

    def _add_shift_for_day(self, day: DayOfWeek, shift: 'Shift'):
        if not self._shift_operational_on_day(shift, day):
            return
        tp = shift.time_period
        if tp not in self.schedule[day]:
            self.schedule[day][tp] = {}

        if shift not in self.schedule[day][tp]:
            self.schedule[day][tp][shift] = []

    def _shift_operational_on_day(self, shift: 'Shift', day: DayOfWeek) -> bool:
        for u in shift.unoperational_days:
            if isinstance(u, DayOfWeek):
                if u == day:
                    return False
            else:
                s = str(u).lower()
                if s == day.name.lower() or s == day.value.lower():
                    return False
        return True

    # ----------------------
    # Small lookup helpers
    # ----------------------
    def _vol_shifts_of_day(self, volunteer: 'Volunteer', day: DayOfWeek) -> List['Shift']:
        result: List['Shift'] = []
        for tp_map in (self.schedule.get(day) or {}).values():
            for shift, vols in tp_map.items():
                if volunteer in vols:
                    result.append(shift)
        return result

    def _vol_has_time_period(self, volunteer: 'Volunteer', day: DayOfWeek, tp: 'TimePeriod') -> bool:
        tp_map = self.schedule.get(day, {}).get(tp, {})
        for vols in tp_map.values():
            if volunteer in vols:
                return True
        return False

    def available_vols_day(self, day: DayOfWeek) -> List[Volunteer]:
        vols = []
        for vol in self.vols_shifts:
            fulfilled_max_shifts = len(self.vols_shifts[vol][day]) >= vol.max_number_of_shifts
            if day not in vol.days_off and not fulfilled_max_shifts:
                vols.append(vol)
        return deepcopy(vols)

    def available_vols_tp_day(self, day: DayOfWeek, tp: TimePeriod) -> List[Volunteer]:
        vols = []
        for vol in self.vols_shifts:
            fulfilled_max_shifts = len(self.vols_shifts[vol][day]) >= vol.max_number_of_shifts
            already_has_tp = tp in self.vols_shifts[vol][day]
            if (day not in vol.days_off
                and not fulfilled_max_shifts
                and not already_has_tp 
                and not tp in vol.unavailable_periods):
                vols.append(vol)
        return deepcopy(vols)

    def shifts_in_day_tp(self, day: DayOfWeek, tp: TimePeriod) -> List[Shift]:
        return deepcopy([shift for shift in self.schedule.get(day, {}).get(tp, {}).keys()])

    def shifts_in_day(self, day: DayOfWeek) -> List[Shift]:
        shifts : List[Shift] = []
        for tp_map in self.schedule.get(day, {}).values():
            shifts.extend(tp_map.keys())
        return deepcopy(shifts)

    def _vols_in_shift(self, shift: Shift, day: DayOfWeek) -> List[Volunteer]:
        return self.schedule.get(day, {}).get(shift.time_period, {}).get(shift, [])

    def has_shift_minimum(self, shift: Shift, day: DayOfWeek) -> bool:
        return len(self._vols_in_shift(shift, day)) >= shift.min_people
    
    # ----------------------
    # Core mutation: assign
    # ----------------------
    def can_assign(self, volunteer: 'Volunteer', day: DayOfWeek, shift: 'Shift') -> Optional[str]:
        """
        Return None if ok, else a short reason string (no mutation).
        Enforces:
          [x] shift operational on day
          [x] volunteer not on day off
          [x] only one shift per time period
          [x] at most 2 shifts per day for volunteer
          [x] shift capacity (max_people)
          [x] unavailable time periods respected
          [] volunteer fixed_shift respected (if set, must match shift.name)
        """

        if not self._shift_operational_on_day(shift, day):
            return f"shift {shift.name!r} not operational on {day.name}"
        if day.value in volunteer.days_off:
            return f"volunteer {volunteer.name!r} has {day.name} as day off"
        # if volunteer.fixed_shift and volunteer.fixed_shift != shift.name:
        #         return f"volunteer {volunteer.name!r} fixed to {volunteer.fixed_shift!r}"
        if self._vol_has_time_period(volunteer, day, shift.time_period):
            return f"volunteer {volunteer.name!r} already has a shift in time period {shift.time_period.name!r} on {day.name}"
        if shift.time_period in volunteer.unavailable_periods:
            return f"volunteer {volunteer.name!r} is unavailable in time period {shift.time_period.name!r}"
        if len(self._vol_shifts_of_day(volunteer, day)) >= volunteer.max_number_of_shifts:
            return f"""volunteer {volunteer.name!r} already has 
                        reached its maximum number of {volunteer.max_number_of_shifts} shifts on {day.name}
                        """

        assigned = self.schedule.get(day, {}).get(shift.time_period, {}).get(shift, [])
        if shift.max_people is not None and len(assigned) >= shift.max_people:
            return f"shift {shift.name!r} on {day.name} at max capacity ({shift.max_people})"
        return None

    def assign(self, volunteer: 'Volunteer', day: DayOfWeek, shift: 'Shift', *, raise_on_error: bool = False) -> bool:
        """
        Assign volunteer to shift on day if allowed.
        Returns True on success, False on failure (or raises AssignmentError if raise_on_error).
        """
        err = self.can_assign(volunteer, day, shift)
        if err:
            if raise_on_error:
                raise AssignmentError(err)
            return False

        # ensure structure exists
        if shift.time_period not in self.schedule[day]:
            self.schedule[day][shift.time_period] = {}
        if shift not in self.schedule[day][shift.time_period]:
            self.schedule[day][shift.time_period][shift] = []
        # idempotent
        if volunteer in self.schedule[day][shift.time_period][shift]:
            return True
        self.schedule[day][shift.time_period][shift].append(volunteer)
        self.vols_shifts[volunteer][day][shift.time_period] = shift
        return True

    # ----------------------
    # Utility readers for printing/reporting
    # ----------------------
    def iter_assignments(self) -> Iterable[tuple]:
        """Yield (day, time_period, shift, tuple(volunteers))"""
        for day, tp_map in self.schedule.items():
            for tp, shift_map in tp_map.items():
                for shift, vols in shift_map.items():
                    yield day, tp, shift, tuple(vols)

    # ----------------------
    # Printing/Debugging
    # ----------------------

    def pretty(self, *, include_empty: bool = True) -> str:
        """Return the schedule as a readable, deterministic string."""
        lines: List[str] = []

        for day in DayOfWeek:
            lines.append(f"\n{'=' * 60}")
            lines.append(f"{day.name.title()} ({day.value})")
            lines.append("=" * 60)

            tp_map = self.schedule.get(day, {})

            if not tp_map:
                lines.append("  No time periods")
                continue

            ordered_periods = sorted(
                tp_map.items(),
                key=lambda item: (
                    item[0].start,
                    item[0].end,
                    item[0].name,
                ),
            )

            for time_period, shift_map in ordered_periods:
                if not include_empty and not shift_map:
                    continue


                lines.append(
                    f"\n  {time_period.name} "
                    f"({time_period.start:%H:%M}–{time_period.end:%H:%M})"
                )

                if not shift_map:
                    lines.append("    No operational shifts")
                    continue

                ordered_shifts = sorted(
                    shift_map.items(),
                    key=lambda item: item[0].name,
                )

                for shift, volunteers in ordered_shifts:
                    assigned_count = len(volunteers)

                    if assigned_count < shift.min_people:
                        status = "UNDER MINIMUM"
                    elif assigned_count >= shift.max_people:
                        status = "FULL"
                    else:
                        status = "OK"

                    volunteer_names = ", ".join(
                        sorted(volunteer.name for volunteer in volunteers)
                    )

                    if not volunteer_names:
                        volunteer_names = "—"

                    lines.append(
                        f"    • {shift.name} "
                        f"[{shift.work_type.value}]"
                    )
                    lines.append(
                        f"      People: {assigned_count} "
                        f"(min={shift.min_people}, max={shift.max_people}) "
                        f"[{status}]"
                    )
                    lines.append(
                        f"      Volunteers: {volunteer_names}"
                    )

        return "\n".join(lines).lstrip()


    def pretty_print(self, *, include_empty: bool = True) -> None:
        """Print the formatted schedule."""
        print(self.pretty(include_empty=include_empty))


    def __str__(self) -> str:
        return self.pretty()


"""
Considering only required shifts (forget about importance for now):

1. assign all shifts to the minium, first considering preferences, fallback to
getting random volunteers

2. if there are still volunteers without their required num of shifts, 
   assign them to a joker shift

Them managers should handle people in Others manually.
"""
def generate_schedule(all_shifts: List['Shift'], volunteers: List['Volunteer'], time_periods: List['TimePeriod']) -> Schedule:
    print("Assigning days off")
    random.shuffle(volunteers) # for fairness
    vols_with_days_off = assign_days_offs(all_shifts, volunteers)

    joker_shift = Shift(
        name="Other",
        min_people=0,
        max_people=100,
        unoperational_days=(),
        time_period=TimePeriod(
            name="Other",
            start=time(7, 0),
            end=time(21, 0)
        )
    )
    all_shifts.append(joker_shift)

    print("Initiating schedule")
    sched = Schedule(all_shifts, vols_with_days_off, time_periods)


    for day in list(DayOfWeek):
        print(f"Assigning day {day.name}")
        for time_period in time_periods:
            print(f"Assigning time period {time_period.name}")
            shifts = sched.shifts_in_day_tp(day, time_period)
            for shift in shifts:
                print(f"Assigning shift {shift.name}")
                # 1. fill only volunteers with preferences
                all_available = iter(sched.available_vols_tp_day(day, time_period))
                while sched.has_shift_minimum(shift, day):
                    try:
                        vol = next(all_available)
                    except StopIteration:
                        break
                    if shift.work_type in vol.desired_work:
                        sched.assign(vol, day, shift)

                # 2. if not minimum fulfilled, assign any other volunteer available
                while not sched.has_shift_minimum(shift, day):
                    available_vols_others = sched.available_vols_tp_day(day, time_period)
                    if not available_vols_others:
                        raise Exception(f"Failed to fulfill minimum for shift {shift.name} in time period {time_period.name}")
                    vol = random.choice(available_vols_others)
                    sched.assign(vol, day, shift)

                # 3. final validation
                if not sched.has_shift_minimum(shift, day):
                    raise Exception(f"Failed to fulfill minimum for shift {shift.name} in time period {time_period.name}")

        # 3. if there are still volunteers in the day pool, assign them to Other shift
        for vol in sched.available_vols_day(day):
            sched.assign(vol, day, joker_shift)

    return sched


def assign_days_offs(shifts: List[Shift], volunteers: List[Volunteer]) -> List[Volunteer]:
    """
    TODO!!!: volunteers.days_off is now immutable so we had to deal with new vars,
    maybe find another way

    TODO: days off are being concentrated in a few days which is ok for Saturday and Sunday
    but for weekdays, we need to distribute them randomly
    """
    random.shuffle(volunteers)

    # Sunday first
    vols_sun = assign_weekend_day_off(shifts, DayOfWeek.SUNDAY, volunteers)

    # Saturday
    vols_sat = assign_weekend_day_off(shifts, DayOfWeek.SATURDAY, vols_sun)

    # weekdays (todo randomize)
    days: List[DayOfWeek] = [DayOfWeek.MONDAY, DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY, DayOfWeek.THURSDAY, DayOfWeek.FRIDAY]
    random.shuffle(days)
    final_vols = deepcopy(vols_sat)
    for day in days:
        final_vols = assign_weekend_day_off(shifts, day, final_vols)

    for v in final_vols:
        if len(v.days_off) != v.max_days_off:
            raise RuntimeError(f"{v.name} ended with {len(v.days_off)} days off (expected {v.max_days_off})")

    return final_vols

def assign_weekend_day_off(shifts: List[Shift],
                           day: DayOfWeek, volunteers: List[Volunteer]) -> List[Volunteer]:
    off_count = 0
    max_off_day = max(0, max_vols_off(shifts, day, len(volunteers)))
    vols : List[Volunteer] = []

    for vol in volunteers:
        if len(vol.days_off) == vol.max_days_off:
            vols.append(vol)
            continue

        if day.name not in vol.days_off:
            days_off = vol.days_off + (day.value,)
            new_vol = Volunteer(
                name=vol.name,
                days_off=days_off,
                fixed_shift=vol.fixed_shift,
                desired_work=vol.desired_work,
                max_days_off=vol.max_days_off,
                unavailable_periods=vol.unavailable_periods
                    )
            vols.append(new_vol)

        off_count += 1

        if off_count >= max_off_day:
            break

    return vols

def min_needed_level3(shifts: List[Shift], day: DayOfWeek) -> int:
    """min number of volunteers for level3 shifts"""
    n = 0
    for shift in shifts:
        if day.name in shift.unoperational_days:
            continue
    return n

def max_vols_off(shifts: List[Shift], day: DayOfWeek, total_vols: int) -> int:
    """how many volunteers can get day off this day"""
    return total_vols - min_needed_level3(shifts, day)
