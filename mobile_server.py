import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import blog_content_gen
import config as cfg
from blog_automation_flow import run_main_loop


class _DummyVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class _DummyRoot:
    def after(self, _ms, fn):
        try:
            fn()
        except Exception:
            pass


class _DummyBtn:
    def config(self, **_kwargs):
        return


class HeadlessApp:
    def __init__(self):
        self.root = _DummyRoot()
        self.btn_run = _DummyBtn()
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.image_dir = os.path.join(self.base_dir, "generated_images")
        if not os.path.exists(self.image_dir):
            os.makedirs(self.image_dir)
        self.custom_img_paths = []
        self.img_mode_var = _DummyVar("ai")
        self.is_paused = False
        self._logs = []
        self._lock = threading.Lock()
        self.master_guidelines = ""

    def log(self, msg, level="info"):
        del level
        with self._lock:
            self._logs.append(msg)
            # 메모리 보호
            if len(self._logs) > 1500:
                self._logs = self._logs[-1500:]

    def get_logs(self, tail=200):
        with self._lock:
            return self._logs[-tail:]

    async def check_pause(self):
        while self.is_paused:
            await asyncio.sleep(0.5)

    async def wait_with_pause(self, seconds):
        steps = int(seconds * 2)
        for _ in range(steps):
            await self.check_pause()
            await asyncio.sleep(0.5)
        if seconds % 0.5 > 0:
            await self.check_pause()
            await asyncio.sleep(seconds % 0.5)

    def _ask_yesno_on_main(self, _title, _message):
        # 모바일 서버에서는 수동 확인을 사용하지 않음
        return True

    async def generate_images(self, config, required_keyword, extra_keyword=None, title=None, image_desc=None):
        return await blog_content_gen.generate_images(
            config, required_keyword, extra_keyword, self.log, self.image_dir, title=title, image_desc=image_desc
        )

    async def generate_outline(self, config, required_keyword, extra_keyword=None):
        master = self.master_guidelines or ""
        return await blog_content_gen.generate_outline(config, required_keyword, extra_keyword, self.log, master)

    async def generate_body_from_outline(self, config, title, outline_str, required_keyword, extra_keyword=None, account_id=None):
        master = self.master_guidelines or ""
        return await blog_content_gen.generate_body_from_outline(
            config, title, outline_str, required_keyword, extra_keyword, self.log, master, account_id
        )


class AppState:
    def __init__(self):
        self.app = HeadlessApp()
        self.running = False
        self.last_error = ""
        self.thread = None
        self.lock = threading.Lock()

    def start(self, config):
        with self.lock:
            if self.running:
                raise RuntimeError("이미 실행 중입니다.")
            self.running = True
            self.last_error = ""

        def _worker():
            try:
                self.app.master_guidelines = config.get("master_guidelines", "")
                asyncio.run(run_main_loop(self.app, config))
            except Exception as e:
                self.last_error = str(e)
                self.app.log(f"❌ 서버 실행 오류: {e}")
            finally:
                with self.lock:
                    self.running = False

        self.thread = threading.Thread(target=_worker, daemon=True)
        self.thread.start()


STATE = AppState()


def _default_keywords():
    return "듀라코트 리빙코트, 욕실코팅제, 타일코팅제, 식탁코팅, 원목코팅, 수전코팅"


