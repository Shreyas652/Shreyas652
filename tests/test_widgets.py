import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def load_generator():
    path = Path(".github/scripts/generate_widgets.py")
    spec = importlib.util.spec_from_file_location("generate_widgets", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_all_widget_renderers_return_accessible_svg():
    module = load_generator()
    fixture = json.loads(Path("tests/fixtures/github_profile.json").read_text(encoding="utf-8"))
    for renderer in (module.languages_svg, module.activity_svg, module.project_svg, module.building_svg):
        root = ET.fromstring(renderer(fixture))
        assert root.tag.endswith("svg")
        assert root.attrib["role"] == "img"
        assert root.attrib["aria-labelledby"] == "title desc"


def test_widget_text_is_xml_escaped():
    module = load_generator()
    assert module.text("<script>&", 80) == "&lt;script&gt;&amp;"
