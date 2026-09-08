import re
import urllib.request

ua = {"User-Agent": "Mozilla/5.0"}
cats = [
    "wedding", "love", "people", "lifestyle", "nature", "business",
    "technology", "travel", "sports", "animation", "abstract",
]
# also discover related slugs from wedding page
ids = set()
pages_ok = []
for c in cats:
    for page in range(1, 30):
        u = f"https://mixkit.co/free-stock-video/{c}/" if page == 1 else f"https://mixkit.co/free-stock-video/{c}/?page={page}"
        try:
            req = urllib.request.Request(u, headers=ua)
            html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
            found = set(re.findall(r"/free-stock-video/[^\"']+-(\d+)/", html))
            found |= set(re.findall(r"assets\.mixkit\.co/videos/(\d+)/", html))
            new = found - ids
            if not found or not new:
                print(f"{c} page {page} stop found={len(found)} new={len(new)}")
                break
            ids |= found
            pages_ok.append(u)
            print(f"{c} p={page} +{len(new)} total={len(ids)}")
        except Exception as e:
            print(f"{c} p={page} FAIL {e}")
            break
print("TOTAL", len(ids))
