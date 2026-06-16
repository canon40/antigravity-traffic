# Google FLOW 뮤직비디오 10분 가이드

원본: [AI로 뮤직비디오 10분 컷 (lV9UzdYkT20)](https://www.youtube.com/watch?v=lV9UzdYkT20)

## 바로 열기

1. **`open_mv_guide.bat`** 더블클릭  
2. 브라우저: http://127.0.0.1:8766/guide/mv-flow/

또는 쇼츠 스튜디오 실행 후 **YouTube 학습** 페이지에서 「MV 10분 가이드」 링크.

## 파일 위치

| 용도 | 경로 |
|------|------|
| HTML 가이드 (체크리스트) | `docs/guides/lV9UzdYkT20-google-flow-mv/index.html` |
| 구조화 플레이북 JSON | `data/shorts_factory/playbooks/lV9UzdYkT20_google_flow_mv.json` |
| 학습 자막 | `data/shorts_factory/youtube_learned/lV9UzdYkT20.ko.vtt` |
| 진화 플레이북 | `data/shorts_factory/youtube_evolution.json` |

## API

- `GET /api/playbooks/mv-flow` — JSON 플레이북

## 다시 학습

```powershell
Set-Location "d:\@code\antigravity\blogauto\login2"
.\.venv\Scripts\python.exe learn_youtube_evolution.py "https://youtu.be/lV9UzdYkT20"
```

## 9단계 요약

1. FLOW — 캐릭터 4:3 · 4장  
2. FLOW — 배경 16:9 · 4장  
3. FLOW — @에셋 영상 6초  
4. FLOW — 프레임 영상 (Veo 3.1 Lite)  
5. FLOW — 트림·확장  
6. Suno — AI 가사·음악  
7. MV 도구 — 스토리보드·일괄 영상  
8. Seamless Loop Studio (선택)  
9. CapCut — 합성·전환·내보내기  
