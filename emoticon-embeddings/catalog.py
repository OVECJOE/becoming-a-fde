from schemas import EmoticonCategory, EmoticonProfile

EMOTICONS_CATALOG = [
    EmoticonProfile(
        symbol=":)", categories=(EmoticonCategory.HAPPY,), valence=0.6, intensity=0.4
    ),
    EmoticonProfile(
        symbol=":-)", categories=(EmoticonCategory.HAPPY,), valence=0.5, intensity=0.3
    ),
    EmoticonProfile(
        symbol=":D", categories=(EmoticonCategory.HAPPY,), valence=0.9, intensity=0.8
    ),
    EmoticonProfile(
        symbol="XD",
        categories=(EmoticonCategory.HAPPY, EmoticonCategory.PLAYFUL),
        valence=0.9,
        intensity=0.9,
    ),
    EmoticonProfile(
        symbol="^_^", categories=(EmoticonCategory.HAPPY,), valence=0.7, intensity=0.5
    ),
    EmoticonProfile(
        symbol=":(", categories=(EmoticonCategory.SAD,), valence=-0.6, intensity=0.4
    ),
    EmoticonProfile(
        symbol=":-(", categories=(EmoticonCategory.SAD,), valence=-0.5, intensity=0.3
    ),
    EmoticonProfile(
        symbol="T_T", categories=(EmoticonCategory.SAD,), valence=-0.8, intensity=0.8
    ),
    EmoticonProfile(
        symbol=":'(", categories=(EmoticonCategory.SAD,), valence=-0.9, intensity=0.95
    ),
    EmoticonProfile(
        symbol=">:(", categories=(EmoticonCategory.ANGRY,), valence=-0.8, intensity=0.9
    ),
    # frustrated/embarrassed, not pure anger; judgment call, could argue CONFUSED instead
    EmoticonProfile(
        symbol=">_<", categories=(EmoticonCategory.ANGRY,), valence=-0.4, intensity=0.6
    ),
    # annoyed/unimpressed rather than fully neutral; slight negative lean
    EmoticonProfile(
        symbol="-_-", categories=(EmoticonCategory.NEUTRAL,), valence=-0.3, intensity=0.3
    ),
    EmoticonProfile(
        symbol=":|", categories=(EmoticonCategory.NEUTRAL,), valence=0.0, intensity=0.1
    ),
    # genuinely ambiguous: playful wink vs. sarcastic undertone, picked PLAYFUL as primary
    EmoticonProfile(
        symbol=";)", categories=(EmoticonCategory.PLAYFUL,), valence=0.5, intensity=0.5
    ),
    EmoticonProfile(
        symbol=":P", categories=(EmoticonCategory.PLAYFUL,), valence=0.5, intensity=0.5
    ),
    EmoticonProfile(
        symbol=":3",
        categories=(EmoticonCategory.HAPPY, EmoticonCategory.PLAYFUL),
        valence=0.6,
        intensity=0.4,
    ),
    EmoticonProfile(
        symbol="8)",
        categories=(EmoticonCategory.HAPPY, EmoticonCategory.PLAYFUL),
        valence=0.6,
        intensity=0.5,
    ),
    EmoticonProfile(
        symbol=":O", categories=(EmoticonCategory.SURPRISED,), valence=0.0, intensity=0.7
    ),
    EmoticonProfile(
        symbol="o_O",
        categories=(EmoticonCategory.CONFUSED, EmoticonCategory.SURPRISED),
        valence=-0.1,
        intensity=0.5,
    ),
    EmoticonProfile(
        symbol="<3", categories=(EmoticonCategory.LOVE,), valence=0.8, intensity=0.6
    ),
]
