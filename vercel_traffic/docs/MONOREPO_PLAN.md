# canon40/antigravity-traffic Monorepo 계획

Antigravity login2의 기능을 [canon40/antigravity-traffic](https://github.com/canon40/antigravity-traffic) 한 저장소에서 **역할별로 나누고**, 웹 허브에서 어디서 무엇을 실행하는지 안내하는 구조입니다.

## 원칙

| 원칙 | 이유 |
|------|------|
| 클라우드 = httpx만 | Vercel 10초 제한, Playwright 불가 |
| PC = Playwright·Tk·장시간 작업 | 브라우저 프로필·GUI 필요 |
| 비밀 = 커밋 금지 | `accounts.json`, API 키는 `.gitignore` |
| UI = 허브 + 각 모듈 | 한 URL에서 트래픽, PC 모듈 링크·설명 |

## 권장 디렉터리

```
canon40/antigravity-traffic/
├── README.md                 # 허브 소개·빠른 시작
├── cloud/                    # ← 현재 vercel_traffic (Vercel Root)
│   ├── api/
│   ├── public/index.html     # Traffic Hub
│   └── traffic_session.py
├── pc/                       # login2 PC 프로그램
│   ├── autoblog/             # blog_main, blog_gui_tabs, automation
│   ├── client/               # vercel_traffic_client.py
│   ├── mobile/               # mobile_server.py
│   ├── shorts/               # shorts_factory (선택)
│   ├── scripts/              # verify, traffic_once
│   ├── wiki/                 # 네이버 메이트 등
│   ├── run_gui.bat
│   ├── run_install.bat
│   └── requirements.txt
├── docs/
│   ├── setup-pc.md
│   ├── setup-vercel.md
│   └── modules.md
└── .gitignore                # accounts.json, venv, generated_images
```

## 모듈 맵 (UI 탭과 동일)

| 모듈 | 실행 위치 | 진입점 |
|------|-----------|--------|
| 클라우드 트래픽 | Vercel | `cloud/public/` 또는 API |
| 블로그 자동 발행 | PC | `run_gui.bat` |
| 모바일 원격 | PC :8787 | `python mobile_server.py` |
| 로컬 트래픽 1회 | PC | `traffic_once.bat` |
| 이웃·티스토리 방문 | PC Playwright | 평일 일과 / GUI |
| 쇼츠·YouTube 학습 | PC | `learn_youtube_evolution.py` |

## 마이그레이션 단계

### 1단계 (완료 가능) — 클라우드 + 허브 UI

- [x] `vercel_traffic` API
- [x] `public/index.html` Traffic Hub
- [ ] `canon40/antigravity-traffic`에 푸시 후 Vercel 연결

### 2단계 — PC 패키지

- `pc/`에 login2 핵심 복사 (최소: client, scripts, blog_*, mobile_server)
- 루트 `README`에서 `cd pc && run_install.bat` 안내
- `accounts.json.example` 커밋

### 3단계 — 원격 접근

- PC: Tailscale / Cloudflare Tunnel로 `mobile_server` 외부 노출 (선택)
- 클라우드: Base44 → `POST /api/traffic` (PC 꺼져도 트래픽)

### 4단계 — 통합 설정

- 허브 UI에서 API URL·secret 저장 (localStorage)
- PC `accounts.json`과 동일 키 문서화 (`vercel_*`, `product_url`)

## Vercel 설정 체크리스트

- Root Directory: `cloud` (또는 `vercel_traffic`)
- `WEBHOOK_SECRET` 설정
- 배포 URL → PC `vercel_api_url` / 허브 설정에 입력

## 검증

```bash
# PC (pc/ 루트 기준)
python scripts/verify_vercel_traffic.py
```

허브 UI: 배포 URL `/` → 헬스 체크 → 트래픽 1회
