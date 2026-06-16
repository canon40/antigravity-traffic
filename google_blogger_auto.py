import os
import pickle
from urllib.parse import urlparse
import base64
import io

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

from config import GOOGLE_API_KEY

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from google.genai import Client as GenAIClient
    from google.genai import types as genai_types
    GENAI_CLIENT_AVAILABLE = True
except ImportError:
    GENAI_CLIENT_AVAILABLE = False

GEMINI_TEXT_MODEL = os.environ.get("BLOG_GEMINI_TEXT_MODEL", "gemini-2.5-flash")

# .env에서 환경 변수 로드
load_dotenv()

# 대표님의 블로그 ID (우선순위: .env > 하드코딩 값)
BLOG_ID = os.getenv("BLOG_ID") or "80488746860695244"


def get_blogger_service():
    """
    구글 블로그(Blogger) API 인증.
    최초 1회는 브라우저가 열리며 구글 계정 로그인이 필요하고,
    이후에는 로컬의 token.pickle을 재사용한다.
    """
    scopes = ["https://www.googleapis.com/auth/blogger"]
    creds = None

    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "client_secrets.json", scopes
            )
            creds = flow.run_local_server(port=0)

        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    return build("blogger", "v3", credentials=creds)


def generate_image_src(keyword: str) -> str:
    """
    Imagen 3 모델로 키워드에 맞는 이미지를 1장 생성하고,
    1순위: IMGUR_CLIENT_ID가 있으면 Imgur에 업로드 → https 이미지 URL 반환
    2순위: 실패 시 data URL(src="data:image/png;base64,...")을 반환
    최종적으로 src에 그대로 넣을 수 있는 문자열을 돌려준다.
    문제가 생기면 빈 문자열을 반환하고, 글은 이미지 없이 올라간다.
    """
    if not GENAI_CLIENT_AVAILABLE:
        print("[WARN] google.genai 패키지가 없어 이미지 없이 진행합니다.")
        return ""

    api_key = os.getenv("GEMINI_API_KEY") or GOOGLE_API_KEY
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        print("[WARN] GEMINI_API_KEY / GOOGLE_API_KEY 가 설정되지 않아 이미지 없이 진행합니다.")
        return ""

    client = GenAIClient(api_key=api_key, http_options={"api_version": "v1beta"})

    print(f"[IMAGE] '{keyword}' 관련 이미지를 생성 중입니다...(Imagen 3)")

    prompt = (
        f"A professional high-quality studio photograph about {keyword}, "
        "premium coating product aesthetic, clean background, 8k resolution, "
        "cinematic lighting, detailed coating texture, no people, no text."
    )

    try:
        res = client.models.generate_images(
            model="imagen-3.0-generate-002",
            prompt=prompt,
            config=genai_types.GenerateImagesConfig(number_of_images=1),
        )
        if not res or not getattr(res, "generated_images", None):
            print("[WARN] 이미지 생성 결과가 비어 있어 이미지 없이 진행합니다.")
            return ""

        img_obj = res.generated_images[0]
        # google.genai 응답 타입 호환 처리
        if hasattr(img_obj, "image") and img_obj.image is not None:
            pil_img = img_obj.image
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            data = buf.getvalue()
        else:
            data = getattr(img_obj, "image_bytes", b"") or b""

        if not data:
            print("[WARN] 이미지 바이트가 없어 이미지 없이 진행합니다.")
            return ""

        # 1순위: Imgur 업로드 (IMGUR_CLIENT_ID + requests 가능할 때)
        imgur_client_id = os.getenv("IMGUR_CLIENT_ID")
        if imgur_client_id and REQUESTS_AVAILABLE:
            try:
                print("[IMAGE] Imgur에 이미지 업로드 중...")
                b64_body = base64.b64encode(data).decode("ascii")
                headers = {"Authorization": f"Client-ID {imgur_client_id}"}
                resp = requests.post(
                    "https://api.imgur.com/3/image",
                    headers=headers,
                    data={"image": b64_body, "type": "base64"},
                    timeout=20,
                )
                if resp.status_code == 200:
                    j = resp.json()
                    link = j.get("data", {}).get("link")
                    if link:
                        print(f"[OK] Imgur 업로드 완료: {link}")
                        return link
                print(f"[WARN] Imgur 업로드 실패(status={resp.status_code}), data URL로 대체합니다.")
            except Exception as e:
                print(f"[WARN] Imgur 업로드 중 예외 발생: {e}. data URL로 대체합니다.")

        # 2순위: data URL 그대로 사용
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        print(f"[FAIL] 이미지 생성 실패: {e}")
        return ""


