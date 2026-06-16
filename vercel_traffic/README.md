# Traffic Hub (canon40/traffic — 클라우드)

[canon40/traffic](https://github.com/canon40/traffic) 저장소의 **Vercel 배포 단위**입니다.  
PC 전체 Autoblog(login2)를 올리지 않고, **10초 이내 HTTP 트래픽 API + 웹 허브 UI**만 서버리스로 동작합니다.

## 배포

1. GitHub `canon40/traffic`에 푸시
2. Vercel 새 프로젝트 → **Root Directory**: 이 폴더 (`vercel_traffic` 또는 monorepo 시 `cloud`)
3. 환경변수 (권장): `WEBHOOK_SECRET`
4. 배포 후 `https://<프로젝트>.vercel.app/` 에서 **Traffic Hub** UI 확인

## 구조

```
vercel_traffic/
├── api/index.py          # FastAPI (health, traffic)
├── traffic_session.py    # httpx 모바일 UA 1회 GET
├── public/index.html     # Traffic Hub 웹 UI (어디서든)
├── vercel.json
└── requirements.txt
```

## API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/health` | 서버 상태 |
| POST | `/api/traffic` | `{"target_url":"...", "timeout_sec":8}` |

인증: `Authorization: Bearer <WEBHOOK_SECRET>` 또는 `X-Webhook-Secret`

## PC 연동

PC Autoblog는 `vercel_traffic_client.py` + `accounts.json`으로 이 API를 호출합니다.

```bash
python scripts/verify_vercel_traffic.py
```

## monorepo 계획

전체 프로그램을 `canon40/traffic`에 모을 때 권장 레이아웃은 `docs/MONOREPO_PLAN.md`를 참고하세요.
