"""Gradio-SDK entry cho Hugging Face free tier (khong Docker).
Web chinh (index.html + /api/*) chay tren FastAPI port 7860,
mount them UI Gradio nho o /gradio (nhap key, xem trang thai).
Logic dich/sub/vision tai su dung tu server.py."""
import os, json, glob, asyncio

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# ffmpeg tren HF: dung binary tinh tu imageio-ffmpeg
try:
    import imageio_ffmpeg
    os.environ.setdefault("FFMPEG_BIN", imageio_ffmpeg.get_ffmpeg_exe())
except Exception as e:
    print("imageio-ffmpeg missing:", e)

import server as S
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
import gradio as gr

app = FastAPI()

@app.get("/")
def root():
    return FileResponse(os.path.join(HERE, "index.html"))

@app.get("/api/config")
def cfg_get():
    base = S.LLM_URL.rsplit("/chat/completions", 1)[0]
    return {"base_url": base, "model": S.LLM_MODEL,
            "vision_model": S.VISION_MODEL, "has_key": bool(S.LLM_KEY)}

@app.post("/api/config")
async def cfg_post(req: Request):
    body = await req.json()
    base = (body.get("base_url") or "").rstrip("/")
    if base:
        S.LLM_URL = base + "/chat/completions"
        S.V9_URL = base + "/chat/completions"
    if body.get("model"): S.LLM_MODEL = body["model"]
    if body.get("vision_model"): S.VISION_MODEL = body["vision_model"]
    if "api_key" in body: S.LLM_KEY = body["api_key"] or ""
    return {"ok": True}

def _subs_or_404(vid, lang="zh"):
    subs = S.CACHE.get(vid)
    if not subs:
        hit = S.cload(vid, lang)
        subs = hit["subs"] if hit else []
    return subs

@app.get("/api/subs")
def api_subs(v: str, lang: str = "zh"):
    import subprocess, tempfile
    hit = S.cload(v, lang)
    if hit:
        return {"track": hit.get("track", "cached"), "cached": True, "subs": hit["subs"]}
    tmp = tempfile.mkdtemp()
    out = os.path.join(tmp, "s")
    subprocess.run(["yt-dlp", "--skip-download", "--write-auto-sub",
                    "--sub-langs", f"{lang}.*,en", "--sub-format", "vtt",
                    "-o", out + ".%(ext)s",
                    f"https://www.youtube.com/watch?v={v}"],
                   capture_output=True, timeout=300)
    files = glob.glob(os.path.join(tmp, "*"))
    if not files:
        return JSONResponse({"error": "Khong tai duoc sub"}, status_code=500)
    files.sort(key=lambda f: 0 if lang in f else 1)
    vtt = open(files[0], encoding="utf-8", errors="ignore").read()
    subs = S.parse_vtt(vtt)
    S.CACHE[v] = subs
    S.CUR_VID[0] = v
    if not os.path.exists(S.mpath(v)):
        S.build_meta(v, [s["text"] for s in subs])
    for k in range(min(6, len(subs))):
        subs[k]["vi"] = S.translate_zh_vi(subs[k]["text"])
        subs[k]["orig"] = subs[k]["text"]
    for s in subs:
        s.setdefault("orig", s["text"])
    S.csave(v, lang, os.path.basename(files[0]))
    if not S.video_path(v):
        import threading
        threading.Thread(target=S.ensure_video, args=(v,), daemon=True).start()
    return {"track": os.path.basename(files[0]), "subs": subs}

@app.get("/api/tr")
def api_tr(v: str, i: int = 0, n: int = 12, lang: str = "zh", novision: str = "0"):
    subs = _subs_or_404(v, lang)
    if not subs:
        return JSONResponse({"error": "NO_CACHE"}, status_code=404)
    S.CUR_VID[0] = v
    S.maybe_learn(v, i)
    todo = [k for k in range(i, min(i + n, len(subs))) if "vi" not in subs[k]]
    if todo:
        vrt = None if novision == "1" else S.vision_batch(v, todo)
        if vrt is None:
            full = [s["text"] for s in subs]
            vis = S.translate_batch([subs[k]["text"] for k in todo], full, todo[0])
            for k, vi in zip(todo, vis):
                subs[k]["vi"] = vi
                subs[k]["orig"] = subs[k]["text"]
    res = [{"i": k, "vi": subs[k].get("vi", subs[k]["text"])}
           for k in range(i, min(i + n, len(subs)))]
    S.csave(v, lang, "cached")
    return {"subs": res}

