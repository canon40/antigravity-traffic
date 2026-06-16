# Antigravity Traffic

[canon40/antigravity-traffic](https://github.com/canon40/antigravity-traffic) — 네이버 쇼핑 SEO·트래픽·블로그 자동화 통합 저장소입니다.

이 저장소에는 **두 계열**이 공존합니다.

| 계열 | 대상 | 빠른 시작 |
|------|------|-----------|
| **Autoblog (login2)** | 네이버·티스토리 발행, Vercel 트래픽, 쇼츠, 모바일 원격 | `run_install.bat` → `run_gui.bat` |
| **SEO Rank Tools** | 순위 체크, 트래픽 집중, 블로그 초안 | `run_rank_check.bat`, `run_traffic_focus.bat` |

에이전트·개발자는 Autoblog 작업 시 [`AGENTS.md`](AGENTS.md)를 먼저 읽으세요.

---

## Autoblog (login2)

네이버·티스토리 블로그 자동 발행, 상품 트래픽(Vercel), 쇼츠 콘티·FLOW, 모바일 원격 제어.

```bash
copy accounts.json.example accounts.json   # 값 입력 후
run_install.bat
run_gui.bat
```

| 모듈 | 설명 |
|------|------|
| `blog_main.py` | Tk GUI 메인 |
| `vercel_traffic_client.py` | Vercel 클라우드 트래픽 |
| `vercel_traffic/` | Vercel 배포용 API + Traffic Hub UI |
| `mobile_server.py` | 모바일 원격 (8787) |
| `shorts_factory/` | 쇼츠 콘티·FLOW 보드 |

- Vercel Root Directory: **`vercel_traffic`**
- 연동 검증: `python scripts/verify_vercel_traffic.py`
- 문서: [`wiki/04_ai_briefing_geo.md`](wiki/04_ai_briefing_geo.md), [`docs/checklists/youtube_4videos_blog_shorts.md`](docs/checklists/youtube_4videos_blog_shorts.md)

`accounts.json`과 `.env`는 커밋하지 마세요.

---

## SEO Rank Tools (레거시 루트 스크립트)

네이버 쇼핑 순위·트래픽·블로그 초안 (기존 `rank_*.py`, `traffic_single.py` 등).

| BAT | 기능 |
|-----|------|
| `run_rank_check.bat` | 순위 즉시 체크 |
| `run_traffic_focus.bat` | 자동차코팅제 집중 트래픽 |
| `run_blog_post.bat` | SEO 블로그 글 생성 |

보안 설정: `security_vault/credentials.json` (커밋 금지)

자세한 루틴·옵션은 원격 초기 README 내용을 참고하거나 각 스크립트 `--help`를 사용하세요.
