# Working Style

This repo is in early architecture/bootstrap. Treat existing product docs as working notes unless a
decision is recorded in `docs/decisions.jsonl`.

## Current Rules

- Do not run project pipeline tasks directly on host Python.
- Use Docker/Compose locally and the same container command surface in CI.
- Keep anime first class.
- Keep v1 focused on anime, TV, and movies.
- Do not add music scope without a new accepted decision.
- Classify every source before implementation: `BACKBONE_SOURCE`, `ID_SOURCE`, `LOCAL_EVIDENCE`,
  `RUNTIME_ONLY`, `PAID_EXPERIMENT_ONLY`, or `BLOCKED`.
- Prefer free-access reproducibility for canonical pipelines. Paid/contract access is private
  experiment-only unless an accepted decision records rights evidence and approval.
- Keep model choices aligned with `docs/model-selection.md`; do not swap canonical models without a
  new accepted decision.
- Credentials do not imply redistribution rights.
- Use JSONL for append-only decisions.
- Treat dense JSONL files such as `docs/decisions.jsonl` and `docs/backlog.jsonl` as coordinated
  merge surfaces during parallel work. Do not ask multiple agents to independently choose the next
  numeric decision ID or rewrite adjacent backlog rows. A single coordinator should do the final
  rebase, renumbering, backlog-reference update, validation, and push for those files.

## Tooling

Use `ruff`, `pyright`, and `pytest` as validation gates inside the container.

Prefer small, typed Python modules over notebook-style data scripts.

## PR Review Workflow

When asked to review a PR for an agent, use a code-review stance and leave the feedback on the PR so
the responsible agent can act without needing this chat.

Review flow:

- Inspect PR metadata, patch, changed files, comments, reviews, and CI/check status.
- Pull failing check logs when checks are red, and distinguish content feedback from merge blockers.
- Prioritize actionable issues: broken contracts, dependency/order problems, failing validation,
  scope drift, missing tests, and conflicts with accepted decisions.
- Reference the relevant file, line, backlog item, decision ID, or CI failure in each point.
- Prefer one concise PR comment or formal review with required changes. If GitHub blocks a formal
  review because the PR author is the same account, post the same feedback as a regular PR comment.
- Do not fix the PR during review unless explicitly asked; the PR-owning agent should receive clear
  instructions instead.
- When taking over conflict-only PRs, prefer rebasing onto current `main`, preserving the branch's
  substantive code changes, and serializing decision/backlog JSONL edits so IDs remain monotonically
  ordered and unique.

See `docs/runbooks/pr-review.md` for the command workflow.
