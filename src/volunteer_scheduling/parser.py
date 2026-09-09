"""
YAML parser
"""

import yaml
from . import schedule_2

def parse(path: str) -> schedule_2.ShiftsVolunteersYAML:
    with open(path) as f:
        data = yaml.safe_load(f)

    periods = [schedule_2.TimePeriod(**p) for p in data.get('time_periods', [])]
    period_map = {p.name.strip().lower(): p for p in periods}

    shifts = []
    for s in data.get('shifts', []):
        tp_name = s['time_period']
        tp_name_clean = tp_name.strip().lower()
        if tp_name_clean not in period_map:
            raise ValueError(f"Unknown time_period: {tp_name}")
        shifts.append(schedule_2.Shift(
            name=s['name'],
            time_period=period_map[tp_name_clean],
            min_people=s['min_people'],
            max_people=s['max_people'],
            unoperational_days=s.get('unoperational_days', ())
        ))

    volunteers = [schedule_2.Volunteer(**v) for v in data.get('volunteers', [])]

    return schedule_2.ShiftsVolunteersYAML(time_periods=periods, shifts=shifts, volunteers=volunteers)