@app.get("/api/retrans")
def api_retrans(v: str, idx: str = "[]", lang: str = "zh"):
    subs = _subs_or_404(v, lang)
    if not subs:
        return JSONResponse({"error": "NO_CACHE"}, status_code=404)
    idxs = json.loads(idx)
    fixed = []
    for k in idxs:
        if 0 <= k < len(subs):
            vv = subs[k].get("vi", "")
            if not vv or S.has_cjk(vv):
                nv = S.translate_zh_vi(subs[k]["text"])
                if nv and not S.has_cjk(nv):
                    subs[k]["vi"] = nv
                    subs[k]["orig"] = subs[k]["text"]
                    fixed.append({"i": k, "vi": nv})
            else:
                fixed.append({"i": k, "vi": vv})
    S.csave(v, lang, "cached")
    return {"fixed": fixed}

@app.get("/api/vision")
def api_vision(v: str, i: int = 0, n: int = 30):
    subs = _subs_or_404(v)
    cand = [k for k in range(i, min(i + n, len(subs)))
            if not subs[k].get("verified") and S.NEED_VISION.search(subs[k]["text"])]
    res = S.vision_verify(v, cand[:12])
    return {"checked": len(cand), "fixed": res}

@app.get("/api/meta")
def api_meta(v: str):
    return S.mload(v)

@app.post("/api/meta")
async def api_meta_post(req: Request):
    body = await req.json()
    S.msave(body["v"], body["meta"])
    return {"ok": True}

@app.get("/api/clear")
def api_clear(v: str = ""):
    import glob as g
    n = 0
    if v:
        for f in g.glob(os.path.join(S.CACHE_DIR, f"{v}_*.json")):
            os.remove(f)
            n += 1
        S.CACHE.pop(v, None)
        return {"ok": f"Da xoa {n} cache cua {v}"}
    for f in g.glob(os.path.join(S.CACHE_DIR, "*.json")):
        os.remove(f)
        n += 1
    S.CACHE.clear()
    return {"ok": f"Da xoa toan bo {n} cache"}

@app.get("/api/voice")
def api_voice(t: str = "", v: str = "vi-VN-HoaiMyNeural"):
    import hashlib, edge_tts
    if v not in ("vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"):
        v = "vi-VN-HoaiMyNeural"
    text = t[:300]
    h = hashlib.md5((v + text).encode()).hexdigest()
    fp = os.path.join(S.VOICE_DIR, f"{h}.mp3")
    if not os.path.exists(fp):
        asyncio.run(edge_tts.Communicate(text, v).save(fp))
    return FileResponse(fp, media_type="audio/mpeg")

# ---- UI Gradio nho: nhap key + mo web chinh ----
with gr.Blocks(title="YT Sub Viet") as demo:
    gr.Markdown("# 🎬 YT Sub Việt realtime\nWeb chính ở trang gốc `/`. Nhập key rồi bấm **Mở web**.")
    base = gr.Textbox(value="https://openrouter.ai/api/v1", label="Base URL")
    key = gr.Textbox(type="password", label="API Key")
    model = gr.Textbox(value="google/gemma-3-27b-it", label="Model dịch")
    vmodel = gr.Textbox(value="google/gemma-3-27b-it", label="Model vision")
    out = gr.Textbox(label="Trạng thái")
    ob = gr.Button("Lưu key")
    ob.click(lambda b, k, m, vm: S.__dict__.update(
        LLM_URL=b.rstrip("/") + "/chat/completions",
        V9_URL=b.rstrip("/") + "/chat/completions",
        LLM_MODEL=m, VISION_MODEL=vm, LLM_KEY=k) or "Đã lưu! Về trang / để xem.",
        [base, key, model, vmodel], out)
    gr.HTML('<a href="/" target="_blank"><button style="padding:10px 20px;font-size:16px">▶ Mở web xem phim</button></a>')

app = gr.mount_gradio_app(app, demo, path="/gradio")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
