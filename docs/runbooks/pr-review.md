# PR Review Runbook

Use this runbook when reviewing a GitHub pull request for another developer or agent.

## Goals

- Give the PR-owning agent actionable feedback in GitHub, not only in chat.
- Separate content/design feedback from CI or validation blockers.
- Keep the review grounded in accepted decisions, backlog items, and changed files.

## Workflow

1. Inspect PR metadata:

```sh
gh pr view <number> --json number,title,state,author,headRefName,baseRefName,url,body,mergeable,reviewDecision,statusCheckRollup
```

2. Inspect the patch:

```sh
gh pr diff <number> --patch
```

3. Inspect checks and pull logs for failures:

```sh
gh pr checks <number>
gh run view <run-id> --job <job-id> --log
```

4. Inspect existing comments and reviews:

```sh
gh pr view <number> --comments --json comments,reviews,latestReviews,files
```

5. Write feedback in review order:

- correctness or contract violations;
- failing CI or validation blockers;
- missing tests or docs;
- smaller polish items only when they matter.

6. Submit a formal review when GitHub allows it:

```sh
gh pr review <number> --request-changes --body-file /tmp/review.md
```

7. If GitHub refuses a formal review because the PR belongs to the same account, post the same
   feedback as a regular PR comment:

```sh
gh pr comment <number> --body-file /tmp/review.md
```

## Review Standards

- Keep findings specific and actionable.
- Cite file paths, lines, backlog IDs, decision IDs, or check failures.
- Do not make unrelated edits while reviewing unless the user asks for fixes.
- Do not approve a PR with failing required checks.
