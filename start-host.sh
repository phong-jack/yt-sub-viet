#!/bin/bash
# Host web xem phim tren may nay (1 lenh) - mo cho may khac cung wifi
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Cai Python 3.10+ truoc"; exit 1; }
command -v ffmpeg >/dev/null || echo "[WARN] Chua co ffmpeg (cat frame vision can)"
python3 -m pip install -q yt-dlp edge-tts 2>/dev/null
export PYTHONIOENCODING=utf-8 HOST=0.0.0.0 PORT=7378
echo "Mo web: http://localhost:7378 (may khac cung wifi xem IP in ben duoi)"
(python3 -c "import webbrowser; webbrowser.open('http://localhost:7378')" 2>/dev/null &)
python3 -u server.py
