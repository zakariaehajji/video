import re
import urllib.request

hdrs = {"User-Agent": "Mozilla/5.0"}
urls = [
    "https://mixkit.co/free-stock-video/search/wedding/",
    "https://mixkit.co/free-stock-video/search/bride/",
    "https://mixkit.co/free-stock-video/search/couple/",
    "https://mixkit.co/free-stock-video/search/marriage/",
    "https://mixkit.co/free-stock-music/mood/romantic/",
    "https://mixkit.co/free-stock-music/search/wedding/",
]

for u in urls:
    try:
        req = urllib.request.Request(u, headers=hdrs)
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        vids = sorted(set(re.findall(r"assets\.mixkit\.co/videos/(\d+)/\1-720\.mp4", html)))
        mus = sorted(set(re.findall(r"assets\.mixkit\.co/music/preview/([^\"]+\.mp3)", html)))
        mus_pages = sorted(set(re.findall(r"/free-stock-music/([a-z0-9\-]+-\d+)/", html)))
        print("\n", u)
        print(" video ids", vids[:25], "count", len(vids))
        print(" music preview", mus[:12])
        print(" music pages", mus_pages[:12])
    except Exception as e:
        print(u, "ERR", e)
