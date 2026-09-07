# PROJECT CONTEXT — YT Sub Việt Realtime
> Đọc file này đầu tiên khi tiếp tục code. Cập nhật nó mỗi khi đổi kiến trúc.

## 1. Dự án là gì
Web xem YouTube + sub Việt realtime: lấy sub gốc (yt-dlp) → dịch Trung-Việt
phong cách truyện (giữ xưng hô Hán-Việt) → **vision nhìn frame** để gán đúng
người nói/nghe/người thứ 3 → voice Việt đọc sub → sync khớp giờ video.

Repo GitHub: `phong-jack/yt-sub-viet` (public).
Thư mục local dev: `C:/Users/ngoti/youtube-stream-sub/`
Server local: `http://127.0.0.1:7378` (`python -u server.py`, PYTHONIOENCODING=utf-8).
HF Space: `phongpro5141/yt-sub-viet` (đang lỗi infra, hello-world cũng chết — tạm bỏ).

## 2. Kiến trúc file
```
server.py   backend stdlib-only (KHÔNG thêm pip dep vào đây!) + mọi prompt/logic
index.html  frontend 1 file (YT IFrame API + sync + seek + voice + key modal + vision toggle)
app.py      entry cho host free (FastAPI+Gradio mount) — local KHÔNG dùng
cache/      <vid>_zh.json (sub+vi+speaker+verified), <vid>_meta.json (knowledge),
            <vid>.mp4 (360p để cắt frame), voice/*.mp3 — TTL 60 ngày
start.bat / start-host.bat(.sh)  chạy local-only / LAN
```

## 3. Luồng dịch realtime (1-pass, vision-inline)
- `GET /api/subs?v=&lang=` → yt-dlp tải sub → parse VTT (dur = end gốc) →
  build knowledge (80 câu đầu) → dịch 6 câu đầu → trả full sub.
  Phim mới: thread nền tải mp4 360p (`ensure_video`) cho vision.
- `GET /api/tr?v=&i=&n=&novision=` → **vision_batch trước** (1 frame giữa batch
  + sub + knowledge + CTX → JSON {nguoi_noi, nguoi_nghe, nguoi_thu3, dich}) →
  fail mới rớt text (`translate_batch` + CTX trước/sau 2 câu).
  Từng group 6 câu vision fail → fallback text cho group đó (không bỏ cả batch).
- `GET /api/retrans?v=&idx=[...]` → cổng retrans: câu nào còn chữ Trung/thiếu
  vi thì dịch lại ngay (verify 2 vòng + MyMemory), frontend gọi TRƯỚC khi resume.
- `GET /api/vision?v=&i=&n=` → nút tay 👁 Check đoạn này (dùng chung vision_batch).
- Frontend: pause video khi lấy sub lần đầu; tua (>3s jump hoặc BUFFERING→PLAYING
  lệch giờ) → pause → dịch đúng đoạn → retransGate sạch chữ Trung → resume.
  Lag mạng (không nhảy giờ) thì KHÔNG pause. sub chỉ hiện khi đã có `vi`
  (không hiện gốc Trung). Poll backup 400ms + `stableTime()` (giờ đứng yên mới đọc,
  vì YouTube trả giờ cũ vài trăm ms sau seek).
- Voice: `/api/voice?t=&v=` (Edge-TTS Hoài My/Nam Minh, cache mp3).
- Knowledge: `/api/meta` GET/POST. AI học nền mỗi 60 câu (`learn_meta` thread).
- Config key: `/api/config` GET/POST {base_url, api_key, model, vision_model}
  (key trong RAM, web lưu localStorage + tự POST lại).

## 4. Knowledge schema v2 (chống hallucination xưng hô)
```json
{"bo_canh":"hiện đại",
 "nhan_vat":[{"ten","tuoi","gioi_tinh","vai","dac_diem",
              "do_tin_cay":"du_doan|xac_nhan","xac_nhan_boi":"..."}],
 "quan_he":[{"a","b","xung"}],   // cặp explicit, chỉ dùng đúng cặp
 "glossary":{...}, "mac_dinh":"ta-ngươi"}
```
Luật cứng mọi prompt: không khớp nhân vật / nhân vật `du_doan` mà thoại hiện tại
không gọi rõ → NGƯỜI LẠ → **ta-ngươi**, cấm đoán bừa bố/con/anh/em.
`learn_meta` có nhiệm vụ XÁC NHẬN từ bằng chứng xưng hô (X gọi Y là bố → X là con).

