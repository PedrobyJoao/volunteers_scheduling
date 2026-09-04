"""
TODOs:

[x] shift operational on day
[x] volunteer not on day off
[x] volunteer fixed_shift respected (if set, must match shift.name)
[x] only one shift per time period
[x] at most 2 shifts per day for volunteer
[x] shift capacity (max_people)
[] for remaining volunteers without shifts assigned, assign them to shift Others
[] verify if all volunteers were assigned
[] assign days off if not assigned yet
[] ignore preferences when minimum quote is not reached for level 3 shifts
[] Min people needed for the shift
[] return error if no volunteers were filled
[] Check volunteers' days off
[] only one shift per phase of day
[] two shifts per day per volunteer
[] volunteer preferences of days phase
[] Preferences of shifts
[] consider that one of the day phases might be required for everyone
(as now it's considered early morning required)
[] use pydantic
""" 
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Iterable
from pydantic import BaseModel, ConfigDict
from datetime import time
from enum import Enum
from copy import deepcopy
import random

class DayOfWeek(Enum):
    MONDAY = "Mon"
    TUESDAY = "Tue"
    WEDNESDAY = "Wed"
    THURSDAY = "Thu"
    FRIDAY = "Fri"
    SATURDAY = "Sat"
    SUNDAY = "Sun"

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
    work_type: WorkType
    min_people: int
    max_people: int
    importance: int # todo: change from importance to required?
    unoperational_days: tuple[str, ...]

class Volunteer(BaseModel):
    name: str
    days_off: List[str]
    fixed_shift: str = "" # for people only working on the same thing (e.g.: construction, agriculture)
    desired_work: List[WorkType] 
    # todo: how many shifts to be worked (default = 2)
    # todo: how many days off (default = 2)

class AssignmentError(RuntimeError):
    """Raised when an assignment cannot be performed because of business rules."""

@dataclass
class Schedule:
    def __init__(self, shifts: List['Shift'], time_periods: List['TimePeriod']):
            self.schedule : Dict[DayOfWeek, Dict['TimePeriod', Dict['Shift', List['Volunteer']]]] = {}
            for day in DayOfWeek:
                self.schedule[day] = {}
                for tp in time_periods:
                    self.schedule[day][tp] = {}
                for shift in shifts:
                    self._add_shift_for_day(day, shift)

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

    def find_volunteer_assignments(self, volunteer: 'Volunteer') -> Dict[DayOfWeek, List['Shift']]:
        result: Dict[DayOfWeek, List['Shift']] = {}
        for day, tp_map in self.schedule.items():
            assigned = []
            for shifts in tp_map.values():
                for shift, vols in shifts.items():
                    if volunteer in vols:
                        assigned.append(shift)
            if assigned:
                result[day] = assigned
        return result

    # ----------------------
    # Core mutation: assign
    # ----------------------
    def can_assign(self, volunteer: 'Volunteer', day: DayOfWeek, shift: 'Shift') -> Optional[str]:
        """
        Return None if ok, else a short reason string (no mutation).
        Enforces:
          [x] shift operational on day
          [x] volunteer not on day off
          [x] volunteer fixed_shift respected (if set, must match shift.name)
          [x] only one shift per time period
          [x] at most 2 shifts per day for volunteer
          [x] shift capacity (max_people)
        """

        if not self._shift_operational_on_day(shift, day):
            return f"shift {shift.name!r} not operational on {day.name}"
        if day.value in volunteer.days_off:
            return f"volunteer {volunteer.name!r} has {day.name} as day off"
        if volunteer.fixed_shift and volunteer.fixed_shift != shift.name:
                return f"volunteer {volunteer.name!r} fixed to {volunteer.fixed_shift!r}"
        if self._vol_has_time_period(volunteer, day, shift.time_period):
            return f"volunteer {volunteer.name!r} already has a shift in time period {shift.time_period.name!r} on {day.name}"
        if len(self._vol_shifts_of_day(volunteer, day)) >= 2:
            return f"volunteer {volunteer.name!r} already has 2 shifts on {day.name}"

        assigned = self.schedule.get(day, {}).get(shift.time_period, {}).get(shift, [])
        if shift.max_people is not None and len(assigned) >= shift.max_people:
            return f"shift {shift.name!r} on {day.name} at max capacity ({shift.max_people})"
        return None

    def assign(self, volunteer: 'Volunteer', day: DayOfWeek, shift: 'Shift', *, raise_on_error: bool = True) -> bool:
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
        return True

    # ----------------------
    # Validation functions
    # ----------------------
    def validate_minima(self) -> List[str]:
        """
        TODO: we actually want to return error if level 3 importance

        Return list of problems where shift.min_people is not met.
        Each item is a short string describing the problem.
        """
        problems: List[str] = []
        for day, tp_map in self.schedule.items():
            for shift_map in tp_map.values():
                for shift, vols in shift_map.items():
                    # if shift is unoperational this day we skip (shouldn't be present, but safe)
                    if not self._shift_operational_on_day(shift, day):
                        continue
                    if shift.min_people is not None and len(vols) < shift.min_people:
                        problems.append(f"{day.name}: shift {shift.name!r} needs {shift.min_people} but has {len(vols)}")
        return problems

    def unassigned_volunteers(self, all_volunteers: List['Volunteer']) -> List['Volunteer']:
        # TODO: not sure if so useful
        """Return list of volunteers that have zero assignments in the week (ignoring those with days_off covering full week)."""
        result: List['Volunteer'] = []
        for vol in all_volunteers:
            assigns = self.find_volunteer_assignments(vol)
            if not assigns:
                result.append(vol)
        return result

    # ----------------------
    # Utility readers for printing/reporting
    # ----------------------
    def iter_assignments(self) -> Iterable[tuple]:
        """Yield (day, time_period, shift, tuple(volunteers))"""
        for day, tp_map in self.schedule.items():
            for tp, shift_map in tp_map.items():
                for shift, vols in shift_map.items():
                    yield day, tp, shift, tuple(vols)


