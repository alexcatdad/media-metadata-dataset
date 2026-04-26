json = __import__("json")
Path = __import__("pathlib").Path
cast = __import__("typing").cast


FIXTURE_PATH = Path("benchmarks/fixtures/anime-chat-judgment-v1.jsonl")
RELATIONSHIP_LABELS = {
    "same_entity",
    "movie_tie_in",
    "special",
    "sequel",
    "alternate_adaptation",
    "unrelated",
    "uncertain",
}


def load_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with FIXTURE_PATH.open(encoding="utf-8") as file:
        lines = file.read().splitlines()
    for line in lines:
        if line.strip():
            parsed = json.loads(line)
            assert isinstance(parsed, dict)
            rows.append(cast(dict[str, object], parsed))
    return rows


def test_fixture_corpus_exists_and_has_multiple_cases() -> None:
    rows = load_rows()

    assert len(rows) >= 6


def test_fixture_corpus_ids_are_unique() -> None:
    rows = load_rows()
    ids = [cast(str, row["id"]) for row in rows]

    assert len(ids) == len(set(ids))


def test_fixture_corpus_uses_supported_relationship_labels() -> None:
    rows = load_rows()

    for row in rows:
        assert row["task"] == "chat_json_judgment"
        expected = cast(dict[str, object], row["expected"])
        assert expected["relationship"] in RELATIONSHIP_LABELS
        assert isinstance(expected["same_entity"], bool)


def test_fixture_corpus_includes_varied_relationship_types() -> None:
    rows = load_rows()
    relationships = {cast(str, cast(dict[str, object], row["expected"])["relationship"]) for row in rows}

    assert {
        "same_entity",
        "movie_tie_in",
        "special",
        "sequel",
        "alternate_adaptation",
        "unrelated",
    } <= relationships
