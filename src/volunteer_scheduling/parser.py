"""
YAML parser
"""

import yaml
from . import schedule_2

def parse(path: str) -> schedule_2.ShiftsVolunteersYAML:
    with open(path) as f:
        data = yaml.safe_load(f)

    periods = [
        schedule_2.TimePeriod(**p)
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
            schedule_2.Shift(
                name=s["name"],
                time_period=period_map[tp_name_clean],
                work_type=s.get("work_type", schedule_2.WorkType.others),
                min_people=s["min_people"],
                max_people=s["max_people"],
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
            schedule_2.Volunteer(**volunteer_data)
        )

    return schedule_2.ShiftsVolunteersYAML(
        time_periods=periods,
        shifts=shifts,
        volunteers=volunteers,
    )