def generate_schedule(shifts: List['Shift'], volunteers: List['Volunteer'], time_periods: List['TimePeriod']) -> Schedule:
    """
    Build a Schedule and try to satisfy requirements:
      - initialize Day -> TimePeriod -> Shifts (only operational shifts added)
      - assign volunteers with fixed_shift to their shifts across days (except their days_off)
      - fill each shift to at least min_people (prefer volunteers that list the shift in desired_shifts)
      - ensure only one shift per time period and max 2 shifts/day per volunteer
      - after filling minima, try to place volunteers with zero assignments into any shift with capacity
      - validate minima and that volunteers were assigned; raise ValueError with diagnostics if issues found
    """
    sched = Schedule(shifts, time_periods)

    # helper: map shift names to shift objects (first-match)
    shifts_by_name: Dict[str, List['Shift']] = {}
    for s in shifts:
        shifts_by_name.setdefault(s.name, []).append(s)

    # Shuffle volunteers for fairness
    random.shuffle(volunteers)

    errors: List[str] = []

    # 1) Assign fixed_shift volunteers across all their available days
    for vol in volunteers:
        if not vol.fixed_shift:
            continue
        # find candidate shift objects with that name
        candidates = shifts_by_name.get(vol.fixed_shift, [])
        if not candidates:
            errors.append(f"fixed_shift {vol.fixed_shift!r} not found for volunteer {vol.name!r}")
            continue
        # try to assign for every day (except day off and unoperational)
        for day in DayOfWeek:
            if day.value in vol.days_off:
                continue
            # prefer the candidate that's operational this day
            assigned_flag = False
            for s in candidates:
                if sched._shift_operational_on_day(s, day):
                    ok = sched.assign(vol, day, s, raise_on_error=False)
                    if ok:
                        assigned_flag = True
                        break
            if not assigned_flag:
                errors.append(f"could not assign fixed_shift {vol.fixed_shift!r} for {vol.name!r} on {day.name}")

    # 2) Fill shifts to at least min_people (by day -> time_period -> shift)
    # Prefer volunteers that desire the shift; otherwise any volunteer who can be assigned.
    for day in DayOfWeek:
        for tp, shift_map in sched.days[day].items():
            # iterate shifts in a stable order (importance desc, then name)
            ordered_shifts = sorted(shift_map.keys(), key=lambda s: (-getattr(s, "importance", 0), s.name))
            for shift in ordered_shifts:
                assigned = shift_map[shift]
                # skip if already meets min
                while len(assigned) < (shift.min_people or 0):
                    # first pass: volunteers that desire this shift
                    candidate = None
                    # prefer volunteers that requested this shift and are eligible
                    for vol in volunteers:
                        if shift.name not in vol.desired_shifts:
                            continue
                        if sched.can_assign(vol, day, shift) is None:
                            candidate = vol
                            break
                    # second pass: anyone eligible
                    if candidate is None:
                        for vol in volunteers:
                            if sched.can_assign(vol, day, shift) is None:
                                candidate = vol
                                break
                    # if no candidate found we cannot meet min for this shift
                    if candidate is None:
                        break
                    # assign and update local assigned var reference
                    sched.assign(candidate, day, shift, raise_on_error=False)
                    assigned = shift_map[shift]

    # 3) Try to place volunteers with zero assignments into any shift that still has capacity
    unassigned = sched.unassigned_volunteers(volunteers)
    for vol in unassigned:
        for day in DayOfWeek:
            if day.value in vol.days_off:
                continue
            placed = False
            for tp, shift_map in sched.days[day].items():
                # skip if volunteer already has a shift in this time period
                if sched._vol_has_time_period(vol, day, tp):
                    continue
                # try any shift with capacity (prefer desired_shifts)
                # desired first
                for shift in sorted(shift_map.keys(), key=lambda s: (-getattr(s, "importance", 0), s.name)):
                    if shift.name in vol.desired_shifts and sched.can_assign(vol, day, shift) is None:
                        sched.assign(vol, day, shift, raise_on_error=False)
                        placed = True
                        break
                if placed:
                    break
                # then any
                for shift in sorted(shift_map.keys(), key=lambda s: (-getattr(s, "importance", 0), s.name)):
                    if sched.can_assign(vol, day, shift) is None:
                        sched.assign(vol, day, shift, raise_on_error=False)
                        placed = True
                        break
                if placed:
                    break
            if placed:
                break

    # 4) Validation: minima and participant coverage
    minima_problems = sched.validate_minima()
    unassigned_after = sched.unassigned_volunteers(volunteers)

    diag_msgs: List[str] = []
    diag_msgs.extend(minima_problems)
    if unassigned_after:
        diag_msgs.append(f"unassigned volunteers: {[v.name for v in unassigned_after]}")

    if diag_msgs:
        # combine diagnostics into a single ValueError so caller can see why scheduling failed
        raise ValueError("Schedule generation problems:\n" + "\n".join(diag_msgs))

    return sched
