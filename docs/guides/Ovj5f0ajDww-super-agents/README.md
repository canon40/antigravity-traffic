# 24/7 Super Agent 가이드 (Base44 영상 로컬 구현)

원본: [How to Build 24/7 Claude Agents! EASILY!](https://youtu.be/Ovj5f0ajDww) — WorldofAI

## 바로 실행

1. **Ollama** 실행: `ollama serve` (모델: `gemma4:e2b` 권장)
2. **`run_super_agents.bat`** 더블클릭 — 리서치 → 스크립트 → HTML 리포트 1회 생성
3. 결과: `data/super_agents/runs/` 폴더의 `.html` (Ctrl+P로 PDF 저장)

## 명령어

| 명령 | 설명 |
|------|------|
| `run_super_agents.bat` | 1회 워크플로 실행 |
| `run_super_agents.bat init` | `workflow.json` 초기화 |
| `run_super_agents.bat status` | Ollama·Gmail 설정 상태 |
| `run_super_agents.bat schedule` | 매일 09:00 KST 자동 실행 등록 |
| `run_super_agents.bat guide` | HTML 가이드 열기 |
| `run_super_agents.bat run --email` | Gmail 발송 포함 |

## Gmail 설정 (선택, 4단계 Notify Agent)

`.env`에 추가:

```
SUPER_AGENT_GMAIL_USER=your@gmail.com
SUPER_AGENT_GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
SUPER_AGENT_EMAIL_TO=your@gmail.com
```

[Gmail 앱 비밀번호](https://myaccount.google.com/apppasswords) 발급 후 사용.

## 에이전트 체인 (영상과 동일 구조)

```
Research → Script → Report (HTML/PDF) → Gmail (선택)
```

| 에이전트 | 영상 (Base44) | login2 로컬 |
|----------|---------------|-------------|
| Research | 웹 딥리서치·신뢰도 | DuckDuckGo + 네이버 + Ollama |
| Script | 영상 대본 | INTRO/SEGMENTS/CTA/OUTRO |
| Report | PDF 브리핑 | 스타일 HTML (인쇄→PDF) |
| Notify | Gmail 연동 | SMTP (선택) |
| Schedule | 클라우드 9AM ET | `schtasks` 9AM KST |

## 설정 파일

`data/super_agents/workflow.json` — 조사 주제·목표·스케줄 수정

## 가이드 페이지

- **`open_super_agents_guide.bat`** 또는 http://127.0.0.1:8766/guide/super-agents/

## 다시 학습

```powershell
Set-Location "d:\@code\antigravity\blogauto\login2"
.\.venv\Scripts\python.exe learn_youtube_evolution.py "https://youtu.be/Ovj5f0ajDww"
```
