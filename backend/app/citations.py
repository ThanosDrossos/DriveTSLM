"""Citation validator: the accountability core of the PoC.

The agent must write every quantitative claim as a markdown-style citation
`[claim text](T3)` where T3 is the id of a prior tool call. This module
checks that every number inside the claim actually appears in that tool
call's result, and flags quantitative statements that carry no citation.

Matching rules (deliberately strict, unit-aware, rounding-consistent):
- A claimed number is valid against a result value if the result value,
  rounded to the precision the claim states, equals the claim
  ("5.2 g" matches 5.23; "3 g" matches 3.47 but not 3.6).
- Unit conversions are tried on the result values: km/h<->m/s, mph<->km/h,
  g<->m/s^2, s<->ms, fractions<->percent.
- A citation with no numbers is allowed (qualitative claim citing evidence).
- Numbers embedded in identifiers (T3, V1, vz_12345, accel_x) are ignored.

Verdict per citation: valid | invalid (numbers not found) | unknown_tool_id.
Uncited quantitative claims are reported with the offending numbers.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

CITATION_RE = re.compile(r"\[([^\]]+)\]\((T\d+)\)")
# numbers not glued to letters/underscores on the left (skips T3, vz_123, V1)
NUMBER_RE = re.compile(r"(?<![A-Za-z_0-9.])-?\d+(?:\.\d+)?")
WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
UNIT_WORDS = r"(?:g|km/h|kph|mph|m/s\^?2?|deg/s|deg|degrees|s|sec|seconds|ms|rpm|%|hz)"
UNCITED_NUM_RE = re.compile(
    rf"(?<![A-Za-z_0-9.])-?\d+(?:\.\d+)?\s*{UNIT_WORDS}(?![A-Za-z])|"
    rf"(?:t\s*=\s*|at\s+)-?\d+(?:\.\d+)?|"
    rf"(?<![A-Za-z_0-9.])-?\d+\.\d+",
    re.IGNORECASE,
)
COUNT_NOUNS_RE = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
    r"(?:distinct\s+|separate\s+)?(impacts?|spikes?|collisions?|events?|detections?)\b",
    re.IGNORECASE,
)

# Conversion factors applied to TOOL values, keyed by the unit the CLAIM
# states. Tool outputs are in g, km/h, deg(/s), s, ms, rpm, %, fractions.
# Blind cross-unit matching is dangerous (2.5 [g threshold] * 1.609 ~ 4 "km/h"),
# so a conversion is only tried when the claim's own unit justifies it.
UNIT_FACTORS: dict[str | None, tuple[float, ...]] = {
    None: (1.0,),
    "g": (1.0, 1 / 9.80665),          # claim g, tool m/s^2 (not emitted, but safe)
    "m/s^2": (9.80665,), "m/s2": (9.80665,), "ms2": (9.80665,),
    "km/h": (1.0,), "kph": (1.0,),
    "mph": (1 / 1.60934,),            # tool km/h -> claim mph
    "m/s": (1 / 3.6,),                # tool km/h -> claim m/s
    "%": (1.0, 100.0),                # tool fraction -> claim percent
    "s": (1.0, 1 / 1000.0), "sec": (1.0, 1 / 1000.0), "seconds": (1.0, 1 / 1000.0),
    "ms": (1.0, 1000.0),
    "deg": (1.0,), "degrees": (1.0,), "deg/s": (1.0,),
    "rpm": (1.0,), "hz": (1.0,),
}
NUM_UNIT_RE = re.compile(
    rf"(?<![A-Za-z_0-9.])(-?\d+(?:\.\d+)?)\s*({UNIT_WORDS})?(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    return (text.replace("−", "-").replace("–", "-")
            .replace("—", "-").replace(",", ""))


def _canon_unit(u: str | None) -> str | None:
    if not u:
        return None
    u = u.lower().replace("^", "")
    return {"kph": "km/h", "sec": "s", "seconds": "s", "degrees": "deg",
            "ms2": "m/s^2", "m/s2": "m/s^2"}.get(u, u)


def _claim_numbers(text: str) -> list[tuple[str, str | None]]:
    """(number_string, unit_or_None) pairs stated in a claim."""
    text = _normalize(text)
    pairs = [(m.group(1), _canon_unit(m.group(2))) for m in NUM_UNIT_RE.finditer(text)]
    for w, n in WORD_NUMBERS.items():
        if re.search(rf"\b{w}\b", text, re.IGNORECASE):
            pairs.append((str(n), None))
    return pairs


def flatten_numbers(obj, out: set[float] | None = None) -> set[float]:
    """All numeric values in a tool result, including numbers inside strings."""
    if out is None:
        out = set()
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, str):
        for m in NUMBER_RE.findall(_normalize(obj)):
            out.add(float(m))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k == "tool_call_id":
                continue
            flatten_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            flatten_numbers(v, out)
    return out


def _decimals(num_str: str) -> int:
    return len(num_str.split(".")[1]) if "." in num_str else 0


def number_supported(num_str: str, values: set[float], unit: str | None = None) -> bool:
    """True if some tool value, converted per the claim's stated unit, rounds
    to the claim at the claim's stated precision."""
    n = float(num_str)
    nd = _decimals(num_str)
    factors = UNIT_FACTORS.get(unit, (1.0,))
    for v in values:
        for f in factors:
            if round(v * f, nd) == round(n, nd):
                return True
            # sign-insensitive: tools report signed values, prose often drops the sign
            if round(abs(v) * f, nd) == round(abs(n), nd):
                return True
    return False