def save_token_from_callback_url(callback_url: str) -> None:
    """
    브라우저로 받은 OAuth 콜백 URL(리다이렉트 주소)을 넘기면
    인증 코드를 토큰으로 교환해 token.pickle에 저장합니다.
    로컬 서버가 이미 꺼져 있어도, 이 URL만 있으면 인증을 완료할 수 있습니다.

    사용 예:
        save_token_from_callback_url(
            "http://localhost:63901/?state=...&code=4/0A...&scope=..."
        )
    """
    parsed = urlparse(callback_url)
    # redirect_uri는 인증 요청 시 사용한 값과 동일해야 함 (예: http://localhost:63901/)
    path = parsed.path if parsed.path else "/"
    redirect_uri = f"{parsed.scheme}://{parsed.netloc}{path}"

    scopes = ["https://www.googleapis.com/auth/blogger"]
    flow = InstalledAppFlow.from_client_secrets_file(
        "client_secrets.json", scopes
    )
    flow.redirect_uri = redirect_uri
    # oauthlib는 https만 허용하므로 로컬 리다이렉트 URL도 https로 변환해 전달
    response_url = callback_url.replace("http://", "https://", 1)
    flow.fetch_token(authorization_response=response_url)
    creds = flow.credentials

    with open("token.pickle", "wb") as token:
        pickle.dump(creds, token)
    print("[OK] 콜백 URL로 토큰 저장 완료 (token.pickle)")


def generate_expert_content(keyword: str) -> str:
    """
    나눔랩 제조 이사/마케팅 전문가 페르소나로, 구글 블로그용 SEO 글을 생성한다.
    """
    if not GENAI_CLIENT_AVAILABLE:
        raise RuntimeError("google-genai 패키지가 필요합니다. pip install google-genai")

    api_key = os.getenv("GEMINI_API_KEY") or GOOGLE_API_KEY
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise ValueError("GEMINI_API_KEY / GOOGLE_API_KEY 가 설정되지 않았습니다.")

    client = GenAIClient(api_key=api_key)

    prompt = f"""
    너는 '나눔랩(Nanum Lab)'의 제조 이사이자 마케팅 전문가야. 
    주제: '{keyword}'
    
    [작성 가이드]
    1. 말투: 평소 잘 사용하지 않는 딱딱한 용어(사료됨, 함에 있어 등)는 절대 사용하지 마. 
       친근하면서도 신뢰감 있는 구어체(~해요, ~입니다)를 사용해.
    2. 전문성: 듀라코트(Duracoat)나 퍼마코트(Permacoat) 제품의 성분 원리를 제조 전문가의 시선에서 설명해줘.
    3. 구조: HTML 형식으로 작성하며, 구글 SEO를 위해 <h2>, <h3> 소제목을 활용하고 본문 중간에 비교 표(<table>)를 포함해.
    4. 분량: 1,500자 이상의 상세한 정보를 제공해.
    """

    response = client.models.generate_content(model=GEMINI_TEXT_MODEL, contents=prompt)
    text = getattr(response, "text", None) or ""
    return str(text).strip()


def post_to_blogger(title: str, content: str, is_draft: bool = True) -> None:
    """
    이미 생성된 제목/본문을 받아 구글 Blogger에 올린다.
    is_draft=True(기본): 초안으로 저장 → draft.blogger.com에서 확인 후 직접 발행
    is_draft=False: 즉시 발행
    """
    if not BLOG_ID:
        raise ValueError("BLOG_ID가 비어 있습니다. .env 파일의 BLOG_ID 또는 하드코딩 값을 확인해 주세요.")

    service = get_blogger_service()
    body = {
        "kind": "blogger#post",
        "title": title,
        "content": content,
    }
    posts = service.posts()
    result = posts.insert(blogId=BLOG_ID, body=body, isDraft=is_draft).execute()
    if is_draft:
        print("[OK] [구글 Blogger] 초안 저장 완료 (draft.blogger.com에서 확인)")
    else:
        print("[OK] [구글 Blogger] 포스팅 완료")
    print(f"확인 주소: {result.get('url', '') or 'draft - draft.blogger.com에서 확인'}")


def post_to_google_blogger(keyword: str) -> None:
    """
    키워드를 받아 글 생성 + 발행까지 단독으로 수행하는 편의 함수.
    """
    print(f"\n[구글 Blogger 포스팅 시작] 주제: {keyword}")

    try:
        # 1) 이미지 src(가능하면 Imgur URL, 아니면 data URL) 생성 시도
        img_src = generate_image_src(keyword)

        # 2) 본문(HTML) 생성
        content = generate_expert_content(keyword)

        # 3) 생성된 이미지가 있으면 본문 맨 앞에 <img> 태그로 삽입
        if img_src:
            img_tag = (
                f'<p><img src="{img_src}" alt="{keyword}" '
                'style="max-width:100%; height:auto; display:block; margin:0 auto 1.5em auto;"></p>\n'
            )
            content = img_tag + content

        # 4) 제목 및 포스팅
        title = f"{keyword}에 대한 제조 전문가의 실전 노하우"
        post_to_blogger(title, content)
    except Exception as e:
        print(f"[FAIL] 오류 발생: {e}")


if __name__ == "__main__":
    target_keyword = input("듀라코트 리빙코트, 욕실코팅제, 타일코팅제, 식탁코팅, 원목코팅, 수전코팅, 욕실유리코팅, 싱크대코팅, 가전코팅, 가스레인지, 인덕션코팅, 전자레인지, 곰팡이억제, 유리코팅, 거실장코팅, 고전가구코팅, 색감복원, 발수복원, 피막형성, 유리막코팅제: ")
    post_to_google_blogger(target_keyword)

