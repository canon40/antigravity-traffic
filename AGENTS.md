# AGENTS.md — Autoblog login2

네이버/티스토리 자동 발행 + 상품 트래픽. Python 3, Tk GUI, Playwright(로컬).

## 실행

```bash
run_install.bat              # CMD 설치 (venv + requirements + 검증)
run_gui.bat                  # 메인 GUI
python mobile_server.py      # 모바일 원격 (8787)
python scripts/verify_vercel_traffic.py   # Vercel 연동 검증
traffic_once.bat             # 트래픽 1회 (로컬)
```

## 프로젝트 스킬 (`.cursor/skills/`)

| 스킬 | 언제 |
|------|------|
| `vercel-traffic` | Vercel/Base44 트래픽 API, 클라우드 연동, 검증 |
| `naver-blog-refresh` | 기존 네이버 글 AI 브리핑·메이트 리프레시 |

작업 전 해당 `SKILL.md`를 읽고 따른다.

## Vercel 트래픽 (요약)

- 배포: **`vercel_traffic/`만** — Root Directory `vercel_traffic`
- PC 연동: `vercel_traffic_client.py`, 설정 `accounts.json`
- 모드: `cloud` / `local` / `both` — Playwright는 Vercel에 배포하지 않음

## 설정 파일

- `accounts.json` — 계정·API 키·`vercel_*`·`product_url` (커밋 금지)

## 컨벤션

- 최소 diff; GUI 변경 시 save/load·`accounts.json` 키 동시 반영
- 한국어 UI 로그 메시지 유지
- wiki: `wiki/00_core.md`, `wiki/03_naver_mate.md`, `wiki/04_ai_briefing_geo.md`
- 체크리스트: `docs/checklists/youtube_4videos_blog_shorts.md`
- 블로그 1단계 진단 CLI: `python scripts/naver_blog_diagnose.py --file 글.txt`
- 쇼츠 니치: `data/shorts_factory/niche_templates.json`, `python -m shorts_factory.build --list-niches`

## Commit Attribution

AI 커밋 시 사용자가 요청한 경우에만:

```
Co-Authored-By: Auto <noreply@cursor.com>
```
