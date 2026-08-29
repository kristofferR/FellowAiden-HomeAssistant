"""Model to validate the coffee schedule data"""

import re

from pydantic import BaseModel, field_validator

from ..const import MAX_WATER_AMOUNT_ML, MIN_WATER_AMOUNT_ML

# Regular expression for profileId: either "p" followed by digits or "plocal" followed by digits
PROFILE_ID_REGEX = re.compile(r"^(p|plocal)\d+$")


class CoffeeSchedule(BaseModel):
    days: list[bool]
    secondFromStartOfTheDay: int
    enabled: bool
    amountOfWater: int
    profileId: str

    @field_validator("days")
    @classmethod
    def validate_days(cls, v):
        if len(v) != 7:
            raise ValueError(
                "The 'days' list must contain exactly 7 boolean values (from Sunday to Saturday)."
            )
        if any(not isinstance(day, bool) for day in v):
            raise ValueError("Each element in 'days' must be a boolean.")
        return v

    @field_validator("secondFromStartOfTheDay")
    @classmethod
    def validate_second_from_start_of_the_day(cls, v):
        if not (0 <= v < 86400):
            raise ValueError(
                "secondFromStartOfTheDay must be between 0 and 86399 (seconds in a day)."
            )
        return v

    @field_validator("amountOfWater")
    @classmethod
    def validate_amount_of_water(cls, v):
        if not (MIN_WATER_AMOUNT_ML <= v <= MAX_WATER_AMOUNT_ML):
            raise ValueError(
                f"amountOfWater must be between {MIN_WATER_AMOUNT_ML} and {MAX_WATER_AMOUNT_ML}."
            )
        return v

    @field_validator("profileId")
    @classmethod
    def validate_profile_id(cls, v):
        if not PROFILE_ID_REGEX.match(v):
            raise ValueError(
                "profileId must be either 'p' followed by a number or 'plocal' followed by a number."
            )
        return v
