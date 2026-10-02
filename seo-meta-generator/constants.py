from pathlib import Path

import dspy

_PROJECT_ROOT = Path(__file__).parent

_CTA_VERBS = {
    "start",
    "discover",
    "learn",
    "try",
    "get",
    "explore",
    "shop",
    "find",
    "join",
    "sign",
    "book",
    "claim",
    "download",
    "contact",
}

_TRAINSET = [
    dspy.Example(
        topic="beginner yoga poses",
        keyword="yoga for beginners",
    ).with_inputs("topic", "keyword"),
    dspy.Example(
        topic="budgeting apps for freelancers",
        keyword="freelancer budgeting app",
    ).with_inputs("topic", "keyword"),
    dspy.Example(
        topic="Python fundamentals",
        keyword="learn python today"
    ).with_inputs("topic", "keyword")
    # ... 3-4 more
]
