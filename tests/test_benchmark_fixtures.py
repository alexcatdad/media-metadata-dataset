json = __import__("json")
Path = __import__("pathlib").Path
cast = __import__("typing").cast

RelationshipLabel = __import__(
    "media_offline_database.modeling",
    fromlist=["RelationshipLabel"],
).RelationshipLabel


FIXTURE_PATH = Path("benchmarks/fixtures/anime-chat-judgment-v1.jsonl")
FACET_FIXTURE_PATH = Path("benchmarks/fixtures/media-facet-inference-judgment-v1.jsonl")
RELATIONSHIP_LABELS = {label.value for label in RelationshipLabel}


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
        assert row["domain"]
        assert row["recipe_version"] == "anime-chat-judgment-v1"
        assert row["source"]
        assert "record_a" in cast(dict[str, object], row["input"])
        assert "record_b" in cast(dict[str, object], row["input"])
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


def test_facet_inference_fixture_contract() -> None:
    rows: list[dict[str, object]] = []
    for line in FACET_FIXTURE_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            parsed = json.loads(line)
            assert isinstance(parsed, dict)
            rows.append(cast(dict[str, object], parsed))

    assert rows
    for row in rows:
        assert row["task"] == "facet_inference_judgment"
        assert row["domain"] in {"anime", "tv", "movie", "media"}
        assert row["recipe_version"] == "media-facet-inference-judgment-v1"
        expected = cast(dict[str, object], row["expected"])
        facets = cast(list[dict[str, object]], expected["facets"])
        assert facets
        assert isinstance(expected["materializable"], bool)
        assert expected["evidence_required"] is True
        for facet in facets:
            assert facet["facet_type"]
            assert facet["facet_value"]
            assert 0 <= cast(float, facet["confidence"]) <= 1
