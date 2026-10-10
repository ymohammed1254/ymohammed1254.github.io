# Tunes

A small self-hosted music player in the style of a streaming app. It searches YouTube and plays the audio through [yt-dlp](https://github.com/yt-dlp/yt-dlp). There are no accounts and no ads. Your likes and playlists are saved in your browser.

## Run it

```bash
cd music
pip install -r requirements.txt
python server.py
```

Then open http://localhost:5000. To use it from your phone on the same Wi-Fi, open `http://<your-computer's-IP>:5000`.

> This needs the Python server running. GitHub Pages only serves static files, so it can't run yt-dlp, and the page at `/music/` on the live site won't play anything by itself.

## Features

- Search any song or artist, with genre shortcuts
- Play, pause, next, previous, seek, volume, shuffle, and repeat (all or one)
- Queue panel with "Play next", "Add to queue", and remove
- Liked Songs and your own playlists, saved in localStorage
- Recently played on the home screen
- Download a track as an audio file
- Lock-screen and media-key controls (Media Session API)
- Keyboard: Space to play/pause, ←/→ to seek 5s, Shift+←/→ for previous/next, `/` to search
- Works on phones, with a bottom tab bar and a mini player

## How it works

- `GET /api/search?q=...`: yt-dlp `ytsearch` with flat extraction, so it's fast.
- `GET /api/stream/<id>`: yt-dlp finds the best audio-only format, and the server passes it through with Range support so seeking works. YouTube's media URLs are tied to the IP that requested them, so the browser can't load them directly. Resolved URLs are cached for 4 hours.
- `GET /api/download/<id>`: the same audio, sent as a file attachment.

If playback stops working, YouTube has probably changed something. Update yt-dlp first: `pip install -U yt-dlp`.

For personal use only. Downloading content may go against YouTube's Terms of Service, so respect artists' rights.
