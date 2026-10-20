/* Browser companion to guardrail/engine.py. Input is data, never executed. */
(function (root) {
  "use strict";
  const MAX_INPUT_CHARS = 8000;
  const RULES = [
    ["instruction_override", "Instruction override", "Attempts to replace or ignore higher-priority instructions.", 35, /\b(ignore|disregard|forget|override|bypass)\b.{0,48}\b(previous|prior|above|system|developer|instruction|policy|rule)s?\b/is],
    ["prompt_exfiltration", "Prompt extraction", "Requests hidden prompts, policies, or instruction text.", 35, /\b(reveal|show|print|repeat|dump|extract)\b.{0,55}\b(system prompt|developer message|hidden instructions?|internal policy|chain[- ]of[- ]thought)\b/is],
    ["secret_exfiltration", "Secret extraction", "Requests secrets, credentials, keys, or tokens. Critical rule.", 45, /\b(reveal|show|print|dump|send|exfiltrate|leak|return)\b.{0,55}\b(api[- ]?keys?|secrets?|passwords?|credentials?|access tokens?|private keys?)\b/is],
    ["tool_execution", "Tool execution", "Attempts command, network, or code execution. Critical rule.", 45, /(?:\bcurl\b|\bwget\b|\bpowershell\b|\bsubprocess\b|\bos\.system\b|\beval\s*\(|\bexec\s*\(|\brm\s+-rf\b|\bsh\s+-c\b|\bfetch\s*\(|\bhttps?:\/\/)/i],
    ["role_hijack", "Role hijacking", "Assigns a new privileged or unrestricted role.", 25, /\b(you are now|act as|switch to|enter)\b.{0,35}\b(admin|developer|system|root|unrestricted|dan|debug)\b/is],
    ["indirect_injection", "Indirect injection", "Embeds instructions in purported retrieved or tool-provided content.", 25, /\b(retrieved (document|context)|tool output|web page|email|attachment)\b.{0,80}\b(instruction|must|ignore|execute|follow)\b/is],
    ["delimiter_smuggling", "Boundary smuggling", "Uses instruction-boundary or chat-template delimiters.", 20, /(?:<\/?(?:system|assistant|developer|tool)>|\[\/?INST\]|<<SYS>>|###\s*(?:system|developer)\b)/i],
  ];
  function assess(raw) {
    const input = String(raw || "");
    const chars = Array.from(input);
    const bounded = chars.slice(0, MAX_INPUT_CHARS).join("");
    const hidden = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2060\u2066-\u2069\ufeff]/g;
    const hadHidden = hidden.test(bounded);
    const normalized = bounded.replace(hidden, "").normalize("NFKC");
    const payloads = [];
    // Bound decoding work and match the server's single-layer Base64 checks.
    const candidates = normalized.matchAll(/(?<![A-Za-z0-9+/=])(?:[A-Za-z0-9+/]{4}){3,}(?:[A-Za-z0-9+/]{4}|[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)(?![A-Za-z0-9+/=])/g);
    for (const match of candidates) {
      if (match[0].length > 1024) continue;
      try {
        const bytes = Uint8Array.from(atob(match[0]), char => char.charCodeAt(0));
        const decoded = new TextDecoder().decode(bytes).replace(/\ufffd/g, "");
        const printable = Array.from(decoded).filter(char => !/[\p{C}\p{Zl}\p{Zp}]/u.test(char)).length;
        if (decoded && printable / Array.from(decoded).length > 0.8) payloads.push(decoded.slice(0, 2000));
      } catch (_) { /* Invalid encoding is not executed or repaired. */ }
      if (payloads.length >= 5) break;
    }
    const haystacks = [normalized, ...payloads];
    const findings = RULES.filter(rule => haystacks.some(text => rule[4].test(text)))
      .map(([id, title, description, weight]) => ({ id, title, description, weight }));
    if (payloads.length) findings.push({ id: "encoded_payload", title: "Encoded payload", description: "Contains a decodable Base64 payload.", weight: 20 });
    if (hadHidden) findings.push({ id: "hidden_unicode", title: "Hidden characters", description: "Contains invisible or directional control characters.", weight: 25 });
    if (/(?:%[0-9a-f]{2}){4,}|(?:\\x[0-9a-f]{2}){4,}|(?:\\u[0-9a-f]{4}){3,}/i.test(normalized)) {
      findings.push({ id: "escaped_payload", title: "Escaped payload", description: "Contains repeated escaped or percent-encoded bytes.", weight: 20 });
    }
    const score = Math.min(100, findings.reduce((sum, finding) => sum + finding.weight, 0));
    const critical = findings.some(finding => ["secret_exfiltration", "tool_execution"].includes(finding.id));
    return { verdict: score >= 40 || critical ? "blocked" : "allowed", score, findings, critical, truncated: chars.length > MAX_INPUT_CHARS, inputLength: chars.length };
  }
  const api = Object.freeze({ assess, MAX_INPUT_CHARS });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Guardrail = api;
})(globalThis);
