import json, re, html, urllib.request, urllib.parse, http.server, os, subprocess, glob, tempfile, sys
try: sys.stdout.reconfigure(encoding='utf-8',errors='backslashreplace'); sys.stderr.reconfigure(encoding='utf-8',errors='backslashreplace')
except Exception: pass
from functools import partial
# gateway 9router thi thoang tra ve chuoi bi double-encode (ThÃ¢n...): phat hien + sua
MOJI=re.compile(r'[ÃÂ][\x80-\xBF\u20AC\u201A\u0192\u201E\u2026\u2020\u2021\u02C6\u2030\u0160\u2039\u0152\u017D\u2018\u2019\u201C\u201D\u2022\u2013\u2014\u02DC\u2122\u0161\u203A\u0153\u017E\u0178\xA0-\xFF]')
_REV = {chr(i):i for i in range(256)}  # latin-1 identity (giua U+0080-U+009F raw)
for _b,_ch in {0x80:'\u20ac',0x82:'\u201a',0x83:'\u0192',0x84:'\u201e',0x85:'\u2026',0x86:'\u2020',0x87:'\u2021',0x88:'\u02c6',0x89:'\u2030',0x8a:'\u0160',0x8b:'\u2039',0x8c:'\u0152',0x8e:'\u017d',0x91:'\u2018',0x92:'\u2019',0x93:'\u201c',0x94:'\u201d',0x95:'\u2022',0x96:'\u2013',0x97:'\u2014',0x98:'\u02dc',0x99:'\u2122',0x9a:'\u0161',0x9b:'\u203a',0x9c:'\u0153',0x9e:'\u017e',0x9f:'\u0178'}.items():
  _REV.setdefault(_ch,_b)
def demojibake(s):
  # gateway doi khi tra UTF-8 bytes doc duoi dang cp1252 (ThÃ¢n, chÆ°a...): sua lai
  if not s or not _REV: return s
  out=[]; buf=[]
  def flush():
    if not buf: return
    run=''.join(buf); buf.clear()
    try:
      b=bytes(_REV[c] for c in run)
      t=b.decode('utf-8')
      out.append(t if t!=run else run); return
    except Exception: pass
    out.append(run)
  for ch in s:
    if ch in _REV and ord(ch)>=0x80: buf.append(ch)
    elif ch in _REV: buf.append(ch)  # ascii gop chung cung duoc (identity)
    else: flush(); out.append(ch)
  flush()
  return ''.join(out)

def parse_vtt(vtt):
    out=[]
    def ts(s):
        m=re.match(r'(\d+):(\d+):(\d+)[.,](\d+)',s)
        h,mn,sec,ms=map(int,m.groups()); return h*3600+mn*60+sec+ms/1000
    blocks=re.split(r'\n\n+',vtt)
    for p in blocks:
        m=re.search(r'(\d+:\d+:\d+[.,]\d+)\s*-->\s*(\d+:\d+:\d+[.,]\d+)',p)
        if not m: continue
        start=ts(m.group(1)); end=ts(m.group(2))
        lines=[l for l in p.splitlines() if l and '-->' not in l and not l.strip().isdigit() and not l.startswith('WEBVTT') and not l.startswith('Kind') and not l.startswith('Language') and not l.startswith('NOTE')]
        text=html.unescape(re.sub(r'<[^>]+>','', ' '.join(lines))).strip()
        if text: out.append({"start":start,"end":end,"text":text})
    # dedup liên tiếp
    ded=[]
    for s in out:
        if not ded or ded[-1]["text"]!=s["text"]: ded.append(s)
    out=ded
    for i in range(len(out)):
        # dur = end gốc của YouTube, kẹp 1..10s, không lấn sang câu sau
        d=out[i].pop("end")-out[i]["start"]
        if i+1<len(out): d=min(d,out[i+1]["start"]-out[i]["start"])
        out[i]["dur"]=max(1,min(d if d>0 else 4,10))
    return out

