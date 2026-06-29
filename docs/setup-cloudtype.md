# Cloudtype 24시간 SEO · 트래픽 허브

[Cloudtype](https://app.cloudtype.io)에서 `antigravity-traffic` 저장소를 배포하면 **브라우저를 닫아도** 순위 추적·트래픽이 백그라운드 스레드로 계속 동작합니다.

## 배포

1. Cloudtype → **New Project** → GitHub `canon40/antigravity-traffic` (branch: `main`)
2. `.cloudtype/app.yaml` 이 자동 적용됩니다.
3. **Ingress** 포트: `8000` (gunicorn 바인딩과 동일)

## 환경 변수 (Cloudtype 대시보드)

| 변수 | 필수 | 설명 |
|------|------|------|
| `CLOUDTYPE` | 자동 | `app.yaml`에서 `1` |
| `HUB_CLOUD_PLATFORM` | 자동 | `cloudtype` |
| `AUTO_START_SCHEDULER` | 권장 | `1` — 기동 시 순위·트래픽 시작 |
| `SUPABASE_URL` | 권장 | 순위·상태 영구 저장 |
| `SUPABASE_SERVICE_KEY` | 권장 | REST 쓰기 |
| `TRAFFIC_TARGET_URL` | 선택 | 스마트스토어 URL |
| `TRAFFIC_INTERVAL_SEC` | 선택 | 트래픽 간격(초), 기본 1200 |
| `NAVER_CLIENT_ID` | 클라우드 권장 | [네이버 검색 API](https://developers.naver.com/docs/serviceapi/search/shopping/shopping.md) — 순위 403 우회 |
| `NAVER_CLIENT_SECRET` | 클라우드 권장 | 검색 API 시크릿 |
| `GEMINI_API_KEY` | 권장 | 블로그 SEO·키워드 분석·JARVIS LLM ([aistudio.google.com/apikey](https://aistudio.google.com/apikey)) |
| `GEMINI_MODEL` | 선택 | 기본 `gemini-2.5-flash` |
| `JARVIS_ROOT` | 선택 | JARVIS 로컬 경로 (PC 연동 시) |

## Vercel과 차이

| | Cloudtype | Vercel |
|---|-----------|--------|
| 24h 백그라운드 스레드 | ✅ gunicorn + daemon | ❌ Cron만 |
| 트래픽 간격 | 20분(환경변수) | Cron 20분 |
| 순위 추적 | `track_interval_minutes` | Cron 매시 |
| 브라우저 탭 전환 | 영향 없음 | 영향 없음 |

## UI

- 좌측 **Traffic / JARVIS** 전환 — 탭을 바꿔도 트래픽은 서버에서 계속 동작합니다.
- **순위 중지** — 순위 스케줄만 중지, 트래픽 유지
- **트래픽만 중지** — 트래픽만 끔
- **24h 시작** — 순위·트래픽 모두 켬

## Cloudtype Start command (설정 탭에 직접 입력 시)

`python app.py` 대신 아래 Flask 명령을 사용하세요:

```bash
gunicorn app:app -b 0.0.0.0:8000 --timeout 120 --workers 1 --access-logfile -
```

> FastAPI가 아닌 **Flask** 프로젝트입니다. `uvicorn`이 아니라 `gunicorn`을 씁니다.

## 확인

```bash
curl https://YOUR-SERVICE.cloudtype.app/api/health
```

배포 URL: [antigravity-traffic ingress](https://app.cloudtype.io/@canon4040/antigravity-traffic:main/antigravity-traffic#ingress)

## Vercel (permacoat.shop) 연동

프론트는 **Vercel**, API·24h 순위·트래픽은 **Cloudtype** (`@canon4040/antigravity-traffic`)에서 실행합니다.

### 1. Cloudtype 재배포

1. [Cloudtype 대시보드](https://app.cloudtype.io/@canon4040/antigravity-traffic:main/antigravity-traffic) → **Redeploy**
2. **Ingress** 탭 → **접속하기** URL 복사  
   예: `https://port-0-antigravity-traffic-xxxx.sel3.cloudtype.app`
3. 터미널에서 확인:
   ```bash
   curl https://<접속하기-URL>/api/health
   ```
   → `{"status":"healthy",...}` 또는 `ok: true` 가 나와야 합니다.

### 2. Vercel 환경변수

[Vercel Project → Settings → Environment Variables](https://vercel.com)

| 변수 | 값 |
|------|-----|
| `CLOUDTYPE_API_BASE` | Cloudtype **접속하기** URL (끝 `/` 없이) |
| `SUPABASE_URL` | (권장) 순위 히스토리 |
| `SUPABASE_SERVICE_KEY` | (권장) |

저장 후 **Redeploy** (Deployments → ⋯ → Redeploy).

### 3. 확인

```bash
curl https://permacoat.shop/api/_proxy/health
curl https://permacoat.shop/api/status
```

- `_proxy/health` → `ok: true` 이면 Vercel→Cloudtype 연결 성공
- Cloudtype 다운 시에도 `/api/status`는 정적 폴백으로 대시보드 표시 (읽기 전용)

> `vercel.json`은 `/api/*`를 `api/hub_proxy.py`로 보냅니다. URL은 **반드시** `CLOUDTYPE_API_BASE`에 Ingress 주소를 넣으세요.
