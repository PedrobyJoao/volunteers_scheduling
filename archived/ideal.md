The ideal algorithm would be:

Considering that we have the following shift types: Kitchen, Cleaning, and Outside.

```
1. assign days off if not assigned (must be equally divided)
2. check if there are enough people for required shifts
 (if not, we should reassign days off but let's do this for another version, let a TODO)
3. fulfill all required shifts with minimum people (e.g.: kitchen, watering, chicken)
    1. if there are not enough people with preference for required shifts, get them
    from cleaning, otherwise just get any available volunteer
    (how this part would go I'm not exactly sure yet)
4. considering all the other shifts, assign all other volunteers to non required shifts randomly
```

for the step 3. in our case specifically let's only work with the Shift Others (Agriculture, construction...) instead
of different shifts for now

## Days off:

Preference for Sunday besides people needed for required shifts of Sunday

Later, preference for random days of week