def _load_defaults():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    accounts_path = os.path.join(base_dir, "accounts.json")
    data = {}
    if os.path.exists(accounts_path):
        try:
            with open(accounts_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    api_key = data.get("gemini_key") or cfg.GOOGLE_API_KEY or cfg.GEMINI_API_KEY or ""
    return {
        "gemini_key": api_key,
        "keywords": data.get("keywords", ""),
        "post_type": data.get("post_type", "제품 홍보"),
        "count": 1,
        "gap": 1,
        "product_url": data.get("product_url", ""),
        "vercel_api_url": data.get("vercel_api_url", ""),
        "vercel_webhook_secret": data.get("vercel_webhook_secret", ""),
        "vercel_enabled": bool(data.get("vercel_enabled", False)),
        "vercel_interval_minutes": int(data.get("vercel_interval_minutes", 20)),
        "vercel_mode": data.get("vercel_mode", "local"),
        "naver_id1": data.get("naver_id1", cfg.NAVER_ACCOUNTS[0]["id"] if len(cfg.NAVER_ACCOUNTS) > 0 else ""),
        "naver_pw1": data.get("naver_pw1", cfg.NAVER_ACCOUNTS[0]["pw"] if len(cfg.NAVER_ACCOUNTS) > 0 else ""),
        "naver_id2": data.get("naver_id2", cfg.NAVER_ACCOUNTS[1]["id"] if len(cfg.NAVER_ACCOUNTS) > 1 else ""),
        "naver_pw2": data.get("naver_pw2", cfg.NAVER_ACCOUNTS[1]["pw"] if len(cfg.NAVER_ACCOUNTS) > 1 else ""),
        "tistory_id": data.get("tistory_id", cfg.TISTORY_ID),
        "tistory_pw": data.get("tistory_pw", cfg.TISTORY_PW),
        "use_naver1": bool(data.get("use_naver1", True)),
        "use_naver2": bool(data.get("use_naver2", True)),
        "use_tistory": bool(data.get("use_tistory", True)),
    }


DEFAULTS = _load_defaults()


def build_config(payload):
    keywords_raw = payload.get("keywords", "")
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
    keywords = list(dict.fromkeys(keywords))

    naver_ids = []
    naver_pws = []
    n1 = (payload.get("naver_id1") or "").strip()
    p1 = (payload.get("naver_pw1") or "").strip()
    n2 = (payload.get("naver_id2") or "").strip()
    p2 = (payload.get("naver_pw2") or "").strip()
    if n1:
        naver_ids.append(n1)
        naver_pws.append(p1)
    if n2:
        naver_ids.append(n2)
        naver_pws.append(p2)

    return {
        "gemini_key": (payload.get("gemini_key") or "").strip(),
        "naver_ids": naver_ids,
        "naver_pws": naver_pws,
        "n2_id": n2,
        "n2_pw": p2,
        "tistory_id": (payload.get("tistory_id") or "").strip(),
        "tistory_pw": (payload.get("tistory_pw") or "").strip(),
        "use_naver1": bool(payload.get("use_naver1", True)),
        "use_naver2": bool(payload.get("use_naver2", False)),
        "use_tistory": bool(payload.get("use_tistory", False)),
        "use_google": bool(payload.get("use_google", False)),
        "manual_confirm": False,
        "vertex_api_key": (payload.get("vertex_api_key") or "").strip(),
        "vertex_project_id": (payload.get("vertex_project_id") or "").strip(),
        "vertex_json": cfg.VERTEX_JSON_PATH,
        "keywords": keywords,
        "post_type": (payload.get("post_type") or "제품 홍보").strip(),
        "product_choice": (payload.get("product_choice") or "none").strip(),
        "product_url": (payload.get("product_url") or "").strip(),
        "image_provider": (payload.get("image_provider") or "auto").strip(),
        "mode": "immediate",
        "count": int(payload.get("count", 1)),
        "gap": int(payload.get("gap", 1)),
        "writing_guidelines": (payload.get("writing_guidelines") or "").strip(),
        "master_guidelines": (payload.get("master_guidelines") or "").strip(),
    }


HTML_PAGE = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
  <title>Autoblog Mobile</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #0b1220; color: #e5e7eb; }
    .wrap { max-width: 760px; margin: 0 auto; padding: 14px; }
    .card { background: #111827; border: 1px solid #2b3548; border-radius: 12px; padding: 12px; margin-bottom: 12px; }
    h1 { font-size: 20px; margin: 0 0 10px; }
    label { display: block; font-size: 13px; margin: 8px 0 4px; color: #9ca3af; }
    input, textarea, select { width: 100%; box-sizing: border-box; background: #0f172a; border: 1px solid #334155; color: #e5e7eb; border-radius: 8px; padding: 8px; }
    textarea { min-height: 72px; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    button { width: 100%; background: #2563eb; border: none; color: white; border-radius: 10px; padding: 12px; font-size: 15px; font-weight: 700; margin-top: 10px; }
    .status { font-size: 13px; color: #93c5fd; margin-top: 8px; }
    pre { white-space: pre-wrap; font-size: 12px; line-height: 1.5; background: #020617; border: 1px solid #334155; border-radius: 8px; padding: 10px; max-height: 42vh; overflow: auto; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Autoblog Mobile</h1>
      <div class="row">
        <div><label>Gemini API Key</label><input id="gemini_key" type="password"/></div>
        <div><label>Post Type</label><select id="post_type">
          <option selected>제품 홍보</option><option>취미글</option><option>알림글</option><option>코팅제 정보</option><option>자동차 정보</option><option>바이크 정보</option><option>맛집/일상</option><option>정보성 팁</option>
        </select></div>
      </div>
      <label>키워드 (쉼표)</label><textarea id="keywords">듀라코트 리빙코트, 욕실코팅제, 타일코팅제, 식탁코팅</textarea>
      <div class="row">
        <div><label>네이버1 ID</label><input id="naver_id1"/></div>
        <div><label>네이버1 PW</label><input id="naver_pw1" type="password"/></div>
      </div>
      <div class="row">
        <div><label>네이버2 ID (선택)</label><input id="naver_id2"/></div>
        <div><label>네이버2 PW (선택)</label><input id="naver_pw2" type="password"/></div>
      </div>
      <div class="row">
        <div><label>티스토리 ID (선택)</label><input id="tistory_id"/></div>
        <div><label>티스토리 PW (선택)</label><input id="tistory_pw" type="password"/></div>
      </div>
      <div class="row">
        <div><label>발행 개수</label><input id="count" type="number" value="1"/></div>
        <div><label>간격(분)</label><input id="gap" type="number" value="1"/></div>
      </div>
      <div class="row">
        <div><label><input id="use_naver1" type="checkbox" checked/> 네이버1 발행</label></div>
        <div><label><input id="use_naver2" type="checkbox"/> 네이버2 발행</label></div>
      </div>
      <div class="row">
        <div><label><input id="use_tistory" type="checkbox"/> 티스토리 발행</label></div>
        <div></div>
      </div>
      <label>상품 URL(선택)</label><input id="product_url" placeholder="https://..."/>
      <label>Vercel API URL</label><input id="vercel_api_url" placeholder="https://프로젝트.vercel.app/api/traffic"/>
      <div class="row">
        <div><label><input id="vercel_enabled" type="checkbox"/> Vercel 트래픽</label></div>
        <div><label>주기(분)</label><input id="vercel_interval_minutes" type="number" value="20"/></div>
      </div>
      <button id="trafficBtn">Vercel 트래픽 1회</button>
      <button id="runBtn">모바일에서 자동화 시작</button>
      <div id="status" class="status">대기 중</div>
    </div>
    <div class="card">
      <label>실시간 로그</label>
      <pre id="logs"></pre>
    </div>
  </div>
  <script>
    const $ = (id) => document.getElementById(id);
    async function loadDefaults() {
      try {
        const res = await fetch("/api/defaults");
        const d = await res.json();
        Object.keys(d).forEach((k) => {
          const el = $(k);
          if (!el) return;
          if (el.type === "checkbox") el.checked = !!d[k];
          else el.value = d[k] ?? "";
        });
      } catch (_) {}
    }
    async function start() {
      const payload = {
        gemini_key: $("gemini_key").value,
        post_type: $("post_type").value,
        keywords: $("keywords").value,
        naver_id1: $("naver_id1").value,
        naver_pw1: $("naver_pw1").value,
        naver_id2: $("naver_id2").value,
        naver_pw2: $("naver_pw2").value,
        tistory_id: $("tistory_id").value,
        tistory_pw: $("tistory_pw").value,
        count: Number($("count").value || 1),
        gap: Number($("gap").value || 1),
        product_url: $("product_url").value,
        vercel_api_url: $("vercel_api_url").value,
        vercel_enabled: $("vercel_enabled").checked,
        vercel_interval_minutes: Number($("vercel_interval_minutes").value || 20),
        use_naver1: $("use_naver1").checked,
        use_naver2: $("use_naver2").checked,
        use_tistory: $("use_tistory").checked,
        use_google: false,
        image_provider: "auto",
      };
      const res = await fetch("/api/start", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload) });
      const j = await res.json();
      $("status").textContent = j.message || "시작됨";
    }
    async function poll() {
      try {
        const res = await fetch("/api/status");
        const j = await res.json();
        $("status").textContent = (j.running ? "실행 중" : "대기") + (j.last_error ? " / 오류: " + j.last_error : "");
        $("logs").textContent = (j.logs || []).join("\\n");
        $("logs").scrollTop = $("logs").scrollHeight;
      } catch (_) {}
    }
    async function startTraffic() {
      const payload = {
        target_url: $("product_url").value,
        vercel_api_url: $("vercel_api_url").value,
        vercel_enabled: $("vercel_enabled").checked,
        vercel_interval_minutes: Number($("vercel_interval_minutes").value || 20),
      };
      const res = await fetch("/api/traffic", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload) });
      const j = await res.json();
      $("status").textContent = j.message || JSON.stringify(j);
    }
    $("trafficBtn").addEventListener("click", startTraffic);
    $("runBtn").addEventListener("click", start);
    loadDefaults();
    setInterval(poll, 2000);
    poll();
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html):
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self._send_html(HTML_PAGE)
            return
        if self.path == "/api/defaults":
            self._send_json(200, DEFAULTS)
            return
        if self.path == "/api/status":
            self._send_json(
                200,
                {
                    "running": STATE.running,
                    "last_error": STATE.last_error,
                    "logs": STATE.app.get_logs(250),
                },
            )
            return
        if self.path == "/api/traffic/health":
            from vercel_traffic_client import health_check, load_vercel_config

            self._send_json(200, health_check(load_vercel_config()))
            return
        self._send_json(404, {"message": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            self._send_json(400, {"message": "invalid json"})
            return

        if self.path == "/api/traffic":
            from vercel_traffic_client import load_vercel_config, trigger_traffic

            cfg = load_vercel_config()
            cfg.update(
                {
                    "vercel_api_url": (payload.get("vercel_api_url") or cfg.get("vercel_api_url") or "").strip(),
                    "vercel_enabled": bool(payload.get("vercel_enabled", cfg.get("vercel_enabled"))),
                    "vercel_interval_minutes": int(payload.get("vercel_interval_minutes") or cfg.get("vercel_interval_minutes") or 20),
                    "vercel_mode": (payload.get("vercel_mode") or cfg.get("vercel_mode") or "local"),
                    "product_url": (payload.get("target_url") or payload.get("product_url") or cfg.get("product_url") or "").strip(),
                }
            )
            try:
                outcome = trigger_traffic(config=cfg, log=STATE.app.log)
                self._send_json(
                    200 if outcome.get("ok") else 502,
                    {"message": "트래픽 완료" if outcome.get("ok") else "트래픽 실패", "outcome": outcome},
                )
            except Exception as e:
                self._send_json(400, {"message": str(e)})
            return

        if self.path != "/api/start":
            self._send_json(404, {"message": "not found"})
            return
        try:
            from vercel_traffic_client import load_vercel_config, trigger_traffic

            config = build_config(payload)
            STATE.start(config)
            if payload.get("vercel_enabled") or load_vercel_config().get("vercel_enabled"):
                vcfg = load_vercel_config()
                vcfg["vercel_api_url"] = (payload.get("vercel_api_url") or vcfg.get("vercel_api_url") or "").strip()
                target = (config.get("product_url") or "").strip()
                if target:
                    threading.Thread(
                        target=lambda: trigger_traffic(target, config=vcfg, log=STATE.app.log),
                        daemon=True,
                    ).start()
            self._send_json(200, {"message": "자동화가 시작되었습니다."})
        except Exception as e:
            self._send_json(400, {"message": str(e)})


if __name__ == "__main__":
    host = "0.0.0.0"
    port = 8787
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"[mobile] server started: http://{host}:{port}")
    server.serve_forever()

