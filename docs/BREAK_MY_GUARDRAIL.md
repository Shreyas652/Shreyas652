# Break My Guardrail: maintainer notes

The challenge is intentionally deterministic. `guardrail/engine.py` normalizes
and bounds the issue text, then applies an explicit set of weighted rules. It
does not call a model, execute input, or fetch URLs found in input.

## After a bypass

1. Read the linked public issue and reduce it to the smallest safe test case.
2. Add that test case to `tests/test_guardrail.py` as a regression test.
3. Add or narrow a rule in `guardrail/engine.py`. Prefer a specific signal over
   a broad keyword so ordinary requests do not become false positives.
4. Run `python -m pytest -q` and `python scripts/validate_repo.py`.
5. In the pull request, explain the bypass, the new signal, and any expected
   false-positive tradeoff. Never copy secrets or personal data into fixtures.

## Abuse and cost controls

- The workflow is serialized and limited to three attempts per author per UTC day.
- Input is passed to Python through an environment variable, capped at 8,000
  characters, stripped of control characters, and never interpolated into shell.
- Only issue number, author, score, rule IDs, and date enter the repository.
- The workflow uses only the built-in repository token and standard-library code.
- A bypass changes only bounded leaderboard blocks guarded by HTML comments.
