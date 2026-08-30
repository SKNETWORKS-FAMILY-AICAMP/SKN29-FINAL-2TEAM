"""Cheap, explainable successor analysis for non-terminal text blocks.

This module only proposes relations. It never mutates a document and never
auto-applies a correction; promotion belongs to the evaluated policy layer.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import re
from time import perf_counter
from typing import Any

from .features import add_spatial_features
from .semantic_scope import filter_ordering_records


TEXT_LABELS = frozenset({"text", "paragraph"})
TERMINAL_MARKS = (".", "!", "?", "。", "！", "？")
CLOSING_MARKS = "\"'”’)]}》〉」』】"

# These are deliberately surface-form features, not a replacement for Korean
# morphological analysis.  Ambiguous one-syllable connective endings such as
# bare ``고`` are excluded because nouns and labels can end with the same text.
KOREAN_OPEN_CLAUSE_ENDINGS = (
    "기 때문에",
    "기 위해",
    "함으로써",
    "하면서도",
    "하더라도",
    "하였지만",
    "하였으나",
    "되었지만",
    "되었으나",
    "으면서",
    "으므로",
    "더라도",
    "했지만",
    "했으나",
    "하지만",
    "하면서",
    "하는데",
    "하므로",
    "하거나",
    "하도록",
    "하여",
    "해서",
    "하며",
    "하고",
    "되면서",
    "되지만",
    "되는데",
    "되므로",
    "되어서",
    "으며",
    "면서",
    "지만",
    "는데",
    "은데",
    "거나",
    "도록",
    "다가",
    "아서",
    "어서",
    "므로",
    "니까",
)
KOREAN_FINAL_ENDINGS = (
    "있습니까",
    "없습니까",
    "합니까",
    "됩니까",
    "습니까",
    "입니까",
    "하십시오",
    "습니다",
    "합니다",
    "됩니다",
    "입니다",
    "하였습니다",
    "되었습니다",
    "하였다",
    "되었다",
    "했습니다",
    "됐습니다",
    "했다",
    "됐다",
    "한다",
    "된다",
    "있다",
    "없다",
    "이다",
    "였다",
    "이에요",
    "있나요",
    "없나요",
    "하나요",
    "되나요",
    "인가요",
    "예요",
    "해요",
    "돼요",
    "네요",
    "군요",
    "지요",
    "세요",
    "나요",
    "까요",
    "죠",
    "다",
    "요",
)
KOREAN_PARTICLE_GROUPS = {
    "object": ("을", "를"),
    "topic_or_subject": ("은", "는", "이", "가"),
    "adverbial": ("에서", "에게", "으로", "로"),
    "connective": ("와", "과"),
}
_HANGUL_RE = re.compile(r"[가-힣]")


@dataclass(frozen=True)
class ContinuationConfig:
    """Conservative defaults; thresholds are experimental until corpus validation."""

    max_candidates_per_anchor: int = 4
    max_down_gap_norm: float = 0.08
    min_down_horizontal_overlap: float = 0.5
    max_side_gap_norm: float = 0.05
    min_side_vertical_overlap: float = 0.65
    min_size_similarity: float = 0.55
    auto_score_threshold: float = 0.82
    auto_margin_threshold: float = 0.15
    min_paragraph_characters: int = 20
    min_paragraph_tokens: int = 7
    min_korean_paragraph_tokens: int = 3
    min_korean_syllables: int = 12


def _overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))


def _horizontal_overlap(first: dict[str, Any], second: dict[str, Any]) -> float:
    return _overlap(
        first["left_norm"], first["right_norm"],
        second["left_norm"], second["right_norm"],
    ) / max(min(first["width_norm"], second["width_norm"]), 1e-9)


def _vertical_overlap(first: dict[str, Any], second: dict[str, Any]) -> float:
    return _overlap(
        first["bottom_norm"], first["top_norm"],
        second["bottom_norm"], second["top_norm"],
    ) / max(min(first["height_norm"], second["height_norm"]), 1e-9)


def _size_similarity(first: dict[str, Any], second: dict[str, Any]) -> float:
    width = min(first["width_norm"], second["width_norm"]) / max(
        first["width_norm"], second["width_norm"], 1e-9
    )
    height = min(first["height_norm"], second["height_norm"]) / max(
        first["height_norm"], second["height_norm"], 1e-9
    )
    return min(width, height)


def _strip_closing_marks(text: str) -> str:
    return text.rstrip().rstrip(CLOSING_MARKS).rstrip()


def _ends_terminal_mark(text: str) -> bool:
    return _strip_closing_marks(text).endswith(TERMINAL_MARKS)


def _has_unclosed_delimiter(text: str) -> bool:
    pairs = (("(", ")"), ("[", "]"), ("{", "}"), ("《", "》"), ("「", "」"), ("『", "』"))
    return any(text.count(opening) > text.count(closing) for opening, closing in pairs)


def _cheap_text_continuity(first_text: str, second_text: str) -> dict[str, Any]:
    """Return auditable, low-cost multilingual evidence.

    The evidence is intentionally divided into strong/supporting/weak signals.
    Weak Korean particle suffixes are observable but cannot by themselves open
    the automatic-reorder gate.  Closed Korean endings act as a counter-signal.
    """

    contributions: list[dict[str, Any]] = []

    def add(reason: str, family: str, weight: float, strength: str) -> None:
        contributions.append(
            {
                "reason": reason,
                "family": family,
                "weight": weight,
                "strength": strength,
            }
        )

    first = first_text.rstrip()
    second = second_text.lstrip()
    if first.endswith(("-", "‐", "‑")):
        add("hyphenated_tail", "fragment_boundary", 1.0, "strong")
    if second and (second[0].islower() or second[0] in ",;:)]}%"):
        add("continuation_like_start", "next_block_start", 0.7, "strong")
    if first.endswith((",", ";", ":")):
        add("open_punctuation_tail", "fragment_boundary", 0.65, "strong")
    if _has_unclosed_delimiter(first):
        add("unclosed_delimiter_tail", "fragment_boundary", 0.75, "strong")

    lexical_tail = _strip_closing_marks(first)
    open_ending = next(
        (ending for ending in KOREAN_OPEN_CLAUSE_ENDINGS if lexical_tail.endswith(ending)),
        None,
    )
    closed_ending = next(
        (ending for ending in KOREAN_FINAL_ENDINGS if lexical_tail.endswith(ending)),
        None,
    )
    # Explicit final endings take precedence: for example, the interrogative
    # ``합니까`` also has the surface suffix ``니까`` but is a closed clause.
    # Punctuation tails were not stripped, so ``합니다,`` remains open.
    counter_reasons: list[str] = []
    counter_score = 0.0
    if closed_ending is not None:
        counter_reasons.append("korean_closed_clause_tail")
        counter_score = 1.0
    elif open_ending is not None:
        add("korean_open_clause_tail", "korean_clause_ending", 0.55, "supporting")

    # Particles are intentionally weak: surface matching cannot reliably tell
    # particles from labels/nouns without a tokenizer. They improve audit and
    # ranking only and never satisfy the automatic text-evidence gate alone.
    if lexical_tail and _HANGUL_RE.search(lexical_tail):
        for group, endings in KOREAN_PARTICLE_GROUPS.items():
            if lexical_tail.endswith(endings):
                add(f"korean_{group}_particle_tail", "korean_particle", 0.15, "weak")
                break

    positive_score = min(sum(item["weight"] for item in contributions), 1.0)
    score = max(0.0, positive_score - counter_score)
    strengths = {item["strength"] for item in contributions}
    if "strong" in strengths:
        evidence_strength = "strong"
    elif "supporting" in strengths:
        evidence_strength = "supporting"
    elif "weak" in strengths:
        evidence_strength = "weak"
    else:
        evidence_strength = "none"
    auto_gate_passed = (
        evidence_strength in {"strong", "supporting"} and counter_score == 0.0
    )
    return {
        "score": round(score, 6),
        "positive_score": round(positive_score, 6),
        "counter_score": round(counter_score, 6),
        "evidence_strength": evidence_strength,
        "auto_gate_passed": auto_gate_passed,
        "reasons": [item["reason"] for item in contributions],
        "counter_reasons": counter_reasons,
        "contributions": contributions,
    }


def _paragraph_profile(text: str, config: ContinuationConfig) -> dict[str, Any]:
    token_count = len(text.split())
    hangul_syllable_count = len(_HANGUL_RE.findall(text))
    common_length_gate = len(text) >= config.min_paragraph_characters
    general_gate = token_count >= config.min_paragraph_tokens
    korean_gate = (
        hangul_syllable_count >= config.min_korean_syllables
        and token_count >= config.min_korean_paragraph_tokens
    )
    return {
        "is_paragraph_like": common_length_gate and (general_gate or korean_gate),
        "character_count": len(text),
        "token_count": token_count,
        "hangul_syllable_count": hangul_syllable_count,
        "matched_profile": "korean" if common_length_gate and korean_gate else "general" if common_length_gate and general_gate else "none",
    }


def _candidate(
    anchor: dict[str, Any], item: dict[str, Any], config: ContinuationConfig
) -> dict[str, Any] | None:
    size_similarity = _size_similarity(anchor, item)
    if size_similarity < config.min_size_similarity:
        return None

    horizontal_overlap = _horizontal_overlap(anchor, item)
    vertical_overlap = _vertical_overlap(anchor, item)
    down_gap = anchor["bottom_norm"] - item["top_norm"]
    side_gap = item["left_norm"] - anchor["right_norm"]

    if 0 <= down_gap <= config.max_down_gap_norm and horizontal_overlap >= config.min_down_horizontal_overlap:
        direction = "DOWN"
        proximity = 1.0 - down_gap / max(config.max_down_gap_norm, 1e-9)
        alignment = horizontal_overlap
    elif 0 <= side_gap <= config.max_side_gap_norm and vertical_overlap >= config.min_side_vertical_overlap:
        direction = "RIGHT"
        proximity = 1.0 - side_gap / max(config.max_side_gap_norm, 1e-9)
        alignment = vertical_overlap
    else:
        return None

    text_evidence = _cheap_text_continuity(
        str(anchor.get("text") or ""), str(item.get("text") or "")
    )
    text_score = text_evidence["score"]
    same_parent = anchor.get("parent_ref") == item.get("parent_ref")
    parent_score = 1.0 if same_parent else 0.0
    total = (
        0.35 * proximity
        + 0.30 * alignment
        + 0.20 * size_similarity
        + 0.10 * parent_score
        + 0.05 * text_score
    )
    return {
        "candidate_ref": item["self_ref"],
        "direction": direction,
        "score": round(total, 6),
        "score_breakdown": {
            "proximity": round(proximity, 6),
            "alignment": round(alignment, 6),
            "size_similarity": round(size_similarity, 6),
            "same_parent": same_parent,
            "cheap_text_continuity": round(text_score, 6),
            "cheap_text_positive": text_evidence["positive_score"],
            "cheap_text_counter": text_evidence["counter_score"],
        },
        "text_reasons": text_evidence["reasons"],
        "text_counter_reasons": text_evidence["counter_reasons"],
        "text_evidence": text_evidence,
        "geometry": {
            "down_gap_norm": round(down_gap, 6),
            "side_gap_norm": round(side_gap, 6),
            "horizontal_overlap": round(horizontal_overlap, 6),
            "vertical_overlap": round(vertical_overlap, 6),
        },
        "observed_order_delta": item["order_index"] - anchor["order_index"],
    }


def analyze_continuation_successors(
    document: dict[str, Any],
    records: list[dict[str, Any]],
    config: ContinuationConfig | None = None,
) -> dict[str, Any]:
    """Rank nearby DOWN/RIGHT successors and expose ambiguity and timings."""

    started = perf_counter()
    active = config or ContinuationConfig()
    required = filter_ordering_records(records)
    enriched = add_spatial_features(document, required)
    text_records = [item for item in enriched if item["label"] in TEXT_LABELS]
    pages: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in text_records:
        pages[item["page_no"]].append(item)

    analyses: list[dict[str, Any]] = []
    evaluated_pairs = 0
    for anchor in text_records:
        anchor_text = str(anchor.get("text") or "").rstrip()
        if not anchor_text or _ends_terminal_mark(anchor_text):
            continue
        ranked = []
        for item in pages[anchor["page_no"]]:
            if item["self_ref"] == anchor["self_ref"]:
                continue
            evaluated_pairs += 1
            candidate = _candidate(anchor, item, active)
            if candidate is not None:
                ranked.append(candidate)
        ranked.sort(key=lambda item: (-item["score"], item["candidate_ref"]))
        ranked = ranked[: active.max_candidates_per_anchor]
        if not ranked:
            continue
        best = ranked[0]
        runner_up_score = ranked[1]["score"] if len(ranked) > 1 else 0.0
        margin = best["score"] - runner_up_score
        paragraph_profile = _paragraph_profile(anchor_text, active)
        paragraph_like = paragraph_profile["is_paragraph_like"]
        explicit_text_continuity = best["text_evidence"]["auto_gate_passed"]
        text_counter_signal = bool(best["text_counter_reasons"])
        auto_blockers: list[str] = []
        if not paragraph_like:
            auto_blockers.append("not_paragraph_like")
        if not explicit_text_continuity:
            auto_blockers.append("no_explicit_text_continuity")
        if text_counter_signal:
            auto_blockers.append("text_counter_signal")
        if best["score"] < active.auto_score_threshold:
            auto_blockers.append("score_below_threshold")
        if margin < active.auto_margin_threshold:
            auto_blockers.append("margin_below_threshold")
        if (
            best["observed_order_delta"] == 1
            and margin >= active.auto_margin_threshold
            and not text_counter_signal
        ):
            decision = "PRESERVE_CONFIRMED"
        elif (
            best["observed_order_delta"] > 1
            and paragraph_like
            and explicit_text_continuity
            and best["score"] >= active.auto_score_threshold
            and margin >= active.auto_margin_threshold
        ):
            decision = "AUTO_REORDER_ELIGIBLE"
        else:
            decision = "REVIEW_REQUIRED"
        analyses.append(
            {
                "page_no": anchor["page_no"],
                "anchor_ref": anchor["self_ref"],
                "anchor_text": anchor_text,
                "paragraph_like": paragraph_like,
                "paragraph_profile": paragraph_profile,
                "explicit_text_continuity": explicit_text_continuity,
                "text_evidence_strength": best["text_evidence"]["evidence_strength"],
                "text_counter_signal": text_counter_signal,
                "auto_blockers": auto_blockers,
                "decision": decision,
                "best_successor_ref": best["candidate_ref"],
                "best_direction": best["direction"],
                "best_score": best["score"],
                "needs_reorder": best["observed_order_delta"] != 1,
                "runner_up_score": runner_up_score,
                "score_margin": round(margin, 6),
                "candidates": ranked,
            }
        )

    elapsed = perf_counter() - started
    return {
        "schema_version": "1.1",
        "mode": "ANALYSIS_ONLY",
        "source_mutated": False,
        "config": asdict(active),
        "metrics": {
            "page_count": len(pages),
            "text_record_count": len(text_records),
            "nonterminal_analysis_count": len(analyses),
            "evaluated_pair_count": evaluated_pairs,
            "elapsed_seconds": round(elapsed, 6),
            "milliseconds_per_page": round(1000 * elapsed / max(len(pages), 1), 6),
            "external_model_calls": 0,
        },
        "analyses": analyses,
    }
