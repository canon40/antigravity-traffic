# Vercel 24시간 SEO · 트래픽 허브 배포

홈페이지(`app.py` + `templates/index.html`)를 Vercel에 올리면 **PC 없이** 순위 추적·SEO 점검·클라우드 트래픽이 동작합니다.

## 무엇이 클라우드에서 되는지

| 기능 | Vercel | PC 전용 |
|------|--------|---------|
| 순위 추적 대시보드 | ✅ | |
| 매시 Cron 자동 추적 | ✅ | |
| SEO 체크리스트 | ✅ | |
| 콘텐츠 템플릿 생성 | ✅ | |
| httpx 클라우드 트래픽 | ✅ | |
| Supabase 순위 히스토리 | ✅ (설정 시) | |
| Playwright 블로그 발행 | | ✅ `run_gui.bat` |
| .bat / JARVIS 실행 | | ✅ 로컬 |

## 1. Supabase (24시간 데이터 유지 — 강력 권장)

Vercel `/tmp`는 인스턴스마다 초기화됩니다. **히스토리·로그·Cron 상태**를 유지하려면 Supabase를 씁니다.

1. [Supabase](https://supabase.com) 프로젝트 생성
2. SQL Editor에서 `docs/sql/rank_hub.sql` 실행
3. Vercel 환경변수:

| 변수 | 값 |
|------|-----|
| `SUPABASE_URL` | `https://xxxx.supabase.co` |
| `SUPABASE_SERVICE_KEY` | service_role 키 (anon만 쓸 경우 RLS 정책 확인) |

## 2. Vercel 프로젝트 연결

1. GitHub에 이 저장소 푸시
2. [Vercel](https://vercel.com) → **Add New Project** → 저장소 선택
3. **Root Directory**: `.` (저장소 루트 — `vercel.json`이 있는 위치)
4. **Framework Preset**: Other
5. Install Command는 `vercel.json`의 `requirements-vercel.txt` 사용 (자동)

### 환경변수 (Vercel Dashboard → Settings → Environment Variables)

| 변수 | 필수 | 설명 |
|------|------|------|
| `SUPABASE_URL` | 권장 | 순위·상태 영구 저장 |
| `SUPABASE_SERVICE_KEY` | 권장 | REST 쓰기 |
| `CRON_SECRET` | 권장 | Cron 엔드포인트 보호 (`Authorization: Bearer ...`) |
| `WEBHOOK_SECRET` | 선택 | `POST /api/traffic` 외부 웹훅 인증 |
| `TRAFFIC_TARGET_URL` | 선택 | 기본 스마트스토어 URL (미설정 시 config 첫 상품) |

## 3. Cron (24시간 자동)

`vercel.json`에 등록됨:

| 경로 | 주기 | 역할 |
|------|------|------|
| `/api/cron/track` | 매시 정각 | 우선 키워드 순위 추적 (배치) |
| `/api/cron/traffic` | 20분마다 | 스마트스토어 httpx 방문 1회 |

홈페이지에서 **자동 추적**을 켜면 `auto_enabled=true`가 Supabase에 저장되고 Cron이 실행됩니다. 끄면 Cron은 건너뜁니다.

> Vercel **Pro** 이상에서 Cron이 안정적입니다. Hobby는 Cron 제한이 있을 수 있습니다.

## 4. 배포 후 확인

```bash
# 로컬에서 (배포 URL을 넣은 뒤)
curl https://YOUR-PROJECT.vercel.app/api/health
curl -X POST https://YOUR-PROJECT.vercel.app/api/traffic \
  -H "Content-Type: application/json" \
  -d "{\"target_url\":\"https://smartstore.naver.com/nanumlab\"}"
```

홈페이지 `/` → 상태 **24h Cron** → **지금 추적** / **클라우드 트래픽** 테스트.

## 5. PC Autoblog와 함께 쓰기

`accounts.json` (커밋 금지):

```json
{
  "vercel_api_url": "https://YOUR-PROJECT.vercel.app/api/traffic",
  "vercel_enabled": true,
  "vercel_mode": "both",
  "product_url": "https://smartstore.naver.com/nanumlab/products/12639296730"
}
```

검증:

```bash
python scripts/verify_vercel_traffic.py
```

## 6. `vercel_traffic/` 별도 프로젝트 (선택)

트래픽만 분리 배포하려면 Root Directory를 `vercel_traffic`로 두면 됩니다.  
**통합 허브**는 루트 배포 한 번으로 순위 + 트래픽 API(`/api/traffic`)를 모두 제공합니다.
