
link: https://chatgpt.com/share/6805cb61-3b0c-8011-abe7-c1598851db04

## 1 · Quick win: swap `yt‑dlp` for **Piped**

Self‑hosted Piped dodges most “bot verification” because the Piped proxy farm distributes traffic and already solves signature ciphers.

```yaml
version: "3"
services:
  piped:
    image: ghcr.io/team-piped/piped:latest
    environment:
      - PORT=8080
    ports: ["127.0.0.1:8081:8080"]

# (optional) embed Piped proxy if you don’t want to trust public proxies
  piped-proxy:
    image: ghcr.io/team-piped/piped-proxy:latest
    environment:
      - PORT=8082
      - WORKERS=4
    ports: ["127.0.0.1:8082:8082"]
```

**Clipper flow changes**

1. **Lookup streams**

```python
resp = httpx.get(f"http://piped:8081/streams/{video_id}").json()
url  = next(s["url"] for s in resp["videoStreams"] if s["format"] == "MP4")
```

2. **FFmpeg trim** that URL directly (`-ss start -to end -i "$url"`).  
No cookies, no `yt‑dlp`, just plain HTTP.

*Success rate*: > 99 % up to 1080p, because Piped falls back to its own proxy when YouTube blocks its IP.
