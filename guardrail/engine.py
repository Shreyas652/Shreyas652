"""A small, explainable prompt-injection policy engine.

This module deliberately does not execute, import, request, or render attacker
input. It normalizes text, applies bounded pattern checks, and returns data.
"""
from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass

MAX_INPUT_CHARS = 8_000
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\u2066-\u2069\ufeff]")
BASE64_RE = re.compile(r"(?<![A-Za-z0-9+/])(?:[A-Za-z0-9+/]{4}){4,}(?:==|=)?(?![A-Za-z0-9+/])")


@dataclass(frozen=True)
class Finding:
    rule_id: str
    description: str
    weight: int


@dataclass(frozen=True)
class Assessment:
    verdict: str
    risk_score: int
    findings: tuple[Finding, ...]
    truncated: bool
    input_length: int


RULES = (
    (
        "instruction_override",
        "Attempts to replace or ignore higher-priority instructions",
        35,
        re.compile(r"\b(ignore|disregard|forget|override|bypass)\b.{0,48}\b(previous|prior|above|system|developer|instruction|policy|rule)s?\b", re.I | re.S),
    ),
    (
        "prompt_exfiltration",
        "Requests hidden prompts, policies, or instruction text",
        35,
        re.compile(r"\b(reveal|show|print|repeat|dump|extract)\b.{0,55}\b(system prompt|developer message|hidden instructions?|internal policy|chain[- ]of[- ]thought)\b", re.I | re.S),
    ),
    (
        "secret_exfiltration",
        "Requests secrets, credentials, keys, or tokens",
        45,
        re.compile(r"\b(reveal|show|print|dump|send|exfiltrate|leak|return)\b.{0,55}\b(api[- ]?keys?|secrets?|passwords?|credentials?|access tokens?|private keys?)\b", re.I | re.S),
    ),
    (
        "tool_execution",
        "Attempts command, network, or code execution",
        45,
        re.compile(r"(?:\bcurl\b|\bwget\b|\bpowershell\b|\bsubprocess\b|\bos\.system\b|\beval\s*\(|\bexec\s*\(|\brm\s+-rf\b|\bsh\s+-c\b|\bfetch\s*\(|\bhttps?://)", re.I),
    ),
    (
        "role_hijack",
        "Assigns a new privileged or unrestricted role",
        25,
        re.compile(r"\b(you are now|act as|switch to|enter)\b.{0,35}\b(admin|developer|system|root|unrestricted|dan|debug)\b", re.I | re.S),
    ),
    (
        "indirect_injection",
        "Embeds instructions in purported retrieved or tool-provided content",
        25,
        re.compile(r"\b(retrieved (document|context)|tool output|web page|email|attachment)\b.{0,80}\b(instruction|must|ignore|execute|follow)\b", re.I | re.S),
    ),
    (
        "delimiter_smuggling",
        "Uses instruction-boundary or chat-template delimiters",
        20,
        re.compile(r"(?:<\/?(?:system|assistant|developer|tool)>|\[/?INST\]|<<SYS>>|###\s*(?:system|developer)\b)", re.I),
    ),
)


def sanitize(value: str) -> tuple[str, bool, bool]:
    original_length = len(value)
    bounded = value[:MAX_INPUT_CHARS]
    had_hidden = bool(CONTROL_RE.search(bounded) or ZERO_WIDTH_RE.search(bounded))
    cleaned = CONTROL_RE.sub("", bounded)
    cleaned = ZERO_WIDTH_RE.sub("", cleaned)
    return unicodedata.normalize("NFKC", cleaned), original_length > MAX_INPUT_CHARS, had_hidden


def decoded_payloads(value: str) -> list[str]:
    payloads: list[str] = []
    for match in BASE64_RE.finditer(value[:MAX_INPUT_CHARS]):
        candidate = match.group(0)
        if len(candidate) > 1_024:
            continue
        try:
            decoded = base64.b64decode(candidate, validate=True).decode("utf-8", errors="ignore")
        except (binascii.Error, ValueError):
            continue
        if decoded and sum(ch.isprintable() for ch in decoded) / len(decoded) > 0.8:
            payloads.append(decoded[:2_000])
    return payloads[:5]


def assess(raw_text: str) -> Assessment:
    normalized, truncated, had_hidden = sanitize(raw_text or "")
    findings: dict[str, Finding] = {}
    haystacks = [normalized]
    decoded = decoded_payloads(normalized)
    haystacks.extend(decoded)

    for rule_id, description, weight, pattern in RULES:
        if any(pattern.search(haystack) for haystack in haystacks):
            findings[rule_id] = Finding(rule_id, description, weight)

    if decoded:
        findings["encoded_payload"] = Finding(
            "encoded_payload", "Contains a decodable Base64 payload", 20
        )
    if had_hidden:
        findings["hidden_unicode"] = Finding(
            "hidden_unicode", "Contains invisible or directional control characters", 25
        )
    if re.search(r"(?:%[0-9a-f]{2}){4,}|(?:\\x[0-9a-f]{2}){4,}|(?:\\u[0-9a-f]{4}){3,}", normalized, re.I):
        findings["escaped_payload"] = Finding(
            "escaped_payload", "Contains repeated escaped or percent-encoded bytes", 20
        )

    score = min(100, sum(finding.weight for finding in findings.values()))
    critical = {"secret_exfiltration", "tool_execution"}
    blocked = score >= 40 or bool(critical.intersection(findings))
    return Assessment(
        verdict="blocked" if blocked else "allowed",
        risk_score=score,
        findings=tuple(findings.values()),
        truncated=truncated,
        input_length=len(raw_text or ""),
    )
