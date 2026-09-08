import re
import urllib.request

ua = {"User-Agent": "Mozilla/5.0"}
queries = [
    "wedding", "bride", "groom", "couple", "marriage", "kiss", "dance",
    "celebration", "love", "family", "flowers", "ring", "party", "romance",
    "elegant", "proposal", "engagement", "ceremony", "reception", "hug",
]
cats = [
    "wedding", "love", "people", "lifestyle", "nature", "food", "city",
]
ids = set()
for q in queries:
    for page in range(1, 6):
        u = f"https://mixkit.co/free-stock-video/?q={q}&page={page}"
        try:
            req = urllib.request.Request(u, headers=ua)
            html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
            found = set(re.findall(r"/free-stock-video/[^\"']+-(\d+)/", html))
            found |= set(re.findall(r"assets\.mixkit\.co/videos/(\d+)/", html))
            if not found:
                break
            ids |= found
            print(f"q={q} p={page} +{len(found)} total={len(ids)}")
        except Exception as e:
            print("fail", u, e)
            break
for c in cats:
    u = f"https://mixkit.co/free-stock-video/{c}/"
    try:
        req = urllib.request.Request(u, headers=ua)
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
        found = set(re.findall(r"/free-stock-video/[^\"']+-(\d+)/", html))
        found |= set(re.findall(r"assets\.mixkit\.co/videos/(\d+)/", html))
        ids |= found
        print(f"cat={c} +{len(found)} total={len(ids)}")
    except Exception as e:
        print("fail cat", c, e)
print("TOTAL", len(ids))
