"""422 responses never echo what the client sent (T-018 step 6; found in T-017).

A visitor's key pasted into the wrong place is the case that matters: as an unknown field, inside
a field that is too long or the wrong type, as a field name, or in a body that isn't JSON.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from gradpath.api.deps import get_answer_model, get_extraction_model, get_retrieval
from gradpath.api.main import UNKNOWN_FIELD, create_app, safe_validation_errors

KEY = "sk-ant-api03-" + "Q" * 40


def client() -> TestClient:
    """FastAPI solves dependencies before reporting body errors, so give it placeholders; a
    validation error means none of them is ever used."""
    app = create_app(use_lifespan=False)
    for dep in (get_retrieval, get_answer_model, get_extraction_model):
        app.dependency_overrides[dep] = object
    app.state.retrieval = object()  # /api/search reads it directly
    return TestClient(app)


def profile(**extra) -> dict:
    return {"skills": ["SQL"], "weekly_hours": 8, **extra}


JD = "Backend engineer, new grad. Build REST APIs in Python and SQL. " * 2


@pytest.mark.parametrize(
    ("path", "body", "loc"),
    [
        ("/api/chat", {"question": "What is an index?", "api_key": KEY}, ["body", UNKNOWN_FIELD]),
        ("/api/chat", {"question": "What is an index?", KEY: 1}, ["body", UNKNOWN_FIELD]),
        ("/api/chat", {"question": KEY * 50}, ["body", "question"]),
        ("/api/chat", {"question": ["list", KEY]}, ["body", "question"]),
        ("/api/search", {"query": "sql", "key": KEY}, ["body", UNKNOWN_FIELD]),
        (
            "/api/career/prepare",
            {"job_description": JD, "profile": profile(anthropic_key=KEY)},
            ["body", "profile", UNKNOWN_FIELD],
        ),
        (
            "/api/career/prepare",
            {"job_description": JD, "profile": profile(skills=["SQL", {"k": KEY}])},
            ["body", "profile", "skills", 1],
        ),
    ],
)
def test_a_key_in_the_wrong_place_never_comes_back(path, body, loc, caplog):
    with caplog.at_level(logging.DEBUG):
        resp = client().post(path, json=body)
    assert resp.status_code == 422
    assert KEY not in resp.text and "QQQQ" not in resp.text
    assert KEY not in caplog.text and "QQQQ" not in caplog.text
    errors = resp.json()["detail"]
    assert loc in [e["loc"] for e in errors]
    for e in errors:
        assert set(e) == {"loc", "msg", "type"}


def test_a_body_that_is_not_json_never_comes_back():
    resp = client().post(
        "/api/chat", content=f'{{"question": "{KEY}', headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 422 and KEY not in resp.text and "QQQQ" not in resp.text
    assert all(set(e) == {"loc", "msg", "type"} for e in resp.json()["detail"])


def test_the_frontend_still_gets_the_row_it_needs():
    """`lib/api.ts` fieldPaths reads `loc` (minus "body") to mark the field: indexes survive."""
    body = {"job_description": JD, "profile": profile(skills=["SQL", "x" * 500])}
    errors = client().post("/api/career/prepare", json=body).json()["detail"]
    assert ["body", "profile", "skills", 1] in [e["loc"] for e in errors]


def test_unsafe_location_parts_are_masked():
    errors = [
        {"loc": ("body", "profile", "a-b c", 3, "x" * 65), "msg": "m", "type": "t", "input": KEY,
         "ctx": {"error": KEY}},
        {"loc": ("body", "fine_name"), "msg": "m" * 500, "type": "extra_forbidden", "input": KEY},
    ]  # fmt: skip
    cleaned = safe_validation_errors(errors)
    assert cleaned[0] == {"loc": ["body", "profile", "?", 3, "?"], "msg": "m", "type": "t"}
    assert cleaned[1]["loc"] == ["body", UNKNOWN_FIELD] and len(cleaned[1]["msg"]) == 200
    assert KEY not in str(cleaned)


@pytest.mark.parametrize(
    ("part", "shown"),
    [
        ("skills", "skills"),
        (2, 2),
        ("123", "?"),
        ("naïve", "?"),
        ("name
", "?"),
        ("x" * 64, "x" * 64),
        ("x" * 65, "?"),
        ("list[str]", "?"),
    ],
)
def test_location_parts_table(part, shown):
    (cleaned,) = safe_validation_errors([{"loc": ("body", part), "msg": "m", "type": "t"}])
    assert cleaned["loc"] == ["body", shown]