## 5. Verify (skill dich-truyen)
- Mọi output quét `[\u4e00-\u9fff]`: sót → retry kèm CTX 2 vòng → MyMemory →
  log `VERIFY-FAIL`. Ép trong `llm_batch`, `vision_batch`, `translate_zh_vi`.
- `demojibake()`: gateway 9router thỉnh thoảng trả UTF-8 bytes đọc dạng
  cp1252/latin-1 (`ThÃ¢n`, `chÆ°a`) → sửa bằng bảng `_REV` cứng
  (latin-1 identity + cp1252 extras). Text sạch giữ nguyên 10/10 test.

## 6. GOTCHAS (đừng đào lại)
1. **Vision chỉ nhận JPEG**: PNG tự chế/data-URL lỗi `octet-stream`; frame phải
   `ffmpeg ... -q:v 4 file.jpg` + `data:image/jpeg;base64,`. Model vision qua
   9router: `ollama/gemma4:31b-cloud`.
2. **YouTube `getCurrentTime()` trả giờ CŨ** vài trăm ms sau seek → phải
   `stableTime()` (poll 100ms, đứng yên 3 lần) trước khi tính `ci`.
3. **Player tạo bởi nút Load phải gắn `onStateChange`** (bug từng làm seek-detection chết).
4. **Stdout/file trên Windows là cp1252** → luôn chạy `PYTHONIOENCODING=utf-8 python -u`;
   `open(...,'w')` trong code PHẢI có `encoding='utf-8'` (csave từng crash câm).
5. **`/api/tr` sau restart trả `[]` câm** → đã fix: tự `cload` đĩa, không có thì 404
   `NO_CACHE`; frontend có watchdog `resyncSubs()` sau 5 vòng đứng im.
6. **Đừng cắt `subs[:2000]`** — phim này 5177 câu, cắt là nửa sau trắng sub.
7. **Bash tool + `&`**: `cd X && cmd &` background cả cd → dùng absolute path
   hoặc tách lệnh. `/tmp` của bash ≠ `/tmp` của Windows Python → dùng thư mục project.
8. **`git` + file cache đổi liên tục** (server csave mỗi batch) → commit/push từ
   clone riêng, hoặc `checkout` file đó trước khi pull.
9. **HF Space infra lỗi** (9/2026): hello-world cũng RUNTIME_ERROR — đừng tốn giờ,
   dùng Koyeb/tunnel. Gradle pin từng cần: `gradio==4.44.1 + huggingface_hub==0.33.1`
   (hub mới xóa `HfFolder`).
10. **Vercel/Netlify KHÔNG host được backend** (serverless, không ffmpeg/disk/process nền).

## 7. Quản lý server local
- Xem process: `netstat -ano | findstr 7378` → `taskkill //F //PID <pid>`
- Restart chuẩn: `PYTHONIOENCODING=utf-8 python -u server.py > out.log 2>&1 &`
- Log: `out.log` (request + vision-rt/learn/meta), `dl.log` (tải mp4).
- Cloudflared tunnel (đÃ TẮT 9/2026, cần thì chạy lại):
  `Start-Process cloudflared.exe 'tunnel --url http://127.0.0.1:7378'` (tránh WARP xung đột QUIC).

## 8. Trạng thái hiện tại (7/9/2026)
- Phim `ji5y8zz-jeA`: 5177 sub, dịch ~4200+, vision-inline chạy, voice ok.
- Còn chậm: mỗi batch vision ~30-60s (chấp nhận, ưu tiên chuẩn).
- Việc dở: autoVision toàn phim (tắt auto, chỉ nút tay); HF Space bỏ; Koyeb chưa deploy.
