# Cloudtype + Vercel 운영 런북

프론트는 Vercel, API/백그라운드 작업은 Cloudtype에서 상시 실행한다.

## 1) 역할 분리

- Vercel: `index.html` 및 프론트 라우팅
- Vercel API: `/api/*` 프록시 (`api/index.py`)
- Cloudtype: 실제 API (`api/jarvis_mobile_server.py`) + 워커

## 2) 필수 환경변수

### Vercel

- `CLOUDTYPE_API_BASE=https://<cloudtype-public-domain>`

### Cloudtype

- `PORT` (플랫폼 자동 주입 권장)
- `JARVIS_MOBILE_TOKEN`
- `GEMINI_API_KEY`
- 선택: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`

## 3) 헬스체크

- Vercel 프록시 상태: `/api/_proxy/health`
- 실제 API 상태: `/api/health` (Vercel 경유 시 Cloudtype로 전달됨)

## 4) 도메인 충돌 방지

- `permacoat.shop`는 Vercel에 연결
- `/api/*`는 Vercel이 Cloudtype API로 프록시
- Cloudtype 도메인은 외부에 직접 노출해도 되지만, 클라이언트 기본 호출은 `permacoat.shop/api/*`로 통일

## 5) 배포 후 점검 순서

1. Cloudtype 배포 성공 확인
2. Vercel 재배포
3. `https://<your-domain>/api/_proxy/health` 확인
4. `https://<your-domain>/api/health` 확인
5. 모바일/대시보드 실제 기능 호출 검증

### 자동 점검 스크립트

PowerShell:

`.\scripts\check_cloudtype_vercel.ps1 -Domain permacoat.shop`
