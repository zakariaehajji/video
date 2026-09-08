import re
import urllib.request

ua = {"User-Agent": "Mozilla/5.0"}
u = "https://mixkit.co/free-stock-video/?q=wedding"
req = urllib.request.Request(u, headers=ua)
html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
# pagination hints
for pat in [r'page=\d+', r'rel="next"', r'/page/\d+', r'data-page', r'pagination']:
    m = re.findall(pat, html, flags=re.I)
    print(pat, len(m), m[:8])
# try alternate page urls
alts = [
    "https://mixkit.co/free-stock-video/?q=wedding&page=2",
    "https://mixkit.co/free-stock-video/wedding/?page=2",
    "https://mixkit.co/free-stock-video/wedding/2/",
    "https://mixkit.co/free-stock-video/?q=wedding&p=2",
]
base = set(re.findall(r"/free-stock-video/[^\"']+-(\d+)/", html))
print("base", len(base), sorted(base)[:5])
for a in alts:
    try:
        req = urllib.request.Request(a, headers=ua)
        h = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
        ids = set(re.findall(r"/free-stock-video/[^\"']+-(\d+)/", h))
        print(a, len(ids), "overlap", len(ids & base), "new", len(ids - base), sorted(ids - base)[:5])
    except Exception as e:
        print(a, e)
