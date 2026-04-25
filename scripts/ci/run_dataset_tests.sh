#!/usr/bin/env sh
set -eu

pytest \
  tests/test_keyless_artifact.py \
  tests/test_bootstrap_artifact.py \
  tests/test_build_anime.py \
  tests/test_query_preview.py \
  tests/test_concept_corpus_slice.py \
  tests/test_corpus_slice_manifests.py \
  tests/test_corpus_concept_search.py \
  tests/test_death_note_bootstrap.py \
  tests/test_designated_survivor_bootstrap.py \
  tests/test_ghost_in_the_shell_bootstrap.py \
  tests/test_anilist_concept_search.py \
  tests/test_anilist_enrichment.py \
  tests/test_anilist_metadata_enrichment.py \
  tests/test_ingest_anilist.py \
  tests/test_manami_ingest.py \
  tests/test_relationships.py
