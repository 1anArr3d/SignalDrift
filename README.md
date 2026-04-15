# SignalDrift

Automated Reddit-to-Shorts pipeline. Crawls AITA drama posts, writes first-person narrated scripts via Claude, synthesizes TTS with word-level timing, renders captioned 1080x1920 MP4s, and uploads to YouTube Shorts + Google Drive.

## Quickstart

```bash
git clone <repo> && cd SignalDrift
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env  # fill in API keys

# First run
python main.py --stage crawl   # fill queue from Reddit
python main.py --stage forge   # render + upload 1 video
```

## Requirements

- Python 3.11+
- `ffmpeg` on PATH
- Anthropic API key
- Azure Speech key + region
- Google OAuth credentials (`client_secret.json`) with YouTube Data API v3 and Drive API enabled

## Usage

```bash
python main.py                          # crawl + forge 1 video
python main.py --count 5                # forge 5 videos
python main.py --stage crawl            # crawl only
python main.py --stage forge --count 3  # forge from queue
python main.py --post-id <id>           # re-forge specific post
python main.py --post-id <id> --draft-only  # inspect script first
```

See [MVP.md](MVP.md) for full architecture, config reference, and deployment notes.