LLM_URL="http://localhost:20128/v1/chat/completions"
LLM_MODEL="gemma4"
LLM_KEY=""  # user tu nhap qua modal -> /api/config (khong hardcode)
# Prompt SRT streaming rút gọn từ skill dich-truyen + context window chống ngược ngữ pháp Trung-Việt
SRT_SYS=("Bạn là dịch giả phụ đề phim Trung-Việt. "
"NHIỆM VỤ: dịch các dòng CHÍNH (đánh số) sang tiếng Việt tự nhiên, văn nói, câu ngắn gọn hợp sub. "
"Các dòng [CTX trước/sau] chỉ là ngữ cảnh để hiểu chủ ngữ, thời gian, liên kết câu — KHÔNG dịch chúng. "
"Tiếng Trung hay đảo/lược chủ ngữ, bổ ngữ đặt trước — khi sang Việt phải sắp lại đúng: Ai làm gì, với ai, khi nào. "
"VD: srt1 thiếu chủ ngữ + srt2 có chủ ngữ → mượn chủ ngữ srt2 cho srt1, không dịch ngược. "
"NGƯỜI THỨ 3: nếu câu nhắc đến người vắng mặt (tên riêng, hắn/nàng chỉ người khác) → giữ gọi bằng TÊN hoặc anh ấy/cô ấy/ông ấy, TUYỆT ĐỐI KHÔNG nhầm với người đang nghe. "
"Xưng hô cổ trang: ta-ngươi-hắn-nàng, hiện đại: ta-anh-em; KHÔNG dùng tôi/cậu/bạn/mày/mình. "
"Tên riêng Hán-Việt viết hoa. NGƯỜI LẠ (không khớp knowledge): xưng ta-ngươi, cấm đoán bừa bố/con/anh/em. OUTPUT 100% TIẾNG VIỆT: cấm tuyệt đối mọi ký tự Trung ([\u4e00-\u9fff]) - sót 1 chữ cũng là lỗi nghiêm trọng, phải dịch nốt chữ đó. Chỉ trả về đúng số dòng CHÍNH, mỗi dòng 1 bản dịch, giữ thứ tự, không đánh số, không giải thích.")
CJK=re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf]')
def has_cjk(s): return bool(s and CJK.search(s))
def mymem(text):
  q=urllib.parse.urlencode({"q":text[:450],"langpair":"zh|vi"})
  data=urllib.request.urlopen(f"https://api.mymemory.translated.net/get?{q}",timeout=15).read().decode()
  j=json.loads(data)
  t=j.get("responseData",{}).get("translatedText","")
  if t and "QUERY LENGTH" not in t and "INVALID" not in t.upper(): return post(t)
  return None
REPS={"tôi":"ta","Tôi":"Ta","cậu":"ngươi","bạn":"ngươi","mày":"ngươi","mình":"ta"}
def post(s):
 for k,v in REPS.items(): s=s.replace(k,v)
 return demojibake(s.strip())
META_CACHE={}
def mpath(vid): return os.path.join(CACHE_DIR,f"{vid}_meta.json")
def mload(vid):
 if vid in META_CACHE: return META_CACHE[vid]
 try:
  p=mpath(vid)
  if os.path.exists(p):
   META_CACHE[vid]=json.load(open(p,encoding='utf-8'))
   return META_CACHE[vid]
 except Exception as e: print("meta load err",e)
 return {"boi_canh":"cổ trang","nhan_vat":[],"xung_ho":"ta-ngươi","glossary":{}}
