"""Independent reference for the three Ctrip hotel groups."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


def snapshot_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_ctrip(page, html_path: Path, reference_dir: Path) -> dict:
    cards = page.locator(".hotel-card")
    if cards.count() < 15:
        raise RuntimeError("Ctrip reference needs at least 15 hotel cards")
    items = []
    for index in range(15):
        lines = [line.strip() for line in cards.nth(index).inner_text().splitlines() if line.strip()]
        text = "\n".join(lines)
        prices = [int(value.replace(",", "")) for value in re.findall(r"¥\s*([\d,]+)", text)]
        reviews = re.search(r"([\d,]+)\s*条点评", text)
        if not prices or reviews is None:
            raise RuntimeError(f"Ctrip card {index + 1} lacks a visible price or review count")
        items.append({"index": index + 1, "name": lines[0],
                      "price": prices[-1], "reviews": int(reviews.group(1).replace(",", ""))})
    candidates = [min(items[start:start + 5], key=lambda item: (item["price"], item["index"]))
                  for start in (0, 5, 10)]
    recommendation = min(candidates, key=lambda item: (-item["reviews"], item["price"], item["index"]))
    reference = {"snapshot_sha256": snapshot_sha256(html_path), "items": items,
                 "candidates": candidates, "recommendation": recommendation}
    reference_dir.mkdir(parents=True, exist_ok=True)
    (reference_dir / "reference.json").write_text(
        json.dumps(reference, ensure_ascii=False, indent=2), encoding="utf-8")
    return reference


def evaluate_ctrip(trajectory: list[dict], reference: dict) -> dict:
    final = next((step for step in reversed(trajectory)
                  if step.get("agent_state", {}).get("current_subtask") == "S5"
                  and step["agent_state"].get("subtask_status") == "completed"
                  and step.get("action", {}).get("type") == "stop"), None)
    summary = (final or {}).get("agent_state", {}).get("progress_summary", "")
    compact = summary.replace(",", "").replace("，", "")
    candidate_facts_match = all(
        f"¥{item['price']}" in compact and str(item["reviews"]) in compact
        for item in reference["candidates"]
    )
    recommendation_text = compact.rsplit("推荐", 1)[-1] if "推荐" in compact else ""
    expected = reference["recommendation"]
    recommendation_correct = (
        str(expected["reviews"]) in recommendation_text
        and (bool(re.search(rf"第\s*{expected['index']}\s*个", recommendation_text))
             or expected["name"] in recommendation_text)
    )
    return {"candidate_facts_match": candidate_facts_match,
            "recommendation_correct": recommendation_correct,
            "reference_candidates": reference["candidates"],
            "reference_recommendation": expected,
            "reported_final_summary": summary}
