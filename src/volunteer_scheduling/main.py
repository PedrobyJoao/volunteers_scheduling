import yaml
from pydantic import TypeAdapter
from . import schedule
from . import sheets


def main():
  with open("data.yml") as f:
      data = yaml.safe_load(f)
      obj = TypeAdapter(schedule.ShiftsVolunteersYAML).validate_python(data)
  
  week_schedule = schedule.generate_schedule(obj.shifts, obj.volunteers)
  sheets.write_pretty_schedule_xlsx(week_schedule)
  print(schedule.pretty_schedule(week_schedule))


main()
