#!/usr/bin/env python3
"""Generate docs/PILOT_EXAMPLES.md from the real benchmark records. READ-ONLY
with respect to the benchmark; writes only the markdown file.

Generated rather than hand-written so the document cannot drift from the data.

    python scripts/benchmark/make_examples_doc.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from semintegrity.benchmark.loader import is_frozen, load_split  # noqa: E402
from semintegrity.utils.paths import data_path  # noqa: E402

OUT = ROOT / "docs" / "PILOT_EXAMPLES.md"

# One per class where possible, spanning all three domains and all three answer
# types, and deliberately including the constraint that carries a recorded
# source discrepancy — an example set that hid the awkward case would misrepresent
# the benchmark.
SELECTED = ["K-C1-GEO-01", "K-C3-SCI-01", "K-C4-POL-01"]

CLASS_NAME = {
    "C1": "Atomic — a single proposition with direct mutual exclusion",
    "C2": "Conjunctive / relational — propositions that must hold jointly",
    "C3": "Quantified / rule-based — universal quantification with variable binding",
    "C4": "Temporal — reasoning over validity intervals or ordering",
}


def esc(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def main() -> int:
    directory = data_path("benchmark") / "pilot"
    constraints, probes = load_split(directory)
    by_cid = {c.constraint_id: c for c in constraints}
    probes_by: dict[str, list] = {}
    for p in probes:
        probes_by.setdefault(p.constraint_id, []).append(p)
    for g in probes_by.values():
        g.sort(key=lambda p: p.index)

    missing = [c for c in SELECTED if c not in by_cid]
    if missing:
        print(f"selected constraints not in the benchmark: {missing}", file=sys.stderr)
        return 2

    lines: list[str] = []
    lines.append("# Pilot benchmark — three worked examples\n")
    lines.append(
        f"Generated from the real records by `scripts/benchmark/make_examples_doc.py`, "
        f"so it cannot drift from the data. "
        f"**{len(constraints)} constraints · {len(probes)} probes · "
        f"all DRAFT · split frozen: {'yes' if is_frozen(directory) else 'no'}.**\n"
    )
    lines.append("Full inspection of all twelve:\n")
    lines.append("```bash\npython scripts/benchmark/inspect_pilot.py\n```\n")
    lines.append(
        "These three are chosen to span three classes, three domains and all three "
        "answer types, and the third deliberately includes the constraint carrying a "
        "recorded source discrepancy — an example set that showed only the clean cases "
        "would misrepresent the benchmark.\n"
    )
    lines.append("---\n")

    for n, cid in enumerate(SELECTED, start=1):
        c, ps = by_cid[cid], probes_by[cid]
        n_ok = sum(e.supports_gold for e in c.evidence)
        flag = any("DISCREPANCY" in (e.note or "") for e in c.evidence)

        lines.append(f"## {n}. `{c.constraint_id}` — {CLASS_NAME[c.constraint_class.value]}\n")
        lines.append("| | |\n|---|---|")
        lines.append(f"| **Class** | {c.constraint_class.value} |")
        lines.append(f"| **Domain** | {c.domain.value} |")
        lines.append(f"| **Family** | {c.family_id} (schema {c.schema_id}) |")
        lines.append(f"| **Answer type** | {c.answer_type.value} |")
        lines.append(f"| **Ground truth** | **{esc(c.gold_answer)}** |")
        lines.append(f"| **Answer space** | {', '.join(esc(a) for a in c.answer_space)} |")
        lines.append(f"| **Status** | **{c.verification_status.value}** — "
                 f"{n_ok}/{len(c.evidence)} machine checks pass; no human review |")
        lines.append("")
        lines.append(f"**In plain English:** {esc(c.constraint_text)}\n")
        lines.append(f"**Formal representation:** `{esc(c.notes.removeprefix('logical_form: '))}`  ")
        lines.append(f"**D0 predicate:** `{c.formal_predicate}`\n")
        lines.append(f"**Gold proposition:** {esc(c.gold_proposition)}\n")

        ents = ", ".join(f"{e.label} (`{e.qid}`, {e.sitelinks} sitelinks)" for e in c.entity_records)
        lines.append(f"**Entities:** {ents}\n")

        lines.append("### All 8 probes\n")
        lines.append("| Probe | In 5-probe run | Syntax | Polarity | Register | Direction | Expects | Question |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for p in ps:
            in_run = "yes" if "pilot_run_subset=yes" in p.notes else "—"
            lines.append(
                f"| `{p.probe_id.rsplit('-', 1)[1]}` | {in_run} | {p.syntax.value} | "
                f"{p.polarity.value} | {p.register.value} | {p.directionality.value} | "
                f"**{esc(p.expected_answer)}** | {esc(p.probe_text)} |"
            )
        lines.append("")
        lines.append(
            "Every `(polarity × register × direction)` cell appears exactly once — "
            "4 affirmative / 4 negated, 4 formal / 4 colloquial, 4 direct / 4 reverse. "
            "Syntax splits 3/3/2 because 8 is not divisible by 3 (ADR-0003).\n"
        )

        lines.append(f"### Evidence ({n_ok}/{len(c.evidence)} pass)\n")
        for e in c.evidence:
            mark = "PASS" if e.supports_gold else "FAIL"
            warn = " ⚠ **DISCREPANCY**" if "DISCREPANCY" in (e.note or "") else ""
            lines.append(f"- **[{mark}]**{warn} `{e.query}` — {esc(e.comparison)}  ")
            lines.append(f"  <{e.url}>, retrieved {e.retrieved_at}")
            if "DISCREPANCY" in (e.note or ""):
                lines.append(f"  > {esc(e.note)}")
        lines.append("")

        multi = [
            e for e in c.evidence
            if e.supports_gold and "," in e.observed_value and "count=" not in e.observed_value
        ]
        if multi:
            lines.append(
                "> **Note on multi-valued evidence.** The knowledge base returns more than "
                "one value for a check above; it passed because the expected value is among "
                "them. Wikidata records historical as well as current statements, so a "
                "constraint worded as \"exactly one\" can legitimately meet a KB statement "
                "that lists several. Whether the wording should be tightened is a question "
                "for human review.\n"
            )

        if c.ambiguity_notes:
            lines.append(f"**Known ambiguity:** {esc(c.ambiguity_notes)}\n")
        if flag:
            lines.append(
                "> **This constraint is blocked from EVIDENCE_VERIFIED** until the "
                "discrepancy is adjudicated by a human, even though every check passes. "
                "A check that confirms a discrepancy exists does not resolve it.\n"
            )
        lines.append("---\n")

    lines.append("## What these examples are not\n")
    lines.append(
        "- **Not verified.** All twelve constraints are `DRAFT`. Machine evidence "
        "confirms specific Wikidata statements; it does not establish that a constraint "
        "is well-posed, unambiguously worded or correctly classified.\n"
        "- **Not human-reviewed.** No person has checked any of this. The schema rejects "
        "`HUMAN_VALIDATED` without a named validator and date, so no script can claim it.\n"
        "- **Not frozen.** The pilot split carries no freeze manifest.\n"
        "- **Probe equivalence unvalidated.** §4.4.5 requires two blinded annotators per "
        "probe: 96 × 2 = 192 judgements, none performed.\n"
    )
    lines.append(
        "\n## One open decision these examples make concrete\n\n"
        "In example 1, probe `P01` expects `Canberra` while `P05`–`P08` expect `NO`. "
        "Whether those probe *the same question* — and so whether this constraint yields "
        "28 comparable pairs or two separate sets of 4 — depends on "
        "`EQUIVALENCE_KEY_FIELDS` in `schemas/probe.py`, which currently excludes "
        "`polarity`. This is **Q21**, deliberately unresolved. Both polarities are "
        "generated and each probe records its own expected answer, so either decision "
        "works on exactly this data.\n"
    )

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(lines)} lines) from {len(SELECTED)} constraints")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
