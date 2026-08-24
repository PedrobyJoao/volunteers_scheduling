from dataclasses import dataclass, field
from typing import List, Dict
from enum import Enum
import yaml

class DayOfWeek(Enum):
    MONDAY = "Mon"
    TUESDAY = "Tue"
    WEDNESDAY = "Wed"
    THURSDAY = "Thu"
    FRIDAY = "Fri"
    SATURDAY = "Sat"
    SUNDAY = "Sun"

class PhaseOfDay(Enum):
    EARLY_MORNING = 0
    LATE_MORNING = 1
    AFTERNOON = 2
    EVENING = 3

@dataclass
class Shift:
    name: str
    day_phase: PhaseOfDay
    min_people: int
    max_people: int
    importance: int # how important is the shift (1-3, e.g.: lunch is 3)
    unoperational_days: List[str] = field(default_factory=list)

@dataclass
class Volunteer:
    name: str
    days_off: List[str]
    desired_shifts: List[str] = field(default_factory=list)

@dataclass
class DayAssignment:
    shift_to_people: Dict[str, List[str]]

@dataclass
class Schedule:
    days: Dict[DayOfWeek, DayAssignment]

"""
Consider:
- [x] Shift operational days
- [] if no 2 days off are assigned to volunteer, we must assign randomly
    with a preference of assigning everyone to Sunday after assigning all people
    to number 3 importance shifts of Sunday. And then assign volunteers days off
    to random days of the week (all volunteers hsould have 2 days off)
- [] handle error if no volunteers fitted
- [] consider people with fixed shifts ("Misc: Construction, Arts and others..." shift also) that
    will do the same all the work days
- [] verify if all shifts were filled
- [] verify if all volunteers were assigned
"""
def generate_schedule(shifts: List[Shift], volunteers: List[Volunteer]) -> Schedule:
    shifts_by_importance = sorted(shifts, key=lambda s: s.importance, reverse=True)
    schedule = Schedule({day: DayAssignment({}) for day in list(DayOfWeek)})
    # todo: sort volunteers randomly

    # todo: how to handle volunteers assignment of days off?
    # pre-assign volunteers days off when not specified by checking first how many people
    # are needed for level 3 importance shifts on each day, giving preference to assigning people
    # to be off on sunday
    for day in list(DayOfWeek):
        for shift in shifts_by_importance:
            if day.name in shift.unoperational_days:
                continue

            fitted_volunteers =  match_volunteers(shift, volunteers, day) 
            # TODO
    pass


"""
[] Min people needed for the shift
[] return error if no volunteers were filled
"""
def match_volunteers(
    shift: Shift, volunteers: List[Volunteer], 
    day: DayOfWeek) -> List[Volunteer]:
    # TODO
    pass

"""
Requirements:

[] Check volunteers' days off
[] Preferences of shifts

Next versions:

[] Volunteers with fixed shifts
"""
def volunteer_satisfies(volunteer: Volunteer, shift: Shift, day: DayOfWeek) -> Bool:
    # TODO
    pass

def main():
  with open("shifts.yml") as f:
      shifts = [Shift(**s) for s in yaml.safe_load(f)]

  with open("volunteers.yml") as f:
      volunteers = [Volunteer(**v) for v in yaml.safe_load(f)]

  print(shifts)
  print("AND")
  print(volunteers)

main()
