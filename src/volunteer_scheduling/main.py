from . import schedule
from . import sheets
from . import parser


def main():
  obj = parser.parse("data.yml")
  week_schedule = schedule.generate_schedule(obj.shifts, obj.volunteers)
  sheets.write_pretty_schedule_xlsx(week_schedule, obj.time_periods)
  print(schedule.pretty_schedule(week_schedule))


main()
