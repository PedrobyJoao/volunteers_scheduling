"""
YAML parser
"""

import yaml
from . import schedule

def parse(path: str) -> schedule.ShiftsVolunteersYAML:
    with open(path) as f:
        data = yaml.safe_load(f)

    periods = [
        schedule.TimePeriod(**p)
        for p in data.get("time_periods", [])
    ]

    period_map = {
        period.name.strip().lower(): period
        for period in periods
    }

    shifts = []

    for s in data.get("shifts", []):
        tp_name = s["time_period"]
        tp_name_clean = tp_name.strip().lower()

        if tp_name_clean not in period_map:
            raise ValueError(f"Unknown time_period: {tp_name}")

        shifts.append(
            schedule.Shift(
                name=s["name"],
                time_period=period_map[tp_name_clean],
                work_type=s.get("work_type", schedule.WorkType.others),
                min_people=s.get("min_people", 1),
                max_people=s.get("max_people", 5),
                unoperational_days=s.get("unoperational_days", ()),

            )
        )

    volunteers = []

    for v in data.get("volunteers", []):
        volunteer_data = dict(v)
        unavailable_periods = []

        for tp_name in volunteer_data.get("unavailable_periods", []):
            tp_name_clean = tp_name.strip().lower()

            if tp_name_clean not in period_map:
                raise ValueError(
                    f"Unknown unavailable time period {tp_name!r} "
                    f"for volunteer {volunteer_data.get('name')!r}"
                )

            unavailable_periods.append(period_map[tp_name_clean])

        volunteer_data["unavailable_periods"] = tuple(unavailable_periods)

        volunteers.append(
            schedule.Volunteer(**volunteer_data)
        )

    return schedule.ShiftsVolunteersYAML(
        time_periods=periods,
        shifts=shifts,
        volunteers=volunteers,
    )
