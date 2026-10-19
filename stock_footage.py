"""
Royalty-free stock video for scenes. Providers (every clip used is logged with its source + license):
  pexels   Pexels License   (free key; key issuance may be paused)  --set-key pexels KEY
  pixabay  Pixabay License  (free key, pixabay.com/api/docs)       --set-key pixabay KEY
  nasa     Public domain    (NO key)  images.nasa.gov — space/science only; no NASA logos/insignia implying endorsement

  python3 stock_footage.py nasa "earth from space"      # search + download test
"""
import json, re, shutil, subprocess, sys
from pathlib import Path
import requests
from ai_video_engine import load_keys

CACHE = Path.home() / "faceless_content" / "stock_cache"
LICENSE = {"pexels": "Pexels License", "pixabay": "Pixabay License", "nasa": "NASA media (public domain; check third-party credits)"}


class NoStock(Exception):
    pass


def available(extra=()):
    k = load_keys()
    return [p for p in ("pexels", "pixabay") if k.get(p)] + [p for p in extra if p == "nasa"]


def _pexels(q, min_dur, exclude, strict=False):
    r = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": load_keys()["pexels"]}, timeout=20,
                     params={"query": q, "orientation": "portrait", "size": "medium", "per_page": 15})
    if r.status_code in (401, 403):
        raise NoStock(f"Pexels auth failed ({r.status_code})")
    r.raise_for_status()
    for v in r.json().get("videos", []):
        fl = [f for f in v["video_files"] if f.get("file_type") == "video/mp4" and (f.get("height") or 0) >= 1280]
        if v["id"] in exclude or v["duration"] < min_dur or not fl:
            continue
        f = min(fl, key=lambda f: abs((f.get("height") or 0) - 1920))
        return {"id": v["id"], "url": f["link"], "page": v["url"], "author": v["user"]["name"], "duration": v["duration"]}


