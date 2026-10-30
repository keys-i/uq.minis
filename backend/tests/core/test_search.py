import pytest

from uq_minis.core.common import MiniError
from uq_minis.core.search import matches, terms


@pytest.mark.parametrize(
    ("domain", "query", "text", "expected"),
    [
        ("clubs", "I'd like to join a coding club", "Software Society", True),
        ("clubs", "Find gaming clubs without alcohol", "Video Games Society", True),
        ("clubs", "Find gaming clubs without alcohol", "Games and alcohol", False),
        ("courses", "please find courses about maths", "Mathematics 1", True),
        ("courses", "CSSE1001", "CSSE1001 Introduction to Software", True),
        ("animals", "show me birds from Australia", "Pigeon in Australia", True),
        ("announcements", "coding events", "Programming meetup", True),
        ("clubs", "coding", "Hiking Society", False),
        ("clubs", "gaming or hiking clubs", "Bushwalking Society", True),
        ("clubs", "clubs without gaming and alcohol", "Photography club", True),
        ("clubs", "clubs without gaming and alcohol", "Photography and alcohol", False),
        ("clubs", "", "Anything", True),
    ],
)
def test_wording(domain: str, query: str, text: str, expected: bool) -> None:
    assert matches(text, terms(query, domain)) is expected


def test_limit() -> None:
    with pytest.raises(MiniError, match="500"):
        terms("x" * 501)
