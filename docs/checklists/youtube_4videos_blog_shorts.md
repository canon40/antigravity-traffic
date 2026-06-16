# YouTube 4편 핵심 체크리스트 (블로그·쇼츠)

학습 영상 4편에서 Autoblog(login2)에 바로 쓸 수 있는 요약입니다.

| # | 영상 | 채널 | Autoblog 적용 |
|---|------|------|----------------|
| 1 | [GLM-5.2 전격 공개](https://youtu.be/BlTHPuVFbfM) | 토목엔지니어 돌종 | 코딩 에이전트·대체 모델 (선택) |
| 2 | [네이버 블로그 규칙](https://youtu.be/Mi71bRtEGz0) | 마케팅대장 찐대표 | **블로그 새로고침·메이트** |
| 3 | [GBrain 설치](https://youtu.be/4pgGVGA0IxU) | 헤이제임스 | **에이전트 메모리·MCP** |
| 4 | [AI 니치 6+2](https://youtu.be/YjTAK0lr8I0) | moneymonsterTV | **shorts_factory 콘티** |

---

## A. 블로그 (2번 영상 + `naver-blog-refresh`)

### 배경 (한 줄)

네이버 검색 상단 **AI 브리핑**이 요약을 먼저 보여 주면, 예전처럼 블로그 1층 노출만으로 클릭이 나오지 않습니다. AI가 **인용하는 글**만 살아남는 구조입니다.

### 지금 당장 바꿀 3가지

1. **AI가 인용하기 쉬운 구조** — `##` 소제목, 단계별 정리, 표·FAQ, 짧은 문단. 장문 나열·소제목 없음 금지.
2. **직접 경험·출처** — 시공·실패·수치 2문장 이상. 협찬·내돈내산 상단 고지. 메이트 5원칙 (`wiki/03_naver_mate.md`).
3. **검색 의도 = 제목 = 본문 첫 단락** — 키워드만 끼워 넣은 옛 SEO 금지. 사진 핵심은 본문·표에도 텍스트로.

### 5단계 워크플로 (스킬)

| 단계 | 산출물 | Autoblog |
|------|--------|----------|
| 1 진단 | 통과/부족 표 + 치명 3건 | `python scripts/naver_blog_diagnose.py 글.txt` |
| 2 구조 | 제목 후보 + `##` 개요만 | 스킬 2단계 |
| 3 초안 | 1,500자+ 본문 | `blog_content_gen` 또는 수동 |
| 4 인터뷰 | 경험 슬롯 5문 | 사용자 답변 반영 |
| 5 패키지 | 발행용 + 사람 체크리스트 | 재발행 vs 수정 |

### 블로그 발행 전 체크 (복사용)

- [ ] 상단 상업 고지 (해당 시)
- [ ] 직접 경험 2문장+ (수치·장소·시점)
- [ ] `##` 4~6개, 문단 3~4줄 이내
- [ ] 이미지 설명이 본문·표에도 있음
- [ ] 금지어 없음 (안녕하세요, 알아보겠습니다, 도움이 되었으면)
- [ ] 마지막 280자 안에 독자 질문 `?` 1개
- [ ] 태그 5~8개, 글 유형과 일치
- [ ] AI 브리핑에 잘릴 각 소제목이 **한 덩어리 정보**로 읽힘

상세: `wiki/04_ai_briefing_geo.md`, `.cursor/skills/naver-blog-refresh/SKILL.md`

---

## B. 에이전트 메모리 (3번 영상 + GBrain)

### 핵심

- 검색 = 문서 목록 / **뇌 = 출처 달린 합성 답**
- 차별화는 모델이 아니라 **붙인 기억(메모·그래프)**

### 이 프로젝트 권장 (단계)

| 단계 | 방법 | 비용 |
|------|------|------|
| 지금 | `AGENTS.md` + `wiki/` + `.cursor/skills/` | 무료 |
| 선택 | GBrain 로컬 + Claude/Cursor MCP | 로컬 |
| 장기 | `wiki/` → GBrain import 동기화 | 수동/스크립트 |

상세: `docs/integrations/gbrain_mcp_review.md`

---

## C. 쇼츠·FLOW (4번 영상 + `shorts_factory`)

### 원칙

- 해외 **수익 숫자**를 한국에 그대로 쓰지 말 것 → **구조·니치**만 가져오기
- 얼굴 없음 + AI 생성 + **니치 고정**이 공통점
- 찍어내기·저작권·정책 위반 니치는 한국에서 채널 위험

### 6니치 (템플릿: `data/shorts_factory/niche_templates.json`)

| ID | 니치 | 쇼핑쇼츠 연계 |
|----|------|----------------|
| `sleep_ambient` | 수면·잔잔한 롱폼/루프 | 낮음 (브랜드 무관) |
| `ai_documentary` | AI 다큐·설명 | 중 (정보+제품 각도) |
| `affluent_lifestyle` | 고단가 시청자 관심사 | 높음 |
| `deep_sea` | 심해·신기한 자연 | 중 |
| `history_cinematic` | 역사 영화 톤 | 중 |
| `mega_structures` | 다리·터널·인프라 | 중 |

### 한국에서 피할 2니치 (영상 기준)

| ID | 이유 |
|----|------|
| `celebrity_gossip` | 초상권·명예훼손·저작권 |
| `medical_claims` | 의료·건강 효능 단정, 플랫폼 정책 |

### 쇼츠 콘티 전 체크

- [ ] `python -m shorts_factory.build --niche <id> --product <product_id>`
- [ ] 후킹 8자+ · 질문/상황 시작
- [ ] 장면 흐름: 고민 → 제품/효과 → CTA
- [ ] FLOW 프롬프트 영어·실사 B-roll
- [ ] 멘트 패러프레이즈 (100% 복붙 금지)
- [ ] 광고·제휴 표기 (`youtube_description`)

---

## D. 코딩·모델 (1번 영상, 참고)

- GLM 5.2 등 **오픈·접근 가능** 모델은 Claude Code 대체 후보
- 벤치·비전 추론 약점은 코딩/엔지니어링 위주 작업에만 사용
- Autoblog 핵심 루프는 기존 Gemini/Ollama 유지해도 됨

---

## 파일 맵

| 용도 | 경로 |
|------|------|
| AI 브리핑·GEO | `wiki/04_ai_briefing_geo.md` |
| 블로그 진단 CLI | `scripts/naver_blog_diagnose.py` |
| GBrain 검토 | `docs/integrations/gbrain_mcp_review.md` |
| 니치 템플릿 | `data/shorts_factory/niche_templates.json` |
| 니치 로더 | `shorts_factory/niche_templates.py` |
