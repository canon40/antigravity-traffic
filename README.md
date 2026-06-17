# Permacoat SEO 허브 (antigravity-traffic)

네이버 쇼핑 **순위 추적**, **SEO 점검**, **블로그 초안 생성**을 한 화면에서 운영하는 프로그램입니다.

- **웹:** [permacoat.shop](https://permacoat.shop)
- **백엔드 24h:** Cloudtype (`app.py` + gunicorn)
- **프론트·블로그 API:** Vercel (`vercel.json`)

---

## 이 폴더에 남은 것 (핵심만)

```
login2/
├── app.py                 # Flask 메인 (순위·SEO·블로그 API)
├── templates/index.html   # 대시보드 UI
├── static/                # PWA manifest, service worker
├── api/hub_content.py     # Vercel 블로그 초안 API
├── vercel.json            # permacoat.shop 배포 설정
├── .cloudtype/app.yaml    # Cloudtype gunicorn 설정
├── config.defaults.json   # 기본 키워드·상품
├── data/                  # 프로그램 카탈로그·상태 시드
├── vercel_traffic/
│   └── traffic_session.py # HTTP 트래픽 1회 방문
└── scripts/               # 검증·일일 순위 스크립트
```

---

## 실행 방법 (PC 로컬)

```bat
run_install.bat   :: 최초 1회
run.bat           :: http://127.0.0.1:5000
```

| BAT | 용도 |
|-----|------|
| `run.bat` | 로컬 SEO 허브 서버 |
| `run_install.bat` | venv + 패키지 설치 |
| `run_seo_hub_verify.bat` | API 배포 검증 |
| `rank_daily.bat` | 순위 1회 추적 |
| `traffic_once.bat` | 트래픽 1회 테스트 |
| `run_programs_check.bat` | 모듈 점검 |

---

## 배포

- **Cloudtype Start command:** `gunicorn app:app -b 0.0.0.0:8000 --timeout 120 --workers 1 --access-logfile -`
- 문서: `docs/setup-cloudtype.md`, `docs/setup-vercel.md`

---

## 삭제된 것 (레거시)

Autoblog GUI, 숏츠 팩토리, Playwright 블로그 발행, 모바일 앱, 영상 스튜디오 등은 이 저장소에서 제거했습니다.  
JARVIS 전체 기능은 `D:\@code\javis` 저장소를 사용하세요.
