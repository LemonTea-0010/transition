"""Rebuild clean observation images from preserved trajectory scroll positions.

These images reproduce the saved page viewport and are not byte-identical to the
original observation images. Raw model-attempt logs cannot be reconstructed.
"""

import base64
import json
from pathlib import Path
import sys
from urllib.parse import quote

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from environment.server import LocalEnvironment
from transition_experiment.tasks import ROOT, TASKS


BATCH = Path(__file__).resolve().parent
TASK_IDS = (
    "taobao_compare_001",
    "bilibili_video_compare_001",
    "amazon_product_compare_001",
)


def to_webp(converter, png: bytes) -> bytes:
    encoded = converter.evaluate("""async (source) => {
      const response = await fetch('data:image/png;base64,' + source);
      const bitmap = await createImageBitmap(await response.blob());
      const canvas = document.createElement('canvas');
      canvas.width = bitmap.width; canvas.height = bitmap.height;
      canvas.getContext('2d').drawImage(bitmap, 0, 0);
      bitmap.close();
      return canvas.toDataURL('image/webp', .85).split(',')[1];
    }""", base64.b64encode(png).decode("ascii"))
    return base64.b64decode(encoded)


with LocalEnvironment(ROOT / "environment" / "normal_page", port=18810) as server:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for task_id in TASK_IDS:
            task = TASKS[task_id]
            output = BATCH / task_id / "clean"
            trajectory = json.loads((output / "trajectory.json").read_text(encoding="utf-8"))
            context = browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
            context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(server.base_url)
                          or route.request.url.startswith(("data:", "blob:")) else route.abort())
            page = context.new_page()
            converter = context.new_page()
            relative = task.path.relative_to(ROOT / "environment" / "normal_page")
            page.goto(server.base_url + "/" + quote(relative.as_posix()), wait_until="domcontentloaded")
            page.wait_for_timeout(1000)
            shots = output / "screenshots"
            shots.mkdir(exist_ok=True)
            for step in trajectory:
                scroll_y = step["observation"].get("scroll_y") or 0
                page.evaluate("y => window.scrollTo(0, y)", scroll_y)
                page.wait_for_timeout(100)
                target = shots / f"step_{step['step']:03d}.webp"
                target.write_bytes(to_webp(converter, page.screenshot()))
            (shots / "final.webp").write_bytes(to_webp(converter, page.screenshot()))
            print(f"{task_id}: restored {len(trajectory)} screenshots", flush=True)
            context.close()
        browser.close()
