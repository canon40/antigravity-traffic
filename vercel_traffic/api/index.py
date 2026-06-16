import os
import sys
from pathlib import Path
from typing import Annotated

# Vercel serverless: traffic_session.py는 상위 폴더에 있음
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from traffic_session import run_traffic_session

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "").strip()
MAX_TIMEOUT_SEC = min(float(os.environ.get("TRAFFIC_TIMEOUT_SEC", "8")), 9.0)

app = FastAPI(
    title="Vercel Traffic API",
    description="Base44 웹훅 연동용 서버리스 트래픽 API (10초 이내 HTTP 방문)",
    version="1.0.0",
)


class TrafficInput(BaseModel):
    target_url: HttpUrl = Field(
        default="https://smartstore.naver.com",
        description="방문할 스마트스토어/상품 URL",
    )
    timeout_sec: float = Field(
        default=MAX_TIMEOUT_SEC,
        ge=1.0,
        le=9.0,
        description="요청 타임아웃(초). Vercel 무료 플랜은 최대 10초",
    )


def verify_webhook(
    authorization: Annotated[str | None, Header()] = None,
    x_webhook_secret: Annotated[str | None, Header(alias="X-Webhook-Secret")] = None,
) -> None:
    if not WEBHOOK_SECRET:
        return
    if authorization == f"Bearer {WEBHOOK_SECRET}":
        return
    if x_webhook_secret == WEBHOOK_SECRET:
        return
    raise HTTPException(status_code=401, detail="인증 실패: WEBHOOK_SECRET이 일치하지 않습니다.")


@app.get("/api/health")
@app.get("/api")
def health_check():
    """Base44가 서버 상태를 감시(GET)할 때 호출."""
    return {
        "status": "healthy",
        "message": "Vercel Python Server is running",
        "execution": "serverless_fastapi",
    }


@app.post("/api/traffic")
def trigger_traffic(
    data: TrafficInput,
    _: Annotated[None, Depends(verify_webhook)] = None,
):
    """Base44가 주기적으로 POST 신호를 보내 트래픽 세션 1회 실행."""
    target_url = str(data.target_url)
    timeout_sec = min(data.timeout_sec, MAX_TIMEOUT_SEC)

    try:
        result = run_traffic_session(target_url, timeout_sec=timeout_sec)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"작업 중 에러 발생: {exc}") from exc

    if not result.get("ok"):
        raise HTTPException(
            status_code=502,
            detail={
                "status": "error",
                "message": f"방문 실패: HTTP {result.get('status_code')}",
                "target_url": target_url,
                "result": result,
            },
        )

    return {
        "status": "success",
        "message": f"{target_url} 대상 트래픽 작업이 성공적으로 완료되었습니다.",
        "execution": "serverless_fastapi",
        "target": target_url,
        "result": result,
    }
