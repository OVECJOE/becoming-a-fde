import os
from typing import Literal

import dspy
from dotenv import load_dotenv

load_dotenv(".env")

lm = dspy.LM("openai/gpt-5-nano", api_key=os.getenv("OPENAI_API_KEY"))
dspy.configure(lm=lm)

Season = Literal["spring", "summer", "autumn", "winter"]


class HaikuBot(dspy.Signature):
    """
    Write a classical haiku given the provided inputs.
    """
    location: str = dspy.InputField(desc="The setting of the poem")
    mood: str = dspy.InputField()
    season: Season = dspy.InputField()
    haiku: str = dspy.OutputField()
    haiku_title: str = dspy.OutputField(desc="The title of the poem; something creative and 3-word one-liner")


def main():
    haiku_bot = dspy.Predict(HaikuBot)
    result = haiku_bot(location="a quiet library", mood="mysterious", season="autumn")
    print(result.haiku_title)
    print("- - -")
    print(result.haiku)


if __name__ == "__main__":
    main()
