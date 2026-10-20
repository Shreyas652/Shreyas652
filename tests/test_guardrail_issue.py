import importlib.util
from pathlib import Path

from guardrail.engine import assess


def load_script_namespace():
    path = Path(".github/scripts/guardrail_issue.py")
    spec = importlib.util.spec_from_file_location("guardrail_issue_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return vars(module)


def test_extracts_only_marked_attack():
    extract = load_script_namespace()["extract_attack"]
    body = "header\n<!-- attack:start -->candidate<!-- attack:end -->\nfooter"
    assert extract(body) == "candidate"


def test_comment_does_not_echo_attacker_markup():
    render = load_script_namespace()["render_comment"]
    attacker = "</table><script>alert(1)</script>"
    comment = render(assess(attacker))
    assert attacker not in comment
    assert "deterministic demonstration" in comment