@dataclass
class CitationCheck:
    claim: str
    tool_id: str
    numbers: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    status: str = "valid"  # valid | invalid | unknown_tool_id


@dataclass
class ValidationReport:
    citations: list[CitationCheck]
    uncited: list[dict]
    n_valid: int
    n_invalid: int
    n_unknown_id: int
    n_uncited: int
    citation_validity_rate: float | None
    fully_grounded: bool

    def to_dict(self) -> dict:
        return {
            "citations": [vars(c) for c in self.citations],
            "uncited_quantitative_claims": self.uncited,
            "n_valid": self.n_valid,
            "n_invalid": self.n_invalid,
            "n_unknown_id": self.n_unknown_id,
            "n_uncited": self.n_uncited,
            "citation_validity_rate": self.citation_validity_rate,
            "fully_grounded": self.fully_grounded,
        }


def validate(answer_text: str, tool_results: dict[str, dict]) -> ValidationReport:
    """tool_results: mapping tool_call_id (e.g. "T3") -> the JSON result dict
    that was returned to the model for that call."""
    flattened: dict[str, set[float]] = {tid: flatten_numbers(res)
                                        for tid, res in tool_results.items()}
    checks: list[CitationCheck] = []
    for m in CITATION_RE.finditer(answer_text):
        claim, tid = m.group(1), m.group(2)
        pairs = _claim_numbers(claim)
        check = CitationCheck(claim=claim, tool_id=tid,
                              numbers=[f"{n} {u}" if u else n for n, u in pairs])
        if tid not in flattened:
            check.status = "unknown_tool_id"
        else:
            check.unmatched = [f"{n} {u}" if u else n for n, u in pairs
                               if not number_supported(n, flattened[tid], u)]
            if check.unmatched:
                check.status = "invalid"
        checks.append(check)

    # scan the remaining text (citations stripped) for uncited quantitative claims
    residual = CITATION_RE.sub(" ", answer_text)
    uncited: list[dict] = []
    seen_spans: set[tuple[int, int]] = set()
    for m in list(UNCITED_NUM_RE.finditer(residual)) + list(COUNT_NOUNS_RE.finditer(residual)):
        span = m.span()
        if any(a <= span[0] < b for a, b in seen_spans):
            continue
        seen_spans.add(span)
        ctx_lo = max(0, span[0] - 60)
        ctx_hi = min(len(residual), span[1] + 60)
        uncited.append({"match": m.group(0).strip(),
                        "context": residual[ctx_lo:ctx_hi].strip()})

    n_valid = sum(1 for c in checks if c.status == "valid")
    n_invalid = sum(1 for c in checks if c.status == "invalid")
    n_unknown = sum(1 for c in checks if c.status == "unknown_tool_id")
    rate = (n_valid / len(checks)) if checks else None
    return ValidationReport(
        citations=checks,
        uncited=uncited,
        n_valid=n_valid,
        n_invalid=n_invalid,
        n_unknown_id=n_unknown,
        n_uncited=len(uncited),
        citation_validity_rate=None if rate is None else round(rate, 3),
        fully_grounded=(n_invalid == 0 and n_unknown == 0 and len(uncited) == 0
                        and len(checks) > 0),
    )


def validate_json(answer_text: str, tool_results_json: str) -> dict:
    return validate(answer_text, json.loads(tool_results_json)).to_dict()
