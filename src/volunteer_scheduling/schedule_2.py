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
[] CP-SAT:
    [x] very good constraint satisfaction of everything literally
    [x] days off equally spread throughout weekdays and saturday
""" 
from __future__ import annotations

from ortools.sat.python import cp_model
from dataclasses import dataclass
from typing import Dict, List, Optional, Iterable, Any, Iterable
from pydantic import BaseModel, ConfigDict
from datetime import time
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
# todo: accept input with different letter cases
class WorkType(Enum):
    kitchen = "Kitchen"
    housekeeping = "Housekeeping"
    others = "Others"

class TimePeriod(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    start: time
    end: time
    required: bool = False

class Shift(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    time_period: TimePeriod
    work_type: WorkType = WorkType.others
    min_people: int
    max_people: int = 5
    unoperational_days: tuple[DayOfWeek, ...]

class Volunteer(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    days_off: tuple[DayOfWeek, ...] = ()
    fixed_shift: str = "" # for people only working on the same thing (e.g.: construction, agriculture)
    desired_work: tuple[WorkType, ...] = ()
    unavailable_periods: tuple[TimePeriod, ...] = ()
    max_days_off: int = 2
    max_number_of_shifts: int = 2

class ScheduleGrid(BaseModel): 
    s: Dict[DayOfWeek, Dict['TimePeriod', Dict['Shift', List['Volunteer']]]] = {}

class ShiftsVolunteersYAML(BaseModel):
    time_periods: List[TimePeriod]
    shifts: List[Shift]
    volunteers: List[Volunteer]

class AssignmentError(RuntimeError):
    """Raised when an assignment cannot be performed because of business rules."""

@dataclass
class Schedule:
    def __init__(self, shifts: List['Shift'], vols: List['Volunteer'], time_periods: List['TimePeriod']):
            self.vols_shifts: Dict[Volunteer, Dict[DayOfWeek, Dict[TimePeriod, Shift]]] = {}
            self.schedule: ScheduleGrid = ScheduleGrid(s={})
            for day in DayOfWeek:
                self.schedule.s[day] = {}
                for tp in time_periods:
                    self.schedule.s[day][tp] = {}
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
        if tp not in self.schedule.s[day]:
            self.schedule.s[day][tp] = {}

        if shift not in self.schedule.s[day][tp]:
            self.schedule.s[day][tp][shift] = []

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
        for tp_map in (self.schedule.s.get(day) or {}).values():
            for shift, vols in tp_map.items():
                if volunteer in vols:
                    result.append(shift)
        return result

    def _vol_has_time_period(self, volunteer: 'Volunteer', day: DayOfWeek, tp: 'TimePeriod') -> bool:
        tp_map = self.schedule.s.get(day, {}).get(tp, {})
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
        random.shuffle(vols)
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
        random.shuffle(vols)
        return deepcopy(vols)

    def shifts_in_day_tp(self, day: DayOfWeek, tp: TimePeriod) -> List[Shift]:
        return deepcopy([shift for shift in self.schedule.s.get(day, {}).get(tp, {}).keys()])

    def _vols_in_shift(self, shift: Shift, day: DayOfWeek) -> List[Volunteer]:
        return self.schedule.s.get(day, {}).get(shift.time_period, {}).get(shift, [])

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

        assigned = self.schedule.s.get(day, {}).get(shift.time_period, {}).get(shift, [])
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
        if shift.time_period not in self.schedule.s[day]:
            self.schedule.s[day][shift.time_period] = {}
        if shift not in self.schedule.s[day][shift.time_period]:
            self.schedule.s[day][shift.time_period][shift] = []
        # idempotent
        if volunteer in self.schedule.s[day][shift.time_period][shift]:
            return True
        self.schedule.s[day][shift.time_period][shift].append(volunteer)
        self.vols_shifts[volunteer][day][shift.time_period] = shift
        return True

    # ----------------------
    # Utility readers for printing/reporting
    # ----------------------
    def iter_assignments(self) -> Iterable[tuple]:
        """Yield (day, time_period, shift, tuple(volunteers))"""
        for day, tp_map in self.schedule.s.items():
            for tp, shift_map in tp_map.items():
                for shift, vols in shift_map.items():
                    yield day, tp, shift, tuple(vols)

    def snapshot(self) -> ScheduleGrid:
        return deepcopy(self.schedule)

    def volunteers(self) -> List[Volunteer]:
        return deepcopy(list(self.vols_shifts.keys()))

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

            tp_map = self.schedule.s.get(day, {})

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

    def pretty_days_off(self):
        for vol in self.vols_shifts:
            print(vol.name, list(map(lambda day: day.name, vol.days_off)))


class ScheduleGenerationError(RuntimeError):
    """Raised when no feasible schedule can satisfy all hard constraints."""


@dataclass(frozen=True)
class SolverConfiguration:
    """
    CP-SAT settings.

    A value of None for max_time_seconds means no explicit time limit.
    For the current schedule size, solving should normally be quick.
    """

    max_time_seconds: Optional[float] = 60.0
    num_search_workers: int = 8
    log_search_progress: bool = False


def _is_shift_operational(shift: Shift, day: DayOfWeek) -> bool:
    """
    Return whether a real shift operates on the given day.

    Pydantic should normally convert YAML values into DayOfWeek members,
    but the string fallback makes this tolerant of already-created objects.
    """

    for unoperational_day in shift.unoperational_days:
        if isinstance(unoperational_day, DayOfWeek):
            if unoperational_day == day:
                return False
            continue

        normalized = str(unoperational_day).strip().lower()

        if normalized in {
            day.name.lower(),
            day.value.lower(),
        }:
            return False

    return True


def _validate_solver_input(
    shifts: list[Shift],
    volunteers: list[Volunteer],
    time_periods: list[TimePeriod],
) -> None:
    if not volunteers:
        raise ScheduleGenerationError(
            "Cannot generate a schedule without volunteers."
        )

    if not time_periods:
        raise ScheduleGenerationError(
            "Cannot generate a schedule without time periods."
        )

    volunteer_names: set[str] = set()

    for volunteer in volunteers:
        if volunteer.name in volunteer_names:
            raise ScheduleGenerationError(
                f"Duplicate volunteer name: {volunteer.name!r}"
            )

        volunteer_names.add(volunteer.name)

        requested_days_off = set(volunteer.days_off)

        if len(requested_days_off) != len(volunteer.days_off):
            raise ScheduleGenerationError(
                f"{volunteer.name!r} has duplicate requested days off."
            )

        if len(requested_days_off) > volunteer.max_days_off:
            raise ScheduleGenerationError(
                f"{volunteer.name!r} requested "
                f"{len(requested_days_off)} days off, but "
                f"max_days_off is {volunteer.max_days_off}."
            )

        if volunteer.max_days_off < 0:
            raise ScheduleGenerationError(
                f"{volunteer.name!r} has a negative max_days_off."
            )

        if volunteer.max_days_off > len(DayOfWeek):
            raise ScheduleGenerationError(
                f"{volunteer.name!r} requests "
                f"{volunteer.max_days_off} days off, but a week has "
                f"{len(DayOfWeek)} days."
            )

        if volunteer.max_number_of_shifts < 0:
            raise ScheduleGenerationError(
                f"{volunteer.name!r} has a negative "
                f"max_number_of_shifts."
            )

    time_period_names: set[str] = set()

    for time_period in time_periods:
        if time_period.name in time_period_names:
            raise ScheduleGenerationError(
                f"Duplicate time-period name: {time_period.name!r}"
            )

        time_period_names.add(time_period.name)

    shift_names: set[str] = set()

    for shift in shifts:
        if shift.name in shift_names:
            raise ScheduleGenerationError(
                f"Duplicate shift name: {shift.name!r}"
            )

        shift_names.add(shift.name)

        if shift.min_people < 0:
            raise ScheduleGenerationError(
                f"Shift {shift.name!r} has negative min_people."
            )

        if shift.time_period not in time_periods:
            raise ScheduleGenerationError(
                f"Shift {shift.name!r} references time period "
                f"{shift.time_period.name!r}, which is not present in "
                f"the top-level time_periods list."
            )

    for volunteer in volunteers:
        for unavailable_period in volunteer.unavailable_periods:
            if unavailable_period not in time_periods:
                raise ScheduleGenerationError(
                    f"Volunteer {volunteer.name!r} references unavailable "
                    f"time period {unavailable_period.name!r}, which is not "
                    f"present in the top-level time_periods list."
                )


def _new_solver(
    configuration: SolverConfiguration,
) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()

    solver.parameters.num_search_workers = (
        configuration.num_search_workers
    )
    solver.parameters.log_search_progress = (
        configuration.log_search_progress
    )

    if configuration.max_time_seconds is not None:
        solver.parameters.max_time_in_seconds = (
            configuration.max_time_seconds
        )

    return solver


def _status_name(status: Any) -> str:
    if status == cp_model.UNKNOWN:
        return "UNKNOWN"

    if status == cp_model.MODEL_INVALID:
        return "MODEL_INVALID"

    if status == cp_model.FEASIBLE:
        return "FEASIBLE"

    if status == cp_model.INFEASIBLE:
        return "INFEASIBLE"

    if status == cp_model.OPTIMAL:
        return "OPTIMAL"

    return getattr(status, "name", str(status))

def _solve_optimization_stage(
    *,
    model: cp_model.CpModel,
    expression: Any,
    maximize: bool,
    stage_name: str,
    configuration: SolverConfiguration,
    require_optimal: bool = False,
) -> tuple[cp_model.CpSolver, int]:
    """
    Optimize one objective and return its best value.

    The caller adds an equality fixing that value before moving to the
    next objective. This gives lexicographic optimization.
    """

    if maximize:
        model.maximize(expression)
    else:
        model.minimize(expression)

    solver = _new_solver(configuration)
    status = solver.solve(model)

    if status == cp_model.INFEASIBLE:
        raise ScheduleGenerationError(
            f"Schedule is infeasible while optimizing: {stage_name}."
        )

    if status == cp_model.MODEL_INVALID:
        raise ScheduleGenerationError(
            f"CP-SAT reported an invalid model while optimizing: "
            f"{stage_name}."
        )

    if status == cp_model.UNKNOWN:
        raise ScheduleGenerationError(
            f"CP-SAT could not find a schedule while optimizing "
            f"{stage_name}. Consider increasing max_time_seconds."
        )

    if require_optimal and status != cp_model.OPTIMAL:
        raise ScheduleGenerationError(
            f"CP-SAT found a feasible schedule but could not prove the "
            f"optimal value for {stage_name}. Solver status: "
            f"{_status_name(status)}. Increase max_time_seconds or set it "
            f"to None."
        )

    value = int(solver.value(expression))

    return solver, value


def _create_required_joker_shifts(
    *,
    volunteers: list[Volunteer],
    time_periods: list[TimePeriod],
) -> dict[int, Shift]:
    """
    Create one joker shift for each required time period.

    Dictionary keys are time-period indexes.
    """

    required_jokers: dict[int, Shift] = {}

    for time_period_index, time_period in enumerate(time_periods):
        if not time_period.required:
            continue

        required_jokers[time_period_index] = Shift(
            name=f"Others — {time_period.name}",
            time_period=time_period,
            work_type=WorkType.others,
            min_people=0,
            max_people=max(1, len(volunteers)),
            unoperational_days=(),
        )

    return required_jokers


def _create_general_joker_shifts(
    *,
    volunteers: list[Volunteer],
) -> list[Shift]:
    """
    Create enough generic assignment slots to satisfy the largest daily
    assignment requirement.

    Each joker uses a distinct synthetic time period. This allows one
    volunteer to have multiple unresolved assignments without violating
    the one-assignment-per-time-period rule inside Schedule.assign().

    These are explicitly unresolved assignments. Managers must later
    choose their actual times without creating conflicts.
    """

    maximum_daily_shifts = max(
        volunteer.max_number_of_shifts
        for volunteer in volunteers
    )

    joker_shifts: list[Shift] = []

    for slot_index in range(maximum_daily_shifts):
        slot_number = slot_index + 1

        synthetic_period = TimePeriod(
            name=f"Unassigned joker slot {slot_number}",
            start=time(0, 0),
            end=time(0, 0),
            required=False,
        )

        joker_shifts.append(
            Shift(
                name=f"Others — unassigned slot {slot_number}",
                time_period=synthetic_period,
                work_type=WorkType.others,
                min_people=0,
                max_people=max(1, len(volunteers)),
                unoperational_days=(),
            )
        )

    return joker_shifts


def generate_schedule(
    all_shifts: list[Shift],
    volunteers: list[Volunteer],
    time_periods: list[TimePeriod],
    *,
    solver_configuration: Optional[SolverConfiguration] = None,
) -> Schedule:
    """
    Generate a weekly volunteer schedule using CP-SAT.

    Hard constraints:
      - User-requested days off are mandatory.
      - Every volunteer gets exactly max_days_off.
      - Working volunteers receive exactly max_number_of_shifts each day.
      - A volunteer receives at most one shift in each time period.
      - Unavailable time periods are respected.
      - Every operational real shift receives exactly min_people.
      - Every applicable required period receives exactly one assignment
        per working and available volunteer.
      - Required-period surplus goes to that period's joker shift.
      - Required periods are ignored on days with no operational real
        shift in that period.
      - max_people is intentionally not enforced.

    Lexicographic objectives:
      1. Maximize Sunday days off.
      2. Balance Monday-Friday days off.
      3. Minimize Saturday days off.
      4. Maximize preferred real-shift assignments.
      5. Minimize general unresolved joker assignments.
    """

    configuration = (
        solver_configuration or SolverConfiguration()
    )

    real_shifts = list(all_shifts)
    volunteers = list(volunteers)
    time_periods = list(time_periods)
    days = list(DayOfWeek)

    _validate_solver_input(
        shifts=real_shifts,
        volunteers=volunteers,
        time_periods=time_periods,
    )

    required_joker_shifts = _create_required_joker_shifts(
        volunteers=volunteers,
        time_periods=time_periods,
    )

    general_joker_shifts = _create_general_joker_shifts(
        volunteers=volunteers,
    )

    model = cp_model.CpModel()

    volunteer_indexes = range(len(volunteers))
    day_indexes = range(len(days))
    shift_indexes = range(len(real_shifts))
    period_indexes = range(len(time_periods))
    general_joker_indexes = range(len(general_joker_shifts))

    day_index_by_day = {
        day: day_index
        for day_index, day in enumerate(days)
    }

    period_index_by_period = {
        time_period: period_index
        for period_index, time_period in enumerate(time_periods)
    }

    shift_indexes_by_period: dict[int, list[int]] = {
        period_index: []
        for period_index in period_indexes
    }

    for shift_index, shift in enumerate(real_shifts):
        period_index = period_index_by_period[shift.time_period]
        shift_indexes_by_period[period_index].append(shift_index)

    # ------------------------------------------------------------
    # Decision variables
    # ------------------------------------------------------------

    # off[v, d] = 1 when volunteer v has day d off.
    off: dict[tuple[int, int], Any] = {}

    # assignment[v, d, s] = 1 when volunteer v works real shift s.
    assignment: dict[tuple[int, int, int], Any] = {}

    # required_joker[v, d, p] = 1 when volunteer v gets the joker
    # assignment for required period p.
    required_joker: dict[tuple[int, int, int], Any] = {}

    # general_joker[v, d, j] = 1 when volunteer v gets unresolved
    # general joker slot j.
    general_joker: dict[tuple[int, int, int], Any] = {}

    for volunteer_index in volunteer_indexes:
        for day_index in day_indexes:
            off[volunteer_index, day_index] = model.new_bool_var(
                f"off_v{volunteer_index}_d{day_index}"
            )

            for shift_index in shift_indexes:
                assignment[
                    volunteer_index,
                    day_index,
                    shift_index,
                ] = model.new_bool_var(
                    f"assign_v{volunteer_index}_"
                    f"d{day_index}_s{shift_index}"
                )

            for period_index in required_joker_shifts:
                required_joker[
                    volunteer_index,
                    day_index,
                    period_index,
                ] = model.new_bool_var(
                    f"required_joker_v{volunteer_index}_"
                    f"d{day_index}_p{period_index}"
                )

            for joker_index in general_joker_indexes:
                general_joker[
                    volunteer_index,
                    day_index,
                    joker_index,
                ] = model.new_bool_var(
                    f"general_joker_v{volunteer_index}_"
                    f"d{day_index}_j{joker_index}"
                )

    # ------------------------------------------------------------
    # Exact days off and mandatory requested days
    # ------------------------------------------------------------

    for volunteer_index, volunteer in enumerate(volunteers):
        model.add(
            sum(
                off[volunteer_index, day_index]
                for day_index in day_indexes
            )
            == volunteer.max_days_off
        )

        for requested_day_off in volunteer.days_off:
            requested_day_index = day_index_by_day[requested_day_off]

            model.add(
                off[
                    volunteer_index,
                    requested_day_index,
                ]
                == 1
            )

    # ------------------------------------------------------------
    # Operational shifts and volunteer availability
    # ------------------------------------------------------------

    for volunteer_index, volunteer in enumerate(volunteers):
        unavailable_periods = set(
            volunteer.unavailable_periods
        )

        for day_index, day in enumerate(days):
            for shift_index, shift in enumerate(real_shifts):
                variable = assignment[
                    volunteer_index,
                    day_index,
                    shift_index,
                ]

                if not _is_shift_operational(shift, day):
                    model.add(variable == 0)
                    continue

                if shift.time_period in unavailable_periods:
                    model.add(variable == 0)
                    continue

                # An off volunteer cannot work.
                model.add(
                    variable
                    <= 1 - off[volunteer_index, day_index]
                )

    # ------------------------------------------------------------
    # Every operational real shift receives exactly min_people
    # ------------------------------------------------------------

    for day_index, day in enumerate(days):
        for shift_index, shift in enumerate(real_shifts):
            shift_variables = [
                assignment[
                    volunteer_index,
                    day_index,
                    shift_index,
                ]
                for volunteer_index in volunteer_indexes
            ]

            if _is_shift_operational(shift, day):
                model.add(
                    sum(shift_variables) == shift.min_people
                )
            else:
                model.add(sum(shift_variables) == 0)

    # ------------------------------------------------------------
    # One assignment per configured time period
    # ------------------------------------------------------------

    for volunteer_index in volunteer_indexes:
        for day_index in day_indexes:
            for period_index in period_indexes:
                same_period_assignments = [
                    assignment[
                        volunteer_index,
                        day_index,
                        shift_index,
                    ]
                    for shift_index in (
                        shift_indexes_by_period[period_index]
                    )
                ]

                if period_index in required_joker_shifts:
                    same_period_assignments.append(
                        required_joker[
                            volunteer_index,
                            day_index,
                            period_index,
                        ]
                    )

                if same_period_assignments:
                    model.add(
                        sum(same_period_assignments) <= 1
                    )

    # ------------------------------------------------------------
    # Required time periods
    # ------------------------------------------------------------

    for period_index, required_period in enumerate(time_periods):
        if not required_period.required:
            continue

        period_shift_indexes = (
            shift_indexes_by_period[period_index]
        )

        for day_index, day in enumerate(days):
            operational_period_shift_indexes = [
                shift_index
                for shift_index in period_shift_indexes
                if _is_shift_operational(
                    real_shifts[shift_index],
                    day,
                )
            ]

            period_operates_on_day = bool(
                operational_period_shift_indexes
            )

            for volunteer_index, volunteer in enumerate(volunteers):
                joker_variable = required_joker[
                    volunteer_index,
                    day_index,
                    period_index,
                ]

                if not period_operates_on_day:
                    # Example: Late Morning on Sunday when Lunch is closed.
                    model.add(joker_variable == 0)
                    continue

                if required_period in volunteer.unavailable_periods:
                    # This volunteer is exempt from the required period.
                    model.add(joker_variable == 0)
                    continue

                real_period_assignments = [
                    assignment[
                        volunteer_index,
                        day_index,
                        shift_index,
                    ]
                    for shift_index in (
                        operational_period_shift_indexes
                    )
                ]

                # If working, exactly one real or joker assignment in
                # the required period. If off, zero.
                model.add(
                    sum(real_period_assignments)
                    + joker_variable
                    == 1 - off[volunteer_index, day_index]
                )

    # ------------------------------------------------------------
    # Exact daily number of shifts
    # ------------------------------------------------------------

    for volunteer_index, volunteer in enumerate(volunteers):
        for day_index in day_indexes:
            daily_assignments = [
                assignment[
                    volunteer_index,
                    day_index,
                    shift_index,
                ]
                for shift_index in shift_indexes
            ]

            daily_assignments.extend(
                required_joker[
                    volunteer_index,
                    day_index,
                    period_index,
                ]
                for period_index in required_joker_shifts
            )

            daily_assignments.extend(
                general_joker[
                    volunteer_index,
                    day_index,
                    joker_index,
                ]
                for joker_index in general_joker_indexes
            )

            model.add(
                sum(daily_assignments)
                == volunteer.max_number_of_shifts
                * (1 - off[volunteer_index, day_index])
            )

            # Explicitly prevent joker assignments on days off.
            for joker_index in general_joker_indexes:
                model.add(
                    general_joker[
                        volunteer_index,
                        day_index,
                        joker_index,
                    ]
                    <= 1 - off[volunteer_index, day_index]
                )

            for period_index in required_joker_shifts:
                model.add(
                    required_joker[
                        volunteer_index,
                        day_index,
                        period_index,
                    ]
                    <= 1 - off[volunteer_index, day_index]
                )

    # ------------------------------------------------------------
    # Lexicographic objective 1: maximize Sunday days off
    # ------------------------------------------------------------

    sunday_index = day_index_by_day[DayOfWeek.SUNDAY]

    sunday_off_expression = sum(
        off[volunteer_index, sunday_index]
        for volunteer_index in volunteer_indexes
    )

    solver, best_sunday_off = _solve_optimization_stage(
        model=model,
        expression=sunday_off_expression,
        maximize=True,
        stage_name="maximizing Sunday days off",
        configuration=configuration,
    )

    model.add(
        sunday_off_expression == best_sunday_off
    )

    # ------------------------------------------------------------
    # Lexicographic objective 2: balance weekday days off
    # ------------------------------------------------------------

    weekday_days = [
        DayOfWeek.MONDAY,
        DayOfWeek.TUESDAY,
        DayOfWeek.WEDNESDAY,
        DayOfWeek.THURSDAY,
        DayOfWeek.FRIDAY,
    ]

    weekday_off_counts: list[Any] = []

    for weekday in weekday_days:
        day_index = day_index_by_day[weekday]

        count_variable = model.new_int_var(
            0,
            len(volunteers),
            f"off_count_{weekday.name.lower()}",
        )

        model.add(
            count_variable
            == sum(
                off[volunteer_index, day_index]
                for volunteer_index in volunteer_indexes
            )
        )

        weekday_off_counts.append(count_variable)

    maximum_weekday_off = model.new_int_var(
        0,
        len(volunteers),
        "maximum_weekday_off",
    )

    minimum_weekday_off = model.new_int_var(
        0,
        len(volunteers),
        "minimum_weekday_off",
    )

    model.add_max_equality(
        maximum_weekday_off,
        weekday_off_counts,
    )

    model.add_min_equality(
        minimum_weekday_off,
        weekday_off_counts,
    )

    weekday_imbalance = model.new_int_var(
        0,
        len(volunteers),
        "weekday_off_imbalance",
    )

    model.add(
        weekday_imbalance
        == maximum_weekday_off - minimum_weekday_off
    )

    solver, best_weekday_imbalance = _solve_optimization_stage(
        model=model,
        expression=weekday_imbalance,
        maximize=False,
        stage_name="balancing Monday-Friday days off",
        configuration=configuration,
    )

    model.add(
        weekday_imbalance == best_weekday_imbalance
    )

    # ------------------------------------------------------------
    # Lexicographic objective 3: minimize Saturday days off
    # ------------------------------------------------------------

    saturday_index = day_index_by_day[DayOfWeek.SATURDAY]

    saturday_off_expression = sum(
        off[volunteer_index, saturday_index]
        for volunteer_index in volunteer_indexes
    )

    solver, best_saturday_off = _solve_optimization_stage(
        model=model,
        expression=saturday_off_expression,
        maximize=False,
        stage_name="minimizing Saturday days off",
        configuration=configuration,
    )

    model.add(
        saturday_off_expression == best_saturday_off
    )

    # ------------------------------------------------------------
    # Lexicographic objective 4: maximize preferences
    # ------------------------------------------------------------

    preferred_assignment_variables: list[Any] = []

    for volunteer_index, volunteer in enumerate(volunteers):
        desired_work = set(volunteer.desired_work)

        if not desired_work:
            continue

        for day_index in day_indexes:
            for shift_index, shift in enumerate(real_shifts):
                if shift.work_type in desired_work:
                    preferred_assignment_variables.append(
                        assignment[
                            volunteer_index,
                            day_index,
                            shift_index,
                        ]
                    )

    if preferred_assignment_variables:
        preference_expression = sum(
            preferred_assignment_variables
        )

        solver, best_preference_score = (
            _solve_optimization_stage(
                model=model,
                expression=preference_expression,
                maximize=True,
                stage_name="maximizing volunteer preferences",
                configuration=configuration,
            )
        )

        model.add(
            preference_expression == best_preference_score
        )

    # ------------------------------------------------------------
    # Lexicographic objective 5: minimize general jokers
    # ------------------------------------------------------------

    general_joker_variables = list(
        general_joker.values()
    )

    if general_joker_variables:
        general_joker_expression = sum(
            general_joker_variables
        )

        solver, best_general_joker_count = (
            _solve_optimization_stage(
                model=model,
                expression=general_joker_expression,
                maximize=False,
                stage_name="minimizing unresolved joker assignments",
                configuration=configuration,
            )
        )

        model.add(
            general_joker_expression
            == best_general_joker_count
        )

    # Final solve with every selected objective value fixed.
    model.minimize(0)

    solver = _new_solver(configuration)
    final_status = solver.solve(model)

    if final_status not in {
        cp_model.FEASIBLE,
        cp_model.OPTIMAL,
    }:
        raise ScheduleGenerationError(
            "The final constrained model could not be solved. "
            f"Solver status: {_status_name(final_status)}."
        )

    # ------------------------------------------------------------
    # Convert solver days off into new immutable Volunteer objects
    # ------------------------------------------------------------

    solved_volunteers: list[Volunteer] = []

    for volunteer_index, volunteer in enumerate(volunteers):
        solved_days_off = tuple(
            day
            for day_index, day in enumerate(days)
            if solver.value(
                off[volunteer_index, day_index]
            )
            == 1
        )

        solved_volunteer = volunteer.model_copy(
            update={
                "days_off": solved_days_off,
            }
        )

        solved_volunteers.append(solved_volunteer)

    # ------------------------------------------------------------
    # Build the existing Schedule result
    # ------------------------------------------------------------

    generated_shifts = (
        real_shifts
        + list(required_joker_shifts.values())
        + general_joker_shifts
    )

    schedule = Schedule(
        shifts=generated_shifts,
        vols=solved_volunteers,
        time_periods=time_periods,
    )

    # Real shifts.
    for volunteer_index, volunteer in enumerate(solved_volunteers):
        for day_index, day in enumerate(days):
            for shift_index, shift in enumerate(real_shifts):
                if solver.value(
                    assignment[
                        volunteer_index,
                        day_index,
                        shift_index,
                    ]
                ) != 1:
                    continue

                schedule.assign(
                    volunteer,
                    day,
                    shift,
                    raise_on_error=True,
                )

    # Required-period jokers.
    for volunteer_index, volunteer in enumerate(solved_volunteers):
        for day_index, day in enumerate(days):
            for period_index, joker_shift in (
                required_joker_shifts.items()
            ):
                if solver.value(
                    required_joker[
                        volunteer_index,
                        day_index,
                        period_index,
                    ]
                ) != 1:
                    continue

                schedule.assign(
                    volunteer,
                    day,
                    joker_shift,
                    raise_on_error=True,
                )

    # General unresolved jokers.
    for volunteer_index, volunteer in enumerate(solved_volunteers):
        for day_index, day in enumerate(days):
            for joker_index, joker_shift in enumerate(
                general_joker_shifts
            ):
                if solver.value(
                    general_joker[
                        volunteer_index,
                        day_index,
                        joker_index,
                    ]
                ) != 1:
                    continue

                schedule.assign(
                    volunteer,
                    day,
                    joker_shift,
                    raise_on_error=True,
                )

    _validate_generated_schedule(
        schedule=schedule,
        volunteers=solved_volunteers,
        real_shifts=real_shifts,
        time_periods=time_periods,
        required_joker_shifts=required_joker_shifts,
    )

    return schedule

def _validate_generated_schedule(
    *,
    schedule: Schedule,
    volunteers: list[Volunteer],
    real_shifts: list[Shift],
    time_periods: list[TimePeriod],
    required_joker_shifts: dict[int, Shift],
) -> None:
    """
    Validate the generated Schedule object after converting the CP-SAT
    result.

    This verifies the important business constraints without relying
    solely on the solver model.

    Validate:

    Volunteer-wise:
    [x] days off
    [x] verify if all volunteers were assigned to their required num of shifts
    [x] only one shift per time period
    [x] volunteer available time periods
    [x] Min people needed for the shift
    [x] required time period
    """

    days = list(DayOfWeek)

    for volunteer in volunteers:
        # 1. check days off
        if len(volunteer.days_off) != volunteer.max_days_off:
            raise ScheduleGenerationError(
                f"{volunteer.name!r} ended with "
                f"{len(volunteer.days_off)} days off; expected "
                f"{volunteer.max_days_off}."
            )

        for day in days:
            assigned_shifts = schedule._vol_shifts_of_day(
                volunteer,
                day,
            )

            if day in volunteer.days_off:
                if assigned_shifts:
                    raise ScheduleGenerationError(
                        f"{volunteer.name!r} has assignments on "
                        f"their day off, {day.value}."
                    )

                continue

            # 2. validate max number of shifts is met for day
            if (
                len(assigned_shifts)
                != volunteer.max_number_of_shifts
            ):
                raise ScheduleGenerationError(
                    f"{volunteer.name!r} has "
                    f"{len(assigned_shifts)} assignments on "
                    f"{day.value}; expected exactly "
                    f"{volunteer.max_number_of_shifts}."
                )

            # 3. no more than 1 shift per time period
            assigned_periods = [
                shift.time_period
                for shift in assigned_shifts
            ]

            if len(assigned_periods) != len(
                set(assigned_periods)
            ):
                raise ScheduleGenerationError(
                    f"{volunteer.name!r} has multiple assignments "
                    f"in the same time period on {day.value}."
                )

            # 4. volunteer availability for time periods
            for assigned_period in assigned_periods:
                if assigned_period in volunteer.unavailable_periods:
                    raise ScheduleGenerationError(
                        f"{volunteer.name!r} is unavailable in "
                        f"{assigned_period.name!r} on {day.value}."
                    )

    for day in days:
        for shift in real_shifts:
            # 5. min people for shift
            assigned_count = len(
                schedule._vols_in_shift(shift, day)
            )

            expected_count = (
                shift.min_people
                if _is_shift_operational(shift, day)
                else 0
            )

            if assigned_count != expected_count:
                raise ScheduleGenerationError(
                    f"Shift {shift.name!r} has {assigned_count} "
                    f"volunteers on {day.value}; expected "
                    f"{expected_count}."
                )

    for period_index, period in enumerate(time_periods):
        if not period.required:
            continue

        real_period_shifts = [
            shift
            for shift in real_shifts
            if shift.time_period == period
        ]

        joker_shift = required_joker_shifts[period_index]

        for day in days:
            operational_period_shifts = [
                shift
                for shift in real_period_shifts
                if _is_shift_operational(shift, day)
            ]

            if not operational_period_shifts:
                continue

            for volunteer in volunteers:
                if day in volunteer.days_off:
                    continue

                if period in volunteer.unavailable_periods:
                    continue

                required_period_count = sum(
                    1
                    for shift in schedule._vol_shifts_of_day(
                        volunteer,
                        day,
                    )
                    if (
                        shift.time_period == period
                        and (
                            shift in operational_period_shifts
                            or shift == joker_shift
                        )
                    )
                )

                if required_period_count != 1:
                    raise ScheduleGenerationError(
                        f"{volunteer.name!r} has "
                        f"{required_period_count} assignments in "
                        f"required period {period.name!r} on "
                        f"{day.value}; expected exactly one."
                    )