def msave(vid,meta):
 META_CACHE[vid]=meta
 json.dump(meta,open(mpath(vid),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
def meta_str(vid):
 m=mload(vid)
 if not m.get("nhan_vat"): return ""
 def fmt(x):
  conf=x.get('do_tin_cay','xac_nhan')
  tag='' if conf=='xac_nhan' else ' [DU DOAN chua xac nhan - dung ta-nguoi tru khi thoai hien tai goi ro]'
  return f"{x.get('ten')} ({x.get('gioi_tinh','?')},{x.get('tuoi','?')} - {x.get('vai')}; nhan dang: {x.get('dac_diem','?')}{tag})"
 nv="; ".join(fmt(x) for x in m["nhan_vat"][:20])
 pairs="; ".join(f"{p.get('a')} goi {p.get('b')}: '{p.get('xung')}'" for p in (m.get("quan_he") or [])[:20])
 gl="; ".join(f"{k}={v}" for k,v in (m.get("glossary") or {}).items())
 bc=m.get('bo_canh') or m.get('boi_canh')
 return (f"[PHIM: bối cảnh {bc}. Nhân vật: {nv}. Cặp xưng hô CHUẨN (chỉ dùng đúng cặp này): {pairs}. "
 f"Glossary: {gl}. LUAT CUNG: (1) NGUOI LA -> ta-nguoi, CAM doan bua. (2) Nhan vat DU DOAN -> coi nhu nguoi la (ta-nguoi), TRU KHI chinh cac dong dang dich co loi goi xac nhan (vd goi 'bo' thi moi la con). (3) Chi dung xung ho quan he khi nhan vat XAC NHAN hoac thoai hien tai tu goi ro.]")
def build_meta(vid, sample):
 # tự trích knowledge phim từ ~80 câu đầu (relationship mapping B0 trong skill)
 try:
  body=json.dumps({"model":LLM_MODEL,"stream":False,"temperature":0.2,"max_tokens":1500,
   "messages":[{"role":"system","content":"Bạn là trợ lý phân tích phim Trung. Chỉ trả JSON thuần. Mỗi nhân vật PHẢI có tuoi+gioi_tinh+dac_diem để phân biệt người lạ. quan_he liệt kê TỪNG CẶP có quan hệ rõ (a gọi b thế nào). Người không rõ quan hệ thì không cho vào quan_he (mặc định ta-ngươi)."},
    {"role":"user","content":"Từ 80 câu sub sau, trích JSON {bo_canh:'cổ trang|hiện đại', nhan_vat:[{ten, tuoi, gioi_tinh, vai, dac_diem, do_tin_cay:'du_doan', xac_nhan_boi:''}], quan_he:[{a, b, xung}], glossary:{tên:phiên âm Hán-Việt}}. Dau phim chua co bang chung xung ho ro thi tat ca la du_doan.\n"+"\n".join(sample[:80])}] }).encode()
  req=urllib.request.Request(LLM_URL,data=body,headers=api_headers())
  d=urllib.request.urlopen(req,timeout=90).read().decode()
  txt=json.loads(d)["choices"][0]["message"]["content"]
  m=re.search(r'\{.*\}',txt,re.S)
  if m:
   meta=json.loads(m.group(0)); msave(vid,meta); print(f"meta built {vid}: {meta}"); return meta
 except Exception as e: print("meta build err",e)
 return mload(vid)
import threading
def learn_meta(vid):
 # AI học liên tục: đọc 40 cặp đã dịch gần nhất + knowledge hiện tại -> bổ sung nhân vật/glossary/xưng hô
 try:
  subs=CACHE.get(vid,[])
  done=[s for s in subs if s.get("vi")]
  if len(done)<10: return
  recent=done[-40:]
  pairs="\n".join(f"RAW: {s['text']}\nVI: {s.get('vi')}" for s in recent)
  cur=json.dumps(mload(vid),ensure_ascii=False)
  body=json.dumps({"model":LLM_MODEL,"stream":False,"temperature":0.2,"max_tokens":1000,
   "messages":[{"role":"system","content":"Bạn là trợ lý học knowledge phim. Chỉ trả JSON thuần cùng schema input {bo_canh, nhan_vat:[{ten,tuoi,gioi_tinh,vai,dac_diem,do_tin_cay,xac_nhan_boi}], quan_he:[{a,b,xung}], glossary, mac_dinh}. NHIEM VU CHINH: XAC NHAN hoac SUA nhan vat tu bang chung xung ho trong cap dich (vd: X goi Y la 'bo' => X la con Y => do_tin_cay='xac_nhan', xac_nhan_boi='cau ... goi bo'). Nhan vat moi mac dinh do_tin_cay='du_doan'. Chi them cap quan_he khi co bang chung goi ro. Nguoi la KHONG cho vao quan_he."},
    {"role":"user","content":f"Knowledge hiện tại:\n{cur}\n\n40 cặp dịch gần nhất:\n{pairs}\n\nTrả JSON knowledge cập nhật."}] }).encode()
  req=urllib.request.Request(LLM_URL,data=body,headers=api_headers())
  d=urllib.request.urlopen(req,timeout=90).read().decode()
  txt=json.loads(d)["choices"][0]["message"]["content"]
  m=re.search(r'\{.*\}',txt,re.S)
  if m:
   meta=json.loads(m.group(0)); msave(vid,meta); print(f"meta learned {vid}: +{len(meta.get('nhan_vat',[]))} nv")
 except Exception as e: print("meta learn err",e)
def maybe_learn(vid, idx):
 # mỗi 60 câu học 1 lần, chạy nền không chặn dịch
 if idx>0 and idx%60==0:
  threading.Thread(target=learn_meta,args=(vid,),daemon=True).start()
 return mload(vid)
def _llm_raw(lines, ctx_before="", ctx_after="", vid=""):
    ctx=""
    if ctx_before: ctx+=f"[CTX trước]: {ctx_before}\n"
    if ctx_after: ctx+=f"[CTX sau]: {ctx_after}\n"
    sys=SRT_SYS+("\n"+meta_str(vid) if vid else "")
    body=json.dumps({"model":LLM_MODEL,"stream":False,"temperature":0.3,"max_tokens":2500,
     "messages":[{"role":"system","content":sys},
      {"role":"user","content":ctx+"Dịch "+str(len(lines))+" dòng CHÍNH sau (dùng CTX để hiểu, chỉ trả "+str(len(lines))+" dòng):\n"+"\n".join(f"{i+1}. {t}" for i,t in enumerate(lines))}] }).encode()
    req=urllib.request.Request(LLM_URL,data=body,headers=api_headers())
    d=urllib.request.urlopen(req,timeout=120).read().decode()
    j=json.loads(d)
    txt=j["choices"][0]["message"]["content"].strip()
    # tách dòng, bỏ số thứ tự
    out=[]
    for l in txt.splitlines():
        l=l.strip()
        if not l: continue
        l=re.sub(r'^\d+[\.\)\:\-\]]\s*','',l).strip()
        out.append(post(demojibake(l)))
    return out
def llm_batch(lines, ctx_before="", ctx_after="", vid=""):
    # VERIFY (skill): sot 1 chu Trung la dich lai - toi da 2 vong + fallback mymem
    out=_llm_raw(lines,ctx_before,ctx_after,vid)
    if len(out)!=len(lines): return out  # lech dong -> de translate_batch retry
    for rnd in range(2):
        bad=[i for i,t in enumerate(out) if has_cjk(t)]
        if not bad: break
        print(f"verify: {len(bad)} dong con chu Trung, dich lai (vong {rnd+1}): {[lines[i][:30] for i in bad][:3]}")
        for i in bad:
            try:
                r=_llm_raw([lines[i]],ctx_before,ctx_after,vid)
                if r and not has_cjk(r[0]): out[i]=r[0]
            except Exception as e: print("verify retry err",e)
    for i,t in enumerate(out):
        if has_cjk(t):
            try:
                m=mymem(lines[i])
                if m and not has_cjk(m): out[i]=m
                else: print(f"VERIFY-FAIL giu goc (van con Trung): {lines[i][:50]}")
            except Exception as e: print("verify mymem err",e)
    return out
def translate_zh_vi(text):
    try:
        r=llm_batch([text])
        if r and not has_cjk(r[0]): return r[0]
        print(f"verify: llm sot Trung, chuyen mymem: {text[:40]}")
    except Exception as e: print("llm err",e)
    try:
        m=mymem(text)
        if m: return m
    except Exception as e: print("trans err",e)
    return text
CUR_VID=[""]
def translate_batch(texts, full=None, base=0):
    # full: toàn bộ sub gốc để lấy CTX trước/sau; base: vị trí batch trong full
    try:
        cb=" ".join(full[base-2:base]) if full and base>=2 else (full[base-1] if full and base>=1 else "")
        ca=" ".join(full[base+len(texts):base+len(texts)+2]) if full else ""
        r=llm_batch(texts,cb,ca,CUR_VID[0])
        if len(r)==len(texts): return r
        print(f"llm lệch dòng {len(r)}/{len(texts)}, retry từng câu có ctx")
    except Exception as e: print("llm batch err",e)
    out=[]
    for j,t in enumerate(texts):
        g=base+j
        cb=full[g-1] if full and g>=1 else ""
        ca=full[g+1] if full and g+1<len(full) else ""
        try:
            r=llm_batch([t],cb,ca,CUR_VID[0])
            out.append(r[0] if r else translate_zh_vi(t))
        except Exception: out.append(translate_zh_vi(t))
    return out

CACHE={}
CACHE_DIR=os.path.join(os.path.dirname(os.path.abspath(__file__)),"cache")
os.makedirs(CACHE_DIR,exist_ok=True)
CACHE_TTL=60*86400  # 60 ngày
import time
def cpath(vid,lang): return os.path.join(CACHE_DIR,f"{vid}_{lang}.json")
def cload(vid,lang):
 try:
  p=cpath(vid,lang)
  if not os.path.exists(p): return None
  if time.time()-os.path.getmtime(p)>CACHE_TTL: return None
  j=json.load(open(p,encoding='utf-8'))
  CACHE[vid]=j["subs"]
  print(f"cache HIT {vid} ({len(j['subs'])} câu)")
  return j
 except Exception as e: print("cache load err",e); return None
def csave(vid,lang,track):
 try:
  subs=CACHE.get(vid,[])
  if not subs: return  # không lưu stub rỗng
  json.dump({"track":track,"subs":subs},open(cpath(vid,lang),'w',encoding='utf-8'),ensure_ascii=False)
 except Exception as e: print("cache save err",e)
import hashlib, asyncio
def ffmpeg_bin(): return os.environ.get("FFMPEG_BIN","ffmpeg")
VOICE_DIR=os.path.join(os.path.dirname(os.path.abspath(__file__)),"cache","voice")
os.makedirs(VOICE_DIR,exist_ok=True)
# ---- Vision verify: frame + gemma vision qua 9router de chuan xung ho ----
VISION_MODEL="ollama/gemma4:31b-cloud"
V9_URL="http://localhost:20128/v1/chat/completions"
def api_headers():
  h={"Content-Type":"application/json"}
  if LLM_KEY: h["Authorization"]="Bearer "+LLM_KEY
  return h
NEED_VISION=re.compile(r'[\u4e00-\u9fff]*[\u4f60\u60a8\u6211\u4ed6\u5979][\u4e00-\u9fff]*')
def video_path(vid):
  for ext in ("mp4","mkv","webm"):
    p=os.path.join(CACHE_DIR,f"{vid}.{ext}")
    if os.path.exists(p): return p
  return None
def ensure_video(vid):
  p=video_path(vid)
  if p: return p
  out=os.path.join(CACHE_DIR,f"{vid}.mp4")
  subprocess.run(["yt-dlp","-f","396","-o",out,f"https://www.youtube.com/watch?v={vid}"],capture_output=True,timeout=3600)
  return out if os.path.exists(out) else None
def frame_b64(vid,t):
  mp4=video_path(vid) or ensure_video(vid)
  import base64 as _b, tempfile as _t
  jp=os.path.join(_t.gettempdir(),f"fr_{vid}_{int(t)}.jpg")
  subprocess.run([ffmpeg_bin(),"-y","-v","error","-ss",str(max(0,t-0.5)),"-i",mp4,"-frames:v","1","-vf","scale=640:-1","-q:v","4",jp],capture_output=True,timeout=120)
  return _b.b64encode(open(jp,'rb').read()).decode()
def vision_batch(vid, idxs):
  # REALTIME 1-pass: frame + sub -> speaker + dich chuan xung ho ngay, khong dich text truoc
  subs=CACHE.get(vid,[])
  if not subs or not video_path(vid): return None  # chua co video -> de text xu ly
  out=[]
  for bi in range(0,len(idxs),6):
    grp=idxs[bi:bi+6]
    try:
      mid=subs[grp[len(grp)//2]]
      px=frame_b64(vid,mid["start"]+min(1,(mid.get("dur",3)/2)))
      lines="\n".join(f"{k+1}. {subs[k]['text']}" for k in grp)
      ctxb=" ".join(s["text"] for s in subs[max(0,grp[0]-2):grp[0]])
      prompt=(("Anh la 1 frame phim. B1: xac dinh NGUOI NOI (tuoi, gioi, vi tri, khop ai trong knowledge) + NGUOI NGHE (ai dang nghe) + NGUOI THU 3 (neu cau noi nhac den ai do vang mat - ghi ro ten). B2: dich "+str(len(grp))+" dong sub Trung sau sang Viet. QUY TAC XUNG HO: nguoi noi goi nguoi nghe theo dung quan he trong knowledge (bo-con, vo-chong...); nguoi thu 3 duoc nhac toi thi goi bang TEN hoac anh ay/co ay/ong ay - TUYET DOI KHONG nham nguoi thu 3 voi nguoi nghe. Knowledge: "+meta_str(vid)+" CTX truoc: "+ctxb+" Tieng Trung hay luoc chu ngu - muon chu ngu tu CTX/anh, sap xep lai dung ngu phap Viet. Chi tra JSON {\"nguoi_noi\": \"...\", \"nguoi_nghe\": \"...\", \"nguoi_thu3\": \"...\", \"dich\": [...] (dung "+str(len(grp))+" dong)}. Cac dong:\n")+lines)
      body=json.dumps({"model":VISION_MODEL,"stream":False,"temperature":0.2,"max_tokens":1200,"messages":[{"role":"user","content":[{"type":"text","text":prompt},{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+px}}]}]}).encode()
      req=urllib.request.Request(V9_URL,data=body,headers=api_headers())
      d=urllib.request.urlopen(req,timeout=180).read().decode('utf-8',errors='ignore')
      txt=json.loads(d)["choices"][0]["message"]["content"]
      m=re.search(r'\{.*\}',txt,re.S)
      if not m or len(json.loads(m.group(0)).get("dich",[]))!=len(grp): raise Exception("lech dong vision")
      r=json.loads(m.group(0))
      spk=r.get("nguoi_noi","")
      for k,vi in zip(grp,r["dich"]):
        vi=post(demojibake(vi))
        if has_cjk(vi):  # VERIFY: vision sot Trung -> ep dich lai bang text
          print(f"verify: vision sot Trung cau {k}, dich lai text: {subs[k]['text'][:30]}")
          vi=translate_zh_vi(subs[k]["text"])
        subs[k]["vi"]=vi; subs[k]["orig"]=subs[k]["text"]; subs[k]["speaker"]=spk; subs[k]["verified"]="vision"
        out.append({"i":k,"vi":subs[k]["vi"]})
      print(f"vision-rt ok {vid} {grp} spk={spk[:50]}")
    except Exception as e:
      print("vision-rt group fail -> text",grp,e)
      try:
        full=[s["text"] for s in subs]
        vis=translate_batch([subs[k]["text"] for k in grp],full,grp[0])
        for k,vi in zip(grp,vis):
          subs[k]["vi"]=vi; subs[k]["orig"]=subs[k]["text"]
          out.append({"i":k,"vi":vi})
      except Exception as e2:
        print("vision-rt group text fail",grp,e2)
        return None
  csave(vid,"zh","cached+vision")
  return out
def vision_verify(vid, idxs):
  # dung chung vision_batch (1-pass, co nguoi noi/nghe/thu3) - giu cho nut check tay
  return vision_batch(vid, idxs) or []
class H(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        u=urllib.parse.urlparse(self.path)
        if u.path=="/api/config":
            global LLM_URL,LLM_MODEL,LLM_KEY,VISION_MODEL,V9_URL
            ln=int(self.headers.get('Content-Length',0))
            body=json.loads(self.rfile.read(ln).decode('utf-8'))
            base=(body.get("base_url") or "").rstrip("/")
            if base:
                LLM_URL=base+"/chat/completions"; V9_URL=base+"/chat/completions"
            if body.get("model"): LLM_MODEL=body["model"]
            if body.get("vision_model"): VISION_MODEL=body["vision_model"]
            if "api_key" in body: LLM_KEY=body["api_key"] or ""
            print(f"config: base={base} model={LLM_MODEL} vision={VISION_MODEL} key={'***' if LLM_KEY else '(trong)'}")
            self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        if u.path=="/api/meta":
            ln=int(self.headers.get('Content-Length',0))
            body=json.loads(self.rfile.read(ln).decode('utf-8'))
            msave(body["v"],body["meta"])
            self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        self.send_response(404);self.end_headers()
    def do_GET(self):
        u=urllib.parse.urlparse(self.path)
        if u.path=="/api/config":
            base=LLM_URL.rsplit("/chat/completions",1)[0]
            self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8");self.end_headers()
            self.wfile.write(json.dumps({"base_url":base,"model":LLM_MODEL,"vision_model":VISION_MODEL,"has_key":bool(LLM_KEY)},ensure_ascii=False).encode())
            return
        if u.path=="/api/vision":
            qs=urllib.parse.parse_qs(u.query)
            vid=qs.get("v",[""])[0]; start=int(qs.get("i",[0])[0]); n=int(qs.get("n",[30])[0])
            try:
                subs=CACHE.get(vid) or (cload(vid,"zh") or {}).get("subs",[])
                cand=[k for k in range(start,min(start+n,len(subs))) if not subs[k].get("verified") and NEED_VISION.search(subs[k]["text"])]
                res=vision_verify(vid,cand[:12])
                self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8");self.end_headers()
                self.wfile.write(json.dumps({"checked":len(cand),"fixed":res},ensure_ascii=False).encode())
            except Exception as e:
                self.send_response(500);self.send_header("Content-Type","application/json");self.end_headers()
                self.wfile.write(json.dumps({"error":str(e)}).encode())
            return
        if u.path=="/api/retrans":
            # CONG retrans: cau nao con chu Trung -> dich lai NGAY, xong moi tra (resume sau)
            qs=urllib.parse.parse_qs(u.query)
            vid=qs.get("v",[""])[0]
            idxs=json.loads(qs.get("idx","[]")[0])
            try:
                subs=CACHE.get(vid)
                if not subs:
                    hit=cload(vid,qs.get("lang",["zh"])[0]); subs=hit["subs"] if hit else []
                fixed=[]
                for k in idxs:
                    if 0<=k<len(subs):
                        v=subs[k].get("vi","")
                        if not v or has_cjk(v):
                            nv=translate_zh_vi(subs[k]["text"])
                            if nv and not has_cjk(nv):
                                subs[k]["vi"]=nv; subs[k]["orig"]=subs[k]["text"]
                                fixed.append({"i":k,"vi":nv})
                            else:
                                print(f"RETRANS-FAIL van con Trung cau {k}: {subs[k]['text'][:40]}")
                        else:
                            fixed.append({"i":k,"vi":v})
                csave(vid,qs.get("lang",["zh"])[0],"cached")
                self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8");self.end_headers()
                self.wfile.write(json.dumps({"fixed":fixed},ensure_ascii=False).encode())
            except Exception as e:
                self.send_response(500);self.send_header("Content-Type","application/json");self.end_headers()
                self.wfile.write(json.dumps({"error":str(e)}).encode())
            return
        if u.path=="/api/voice":
            import edge_tts
            qs=urllib.parse.parse_qs(u.query)
            text=qs.get("t",[""])[0][:300]
            voice=qs.get("v",["vi-VN-HoaiMyNeural"])[0]
            if voice not in ("vi-VN-HoaiMyNeural","vi-VN-NamMinhNeural"): voice="vi-VN-HoaiMyNeural"
            h=hashlib.md5((voice+text).encode()).hexdigest()
            fp=os.path.join(VOICE_DIR,f"{h}.mp3")
            try:
                if not os.path.exists(fp):
                    asyncio.run(edge_tts.Communicate(text,voice).save(fp))
                self.send_response(200);self.send_header("Content-Type","audio/mpeg");self.send_header("Cache-Control","public,max-age=5184000");self.end_headers()
                self.wfile.write(open(fp,'rb').read())
            except Exception as e:
                self.send_response(500);self.send_header("Content-Type","application/json");self.end_headers()
                self.wfile.write(json.dumps({"error":str(e)}).encode())
            return
        if u.path=="/api/clear":
            import shutil
            qs=urllib.parse.parse_qs(u.query)
            vid=qs.get("v",[None])[0]
            try:
                if vid:
                    n=0
                    for f in glob.glob(os.path.join(CACHE_DIR,f"{vid}_*.json")):
                        os.remove(f); n+=1
                    CACHE.pop(vid,None)
                    msg=f"Đã xóa {n} cache của {vid}"
                else:
                    n=0
                    for f in glob.glob(os.path.join(CACHE_DIR,"*.json")):
                        os.remove(f); n+=1
                    CACHE.clear()
                    msg=f"Đã xóa toàn bộ {n} cache"
                self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8");self.end_headers()
                self.wfile.write(json.dumps({"ok":msg},ensure_ascii=False).encode())
            except Exception as e:
                self.send_response(500);self.send_header("Content-Type","application/json");self.end_headers()
                self.wfile.write(json.dumps({"error":str(e)}).encode())
            return
        if u.path=="/api/meta":
            qs=urllib.parse.parse_qs(u.query)
            vid=qs.get("v",[""])[0]
            self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8");self.end_headers()
            self.wfile.write(json.dumps(mload(vid),ensure_ascii=False).encode())
            return
        if u.path=="/api/tr":
            qs=urllib.parse.parse_qs(u.query)
            idx=int(qs.get("i",[0])[0]); n=int(qs.get("n",[12])[0])
            vid=qs.get("v",[""])[0]
            subs=CACHE.get(vid)
            if not subs:  # server vua restart mat RAM -> nap lai tu dia (khong thi tra rong, client doi mai)
                hit=cload(vid,qs.get("lang",["zh"])[0])
                subs=hit["subs"] if hit else []
            if not subs:
                self.send_response(404);self.send_header("Content-Type","application/json; charset=utf-8");self.end_headers()
                self.wfile.write(json.dumps({"error":"NO_CACHE", "msg":"server khong co sub video nay, goi /api/subs truoc"},ensure_ascii=False).encode())
                return
            CUR_VID[0]=vid; maybe_learn(vid,idx)
            res=[]
            todo=[k for k in range(idx,min(idx+n,len(subs))) if "vi" not in subs[k]]
            if todo:
                # REALTIME 1-pass: co video + khong novision -> vision; con lai text
                novision=qs.get("novision",["0"])[0]=="1"
                vrt=None if novision else vision_batch(vid,todo)
                if vrt is None:
                    full=[s["text"] for s in subs]
                    vis=translate_batch([subs[k]["text"] for k in todo],full,todo[0])
                    for k,vi in zip(todo,vis):
                        subs[k]["vi"]=vi; subs[k]["orig"]=subs[k]["text"]
            for k in range(idx,min(idx+n,len(subs))):
                res.append({"i":k,"vi":subs[k].get("vi",subs[k]["text"])})
            qs2=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            csave(vid,qs2.get("lang",["zh"])[0],"cached")
            self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8");self.end_headers()
            self.wfile.write(json.dumps({"subs":res},ensure_ascii=False).encode())
            return
        if u.path=="/api/subs":
            qs=urllib.parse.parse_qs(u.query)
            vid=qs.get("v",[None])[0]
            lang=qs.get("lang",["zh"])[0]
            try:
                hit=cload(vid,lang)
                if hit:
                    subs=hit["subs"]
                    # nếu cache đã dịch full thì trả luôn, không dịch lại
                    self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("X-Cache","HIT");self.end_headers()
                    self.wfile.write(json.dumps({"track":hit.get("track","cached"),"cached":True,"subs":subs},ensure_ascii=False).encode())
                    return
                tmp=tempfile.mkdtemp()
                out=os.path.join(tmp,"s")
                cmd=["yt-dlp","--skip-download","--write-auto-sub","--sub-langs",f"{lang}.*,en",
                     "--sub-format","vtt","-o",out+".%(ext)s",f"https://www.youtube.com/watch?v={vid}"]
                subprocess.run(cmd,capture_output=True,timeout=120)
                files=glob.glob(os.path.join(tmp,"*"))
                if not files: raise Exception("Không tải được sub (video không có sub / bị chặn)")
                # ưu tiên zh
                files.sort(key=lambda f: 0 if lang in f else 1)
                vtt=open(files[0],encoding='utf-8',errors='ignore').read()
                subs=parse_vtt(vtt)
                CACHE[vid]=subs; CUR_VID[0]=vid
                # tai video nen (cho vision realtime) - khong chan
                if not video_path(vid):
                    threading.Thread(target=ensure_video,args=(vid,),daemon=True).start()
                # B0 skill: lập knowledge phim (nhân vật/quan hệ/xưng hô) từ sub trước khi dịch
                if not os.path.exists(mpath(vid)):
                    build_meta(vid,[s["text"] for s in subs])
                # dịch ngay 6 câu đầu để hiện tức thì
                for k in range(min(6,len(subs))):
                    subs[k]["vi"]=translate_zh_vi(subs[k]["text"])
                    subs[k]["orig"]=subs[k]["text"]
                for s in subs: s.setdefault("orig",s["text"])
                csave(vid,lang,os.path.basename(files[0]))
                self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("X-Cache","MISS");self.end_headers()
                self.wfile.write(json.dumps({"track":os.path.basename(files[0]),"subs":subs},ensure_ascii=False).encode())
            except Exception as e:
                self.send_response(500);self.send_header("Content-Type","application/json");self.end_headers()
                self.wfile.write(json.dumps({"error":str(e)}).encode())
            return
        return super().do_GET()

def _lan_ip():
    import socket
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        s.connect(("8.8.8.8",80)); ip=s.getsockname()[0]; s.close()
        return ip
    except Exception: return "localhost"
if __name__=="__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    port=int(os.environ.get("PORT",sys.argv[1] if len(sys.argv)>1 else 7378))
    host=os.environ.get("HOST","0.0.0.0" if len(sys.argv)>1 else "127.0.0.1")
    print(f"Serving {host}:{port}",flush=True)
    if host=="0.0.0.0":
        print(f"Xem tren may nay: http://127.0.0.1:{port}",flush=True)
        print(f"Xem tu dien thoai/may khac cung wifi: http://{_lan_ip()}:{port}",flush=True)
    http.server.ThreadingHTTPServer((host,port),H).serve_forever()
