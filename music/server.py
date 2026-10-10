"""Tunes - a small self-hosted music player backed by yt-dlp.

Run:  pip install -r requirements.txt && python server.py
Then open http://localhost:5000
"""

import os
import threading
import time
import urllib.request
from urllib.error import HTTPError

from flask import Flask, Response, abort, jsonify, request, send_from_directory
import yt_dlp

HERE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=None)

# Resolved stream URLs expire after ~6h; keep them for a bit less than that.
STREAM_TTL = 60 * 60 * 4
_stream_cache = {}
_cache_lock = threading.Lock()

YDL_SEARCH = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist", "skip_download": True}
YDL_STREAM = {"quiet": True, "no_warnings": True, "format": "bestaudio[ext=m4a]/bestaudio/best", "skip_download": True}


def _thumb(video_id):
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def _track(entry):
    vid = entry.get("id")
    return {
        "id": vid,
        "title": entry.get("title") or "Unknown",
        "artist": entry.get("channel") or entry.get("uploader") or "Unknown artist",
        "duration": entry.get("duration") or 0,
        "thumb": _thumb(vid),
    }


@app.get("/api/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    limit = max(1, min(int(request.args.get("limit", 20)), 50))
    # "music" nudges YouTube towards songs instead of reaction videos and tutorials.
    try:
        with yt_dlp.YoutubeDL(YDL_SEARCH) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{q} music", download=False)
    except yt_dlp.utils.DownloadError as e:
        return jsonify(error=str(e)), 502
    entries = [e for e in info.get("entries", []) if e and e.get("id") and e.get("duration")]
    # Skip hour-long mixes and livestreams unless that's all there is.
    songs = [e for e in entries if e["duration"] <= 15 * 60] or entries
    return jsonify([_track(e) for e in songs])


def _resolve(video_id):
    now = time.time()
    with _cache_lock:
        hit = _stream_cache.get(video_id)
        if hit and hit["expires"] > now:
            return hit
    with yt_dlp.YoutubeDL(YDL_STREAM) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    entry = {
        "url": info["url"],
        "headers": info.get("http_headers", {}),
        "mime": f"audio/{info.get('audio_ext') or info.get('ext') or 'mp4'}".replace("audio/m4a", "audio/mp4"),
        "expires": now + STREAM_TTL,
    }
    with _cache_lock:
        _stream_cache[video_id] = entry
    return entry


@app.get("/api/stream/<video_id>")
def stream(video_id):
    """Proxy the audio through this server.

    YouTube's media URLs are tied to the IP that resolved them and don't send
    CORS headers, so the browser can't fetch them directly. Range requests are
    forwarded so seeking works.
    """
    if not video_id.replace("-", "").replace("_", "").isalnum():
        abort(400)
    try:
        src = _resolve(video_id)
    except yt_dlp.utils.DownloadError as e:
        return jsonify(error=str(e)), 502

    headers = dict(src["headers"])
    if "Range" in request.headers:
        headers["Range"] = request.headers["Range"]
    try:
        upstream = urllib.request.urlopen(urllib.request.Request(src["url"], headers=headers), timeout=20)
    except HTTPError as e:
        if e.code == 403:  # URL went stale early; resolve again next time.
            with _cache_lock:
                _stream_cache.pop(video_id, None)
        return jsonify(error=f"upstream {e.code}"), 502

    def generate():
        with upstream:
            while chunk := upstream.read(64 * 1024):
                yield chunk

    out = Response(generate(), status=upstream.status, mimetype=src["mime"])
    for h in ("Content-Length", "Content-Range", "Accept-Ranges"):
        if upstream.headers.get(h):
            out.headers[h] = upstream.headers[h]
    out.headers.setdefault("Accept-Ranges", "bytes")
    return out


@app.get("/api/download/<video_id>")
def download(video_id):
    """Send the audio as a file so it can be saved for offline listening."""
    if not video_id.replace("-", "").replace("_", "").isalnum():
        abort(400)
    try:
        src = _resolve(video_id)
    except yt_dlp.utils.DownloadError as e:
        return jsonify(error=str(e)), 502
    name = request.args.get("name", video_id).replace('"', "")[:120]
    ext = src["mime"].split("/")[1].replace("mp4", "m4a")
    upstream = urllib.request.urlopen(urllib.request.Request(src["url"], headers=src["headers"]), timeout=20)

    def generate():
        with upstream:
            while chunk := upstream.read(64 * 1024):
                yield chunk

    out = Response(generate(), mimetype=src["mime"])
    out.headers["Content-Disposition"] = f'attachment; filename="{name}.{ext}"'
    if upstream.headers.get("Content-Length"):
        out.headers["Content-Length"] = upstream.headers["Content-Length"]
    return out


@app.get("/")
def index():
    return send_from_directory(HERE, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Tunes running on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
