## Problem

I've been doing volunteeer work for the last months, and an usual bottleneck is scheduling shifts for volunteers.

The more volunteers, the more time and energy will be spend in creating a daily or weekly schedule.

From my experience, if there are 10-15 volunteers, it's easier to manage manually the schedule. Either by one
leadership person creating the schedule accordingly to preferences of volunteers for the week/day, or volunteers
choosing daily their tasks.

The more people there are in a group of volunteers, the more needed is a weekly scheduling instead of relying on
daily scheduling of shifts.

Of course, daily scheduling where volunteers are choosing their own shifts are the peak of flexibility for
volunteers, though the price may be high as I mentioned;

The time and energy spent in the scheduling scales with the number of volunteers. These resources could be more wisely
used in planning/improving specific parts of a project, or at least saving working hours being spent on schedule building.

Thus, projects with 15+ might rely on automated shift scheduling for their crew. While, obviously, considering
the amount of working hours, days offs, task preferences... And allowance for changing the schedule.

Also, keep in mind that you don't need to allocate all your shifts in advance. Leadership can allocate the usual
tasks with this automated manner, while keeping manual allocation for misc shifts that might appear daily.

It's important to notice though that schedules have to be clearly available to volunteers, either on a google sheets,
on a website or through a message.

## TODO maybe: talk about my experiences

## Software

For the first version, because I'm trying to solve a bottleneck for a place of 40 volunteers, I imagine a
python program generating a google spreadsheets with the weekly schedule.

Changes will not be automated, this will have to be managed manually changing the spreadsheets for now.

The user of the python program probably needs a very simple frontend because we don't want to expect people to
know how to use even these online runtimes. (Or do we?)

Let's thus organize in requirements:

_Hard requirements:_

- Leadership must be able to manage shifts which includes:
  - Min and Max people needed for the shift
  - Shift hours and days
- Leadership must be able to manage volunteers info which includes:
  - Volunteers' preferences
  - Volunteers with fixed shifts
  - Volunteers' days off

_Soft requirements:_

- Leadership needs some sort of frontend, otherwise we have to rely on file edition like yaml? Maybe we start with yaml
- Leadership needs a way to SAVE the information (e.g.: a file) and RUN the program.
