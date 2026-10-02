import os

import dspy
import spacy
from dotenv import load_dotenv

from constants import _CTA_VERBS, _PROJECT_ROOT, _TRAINSET

load_dotenv(dotenv_path=_PROJECT_ROOT.joinpath(".env"))

nlp = spacy.load("en_core_web_sm")
nlp.enable_pipe("senter")


class GenerateMetaDescription(dspy.Signature):
    topic: str = dspy.InputField(desc="Page topic", min_length=3)
    keyword: str = dspy.InputField(desc="Target keyword", min_length=3)
    meta_description: str = dspy.OutputField(
        desc="Meta description must include the keyword and ends with a call to action",
        max_length=160,
    )


def _ended_with_cta(meta_description: str) -> bool:
    sentences = [str(sent) for sent in nlp(meta_description).sents]
    if not sentences:
        return False

    doc = nlp(sentences[-1].lower())
    if not len(doc):
        return False

    first_token = doc[0]
    return first_token.pos_ == "VERB" or first_token.text in _CTA_VERBS


def metric(example, prediction, trace=None) -> bool:
    less_than_160 = len(prediction.meta_description) <= 160
    keyword_in_meta = example.keyword.lower() in prediction.meta_description.lower()
    return (
        less_than_160
        and keyword_in_meta
        and _ended_with_cta(prediction.meta_description)
    )


def main():
    lm = dspy.LM("openai/gpt-5-nano", api_key=os.getenv("OPENAI_API_KEY"))
    dspy.configure(lm=lm)

    generate = dspy.ChainOfThought(GenerateMetaDescription)
    optimizer = dspy.BootstrapFewShot(metric=metric, max_bootstrapped_demos=3)
    compiled = optimizer.compile(generate, trainset=_TRAINSET)

    print(dspy.inspect_history(n=1))
    for i, demo in enumerate(compiled.predict.demos):
        print(f"Demo {i}: {demo}")


if __name__ == "__main__":
    main()
