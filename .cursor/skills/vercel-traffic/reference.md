# Vercel 트래픽 — reference (검증·학습 기록)

최종 검증: `python scripts/verify_vercel_traffic.py` 로 갱신한다.

## 검증 결과 (최근 실행)

`python scripts/verify_vercel_traffic.py` — **12/12 PASS**

- 로컬 방문: smartstore.naver.com HTTP 200, ~0.43s
- traffic_session 단독: ~0.11s
- cloud_health: `vercel_api_url` 미설정 시 skip (정상)

## 검증 결과 템플릿

| 검사 | 기대 |
|------|------|
| import_vercel_traffic_client | PASS |
| normalize_traffic_url | PASS |
| local_traffic_visit | smartstore HTTP 2xx, &lt;10s |
| traffic_session_module | 동일 |
| cloud_health_check | URL 설정 시 200, 미설정 시 skip |
| file_exists:* | 5개 핵심 파일 존재 |

## 함수 맵 (`vercel_traffic_client.py`)

| 함수 | 용도 |
|------|------|
| `load_vercel_config(path?)` | accounts.json → dict |
| `normalize_traffic_url` | API POST URL |
| `normalize_health_url` | GET health URL |
| `health_check(config)` | 클라우드 ping |
| `trigger_traffic(url?, config?, log?)` | local/cloud/both 실행 |
| `VercelTrafficScheduler` | N분 주기 daemon |

## blog_main.py 메서드

- `_get_vercel_config_from_ui()`
- `vercel_health_check()`, `vercel_trigger_once()`, `toggle_vercel_scheduler()`
- `_run_vercel_traffic_after_publish()` — `start_processing` 연동
- `_vercel_scheduler` — `VercelTrafficScheduler` 인스턴스

## 알려진 이슈·해결

| 증상 | 원인 | 조치 |
|------|------|------|
| 헬스 실패 401 | WEBHOOK_SECRET 불일치 | Vercel env ↔ GUI secret 동기화 |
| cloud 모드 URL 오류 | 빈 `vercel_api_url` | URL 입력 또는 `local` 모드 |
| mobile /api/start NameError | `load_vercel_config` 미 import | 상단에서 `load_vercel_config, trigger_traffic` import (수정됨) |
| Vercel 타임아웃 | Playwright 사용 시도 | httpx만 사용 유지 |

## Base44 웹훅 예시

```http
POST https://YOUR.vercel.app/api/traffic
Authorization: Bearer YOUR_SECRET
Content-Type: application/json

{"target_url": "https://smartstore.naver.com/your-store/products/123"}
```

주기: 15~20분 권장 (GUI `vercel_interval_minutes`와 맞출 것).

## requirements (Vercel)

`vercel_traffic/requirements.txt`: fastapi, pydantic, httpx

## requirements (PC)

프로젝트 루트 venv에 `httpx` 필요 (`vercel_traffic_client`).
