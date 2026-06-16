# 나눔랩 쇼핑 SEO 자동화 시스템 — 실행 가이드

> **목표**: 네이버 쇼핑 "자동차코팅제" 키워드 1페이지 진입

---

## ⚡ 원클릭 실행 (BAT 파일)

| 파일 | 기능 | 언제 쓰나 |
|------|------|----------|
| `run_rank_check.bat` | 순위 즉시 체크 | **매일 아침 순위 확인** |
| `run_traffic_focus.bat` | 자동차코팅제 집중 트래픽 | **하루 3~5회 수동 실행** |
| `run_blog_post.bat` | SEO 블로그 글 생성 | **주 3~5회 블로그 발행** |

---

## 🚀 권장 하루 루틴

```
오전 09:00  run_rank_check.bat      → 오늘 현재 순위 확인
오전 10:00  run_traffic_focus.bat   → 트래픽 세션 1회
            (1번 선택: 테스트 1회 실행)

오후 12:00  run_blog_post.bat       → 블로그 글 1개 생성
            → blog_drafts 폴더에서 HTML 파일을 네이버 블로그에 복붙

오후 02:00  run_traffic_focus.bat   → 트래픽 세션 2회
오후 04:00  run_traffic_focus.bat   → 트래픽 세션 3회
오후 06:00  run_rank_check.bat      → 저녁 순위 확인 (변화 체크)
오후 09:00  run_traffic_focus.bat   → 트래픽 세션 4회 (선택)
```

> **⚠️ 주의**: 하루 5회 이상은 위험합니다. IP를 자주 바꿔주세요!

---

## 📋 각 파일 상세 설명

### 1. 순위 체크 — `run_rank_check.bat`

```
python rank_monitor_live.py           # 1회 즉시 체크
python rank_monitor_live.py --watch   # 60분마다 자동 반복
python rank_monitor_live.py --watch --interval 30  # 30분마다
```

체크 키워드:
- 🎯 자동차코팅제 (집중 공략)
- 📊 바이크코팅제 (비교)
- 🏷️ 퍼마코트 (브랜드)
- 🔍 셀프 유리막 코팅 (롱테일)
- 🔍 유리막코팅제 (롱테일)

결과는 `rank_live_log.csv` 에 자동 누적 저장됩니다.

---

### 2. 트래픽 세션 — `run_traffic_focus.bat`

```
python traffic_single.py --test    # 1회 테스트
python traffic_single.py --engine  # 24시간 연속 (주의!)
```

**안전 설정 (자동 적용):**
- 자동차코팅제 75% 집중 / 25% 기타 키워드 분산
- 세션 간 최소 **15분** 강제 대기
- 시간당 최대 **4회** 제한
- 봇 감지 시 **45분** 자동 쿨다운
- 연속 3회 실패 시 **30분** 추가 대기
- UA 7종 랜덤 로테이션 (PC/Mac/iPhone/Android)

---

### 3. 블로그 글 생성 — `run_blog_post.bat`

```
python blog_autoposter.py --once    # 글 1개 즉시 생성
python blog_autoposter.py --engine  # 무한 자동 발행
```

생성 결과:
- `blog_drafts/` 폴더에 HTML 파일로 저장
- 티스토리 토큰 있으면 → 자동 발행
- 네이버 블로그 → HTML 파일 열어서 내용 복붙

**집중 키워드 (자동 로테이션):**
- 자동차코팅제, 자동차 유리막 코팅, 차량 코팅제, 셀프 유리막 코팅 등

---

### 4. 키워드 트렌드 분석

```
python keyword_trend_analyzer.py
python keyword_trend_analyzer.py --keywords "자동차코팅제,바이크코팅제,유리막코팅"
```

분석 항목:
- 자동차코팅제 vs 바이크코팅제 순위 비교
- 경쟁 강도 분석 (광고 수, 상위 20위 경쟁사 수)
- 진입 용이 키워드 추천

결과는 `keyword_trend_report.json` 에 저장됩니다.

---

## 🛡️ 보안 설정 (`security_vault/credentials.json`)

```json
{
  "tistory_access_token": "YOUR_TOKEN",
  "tistory_blog_name": "your-blog-name",
  "gemini_api_key": "YOUR_GEMINI_KEY"
}
```

- 티스토리 토큰 없어도 동작 (초안 파일로 저장)
- Gemini 키 없어도 동작 (내장 템플릿 사용)

---

## 📁 생성되는 파일

| 파일 | 내용 |
|------|------|
| `permcoat_history.csv` | 트래픽 세션 기록 |
| `rank_live_log.csv` | 실시간 순위 체크 기록 |
| `keyword_trend_report.json` | 키워드 분석 결과 |
| `blog_drafts/*.html` | 생성된 블로그 초안 |

---

## 🔥 지금 당장 할 것

1. `run_rank_check.bat` 실행 → 현재 순위 확인
2. `run_traffic_focus.bat` → 1번 선택 (1회 테스트)
3. 정상 동작 확인 후 → 하루 3~5회 반복
4. `run_blog_post.bat` → 블로그 초안 생성 후 네이버 복붙

---

*나눔랩 퍼마코트 자동차코팅제 — 1페이지 진입 파이팅! 🚀*
