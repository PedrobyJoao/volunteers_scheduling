from . import schedule_2
from . import sheets
from . import parser


def main():
  obj = parser.parse("data.yml")
  week_schedule = schedule_2.generate_schedule(obj.shifts, obj.volunteers, obj.time_periods)
  # sheets.write_pretty_schedule_xlsx(week_schedule, obj.time_periods)
  week_schedule.pretty_print()


main()
