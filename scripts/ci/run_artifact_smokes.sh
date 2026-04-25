#!/usr/bin/env sh
set -eu

mod smoke-artifact --output-dir .mod/out/keyless-smoke
mod bootstrap-artifact --output-dir .mod/out/bootstrap-corpus
mod corpus-concept-preview \
  "romance anime where characters are in university/college" \
  --input-path corpus/bootstrap-concept-romance-college-v1.jsonl \
  --limit 3 >/dev/null
mod anime-build --help >/dev/null
