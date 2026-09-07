import re
import urllib.request

hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

pages = [
    "https://mixkit.co/free-stock-video/wedding-couple-in-a-flower-field-36171/",
    "https://mixkit.co/free-stock-video/portrait-of-a-bride-smiling-40597/",
    "https://mixkit.co/free-stock-video/love/",
    "https://mixkit.co/free-stock-video/wedding/",
    "https://mixkit.co/free-stock-music/beautiful-dream-493/",
    "https://mixkit.co/free-stock-music/wedding-harp-698/",
    "https://mixkit.co/free-stock-music/romantic-461/",
    "https://coverr.co/videos/search?q=wedding",
]

for u in pages:
    try:
        req = urllib.request.Request(u, headers=hdrs)
        with urllib.request.urlopen(req, timeout=25) as r:
            html = r.read().decode("utf-8", "ignore")
        vids = sorted(set(re.findall(r"https://assets\.mixkit\.co/videos/\d+/\d+-720\.mp4", html)))
        vids += sorted(set(re.findall(r"https://assets\.mixkit\.co/videos/download/[^\"]+\.mp4", html)))
        mus = sorted(set(re.findall(r"https://assets\.mixkit\.co/music/[^\"]+\.mp3", html)))
        print("\nOK", u, "status")
        print(" vids", vids[:8])
        print(" mus", mus[:8])
        print(" len html", len(html))
    except Exception as e:
        print("ERR", u, e)

# probe known CDN files
print("\nPROBE CDN")
for url in [
    "https://assets.mixkit.co/videos/36171/36171-720.mp4",
    "https://assets.mixkit.co/videos/40597/40597-720.mp4",
    "https://assets.mixkit.co/videos/download/mixkit-wedding-couple-in-a-flower-field-36171.mp4",
]:
    try:
        req = urllib.request.Request(url, method="HEAD", headers=hdrs)
        with urllib.request.urlopen(req, timeout=15) as r:
            print(url, r.status, r.headers.get("Content-Length"), r.headers.get("Content-Type"))
    except Exception as e:
        print("fail", url, e)
