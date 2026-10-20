# Break My Guardrail: maintainer notes

The challenge is intentionally deterministic. `guardrail/engine.py` normalizes
and bounds the issue text, then applies an explicit set of weighted rules. It
does not call a model, execute input, or fetch URLs found in input.

The control room at docs/index.html provides a browser companion in
docs/guardrail.js. The browser keeps only scores and signal names in a
ten-entry, in-memory session log. Prompt text is never sent to GitHub by
the sandbox. The separate public challenge link opens an issue template;
the visitor chooses what to publish there.

Both engines use the same weighted rules and block threshold. Shared
cases in tests/guardrail-cases.json verify their contracts in Python
and Node. Regex and Unicode behavior can still differ at language edges;
this remains an educational pattern filter, not a production security boundary.

Allowed issue submissions enter the community review log automatically.
They are not verified bypasses: benign requests are allowed too.

## Control room verification

- Run Python pytest and scripts/validate_repo.py.
- Run node --test tests/control-room.test.cjs.
- Serve docs/, then run node scripts/check_browser.cjs with Playwright
  available. Optional PREVIEW_URL and QA_OUTPUT_DIR select the preview
  and screenshot destination.

The project explorer uses public README architecture descriptions. Its
walkthroughs do not invoke project backends. FINVERSE is explicitly a
concept, and Veyra's diagram is a general MCP interaction pattern.

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
