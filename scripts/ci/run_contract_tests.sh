#!/usr/bin/env sh
set -eu

pytest \
  tests/test_docs_policy.py \
  tests/test_settings.py \
  tests/test_llm.py \
  tests/test_sources.py
