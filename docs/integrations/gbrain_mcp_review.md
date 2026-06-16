# GBrain MCP·메모리 연동 검토 (영상 3번)

출처: [클로드 기억력 높이는 법 — GBrain](https://youtu.be/4pgGVGA0IxU)  
프로젝트: [garrytan/gbrain](https://github.com/garrytan/gbrain)

## GBrain이 하는 일

| 기능 | 설명 |
|------|------|
| `search` | 키워드로 메모·문서 검색 |
| `think` | 여러 메모를 **합성 답 + 출처** |
| 지식 그래프 | 인물·회사 관계 (LLM 없이 추출) |
| `capture` / `import` | 메모 수집·일괄 import |
| MCP `gbrain serve` | Claude Code 등 에이전트 연동 |

컨셉: **검색은 페이지를 주고, 뇌는 답을 준다.**

## Autoblog(login2)에 필요한 기억

| 종류 | 예시 | 현재 저장소 |
|------|------|-------------|
| 프로젝트 규칙 | AGENTS, 스킬, 컨벤션 | `AGENTS.md`, `.cursor/` |
| 도메인 지식 | 메이트 5원칙, 제품 Truth | `wiki/` |
| 계정·비밀 | API 키, 네이버 ID | `accounts.json` (**GBrain에 넣지 말 것**) |
| 세션 메모 | 결정·TODO·발행 이력 | 없음 (매 세션 초기화) |
| 쇼츠 플레이북 | YouTube 학습 | `data/shorts_factory/youtube_evolution.json` |

## 권장 아키텍처 (3단계)

### Phase 0 — 지금 (추가 설치 없음)

- `AGENTS.md` + `wiki/` + `.cursor/skills/` = 에이전트 컨텍스트
- 비밀은 `accounts.json`만 (커밋 금지)
- **충분한 범위**: 블로그·트래픽·Vercel 연동 작업

### Phase 1 — GBrain 로컬 (선택, PC)

개발자 PC에만 설치. Cursor/Claude Code가 **장기 메모**가 필요할 때.

```bash
bun install -g github:garrytan/gbrain
gbrain init --pglite
gbrain doctor
gbrain import wiki/
gbrain import .cursor/skills/
# accounts.json 은 import 금지
claude mcp add gbrain -- gbrain serve
```

Cursor의 경우 `.cursor/mcp.json`에 동일 서버 등록 (사용자 수동).

**import 대상 예**

- `wiki/*.md`
- `docs/checklists/`
- `vercel_traffic/docs/`
- 발행 로그·결정 메모 (별도 `notes/` 폴더 생성 시)

### Phase 2 — 프로젝트 스크립트 (미구현, 필요 시)

| 스크립트 | 역할 |
|----------|------|
| `scripts/gbrain_sync.py` | `wiki/` 변경 시 `gbrain import` |
| `scripts/gbrain_query.py` | CLI에서 `gbrain query "..."` 래퍼 |

Autoblog **런타임(GUI·발행)**에는 GBrain을 붙이지 않는다. **코딩 에이전트 보조**용만.

## MCP 연동 시 기대 효과

| 이점 | 설명 |
|------|------|
| 세션 간 기억 | "지난번 Vercel URL 뭐였지?" → think |
| 출처 | 어떤 wiki/스킬에서 왔는지 인용 |
| 갭 분석 | 메모 부족 영역 제안 (GBrain 기능) |

## 리스크·제약

| 항목 | 대응 |
|------|------|
| `accounts.json` 유출 | import 제외, `.gbrainignore` 또는 import 경로 화이트리스트 |
| Windows | bun + gbrain 공식 가이드 따름; WSL 가능 |
| Vercel/클라우드 | GBrain은 **PC 로컬** 전용. 클라우드 API에 배포하지 않음 |
| 중복 | `wiki/`와 GBrain 이중 관리 → **wiki가 소스 오브 트루스**, GBrain은 인덱스 |

## 결론 (권고)

| 우선순위 | 조치 |
|----------|------|
| 필수 | `wiki/04`, 체크리스트, 기존 스킬 유지 |
| 권장 | 장기 작업 시 Phase 1 GBrain + `wiki/` import |
| 보류 | GUI·발행 파이프라인에 GBrain 직접 연결 |
| 금지 | `accounts.json`·비밀키 GBrain import |

다음 액션은 사용자가 GBrain 설치를 원할 때 `scripts/gbrain_sync.py` 추가와 `.cursor/mcp.json` 예시를 커밋하는 것이다.
