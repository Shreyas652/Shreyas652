#!/usr/bin/env python3
"""Static validation for profile links, SVGs, HTML assets, and workflow pins."""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
MAX_ASSET_BYTES = 200 * 1024


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.refs: list[str] = []
        self.images_without_alt: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"] or "")
        for key in ("href", "src"):
            if values.get(key):
                self.refs.append(values[key] or "")
        if tag == "img" and not values.get("alt"):
            self.images_without_alt.append(values.get("src") or "<unknown>")


def local_target(source: Path, value: str) -> tuple[Path | None, str | None]:
    if not value or value.startswith(("http://", "https://", "mailto:")):
        return None, None
    if value.startswith("#"):
        return source, value[1:]
    parsed = urlparse(value)
    path = unquote(parsed.path)
    return (source.parent / path).resolve(), parsed.fragment or None


def validate_svg(errors: list[str]) -> None:
    for path in ROOT.rglob("*.svg"):
        if path.stat().st_size > MAX_ASSET_BYTES:
            errors.append(f"{path.relative_to(ROOT)} exceeds 200 KB")
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            errors.append(f"{path.relative_to(ROOT)} is not well-formed XML: {exc}")
            continue
        if root.tag.split("}")[-1] != "svg":
            errors.append(f"{path.relative_to(ROOT)} root element is not svg")
        if not (root.get("aria-label") or root.get("aria-labelledby")):
            errors.append(f"{path.relative_to(ROOT)} lacks an accessible name")


def validate_readme(errors: list[str]) -> None:
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)|\[[^\]]+\]\(([^)]+)\)", text)
    refs += [(value, "") for value in re.findall(r"<(?:img|source)[^>]+(?:src|srcset)=\"([^\"]+)\"", text)]
    for pair in refs:
        value = next((item for item in pair if item), "")
        target, _fragment = local_target(path, value)
        if target is not None and not target.exists():
            errors.append(f"README.md references missing local file: {value}")
    for tag in re.findall(r"<img\b[^>]*>", text, re.I):
        if not re.search(r"\balt=\"[^\"]+\"", tag, re.I):
            errors.append(f"README image lacks alt text: {tag[:80]}")
    forbidden = ("github-readme-stats.vercel.app", "readme-typing-svg.demolab.com", "komarev.com", "skillicons.dev", "capsule-render.vercel.app")
    for host in forbidden:
        if host in text:
            errors.append(f"README still depends on third-party image service: {host}")


def validate_page(errors: list[str]) -> None:
    path = ROOT / "docs" / "index.html"
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    for image in parser.images_without_alt:
        errors.append(f"docs/index.html image lacks alt text: {image}")
    for value in parser.refs:
        target, fragment = local_target(path, value)
        if target is None:
            continue
        if target == path and fragment:
            if fragment not in parser.ids:
                errors.append(f"docs/index.html references missing anchor: #{fragment}")
        elif not target.exists():
            errors.append(f"docs/index.html references missing local file: {value}")


def validate_action_pins(errors: list[str]) -> None:
    pattern = re.compile(r"^\s*uses:\s*([^\s#]+)", re.M)
    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        for use in pattern.findall(path.read_text(encoding="utf-8")):
            if use.startswith("./"):
                continue
            ref = use.rsplit("@", 1)[-1]
            if not re.fullmatch(r"[0-9a-f]{40}", ref):
                errors.append(f"{path.relative_to(ROOT)} has unpinned action: {use}")


def main() -> int:
    errors: list[str] = []
    validate_svg(errors)
    validate_readme(errors)
    validate_page(errors)
    validate_action_pins(errors)
    if errors:
        print("Repository validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Repository validation passed: local links, HTML anchors/assets, SVG XML/size/accessibility, image alt text, third-party image hosts, and Action SHA pins.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
