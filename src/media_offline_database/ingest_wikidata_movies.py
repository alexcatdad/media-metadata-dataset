from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field

from media_offline_database.bootstrap import BootstrapEntity, BootstrapRelatedEdge
from media_offline_database.sources import SourceRole

WIKIDATA_SOURCE_ID = "wikidata"
WIKIDATA_MOVIE_ADAPTER_VERSION = "wikidata-movie-bootstrap-v1"
WIKIDATA_USER_AGENT = (
    "media-metadata-dataset local compiler "
    "(https://github.com/alexcatdad/media-metadata-dataset)"
)


class WikidataMovieRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    qid: str
    label: str
    aliases: list[str] = Field(default_factory=list)
    publication_date: str | None = None
    runtime_minutes: int | None = None
    imdb_id: str | None = None
    genres: list[str] = Field(default_factory=list)
    directors: list[str] = Field(default_factory=list)
    series: list[str] = Field(default_factory=list)


class WikidataMovieBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_snapshot_id: str
    fetched_at: datetime
    entities: list[BootstrapEntity]
    total_candidates: int


WikidataMovieFetch = Callable[[Sequence[str]], list[WikidataMovieRecord]]


def fetch_wikidata_movie_records(qids: Sequence[str]) -> list[WikidataMovieRecord]:
    unique_qids = list(dict.fromkeys(qids))
    if not unique_qids:
        return []

    values = " ".join(f"wd:{qid}" for qid in unique_qids)
    query = f"""
SELECT ?item
       (SAMPLE(?itemLabel) AS ?itemLabel)
       (MIN(?publicationDate) AS ?firstPublicationDate)
       (SAMPLE(?runtime) AS ?sampleRuntime)
       (SAMPLE(?imdbId) AS ?sampleImdbId)
       (GROUP_CONCAT(DISTINCT ?alias; separator="|") AS ?aliases)
       (GROUP_CONCAT(DISTINCT ?genreLabel; separator="|") AS ?genres)
       (GROUP_CONCAT(DISTINCT ?directorLabel; separator="|") AS ?directors)
       (GROUP_CONCAT(DISTINCT ?seriesLabel; separator="|") AS ?series)
WHERE {{
  VALUES ?item {{ {values} }}
  OPTIONAL {{ ?item rdfs:label ?itemLabel FILTER(LANG(?itemLabel) = "en") }}
  OPTIONAL {{ ?item skos:altLabel ?alias FILTER(LANG(?alias) = "en") }}
  OPTIONAL {{ ?item wdt:P577 ?publicationDate. }}
  OPTIONAL {{ ?item wdt:P2047 ?runtime. }}
  OPTIONAL {{ ?item wdt:P345 ?imdbId. }}
  OPTIONAL {{
    ?item wdt:P136 ?genre.
    ?genre rdfs:label ?genreLabel FILTER(LANG(?genreLabel) = "en")
  }}
  OPTIONAL {{
    ?item wdt:P57 ?director.
    ?director rdfs:label ?directorLabel FILTER(LANG(?directorLabel) = "en")
  }}
  OPTIONAL {{
    ?item wdt:P179 ?seriesItem.
    ?seriesItem rdfs:label ?seriesLabel FILTER(LANG(?seriesLabel) = "en")
  }}
}}
GROUP BY ?item
"""
    response = httpx.get(
        "https://query.wikidata.org/sparql",
        params={"query": query, "format": "json"},
        headers={"User-Agent": WIKIDATA_USER_AGENT},
        timeout=45,
    )
    response.raise_for_status()
    return _records_from_sparql(response.json())


def normalize_wikidata_movie_records(records: Sequence[WikidataMovieRecord]) -> list[BootstrapEntity]:
    entities = [_entity_from_record(record) for record in records]
    _attach_franchise_edges(entities)
    return entities


def normalize_wikidata_movie_batch(
    *,
    qids: Sequence[str],
    fetch_records: WikidataMovieFetch = fetch_wikidata_movie_records,
) -> WikidataMovieBatch:
    fetched_at = datetime.now(tz=UTC)
    unique_qids = list(dict.fromkeys(qids))
    records = fetch_records(unique_qids)
    entities = normalize_wikidata_movie_records(records)
    return WikidataMovieBatch(
        source_snapshot_id=wikidata_movie_snapshot_id(fetched_at),
        fetched_at=fetched_at,
        entities=entities,
        total_candidates=len(unique_qids),
    )


def write_normalized_wikidata_movie_seed(
    *,
    qids: Sequence[str],
    output_path: Path,
    fetch_records: WikidataMovieFetch = fetch_wikidata_movie_records,
) -> Path:
    batch = normalize_wikidata_movie_batch(qids=qids, fetch_records=fetch_records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(entity.model_dump_json() for entity in batch.entities)
        + ("\n" if batch.entities else ""),
        encoding="utf-8",
    )
    return output_path


