# 프로그램 목록 · 부팅 순서 · 에이전트 협업 순서

> **원칙:** 프로그램이 먼저 동작해야 에이전트가 일할 수 있습니다.  
> `run_programs_check.bat` 통과 → 에이전트 파이프라인 시작.

---

## 0단계 — 프로그램 부팅 (사람 / Codex가 먼저 실행)

| 순서 | 배치/명령 | 역할 | 필수 |
|------|-----------|------|------|
| 0 | `run_install.bat` | venv·requirements·Playwright·트래픽 검증 | 최초 1회 |
| 0 | `run_programs_check.bat` | Python·venv·accounts·wiki·drawer·Ollama 점검 | ✅ |
| 1 | `ollama serve` + `ollama pull qwen3:4b` | 로컬 글쓰기 LLM | ✅ |
| 2 | `run_drawer.bat list` | 서랍 모듈·에이전트 체인 확인 | ✅ |
| 3 | `run_gui.bat` | GUI + JARVIS HTTP(8790) | 발행 시 |
| 4 | `run_javis_connect.bat` | JARVIS ↔ Supabase 연동 | 선택 |

한 번에: **`run_boot.bat`** (점검 → drawer list → GUI)

---

## 1단계 — 실행 프로그램 목록 (용도별)

### 블로그 글쓰기·발행

| 프로그램 | 명령 | 하는 일 |
|----------|------|---------|
| **GUI 메인** | `run_gui.bat` | 설정·자동화·지침·스마트스토어 탭 |
| **원고만** | `run_draft.bat "키워드"` | 제목·본문·이미지 → `drafts/` 저장 (발행 없음) |
| **단일 인스턴스** | `blog_single_instance.py` | GUI 중복 실행 방지 |

### 서랍 / Codex / JARVIS

| 프로그램 | 명령 | 하는 일 |
|----------|------|---------|
| **서랍 CLI** | `run_drawer.bat list` | 모듈·에이전트 체인 JSON |
| | `run_drawer.bat route --keyword "..."` | LLM 없이 blog/store/wiki 라우팅 |
| | `run_drawer.bat invoke wiki --post-type "..."` | 지침 슬라이스만 로드 |
| **JARVIS** | `POST :8790/api/javis/start` | GUI 트리거 (`module`: blog/store/wiki) |
| | `GET :8790/api/javis/modules` | 로드된 워커·체인 조회 |

### 스마트스토어·점검

| 프로그램 | 명령 | 하는 일 |
|----------|------|---------|
| 스토어 파이프라인 | `run_store_pipeline.bat` | 키워드·마케팅 리포트 |
| 스토어 설정 점검 | `run_setup_check.bat` | Supabase·스토어 환경 |
| JARVIS 연동 | `run_javis_connect.bat` | env 동기화 |

### 개발·테스트

| 프로그램 | 명령 | 하는 일 |
|----------|------|---------|
| 콘텐츠 스모크 | `python _smoke_content.py` | Ollama+이미지 빠른 테스트 |
| 프로그램 점검 | `python programs_check.py --json` | CI/Codex용 JSON 결과 |

---

## 2단계 — 에이전트 협업 순서 (블로그 1건 기준)

동시에 여러 LLM을 켜지 마세요. 아래 **순서대로 한 명씩** 끝낸 뒤 다음으로 넘깁니다.

```
[1] Router      → module=blog? store? (LLM 없음)
[2] Wiki        → wiki/ 슬라이스만 로드 (LLM 없음)
[3] Ollama      → 개요 → 본문 (qwen3:4b)
[4] Gemini      → (3) 실패 시만, BLOG_API_SPARING=0 일 때
[5] Gemini Image→ IMAGE_DESC + 키워드로 이미지 1장
[6] Playwright  → 네이버/티스토리 발행
[7] Claude Code → (선택) 검수·장문만
[8] Codex       → 전체 감독·코드 수정·store subprocess
```

### JARVIS 멀티 에이전트 — 작업 유형별 모델 우선순위

`drawer/agents.json` → `jarvis_model_routing` · 코드: `drawer/model_router.py`

| 요청 카테고리 | 우선순위 (1 → 2 → 3) | 역할 |
|---------------|----------------------|------|
| **종합 컨트롤러** | Hermes → Codex | 발화 분석·에이전트 업무 배분 |
| **개발·자동화** | Codex → DeepSeek → Hermes | 코드·파일 자율 제어 |
| **알고리즘·수학** | DeepSeek → Codex → Hermes | 로직 검증·디버깅 |
| **블로그·글쓰기** | Gemma2 → Hermes → DeepSeek | 한글 본문·마케팅 원고 |
| **이미지 생성** | Janus(DeepSeek) → Gemini Image → Pollinations | T2I 파일 |
| **이미지 프롬프트** | Hermes → Gemma2 → DeepSeek | IMAGE_DESC·MJ/Flux용 |

CLI: `run_drawer.bat route-model --keyword "욕실코팅"`  
HTTP: `GET /api/javis/routing?keyword=블로그` (GUI + `BLOG_JARVIS_BRIDGE=1`)

블로그 원고 생성 시 `BLOG_JARVIS_MODEL_ROUTING=1`(기본)이면 Ollama에서 **Gemma2 → Hermes → DeepSeek** 순으로 설치된 모델을 시도합니다.

### 역할 매핑 (Autoblog 파이프라인)

| 도구 | 파이프라인에서의 위치 |
|------|---------------------|
| **Hermes** | JARVIS 오케스트레이터·함수호출·지시 준수 |
| **Gemma 2** | [3] 블로그 텍스트 1순위 (Ollama) |
| **DeepSeek** | 알고리즘·이미지(Janus)·텍스트 3순위 |
| **Ollama (qwen3:4b)** | Gemma/Hermes 미설치 시 경량 폴백 |
| **Gemini** | [4] 텍스트 폴백, [5] 이미지 |
| **Claude Code** | [7] 검수·리팩터만 |
| **Codex / Cursor** | [8] 코딩·감독 |
| **JARVIS** | [1] 트리거 → 라우팅 → [6]까지 위임 |

설정 파일: `drawer/agents.json` (`boot_sequence`, `agent_pipeline`, `jarvis_model_routing`)

---

## 3단계 — Codex에게 넘기는 작업 예시

점검 통과 후 Codex/Cursor 에이전트에 순서대로 지시:

1. `run_drawer.bat route --keyword "욕실 타일 코팅"` → `blog` 확인  
2. `run_drawer.bat invoke wiki --post-type "제품 홍보"` → 지침 확인  
3. `run_draft.bat "욕실 타일 코팅"` → 원고+이미지 `drafts/` 생성  
4. 문제 없으면 GUI에서 자동화 시작 또는 JARVIS `module=blog`  
5. 코드·성능 이슈는 **Claude Code [7]** 또는 **Codex [8]** 에만 맡김 (Ollama와 동시 X)

---

## 환경 변수 (에이전트 충돌 방지)

| 변수 | 권장값 |
|------|--------|
| `BLOG_API_SPARING=1` | 유료 Gemini 텍스트 폴백 차단 |
| `BLOG_TEXT_PROVIDER=ollama` | [3]만 사용 |
| `BLOG_IMAGE_PROVIDER=genai` | [5] Gemini 이미지 |
| `BLOG_OLLAMA_MODEL=qwen3:4b` | 가벼운 모델 |
| `BLOG_USE_WIKI=1` | [2] Wiki 슬라이스 |

자세한 CLI: `CODEX_DRAWER.md`
