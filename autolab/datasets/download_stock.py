"""Download legal free wedding stock video into resource/video/library/.

Sources: Mixkit (no key), Pexels API, Pixabay API.
Resume-safe via autolab/datasets/manifest.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).resolve().parent
LIB = ROOT / "resource" / "video" / "library"
MANIFEST_PATH = DATA / "manifest.json"
QUERIES_PATH = DATA / "queries.json"

HEADERS = {"User-Agent": "WeddingAutoLab/1.0 (research; local dataset builder)"}


def load_dotenv_keys() -> None:
    load_dotenv(ROOT / "autolab" / ".env")


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"clips": {}, "stats": {"downloaded": 0, "skipped": 0, "failed": 0}}


def save_manifest(m: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(m, indent=2), encoding="utf-8")


def file_sha1(path: Path, limit: int = 2_000_000) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        h.update(f.read(limit))
    return h.hexdigest()


def download_file(url: str, dest: Path, timeout: int = 120) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp, tmp.open("wb") as out:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
        if tmp.stat().st_size < 50_000:
            tmp.unlink(missing_ok=True)
            return False
        tmp.replace(dest)
        return True
    except Exception:
        tmp.unlink(missing_ok=True)
        return False


def register(
    manifest: dict,
    *,
    source: str,
    source_id: str,
    path: Path,
    query: str,
    license_name: str,
    attribution: str = "",
    url: str = "",
) -> None:
    key = f"{source}:{source_id}"
    if key in manifest["clips"]:
        return
    sha = file_sha1(path) if path.exists() else ""
    # content-hash dedupe
    for existing in manifest["clips"].values():
        if existing.get("sha1") and sha and existing["sha1"] == sha:
            manifest["stats"]["skipped"] = manifest["stats"].get("skipped", 0) + 1
            return
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    manifest["clips"][key] = {
        "source": source,
        "source_id": source_id,
        "path": rel,
        "query": query,
        "license": license_name,
        "attribution": attribution,
        "url": url,
        "sha1": sha,
        "bytes": path.stat().st_size if path.exists() else 0,
    }
    manifest["stats"]["downloaded"] = manifest["stats"].get("downloaded", 0) + 1


# ---------------------------------------------------------------------------
# Mixkit
# ---------------------------------------------------------------------------

def _extract_mixkit_ids(html: str) -> set[str]:
    ids: set[str] = set()
    ids.update(re.findall(r"assets\.mixkit\.co/videos/(\d+)/", html))
    ids.update(re.findall(r"/free-stock-video/[^\"']+-(\d+)/", html))
    return ids


def discover_mixkit_ids(cfg: dict, want: int = 1200) -> list[str]:
    """Discover Mixkit video IDs via category pagination + query landing pages.

    Stops early once ``want`` unique IDs are collected so downloads can begin.
    """
    ids: set[str] = set()
    headers = {**HEADERS, "User-Agent": "Mozilla/5.0"}
    # Prefer wedding-relevant categories first.
    preferred = ["wedding", "love", "people", "lifestyle"]
    rest = [c for c in (cfg.get("mixkit_categories") or []) if c not in preferred]
    categories = preferred + rest
    for cat in categories:
        if len(ids) >= want:
            break
        for page in range(1, 40):
            if len(ids) >= want:
                break
            if page == 1:
                url = f"https://mixkit.co/free-stock-video/{cat}/"
            else:
                url = f"https://mixkit.co/free-stock-video/{cat}/?page={page}"
            try:
                req = urllib.request.Request(url, headers=headers)
                html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
                found = _extract_mixkit_ids(html)
                new = found - ids
                if not found or not new:
                    break
                ids |= found
                print(f"  mixkit {cat} p{page}: +{len(new)} (total {len(ids)})", flush=True)
            except Exception as e:
                print(f"  mixkit page fail {url}: {e}", flush=True)
                break
            time.sleep(0.25)

    if len(ids) < want:
        for page_url in cfg.get("mixkit_search_pages") or []:
            if len(ids) >= want:
                break
            try:
                req = urllib.request.Request(page_url, headers=headers)
                html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
                before = len(ids)
                ids |= _extract_mixkit_ids(html)
                print(f"  mixkit page {page_url}: +{len(ids) - before}", flush=True)
            except Exception as e:
                print(f"  mixkit page fail {page_url}: {e}", flush=True)
            time.sleep(0.25)

    if len(ids) < want:
        for q in cfg.get("mixkit_queries") or []:
            if len(ids) >= want:
                break
            url = "https://mixkit.co/free-stock-video/?" + urllib.parse.urlencode({"q": q})
            try:
                req = urllib.request.Request(url, headers=headers)
                html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
                before = len(ids)
                ids |= _extract_mixkit_ids(html)
                if len(ids) > before:
                    print(f"  mixkit q={q}: +{len(ids) - before}", flush=True)
            except Exception as e:
                print(f"  mixkit q fail {q}: {e}", flush=True)
            time.sleep(0.2)
    return sorted(ids)


def download_mixkit(manifest: dict, target: int) -> None:
    queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    print("Discovering Mixkit IDs...", flush=True)
    # Collect a bit more than target so failed/404 IDs do not leave us short.
    ids = discover_mixkit_ids(queries, want=max(target + 50, int(target * 1.4)))
    # Seed known wedding IDs from existing project usage + common Mixkit wedding set
    seed = [
        "18204", "40597", "40591", "40596", "40599", "40601", "5206",
        "36171", "4829", "5213", "5223", "5183", "5218", "1151",
        "40584", "40586", "40587", "40590", "40593", "40592", "40595", "40602",
    ]
    for s in seed:
        if s not in ids:
            ids.append(s)
    # Prefer seed + wedding-range IDs first (better match for montage craft).
    seed_set = set(seed)
    preferred = [i for i in ids if i in seed_set or i.startswith("40") or i.startswith("18") or i.startswith("52") or i.startswith("36") or i.startswith("48")]
    rest = [i for i in ids if i not in preferred]
    ids = preferred + rest
    print(f"  candidate ids: {len(ids)} (preferred first={len(preferred)})", flush=True)
    out_dir = LIB / "mixkit"
    out_dir.mkdir(parents=True, exist_ok=True)

    for vid in ids:
        if len(manifest["clips"]) >= target:
            break
        key = f"mixkit:{vid}"
        if key in manifest["clips"]:
            continue
        dest = out_dir / f"mixkit_{vid}.mp4"
        if dest.exists() and dest.stat().st_size > 50_000:
            register(
                manifest,
                source="mixkit",
                source_id=vid,
                path=dest,
                query="seed/search",
                license_name="Mixkit Stock Video Free License",
                url=f"https://assets.mixkit.co/videos/{vid}/{vid}-720.mp4",
            )
            save_manifest(manifest)
            continue
        ok = False
        used_url = ""
        for quality in ("720", "360"):
            url = f"https://assets.mixkit.co/videos/{vid}/{vid}-{quality}.mp4"
            print(f"  mixkit {vid} @{quality}...", flush=True)
            if download_file(url, dest):
                ok = True
                used_url = url
                break
            time.sleep(0.2)
        if ok:
            register(
                manifest,
                source="mixkit",
                source_id=vid,
                path=dest,
                query="seed/search",
                license_name="Mixkit Stock Video Free License",
                url=used_url,
            )
            print(f"    OK {dest.name} ({dest.stat().st_size // 1024} KB)", flush=True)
        else:
            manifest["stats"]["failed"] = manifest["stats"].get("failed", 0) + 1
            print(f"    FAIL {vid}", flush=True)
        save_manifest(manifest)
        time.sleep(0.25)


# ---------------------------------------------------------------------------
# Pexels
# ---------------------------------------------------------------------------

def download_pexels(manifest: dict, target: int) -> None:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        print("Pexels: skipped (no PEXELS_API_KEY)", flush=True)
        return
    queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8")).get("wedding") or ["wedding"]
    out_dir = LIB / "pexels"
    out_dir.mkdir(parents=True, exist_ok=True)
    headers = {**HEADERS, "Authorization": key}

    for q in queries:
        if len(manifest["clips"]) >= target:
            break
        page = 1
        while page <= 15 and len(manifest["clips"]) < target:
            url = (
                "https://api.pexels.com/v1/videos/search?"
                + urllib.parse.urlencode({"query": q, "per_page": 40, "page": page})
            )
            try:
                req = urllib.request.Request(url, headers=headers)
                data = json.loads(urllib.request.urlopen(req, timeout=45).read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                print(f"  pexels HTTP {e.code} q={q} page={page}", flush=True)
                break
            except Exception as e:
                print(f"  pexels error: {e}", flush=True)
                break
            videos = data.get("videos") or []
            if not videos:
                break
            for v in videos:
                if len(manifest["clips"]) >= target:
                    break
                vid = str(v.get("id"))
                mkey = f"pexels:{vid}"
                if mkey in manifest["clips"]:
                    continue
                duration = float(v.get("duration") or 0)
                if duration < 3:
                    continue
                files = v.get("video_files") or []
                # Prefer ~720p
                files_sorted = sorted(
                    files,
                    key=lambda f: abs((f.get("height") or 0) - 720),
                )
                chosen = None
                for f in files_sorted:
                    if (f.get("height") or 0) >= 480 and f.get("link"):
                        chosen = f
                        break
                if not chosen:
                    continue
                dest = out_dir / f"pexels_{vid}.mp4"
                if dest.exists() and dest.stat().st_size > 50_000:
                    register(
                        manifest,
                        source="pexels",
                        source_id=vid,
                        path=dest,
                        query=q,
                        license_name="Pexels License",
                        attribution=v.get("user", {}).get("name", ""),
                        url=chosen.get("link", ""),
                    )
                    save_manifest(manifest)
                    continue
                print(f"  pexels {vid} ({q})...", flush=True)
                if download_file(chosen["link"], dest):
                    register(
                        manifest,
                        source="pexels",
                        source_id=vid,
                        path=dest,
                        query=q,
                        license_name="Pexels License",
                        attribution=(v.get("user") or {}).get("name", ""),
                        url=chosen.get("link", ""),
                    )
                    print(f"    OK {dest.name}", flush=True)
                else:
                    manifest["stats"]["failed"] = manifest["stats"].get("failed", 0) + 1
                save_manifest(manifest)
                time.sleep(0.35)
            page += 1
            time.sleep(0.6)


# ---------------------------------------------------------------------------
# Pixabay
# ---------------------------------------------------------------------------

def download_pixabay(manifest: dict, target: int) -> None:
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        print("Pixabay: skipped (no PIXABAY_API_KEY)", flush=True)
        return
    queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8")).get("wedding") or ["wedding"]
    out_dir = LIB / "pixabay"
    out_dir.mkdir(parents=True, exist_ok=True)

    for q in queries:
        if len(manifest["clips"]) >= target:
            break
        page = 1
        while page <= 10 and len(manifest["clips"]) >= 0 and len(manifest["clips"]) < target:
            url = (
                "https://pixabay.com/api/videos/?"
                + urllib.parse.urlencode(
                    {"key": key, "q": q, "per_page": 40, "page": page, "safesearch": "true"}
                )
            )
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                data = json.loads(urllib.request.urlopen(req, timeout=45).read().decode("utf-8"))
            except Exception as e:
                print(f"  pixabay error q={q}: {e}", flush=True)
                break
            hits = data.get("hits") or []
            if not hits:
                break
            for h in hits:
                if len(manifest["clips"]) >= target:
                    break
                vid = str(h.get("id"))
                mkey = f"pixabay:{vid}"
                if mkey in manifest["clips"]:
                    continue
                duration = float(h.get("duration") or 0)
                if duration < 3:
                    continue
                videos = h.get("videos") or {}
                chosen = None
                for quality in ("medium", "small", "large", "tiny"):
                    block = videos.get(quality) or {}
                    if block.get("url"):
                        chosen = block
                        break
                if not chosen:
                    continue
                dest = out_dir / f"pixabay_{vid}.mp4"
                if dest.exists() and dest.stat().st_size > 50_000:
                    register(
                        manifest,
                        source="pixabay",
                        source_id=vid,
                        path=dest,
                        query=q,
                        license_name="Pixabay Content License",
                        attribution=h.get("user", ""),
                        url=chosen.get("url", ""),
                    )
                    save_manifest(manifest)
                    continue
                print(f"  pixabay {vid} ({q})...", flush=True)
                if download_file(chosen["url"], dest):
                    register(
                        manifest,
                        source="pixabay",
                        source_id=vid,
                        path=dest,
                        query=q,
                        license_name="Pixabay Content License",
                        attribution=h.get("user", ""),
                        url=chosen.get("url", ""),
                    )
                    print(f"    OK {dest.name}", flush=True)
                else:
                    manifest["stats"]["failed"] = manifest["stats"].get("failed", 0) + 1
                save_manifest(manifest)
                time.sleep(0.35)
            page += 1
            time.sleep(0.6)


def import_existing_wedding_web(manifest: dict) -> None:
    """Register already-downloaded Mixkit clips under wedding_web."""
    web = ROOT / "resource" / "video" / "wedding_web"
    if not web.exists():
        return
    for p in sorted(web.glob("*.mp4")):
        # wedding_40597.mp4 or similar
        m = re.search(r"(\d{3,})", p.stem)
        sid = m.group(1) if m else p.stem
        key = f"mixkit:{sid}"
        if key in manifest["clips"]:
            continue
        # also copy into library for unified scanning
        dest = LIB / "mixkit" / f"mixkit_{sid}.mp4"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            try:
                dest.write_bytes(p.read_bytes())
            except Exception:
                dest = p
        register(
            manifest,
            source="mixkit",
            source_id=sid,
            path=dest if dest.exists() else p,
            query="legacy_wedding_web",
            license_name="Mixkit Stock Video Free License",
        )
    save_manifest(manifest)


def main() -> None:
    load_dotenv_keys()
    p = argparse.ArgumentParser(description="Download legal wedding stock clips")
    p.add_argument("--sources", default="mixkit", help="comma: mixkit,pexels,pixabay")
    p.add_argument("--target", type=int, default=1000)
    args = p.parse_args()

    LIB.mkdir(parents=True, exist_ok=True)
    (LIB / ".gitkeep").write_text("", encoding="utf-8")
    manifest = load_manifest()
    import_existing_wedding_web(manifest)

    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    print(f"Target={args.target} already={len(manifest['clips'])} sources={sources}", flush=True)

    if "mixkit" in sources:
        download_mixkit(manifest, args.target)
    if "pexels" in sources:
        download_pexels(manifest, args.target)
    if "pixabay" in sources:
        download_pixabay(manifest, args.target)

    save_manifest(manifest)
    print(
        f"DONE clips={len(manifest['clips'])} "
        f"stats={json.dumps(manifest.get('stats', {}))}",
        flush=True,
    )


if __name__ == "__main__":
    main()