def _pixabay(q, min_dur, exclude, strict=False):
    """Pixabay video search (docs: pixabay.com/api/docs/#api_search_videos). No orientation filter exists for
    video, so portrait hits are ranked first. Responses are cached 24h as the API terms require."""
    import hashlib, time
    q = q[:100]
    CACHE.mkdir(parents=True, exist_ok=True)
    cf = CACHE / f"search_pixabay_{hashlib.sha256(q.encode()).hexdigest()[:12]}.json"
    if cf.exists() and time.time() - cf.stat().st_mtime < 86400:
        hits = json.loads(cf.read_text())
    else:
        r = requests.get("https://pixabay.com/api/videos/", timeout=20,
                         params={"key": load_keys()["pixabay"], "q": q, "per_page": 30, "safesearch": "true", "video_type": "film"})
        if r.status_code == 429:
            raise NoStock("Pixabay rate limit hit (100 req/min); retry shortly")
        if r.status_code in (400, 401, 403):
            raise NoStock(f"Pixabay auth failed ({r.status_code}): {r.text[:80]}")
        r.raise_for_status()
        hits = r.json().get("hits", [])
        cf.write_text(json.dumps(hits))

    def rend(v):  # 1080p medium preferred; 'large' is usually 4K, so never chosen
        return next((v["videos"][k] for k in ("medium", "small") if v["videos"].get(k, {}).get("url")), None)

    stem = lambda w: w[:-1] if w.endswith("s") and len(w) > 3 else w
    stop = {"a", "an", "the", "of", "in", "on", "and", "with", "to"}
    toks = {stem(w) for w in re.findall(r"[a-z]+", q.lower()) if w not in stop}
    need = len(toks) if strict else max(1, -(-len(toks) // 2))  # strict: every query word must be in the tags; else at least half

    def overlap(v):
        return len(toks & {stem(w) for w in re.findall(r"[a-z]+", v.get("tags", "").lower())})

    ranked = sorted((v for v in hits if rend(v) and overlap(v) >= need),
                    key=lambda v: (-overlap(v), 0 if rend(v)["height"] > rend(v)["width"] else 1))
    for v in ranked:
        if v["id"] in exclude or v["duration"] < min_dur:
            continue
        return {"id": v["id"], "url": rend(v)["url"], "page": v["pageURL"], "author": v["user"], "duration": v["duration"],
                "tags": v.get("tags")}


BAD_TITLE = re.compile(r"message|administrator|briefing|interview|press|conference|remarks|ceremony|celebrat|welcome|reel|b-roll|"
                       r"media|statement|town hall|webcast|panel|hearing|podcast|promo|trailer|announce|speech|address|honor|award|"
                       r"world cup|anniversary|live|replay|highlights|schedule|overview", re.I)


def nasa_by_id(nid):
    """Pin a specific NASA clip: segment {"clip": "nasa:<nasa_id>"}."""
    urls = requests.get(f"https://images-api.nasa.gov/asset/{nid}", timeout=30).json()["collection"]["items"]
    mp4 = [u["href"] for u in urls if u["href"].lower().endswith(".mp4") and "~" in u["href"]]
    pick = next((u for pref in ("~medium", "~large", "~small") for u in mp4 if pref in u), None)
    if not pick:
        raise NoStock(f"NASA asset {nid} has no mp4")
    return {"id": nid, "url": pick.replace("http://", "https://"), "page": f"https://images.nasa.gov/details/{nid}",
            "author": "NASA", "duration": None, "title": nid, "provider": "nasa", "query": f"pinned:{nid}", "license": LICENSE["nasa"]}


def _nasa(q, min_dur, exclude, strict=False):
    r = requests.get("https://images-api.nasa.gov/search", params={"q": q, "media_type": "video"}, timeout=30)
    r.raise_for_status()
    for it in r.json()["collection"]["items"][:15]:
        nid = it["data"][0]["nasa_id"]
        title = it["data"][0].get("title", "") + " " + nid
        if nid in exclude or BAD_TITLE.search(title):
            continue
        if strict and not all(w in title.lower() for w in re.findall(r"[a-z]+", q.lower())):
            continue
        try:
            urls = requests.get(it["href"], timeout=30).json()
        except Exception:
            continue
        mp4 = [u for u in urls if u.lower().endswith(".mp4") and "~" in u]
        pick = next((u for pref in ("~medium", "~large", "~small") for u in mp4 if pref in u), None)
        if pick:
            return {"id": nid, "url": pick.replace("http://", "https://"), "page": f"https://images.nasa.gov/details/{nid}",
                    "author": it["data"][0].get("center") or "NASA", "duration": None, "title": it["data"][0].get("title")}


def pixabay_candidates(q, strict=True, min_dur=3.0):
    """All Pixabay hits passing the tag gate for a query (strict = every word must be in the tags)."""
    import hashlib, time
    _pixabay(q, min_dur, set(), strict)  # populates the 24h cache (may return None)
    cf = CACHE / f"search_pixabay_{hashlib.sha256(q[:100].encode()).hexdigest()[:12]}.json"
    stem = lambda w: w[:-1] if w.endswith("s") and len(w) > 3 else w
    toks = {stem(w) for w in re.findall(r"[a-z]+", q.lower()) if w not in {"a", "an", "the", "of", "in", "on", "and", "with", "to"}}
    out = []
    for v in json.loads(cf.read_text()):
        tg = {stem(w) for w in re.findall(r"[a-z]+", v.get("tags", "").lower())}
        ok = toks <= tg if strict else len(toks & tg) * 2 >= len(toks)
        r = next((v["videos"][k] for k in ("medium", "small") if v["videos"].get(k, {}).get("url")), None)
        if ok and r and v["duration"] >= min_dur:
            out.append({"id": v["id"], "tags": v.get("tags", ""), "portrait": r["height"] > r["width"], "duration": v["duration"]})
    return out


PROVIDERS = {"pexels": _pexels, "pixabay": _pixabay, "nasa": _nasa}


def search(query, min_dur=3.0, exclude=(), providers=None, strict=False):
    providers = providers or available()
    if not providers:
        raise NoStock("no stock source: add a key (--set-key pixabay KEY) or enable --stock-sources nasa")
    for p in providers:
        hit = PROVIDERS[p](query, min_dur, exclude, strict)
        if hit:
            hit.update(provider=p, query=query, license=LICENSE[p])
            return hit
    return None


def fetch(hit):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{hit['provider']}_{re.sub(r'[^A-Za-z0-9_-]', '_', str(hit['id']))}.mp4"
    if not (p.exists() and p.stat().st_size > 50000):
        with requests.get(hit["url"], stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(p, "wb") as f:
                shutil.copyfileobj(r.raw, f)
    return p


def _size(src, ffmpeg):
    err = subprocess.run([ffmpeg, "-i", str(src)], capture_output=True, text=True).stderr
    m = re.search(r"Video:.*?(\d{3,5})x(\d{3,5})", err)
    return (int(m.group(1)), int(m.group(2))) if m else (1080, 1920)


def _start_offset(src, ffmpeg):
    """Seconds to skip so a clip never opens on black/slate (common in archive footage)."""
    err = subprocess.run([ffmpeg, "-t", "90", "-i", str(src), "-vf", "blackdetect=d=0.3:pix_th=0.10", "-an", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.search(r"black_start:0(?:\.0+)?\s+black_end:([\d.]+)", err)
    return float(m.group(1)) + 0.5 if m else 0.0


def make_clip(src, dur, out, ffmpeg):
    """1080x1920, 30fps, muted, exactly `dur`s (loops short sources). Landscape sources get a blurred-background fit
    instead of a destructive center crop."""
    w, h = _size(src, ffmpeg)
    if w > h:
        vf = ("[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
              "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,format=yuv420p[v]")
        args = ["-filter_complex", vf, "-map", "[v]"]
    else:
        args = ["-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p"]
    ss = _start_offset(src, ffmpeg)
    subprocess.run([ffmpeg, "-y", "-ss", f"{ss:.2f}", "-stream_loop", "-1", "-i", str(src), "-t", f"{dur:.2f}", "-an", *args,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out)], check=True, capture_output=True)


if __name__ == "__main__":
    prov, q = sys.argv[1], " ".join(sys.argv[2:])
    hit = search(q, providers=[prov])
    print(json.dumps(hit, indent=2) if hit else "no match")
    if hit:
        import os
        src = fetch(hit)
        sp = "/private/tmp/claude-501/-Users-user/fd44da8f-b02a-477d-84ce-36857f876d54/scratchpad/stock_test.mp4"
        make_clip(src, 4, sp, os.path.expanduser("~/bin/ffmpeg"))
        print("clip ->", sp, Path(sp).stat().st_size, "bytes")
