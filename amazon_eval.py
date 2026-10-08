"""Screenshot-backed reference and task checks for the saved Device Deals page."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from playwright.sync_api import Page

DISCOUNT = re.compile(r"(?<!\w)(\d{1,2})%\s*off\b", re.I)
GRID_CARD = "div[class*='ProductCard-module__card_']"
TITLE = "p[class*='ProductCard-module__title_'] .a-truncate-cut"
HERO = ((60, "Ring camera and display bundle"), (32, "Kindle reader"),
        (40, "Echo display"), (50, "Echo speaker"))


def snapshot_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_snapshot(page: Page, path: Path, output: Path) -> dict:
    """Capture vertical screenshots; transcribe only text rendered on visible cards."""
    output.mkdir(parents=True, exist_ok=True)
    height = page.evaluate("document.documentElement.scrollHeight")
    if height <= 800 or "Device Deals" not in page.title():
        raise RuntimeError("Amazon Device Deals snapshot did not render or cannot scroll")
    cards = page.locator(GRID_CARD)
    seen = {}
    screenshots = []
    for index, y in enumerate(range(0, height, 600)):
        page.evaluate("y => window.scrollTo(0, y)", y)
        page.wait_for_timeout(120)
        actual = page.evaluate("window.scrollY")
        name = f"audit_{index:02d}.png"
        page.screenshot(path=str(output / name))
        screenshots.append({"file": name, "scroll_y": actual})
        for card_index in range(cards.count()):
            if card_index in seen:
                continue
            card = cards.nth(card_index)
            badge = card.get_by_text(DISCOUNT).first
            title = card.locator(TITLE).first
            if not badge.count() or not title.count():
                continue
            badge_box, title_box = badge.bounding_box(), title.bounding_box()
            if not badge_box or not title_box:
                continue
            if (min(badge_box["y"], title_box["y"]) < 0 or
                    max(badge_box["y"] + badge_box["height"],
                        title_box["y"] + title_box["height"]) > 800):
                continue
            match = DISCOUNT.search(badge.inner_text())
            visible_name = title.inner_text().strip()
            if not match or not visible_name:
                continue
            seen[card_index] = {"id": f"grid_{card_index + 1}", "name": visible_name,
                                "discount_percent": int(match.group(1)),
                                "evidence": name}
    bottom = page.evaluate("window.scrollY + innerHeight >= document.documentElement.scrollHeight - 2")
    if not bottom:
        raise RuntimeError("Amazon Device Deals snapshot bottom was unreachable")
    grid = [seen[i] for i in sorted(seen)]
    # The four hero badges are visible in audit_00; their product names are not
    # printed there, so use only the visible device category.
    hero = [{"id": f"hero_{i}", "name": category, "discount_percent": pct,
             "evidence": "audit_00.png"} for i, (pct, category) in enumerate(HERO, 1)]
    items = hero + grid
    if len(grid) != cards.count() or len(items) < 3:
        raise RuntimeError(f"Amazon snapshot shows {len(grid)}/{cards.count()} readable grid discounts")
    reference = {"snapshot_sha256": snapshot_hash(path), "page_height": height,
                 "bottom_reached": bottom, "screenshots": screenshots, "items": items,
                 "ranking": [x["id"] for x in sorted(items, key=lambda x: x["discount_percent"])[:3]]}
    (output / "reference.json").write_text(json.dumps(reference, ensure_ascii=False, indent=2), encoding="utf-8")
    return reference


def evaluate_amazon(trajectory: list[dict], reference: dict, bottom_y: int) -> dict:
    """Compare the agent's reported observations with the independent reference."""
    observations = []
    for step in trajectory:
        for item in (step.get("agent_state") or {}).get("observations", []):
            observations.append({**item, "step": step["step"],
                                 "screenshot": step["observation"]["screenshot"]})
    bottom = any((step.get("observation") or {}).get("scroll_y", -1) >= bottom_y
                 for step in trajectory)
    # Accept a screenshot-grounded short name when it unambiguously matches
    # the beginning of the printed product title and has the same percentage.
    def norm(item):
        return re.sub(r"[^a-z0-9]", "", item.get("name", "").lower())

    def same(actual, expected):
        if actual.get("discount_percent") != expected["discount_percent"]:
            return False
        if expected["id"].startswith("hero_"):
            return actual["step"] <= 2
        left, right = norm(actual), norm(expected)
        return len(left) >= 8 and (left in right or right in left)

    matched = set()
    for expected in reference["items"]:
        for index, actual in enumerate(observations):
            if index not in matched and same(actual, expected):
                matched.add(index)
                break
    collection = len(matched) == len(reference["items"])
    states = [step.get("agent_state") or {} for step in trajectory]
    final = next((s for s in reversed(states) if s.get("current_subtask") == "S5"), {})
    ranking = final.get("ranking") or []
    by_id = {item["id"]: item for item in reference["items"]}
    expected_ranked = [by_id[item_id] for item_id in reference["ranking"]]
    ranking_correct = (len(ranking) == 3 and all(
        actual.get("discount_percent") == expected_item["discount_percent"]
        and len(norm(actual)) >= 8
        and (norm(actual) in norm(expected_item) or norm(expected_item) in norm(actual))
        for actual, expected_item in zip(ranking, expected_ranked)))
    return {"page_traversal_completed": bottom,
            "discount_collection_completed": collection,
            "collected_count": len(matched), "reference_count": len(reference["items"]),
            "ranking_correct": ranking_correct,
            "reference_ranking": expected_ranked,
            "reported_ranking": ranking,
            "observations": observations}
