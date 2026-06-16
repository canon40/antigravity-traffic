# sangseopage × LoopReel

상세페이지 기획 로직은 `shorts_factory/detail_analyzer.py`에 통합되어 있습니다.

## 실행 (권장)

**`view_detail_page.bat`** — 상세페이지 전용 스튜디오만 엽니다 (3단계 UI).

또는 쇼츠 스튜디오(`view_shorts_factory.bat`)에서 **「상세페이지 스튜디오 ↗」** 버튼.

- URL: http://127.0.0.1:8766/detail/
- UI 파일: `docs/detail_page/index.html`

## 3단계

1. **프로젝트 선택** — 콘티가 있는 작업
2. **니즈·후킹 분석** — API 없음 → `detail_analysis.json`
3. **HTML 생성** — 분석 반영 → `detail_preview.html`, `detail_smartstore.html`

## 산출물 위치

`docs/shorts/{slug}/` (쇼츠 프로젝트와 동일 폴더)
