import yaml
from . import schedule


def main():
  with open("shifts.yml") as f:
      shifts = [schedule.Shift(**s) for s in yaml.safe_load(f)]

  with open("volunteers.yml") as f:
      volunteers = [schedule.Volunteer(**v) for v in yaml.safe_load(f)]

  print(schedule.generate_schedule(shifts, volunteers))

main()
