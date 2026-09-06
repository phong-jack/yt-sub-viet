# Hugging Face Spaces (Docker) — free, nhanh nhất cho web này
# Vì sao HF: free không cần thẻ, có sẵn ffmpeg/python, giữ cache qua persistent storage,
# chạy docker tùy ý (cần yt-dlp + edge-tts mà Streamlit/Railway-free khó chịu).

1. Tạo Space mới tại https://huggingface.co/new-space
   - Chọn **Docker** (blank), visibility tùy (Private nếu chỉ mình xem)
2. Upload 3 file: `server.py`, `index.html`, `Dockerfile` (+ tạo file `.dockerignore` rỗng)
3. Trong Settings → Variables: không cần gì thêm (key do user nhập trên web)
4. Space tự build + chạy ở port 7860 → mở link Space là xem

LƯU Ý QUAN TRỌNG:
- YouTube hay chặn IP datacenter (yt-dlp 429/bot-check). Nếu tải sub lỗi trên host:
  cách 1: mở video ở nhà 1 lần cho cache sub (cache đi theo persistent storage),
  cách 2: dùng cookie: `yt-dlp --cookies-from-browser chrome` (tự up file cookies.txt + sửa lệnh).
- Persistent storage HF giữ `cache/` 60 ngày như local — xem lần 2 instant.
- Free Space ngủ khi không ai xem (~15-30s để thức). Muốn luôn thức thì dùng Railway/Koyeb
  (free nhưng giới hạn giờ chạy) hoặc VPS rẻ (~60k/tháng).
- Mỗi người xem tự nhập key ở popup 🔑 (OpenRouter/Ollama cloud/9router...),
  tiền token tính vào key của họ, chủ host không tốn.
