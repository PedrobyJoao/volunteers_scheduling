import yaml
from . import schedule
from . import sheets


def main():
  with open("shifts.yml") as f:
      shifts = [schedule.Shift(**s) for s in yaml.safe_load(f)]

  with open("volunteers.yml") as f:
      volunteers = [schedule.Volunteer(**v) for v in yaml.safe_load(f)]

  week_schedule = schedule.generate_schedule(shifts, volunteers)
  sheets.write_pretty_schedule_xlsx(week_schedule)

main()
