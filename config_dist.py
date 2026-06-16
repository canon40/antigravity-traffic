# 배포용 설정 (blog auto.exe) — API 키·계정 정보 없음. 사용자가 설정 탭에서 입력 후 저장.
import os

# Google / Gemini API Key (사용자 입력)
GOOGLE_API_KEY = ""
GEMINI_API_KEY = ""

# Google Account (참고/메모)
GOOGLE_ID = ""
GOOGLE_PW = ""
BLOG_ID = ""

# Tistory (사용자 입력)
TISTORY_ID = ""
TISTORY_PW = ""

# Naver (사용자 입력)
NAVER_ACCOUNTS = [
    {"id": "", "pw": ""},
    {"id": "", "pw": ""},
]

# Vertex AI (선택, 사용자 입력)
VERTEX_PROJECT_ID = ""
VERTEX_API_KEY = ""
VERTEX_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vertex-key.json")
