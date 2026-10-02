from enum import StrEnum

from pydantic import BaseModel, Field


class EmoticonCategory(StrEnum):
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    PLAYFUL = "playful"
    SARCASTIC = "sarcastic"
    LOVE = "love"
    SURPRISED = "surprised"
    CONFUSED = "confused"
    NEUTRAL = "neutral"


class EmoticonProfile(BaseModel):
    symbol: str
    categories: tuple[EmoticonCategory, ...] = Field(min_length=1, max_length=3)
    valence: float = Field(
        ge=-1.0,
        le=1.0,
        description="how positive/negative? Continuous (-1.0 to 1.0) gives finer-grained similarity comparisons later",
    )
    intensity: float = Field(
        ge=0, le=1, description="how strong the emotion is, independent of valence"
    )