def wikidata_movie_snapshot_id(fetched_at: datetime) -> str:
    return f"wikidata-movie:{fetched_at.date().isoformat()}"


def _records_from_sparql(payload: dict[str, Any]) -> list[WikidataMovieRecord]:
    records: list[WikidataMovieRecord] = []
    results = payload.get("results")
    if not isinstance(results, dict):
        return []
    results_map = cast(dict[str, object], results)
    bindings_value = results_map.get("bindings")
    if not isinstance(bindings_value, list):
        return []
    bindings = cast(list[object], bindings_value)
    for raw_row in bindings:
        if not isinstance(raw_row, dict):
            continue
        row = cast(dict[str, object], raw_row)
        item = _binding_value(row, "item")
        if item is None:
            continue
        qid = item.rsplit("/", 1)[-1]
        label = _binding_value(row, "itemLabel") or qid
        records.append(
            WikidataMovieRecord(
                qid=qid,
                label=label,
                aliases=_split_pipe(_binding_value(row, "aliases")),
                publication_date=_binding_value(row, "firstPublicationDate"),
                runtime_minutes=_int_from_decimal(_binding_value(row, "sampleRuntime")),
                imdb_id=_binding_value(row, "sampleImdbId"),
                genres=_split_pipe(_binding_value(row, "genres")),
                directors=_split_pipe(_binding_value(row, "directors")),
                series=_split_pipe(_binding_value(row, "series")),
            )
        )
    order = {qid: index for index, qid in enumerate(dict.fromkeys(record.qid for record in records))}
    return sorted(records, key=lambda record: order[record.qid])


def _entity_from_record(record: WikidataMovieRecord) -> BootstrapEntity:
    wikidata_url = f"https://www.wikidata.org/wiki/{record.qid}"
    sources = [wikidata_url]
    if record.imdb_id:
        sources.append(f"https://www.imdb.com/title/{record.imdb_id}/")
    release_year = _release_year(record.publication_date)

    return BootstrapEntity(
        entity_id=f"movie:wikidata:{record.qid}",
        domain="movie",
        canonical_source=wikidata_url,
        source_role=SourceRole.BACKBONE_SOURCE,
        record_source=WIKIDATA_SOURCE_ID,
        title=record.label,
        media_type="MOVIE",
        status="RELEASED" if release_year else "UNKNOWN",
        release_year=release_year or 0,
        synonyms=record.aliases,
        sources=sorted(dict.fromkeys(sources)),
        genres=record.genres,
        studios=[],
        creators=record.directors,
        tags=sorted(
            dict.fromkeys(
                [
                    *_normalized_tags(record.genres),
                    *[f"franchise:{_tag_value(series)}" for series in record.series],
                ]
            )
        ),
        field_sources={
            "title": [wikidata_url],
            "synonyms": [wikidata_url],
            "release_year": [wikidata_url],
            "genres": [wikidata_url],
            "creators": [wikidata_url],
            "sources": [wikidata_url],
        },
    )


def _attach_franchise_edges(entities: list[BootstrapEntity]) -> None:
    by_series: dict[str, list[BootstrapEntity]] = defaultdict(list)
    series_by_entity: dict[str, set[str]] = defaultdict(set)
    for entity in entities:
        for tag in entity.tags:
            if not tag.startswith("franchise:"):
                continue
            series_by_entity[entity.entity_id].add(tag)
            by_series[tag].append(entity)

    for entity in entities:
        target_ids: set[str] = set()
        for series_tag in sorted(series_by_entity[entity.entity_id]):
            for target in by_series[series_tag]:
                if target.entity_id != entity.entity_id:
                    target_ids.add(target.entity_id)
        for target_id in sorted(target_ids):
            target = next(target for target in entities if target.entity_id == target_id)
            entity.related.append(
                BootstrapRelatedEdge(
                    target=target.entity_id,
                    relationship="franchise_related",
                    target_url=target.canonical_source,
                    supporting_urls=[entity.canonical_source, target.canonical_source],
                )
            )


def _binding_value(row: dict[str, object], key: str) -> str | None:
    value = row.get(key)
    if not isinstance(value, dict):
        return None
    binding = cast(dict[str, object], value)
    raw = binding.get("value")
    return raw if isinstance(raw, str) and raw else None


def _split_pipe(value: str | None) -> list[str]:
    if value is None:
        return []
    return sorted(dict.fromkeys(part for part in value.split("|") if part))


def _int_from_decimal(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _release_year(value: str | None) -> int | None:
    if value is None or len(value) < 4:
        return None
    try:
        return date.fromisoformat(value[:10]).year
    except ValueError:
        try:
            return int(value[:4])
        except ValueError:
            return None


def _normalized_tags(values: Sequence[str]) -> list[str]:
    return [_tag_value(value) for value in values if value.strip()]


def _tag_value(value: str) -> str:
    return value.strip().casefold().replace(" ", "_")
