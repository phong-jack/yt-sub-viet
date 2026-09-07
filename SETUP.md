# YT Sub Việt Realtime — Hướng dẫn chạy (ENV đầy đủ)

## 1. Yêu cầu

| Thứ | Bản | Ghi chú |
|---|---|---|
| Python | 3.10+ (đã test 3.12) | `server.py` chỉ dùng **thư viện chuẩn**, không cần pip để chạy web cơ bản |
| ffmpeg | bản mới nhất | sub/vision cần cắt frame: `ffmpeg -version` phải chạy được. Win: https://www.gyan.dev/ffmpeg/builds/ |
| yt-dlp | mới nhất | tải sub: `pip install yt-dlp` (cần cho `/api/subs`) |
| edge-tts | mới nhất | voice Việt: `pip install edge-tts` (không có thì mất voice, web vẫn chạy) |
| Node.js 18+ | tùy chọn | chỉ để chạy test headless (`seek.test.js` kiểu cũ), không bắt buộc |
| LLM API (OpenAI-compatible) | — | dịch + vision. Chọn 1: **9router local** `http://localhost:20128/v1`, **OpenRouter** `https://openrouter.ai/api/v1`, **Ollama cloud**, ... |

## 2. Chạy local (máy công ty / máy nhà - KHÔNG public mạng)

**Windows (khuyên dùng):** double-click 1 trong 2 file:
- `start.bat` — chỉ máy đó xem được (`http://127.0.0.1:7378`, localhost-only, an toàn nhất)
- `start-host.bat` — mở cho máy khác **cùng mạng nội bộ** xem (`0.0.0.0:7378`, Windows Firewall sẽ hỏi → Allow)

**Linux/Mac:** `bash start-host.sh`

**Chạy tay:**
```bash
cd youtube-stream-sub
python -u server.py          # mac dinh http://127.0.0.1:7378 (localhost-only)
# mo LAN:  HOST=0.0.0.0 python -u server.py
# port khac:  python -u server.py 8080   (0.0.0.0:8080)
```

Không cần `pip install` gì để mở web + xem sub cache sẵn.
Cần full tính năng thì: `pip install yt-dlp edge-tts`

> Muốn xem từ ngoài internet thì mới cần tunnel/VPS (xem HOSTING.md) — mặc định KHÔNG mở public.

## 3. Biến môi trường (ENV)

| ENV | Mặc định | Tác dụng |
|---|---|---|
| `PYTHONIOENCODING` | — | **đặt `utf-8`** khi chạy (`PYTHONIOENCODING=utf-8 python -u server.py`) nếu không log/cache tiếng Việt lỗi trên Windows |
| `PORT` | `7378` | chỉ dùng cho bản host (`app.py` đọc `PORT`, vd Hugging Face đặt 7860) |
| `FFMPEG_BIN` | `ffmpeg` | đường dẫn ffmpeg nếu không có trong PATH. Trên host thiếu ffmpeg hệ thống: `pip install imageio-ffmpeg` (app.py tự set) |

## 4. Cấu hình trong web (không cần sửa code)

Mở web lần đầu → popup 🔑 (hoặc nút 🔑 trên bar):

| Trường | Mặc định | VD khác |
|---|---|---|
| Base URL | `http://localhost:20128/v1` | `https://openrouter.ai/api/v1` |
| API Key | trống | `sk-or-...` (lưu ở trình duyệt từng người) |
| Model dịch | `gemma4` | `google/gemma-3-27b-it` |
| Model vision | `ollama/gemma4:31b-cloud` | model nào có vision qua base URL trên |

- Server lưu config qua `POST /api/config` (RAM, mất khi restart → web tự gửi lại từ localStorage).
- Checkbox **👁 Vision**: tích = dịch kèm nhìn frame (chuẩn xưng hô, chậm), bỏ = text-only (nhanh).

## 5. File / thư mục quan trọng

```
server.py        backend chính (stdlib only) + toàn bộ prompt dịch/vision/knowledge
index.html       web xem phim (stream YT + sub đè video + voice + key modal)
app.py           entry cho host free (FastAPI+Gradio mount, đọc PORT) — local không cần
requirements.txt deps cho host (gradio/fastapi/uvicorn/yt-dlp/edge-tts/imageio-ffmpeg)
Dockerfile       build Docker (host Koyeb/Railway/Render)
README.md        metadata Hugging Face Space
HOSTING.md       so sánh các chỗ host free
cache/           sub + bản dịch + knowledge + mp4 + voice (giữ 60 ngày, xem lại instant)
  <videoId>_zh.json    sub gốc + vi + speaker + verified
  <videoId>_meta.json  knowledge phim (nhân vật/quan hệ/glossary)
  <videoId>.mp4        video 360p để cắt frame vision (tự tải nền)
```

## 6. Host free (đã test)

- **Koyeb free** (khuyên dùng): import repo GitHub → Builder Dockerfile → Port 7860 → Deploy, link `.koyeb.app` cố định.
- **Hugging Face (Gradio SDK)**: up `app.py server.py index.html requirements.txt README.md` (+ cache json cho nhanh). Lưu ý: IP datacenter hay bị YouTube 429 khi tải sub mới.
- **Cloudflare Tunnel** (xem ngay, không cần host): `cloudflared tunnel --url http://127.0.0.1:7378` → link `*.trycloudflare.com` (đổi mỗi lần restart; muốn cố định thì login Cloudflare free 1 lần).
- **Vercel/Netlify**: KHÔNG host được backend (serverless timeout, không ffmpeg/disk/process nền).

## 7. Sự cố thường gặp

| Hiện tượng | Nguyên nhân / cách fix |
|---|---|
| Sub hiện chữ Trung | bật retransGate tự xử lý; câu nào vẫn dính thì server log `VERIFY-FAIL`, bấm 👁 Check đoạn này để vision dịch lại |
| Tạm dừng liên tục | bản mới chỉ pause khi **tua** (>3s); lag mạng thì không pause nữa |
| Tua về đoạn cũ không có sub | server restart mất RAM → client tự `/api/subs` đồng bộ lại (dòng 🔄), server cũng tự load đĩa |
| `/api/subs` lỗi 429/chặn | IP bị YouTube chặn → mở ở mạng khác 1 lần cho có cache, hoặc kẹp cookies yt-dlp |
| Voice không đọc | thiếu `edge-tts` hoặc chưa bật nút Voice; mp3 cache ở `cache/voice/` |
| Port 7378 bận | `python -u server.py 8080` rồi mở port đó |
