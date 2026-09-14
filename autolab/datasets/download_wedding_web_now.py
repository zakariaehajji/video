"""Download legal Mixkit wedding clips missing from the local library."""

from __future__ import annotations

import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "resource" / "video" / "library" / "mixkit"
ALLOW = ROOT / "autolab" / "datasets" / "wedding_mixkit_ids.txt"
HDR = {"User-Agent": "Mozilla/5.0"}


def main() -> None:
    LIB.mkdir(parents=True, exist_ok=True)
    allow = [ln.strip() for ln in ALLOW.read_text(encoding="utf-8").splitlines() if ln.strip()]
    have: set[str] = set()
    for p in LIB.glob("mixkit_*.mp4"):
        if p.stat().st_size > 50_000:
            have.add(p.stem.replace("mixkit_", ""))
    need = [i for i in allow if i not in have]
    print(
        f"bridal allow={len(allow)} have={len(have.intersection(allow))} need={len(need)}",
        flush=True,
    )

    fresh: set[str] = set()
    for page in range(1, 8):
        url = (
            "https://mixkit.co/free-stock-video/wedding/"
            if page == 1
            else f"https://mixkit.co/free-stock-video/wedding/?page={page}"
        )
        try:
            html = urllib.request.urlopen(
                urllib.request.Request(url, headers=HDR), timeout=30
            ).read().decode("utf-8", "ignore")
            fresh |= set(re.findall(r"/free-stock-video/[a-z0-9\-]+-(\d+)/", html))
            fresh |= set(re.findall(r"assets\.mixkit\.co/videos/(\d+)/", html))
            print(f"  scraped page {page}: total fresh ids {len(fresh)}", flush=True)
        except Exception as e:
            print(f"scrape fail {page}: {e}", flush=True)
            break

    queue: list[str] = []
    for i in need + sorted(fresh):
        if i not in have and i not in queue:
            queue.append(i)
    queue = queue[:50]
    print(f"downloading up to {len(queue)} clips...", flush=True)

    ok = 0
    fail = 0
    for vid in queue:
        dest = LIB / f"mixkit_{vid}.mp4"
        if dest.exists() and dest.stat().st_size > 50_000:
            ok += 1
            continue
        got = False
        for q in ("720", "360"):
            url = f"https://assets.mixkit.co/videos/{vid}/{vid}-{q}.mp4"
            try:
                req = urllib.request.Request(url, headers=HDR)
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                if len(data) > 50_000:
                    dest.write_bytes(data)
                    print(f"  OK {vid} @{q} {len(data) // 1024}KB", flush=True)
                    ok += 1
                    got = True
                    break
            except Exception:
                pass
            time.sleep(0.15)
        if not got:
            print(f"  FAIL {vid}", flush=True)
            fail += 1
        time.sleep(0.25)

    nlib = len(list(LIB.glob("*.mp4")))
    print(f"DONE ok={ok} fail={fail} library={nlib}", flush=True)


if __name__ == "__main__":
    main()
