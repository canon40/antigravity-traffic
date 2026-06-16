---
name: vercel-traffic
description: >-
  Vercel 서버리스 트래픽 API와 Autoblog(login2) PC 프로그램 연동.
  배포(vercel_traffic/), accounts.json 설정, GUI·평일일과·모바일서버 훅,
  로컬/클라우드/both 모드, Base44 웹훅. Use when user asks Vercel 트래픽,
  클라우드 트래픽, Base44 연동, vercel_traffic, 트래픽 API, or 연동 검증.
---

# Vercel 클라우드 트래픽 (Autoblog login2)

PC Autoblog와 **Vercel 서버리스 HTTP 방문**을 함께 쓰는 연동 스킬이다.
Playwright는 Vercel 10초 제한에 맞지 않으므로 **httpx 모바일 UA 1회 GET**만 사용한다.

## 검증 먼저

연동 수정·배포 후 반드시 실행:

```bash
python scripts/verify_vercel_traffic.py
```

`vercel_api_url`이 `accounts.json`에 있으면 클라우드 헬스도 자동 검사한다.

## 아키텍처 (기억할 핵심)

| 구분 | 경로/역할 |
|------|-----------|
| Vercel 배포 루트 | `vercel_traffic/` (Root Directory로만 배포) |
| API | `vercel_traffic/api/index.py` — FastAPI `app` export |
| 방문 로직 | `vercel_traffic/traffic_session.py` |
| PC 클라이언트 | `vercel_traffic_client.py` |
| GUI | `blog_gui_tabs.py` — ☁️ Vercel 카드 |
| 메인 | `blog_main.py` — 헬스/1회/스케줄러/발행 후 호출 |
| 평일 일과 | `blog_daily_weekday.py` — 발행 후 `trigger_traffic` |
| 모바일 | `mobile_server.py` — `/api/traffic`, `/api/traffic/health` |

**트리거 시점**

1. GUI **트래픽 1회** / **주기 실행** (`VercelTrafficScheduler`)
2. **자동화 시작** + `vercel_on_publish` → `start_processing`에서 병렬 1회
3. **평일 일과** 종료 후 `vercel_enabled`이면 1회
4. **Base44** → `POST https://프로젝트.vercel.app/api/traffic` (PC 꺼도 동작)
5. 모바일 `/api/start` 또는 `/api/traffic`

## accounts.json 키

```json
{
  "vercel_api_url": "https://프로젝트.vercel.app/api/traffic",
  "vercel_webhook_secret": "",
  "vercel_enabled": false,
  "vercel_on_publish": true,
  "vercel_interval_minutes": 20,
  "vercel_mode": "cloud",
  "product_url": "https://smartstore.naver.com/..."
}
```

- `vercel_mode`: `cloud` | `local` | `both`
- `local`만 쓸 때는 API URL 없이도 동작
- `cloud`/`both`는 `vercel_api_url` 필수

## Vercel 배포 체크리스트

1. GitHub에 `vercel_traffic/` 푸시
2. Vercel **Root Directory = `vercel_traffic`**
3. 환경변수 `WEBHOOK_SECRET` (선택이지만 프로덕션 권장)
4. `vercel.json` — `maxDuration: 10`, rewrites → `/api/index.py`

## API 계약

- `GET /api/health` — 상태 확인
- `POST /api/traffic` — body `{"target_url":"...", "timeout_sec":8}`
- 인증: `Authorization: Bearer <WEBHOOK_SECRET>` 또는 `X-Webhook-Secret`

## 학습된 제약 (수정 시 지킬 것)

1. **전체 repo를 Vercel에 올리지 말 것** — Playwright·GUI 의존성 폭발
2. **로컬 Playwright 트래픽**은 `blog_automation_visit.py` 등 PC 전용; 클라우드와 역할 분리
3. `vercel_traffic_client._run_local`은 `vercel_traffic/`를 `sys.path`에 넣어 `traffic_session` import
4. URL 정규화: 베이스만 넣어도 `/api/traffic`, `/api/health`로 자동 보정
5. 스케줄러는 daemon thread; `vercel_enabled` 꺼지면 루프 종료

## 작업 시 참고

- 상세 파일 맵·에러 패턴: `reference.md`
- 네이버 글 리프레시는 별도 스킬: `.cursor/skills/naver-blog-refresh/`

## 일반적인 수정 흐름

1. `scripts/verify_vercel_traffic.py` 실행
2. 실패 항목만 최소 diff로 수정
3. GUI 필드 추가 시 `blog_gui_tabs.py` + `blog_main.py` save/load + `accounts.json` 키 동시 반영
4. 모바일 HTML/JS에도 동일 키 전달 (`mobile_server.py`)
