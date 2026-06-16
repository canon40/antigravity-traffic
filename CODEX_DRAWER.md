# Codex / JARVIS — 서랍(Drawer) 연동 가이드

무거운 Autoblog 전체를 한꺼번에 띄우지 않고, **필요한 워커만** 호출합니다.

**전체 프로그램 목록·에이전트 순서:** `AGENT_PIPELINE.md`  
**부팅:** `run_programs_check.bat` → `run_boot.bat`  
**순서만 보기:** `run_drawer.bat pipeline`

## 3단 구조

| 레이어 | 역할 | 이 프로젝트 |
|--------|------|-------------|
| 1. 라우터 | 의도만 판별 (LLM 없음) | `drawer/router.py`, `drawer/model_router.py` |
| 2. 워커 | 필요 시 import/subprocess | `drawer/registry.py`, `drawer/cli.py` |
| 3. Wiki/DB | 지침·키워드 외부 보관 | `wiki/*.md`, Supabase |

## JARVIS 멀티 에이전트 라우팅

| 작업 | 1순위 | 2순위 | 3순위 |
|------|-------|-------|-------|
| 오케스트레이션 | Hermes | Codex | — |
| 코딩 | Codex | DeepSeek | Hermes |
| 블로그 글 | Gemma2 | Hermes | DeepSeek |
| 이미지 생성 | Janus | Gemini Image | Pollinations |

```bat
run_drawer.bat route-model --keyword "블로그 원고"
run_drawer.bat route-model --text "코덱스로 리팩터"
```

`BLOG_JARVIS_MODEL_ROUTING=1` — 글쓰기 시 Ollama 모델 우선순위 자동 적용

## 에이전트 실행 순서 (`drawer/agents.json`)

1. **Ollama** (qwen3:4b) — 텍스트 우선, 무료
2. **Gemini** — Ollama 실패·유료 허용 시만 (`BLOG_API_SPARING=0`)
3. **Claude Code** — 장문·검수 전용
4. **이미지** — 본문 완료 후 Gemini Image → Vertex

동시에 여러 LLM을 띄우지 마세요.

## CLI (Codex 터미널)

```bat
run_drawer.bat list
run_drawer.bat route --keyword "욕실코팅"
run_drawer.bat invoke wiki --post-type "자동차 정보"
run_drawer.bat invoke store --category 생활 --concept "리빙코트" --api-key YOUR_KEY
```

## JARVIS HTTP (GUI 실행 중)

- `GET http://127.0.0.1:8790/api/javis/modules` — 모듈·라우팅 설정
- `GET http://127.0.0.1:8790/api/javis/routing?keyword=...` — 작업별 모델 우선순위
- `POST http://127.0.0.1:8790/api/javis/start` — `{"module":"blog","keyword":"..."}`

`module`: `blog` | `store` | `neighbor` | `verify` | `wiki`

## 환경 변수

| 변수 | 권장 |
|------|------|
| `BLOG_API_SPARING=1` | 유료 API 폴백 차단 |
| `BLOG_TEXT_PROVIDER=ollama` | 로컬 우선 |
| `BLOG_OLLAMA_MODEL=qwen3:4b` | 가벼운 모델 |
| `BLOG_USE_WIKI=1` | 지침 슬라이스 로드 |

## GUI 경량화

`blog_main.py`는 시작 시 Playwright·`blog_content_gen`·Vertex를 로드하지 않습니다.  
「자동화 시작」을 누를 때만 `drawer.registry.get_automation_flow()`가 로드됩니다.
