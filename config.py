# API Keys and Accounts Configuration
import os

from hub_runtime import is_cloud_hub

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return False

# .env에서 환경변수 로드 (개인 PC용). Vercel·Cloudtype은 대시보드 env만 사용.
if not is_cloud_hub():
    load_dotenv()
    _javis_env = os.environ.get("JARVIS_ROOT", r"D:\@code\javis")
    _javis_dotenv = os.path.join(_javis_env, ".env")
    if os.path.isfile(_javis_dotenv):
        load_dotenv(_javis_dotenv, override=False)
else:
    _javis_env = os.environ.get("JARVIS_ROOT", "")


def _apply_jarvis_claude_fable() -> None:
    """JARVIS Claude Fable 5 전역 모델을 블로그 CLI에도 주입."""
    if not os.path.isdir(_javis_env):
        return
    import sys

    if _javis_env not in sys.path:
        sys.path.insert(0, _javis_env)
    try:
        from pathlib import Path

        from integrations.anthropic_config import apply_claude_fable_globals
        from integrations.claude_fable_bridge import ensure_loop_md

        apply_claude_fable_globals()
        ensure_loop_md(target_dir=Path(__file__).resolve().parent)
    except Exception:
        pass


if not is_cloud_hub():
    _apply_jarvis_claude_fable()

# Google / Gemini API Key (둘 중 하나만 있어도 동작)
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "") or GOOGLE_API_KEY

# Google Account (참고용 메모 – 로그인에는 사용하지 않음)
GOOGLE_ID = os.environ.get("GOOGLE_ID", "")
GOOGLE_PW = os.environ.get("GOOGLE_PW", "")

# Blogger Blog ID (Google Blogger API용, 선택)
BLOG_ID = os.environ.get("BLOG_ID", "")

# Tistory Account (기본값 없음 – 설정 탭/계정 파일에서 입력)
TISTORY_ID = ""
TISTORY_PW = ""

# Naver Accounts (배포용 기본값 없음 – 설정 탭/계정 파일에서 입력)
NAVER_ACCOUNTS = [
    {"id": "", "pw": ""},   # 네이버 1
    {"id": "", "pw": ""},   # 네이버 2
]

# Naver Search API (순위 추적 403 우회 — developers.naver.com 앱 등록 후 검색 API 활성화)
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "") or os.environ.get("NAVER_SEARCH_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "") or os.environ.get("NAVER_SEARCH_CLIENT_SECRET", "")

# Supabase (스마트스토어 키워드 DB — 선택, JARVIS와 동일 프로젝트 재사용 가능)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = (
    os.environ.get("SUPABASE_ANON_KEY", "")
    or os.environ.get("SUPABASE_KEY", "")
)
SUPABASE_SERVICE_KEY = (
    os.environ.get("SUPABASE_SERVICE_KEY", "")
    or os.environ.get("SUPABASE_SECRET_KEY", "")
)
STORE_KEYWORDS_TABLE = os.environ.get("STORE_KEYWORDS_TABLE", "keywords")

# Vertex AI Settings (배포용 기본값 없음 – 설정 탭/계정 파일에서 입력)
VERTEX_PROJECT_ID = os.environ.get("VERTEX_PROJECT_ID", "")
VERTEX_API_KEY = os.environ.get("VERTEX_API_KEY", "")
# Vertex AI 서비스 계정 키 (선택). 배포본에서는 vertex-key.json 등을 exe 옆에 두고 경로만 맞추면 됨.
VERTEX_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vertex-key.json")
