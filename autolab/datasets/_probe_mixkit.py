import re
import urllib.request

ua = {"User-Agent": "Mozilla/5.0"}
urls = [
    "https://mixkit.co/free-stock-video/wedding/",
    "https://mixkit.co/free-stock-video/tags/wedding/",
    "https://mixkit.co/free-stock-video/?q=wedding",
    "https://mixkit.co/free-stock-video/love/",
    "https://mixkit.co/free-stock-video/category/people/",
]
for u in urls:
    try:
        req = urllib.request.Request(u, headers=ua)
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
        ids = set(re.findall(r"/free-stock-video/[^\"']+-(\d+)/", html))
        ids2 = set(re.findall(r"assets\.mixkit\.co/videos/(\d+)/", html))
        print(u, "ok", len(ids | ids2), sorted(ids | ids2)[:10])
    except Exception as e:
        print(u, "FAIL", e)
