"""Nightly retrieval evaluation for Guardian memory."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session, select

from app.models import ChatMeetingArtifact, MeetingArtifactType
from app.services.guardian import guardian_suite_inventory, memory


@dataclass(frozen=True)
class EvalCase:
    query: str
    expected_terms: tuple[str, ...]
    source: str


def _terms_from_text(text: str, limit: int = 5) -> tuple[str, ...]:
    terms: list[str] = []
    for raw in text.replace("_", " ").replace("-", " ").split():
        term = "".join(ch for ch in raw.lower() if ch.isalnum())
        if len(term) < 4 or term in terms:
            continue
        terms.append(term)
        if len(terms) >= limit:
            break
    return tuple(terms)


def _inventory_cases() -> list[EvalCase]:
    cases: list[EvalCase] = []
    for component in guardian_suite_inventory():
        name = str(component.get("name") or "").strip()
        description = str(component.get("description") or "").strip()
        if not name or not description:
            continue
        cases.append(
            EvalCase(
                query=description,
                expected_terms=_terms_from_text(f"{name} {description}"),
                source=f"guardian_suite:{name}",
            )
        )
    return cases


def _meeting_cases(session: Session | None, *, limit: int = 20) -> list[EvalCase]:
    if session is None:
        return []
    rows = session.exec(
        select(ChatMeetingArtifact)
        .where(ChatMeetingArtifact.type.in_([MeetingArtifactType.NOTES, MeetingArtifactType.DECISIONS, MeetingArtifactType.ACTION_ITEMS]))
        .order_by(ChatMeetingArtifact.created_at.desc())
        .limit(max(1, min(limit, 100)))
    ).all()
    cases: list[EvalCase] = []
    for artifact in rows:
        text = " ".join((artifact.content_markdown or "").split())
        if not text:
            continue
        query = text[:400]
        terms = _terms_from_text(text, limit=7)
        if terms:
            cases.append(
                EvalCase(
                    query=query,
                    expected_terms=terms,
                    source=f"meeting_recorder:{artifact.type.value}:{artifact.id}",
                )
            )
    return cases


def _precision_at_5(items: list[dict[str, Any]], expected_terms: tuple[str, ...]) -> float:
    if not expected_terms:
        return 0.0
    hits = 0
    for item in items[:5]:
        haystack = str(item.get("content") or "").lower()
        if any(term in haystack for term in expected_terms):
            hits += 1
    return hits / 5.0


def run_retrieval_eval(
    *,
    session: Session | None = None,
    user_id: str = "guardian-eval",
    room_id: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Compute precision@5 and latency for BM25 and hybrid retriever modes."""
    cases = _inventory_cases() + _meeting_cases(session)
    modes = ["fts", "hybrid"]
    mode_results: dict[str, dict[str, Any]] = {}
    for mode in modes:
        precision_values: list[float] = []
        latency_values: list[float] = []
        evaluated_cases = 0
        for case in cases:
            started = time.perf_counter()
            results = memory.recall_relevant_events(
                user_id=user_id,
                room_id=room_id,
                query=case.query,
                limit=limit,
                mode=mode,
            )
            latency_values.append((time.perf_counter() - started) * 1000.0)
            precision_values.append(_precision_at_5(results, case.expected_terms))
            evaluated_cases += 1
        mode_results[mode] = {
            "cases": evaluated_cases,
            "precision@5": round(sum(precision_values) / len(precision_values), 4) if precision_values else 0.0,
            "avg_latency_ms": round(sum(latency_values) / len(latency_values), 2) if latency_values else 0.0,
        }
    preferred = "hybrid" if mode_results["hybrid"]["precision@5"] > mode_results["fts"]["precision@5"] else "fts"
    return {
        "cases": len(cases),
        "modes": mode_results,
        "preferred_mode": preferred,
        "used_guardian_suite_inventory": True,
        "used_meeting_recorder_artifacts": session is not None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Guardian memory retrieval precision and latency.")
    parser.add_argument("--user-id", default="guardian-eval")
    parser.add_argument("--room-id", default=None)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    from app.core.db import engine

    with Session(engine) as session:
        result = run_retrieval_eval(
            session=session,
            user_id=args.user_id,
            room_id=args.room_id,
            limit=args.limit,
        )
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
