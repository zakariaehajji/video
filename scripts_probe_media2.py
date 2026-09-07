import json
import re
import urllib.request

hdrs = {"User-Agent": "Mozilla/5.0"}

def get(u):
    req = urllib.request.Request(u, headers=hdrs)
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")

for u in [
    "https://mixkit.co/free-stock-video/wedding/",
    "https://mixkit.co/free-stock-video/love/",
    "https://mixkit.co/free-stock-music/mood/romantic/",
]:
    html = get(u)
    ids = sorted(set(int(x) for x in re.findall(r"/videos/(\d+)/", html)))
    ids2 = sorted(set(int(x) for x in re.findall(r"video[_-]?id[\"']?\s*[:=]\s*[\"']?(\d+)", html, re.I)))
    slugs = sorted(set(re.findall(r"/free-stock-video/([a-z0-9\-]+-\d+)/", html)))
    music = sorted(set(re.findall(r"/free-stock-music/([a-z0-9\-]+-\d+)/", html)))
    print(u)
    print(" ids", ids[:30], "n", len(ids))
    print(" ids2", ids2[:20])
    print(" slugs", slugs[:15])
    print(" music", music[:15])
    # find json blobs
    for m in re.finditer(r"<script[^>]*>(\{.*?\})</script>", html, re.S):
        if "36171" in m.group(1) or "video" in m.group(1)[:200].lower():
            s = m.group(1)
            print(" script snippet", s[:200].replace("\n", " "))
            break

# discover music CDN by downloading music page raw for known tracks
print("\nMUSIC CDN")
for slug in ["beautiful-dream-493", "wedding-harp-698", "romantic-461", "skyline-81", "true-love-428"]:
    try:
        html = get(f"https://mixkit.co/free-stock-music/{slug}/")
        urls = sorted(set(re.findall(r"https://[^\"]+\.mp3", html)))
        print(slug, urls[:6])
        # also look for id patterns
        print("  ids", re.findall(r"music/(\d+)/", html)[:10])
        print("  download", re.findall(r"download/[^\"]+", html)[:6])
    except Exception as e:
        print(slug, e)
