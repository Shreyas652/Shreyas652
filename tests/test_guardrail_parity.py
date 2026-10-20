"""Run the same policy contracts as the browser engine tests."""
import json
from pathlib import Path

import pytest

from guardrail.engine import assess

CASES = json.loads((Path(__file__).parent / "guardrail-cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("sample", CASES, ids=[sample["name"] for sample in CASES])
def test_browser_server_contract(sample):
    result = assess(sample["input"])
    assert result.verdict == sample["verdict"]
    assert result.risk_score == sample["score"]
    assert [finding.rule_id for finding in result.findings] == sample["rules"]
