import json
import os
from datetime import datetime

from app_resources import get_storage_dir

CONFIG_PATH = "config.json"


def _output_dir():
    path = os.path.join(get_storage_dir(), "generated_content")
    os.makedirs(path, exist_ok=True)
    return path

WORKFLOW_TYPES = {
    "product_detail": "상품 상세페이지 (ABCD)",
    "blog_review": "블로그 체험 후기",
    "comparison": "비교·선택 가이드",
    "howto": "사용법 튜토리얼",
    "faq": "FAQ 블록",
    "meta_tags": "상품명·태그·메타",
    "seasonal": "시즌 캠페인",
    "benefit": "핵심 혜택 요약",
    "trust": "신뢰·인증 강조",
    "cta": "구매 유도 CTA",
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"store_name": "나눔랩", "brand": "나눔랩"}


def _abcd_product_detail(keyword, product_name, brand):
    return {
        "workflow": "product_detail",
        "title": f"{keyword} | {product_name} - {brand}",
        "sections": {
            "A_주목": (
                f"차량 외장이 금방 흐려지고 물때가 남나요?\n"
                f"'{keyword}'를 검색하신 분들이 가장 먼저 겪는 고민입니다."
            ),
            "B_이점": (
                f"• 셀프 작업으로 전문 코팅샵급 광택 구현\n"
                f"• 발수·오염 방지로 세차 횟수 감소\n"
                f"• {brand} {product_name} — 초보자도 균일하게 도포 가능"
            ),
            "C_근거": (
                f"• 실사용 전후 비교 사진·영상 배치 권장\n"
                f"• 성분·도포 방법·유지 기간을 숫자로 명시\n"
                f"• 구매자 리뷰에서 '{keyword}' 관련 키워드가 자연스럽게 등장하도록 유도"
            ),
            "D_행동유도": (
                f"지금 바로 {product_name} 상세페이지에서 용량·구성을 확인하세요.\n"
                f"첫 구매 고객 대상 사용 가이드 PDF를 함께 제공하면 체류 시간이 늘어납니다."
            ),
        },
        "seo_tags": [keyword, brand, product_name, "셀프코팅", "유리막코팅", "자동차관리"],
        "meta_description": (
            f"{brand} {product_name} — {keyword} 추천. "
            f"셀프 유리막 코팅으로 광택·발수·오염 방지를 한 번에. 사용법·후기·구매 안내."
        )[:160],
    }


def _blog_review(keyword, product_name, brand):
    return {
        "workflow": "blog_review",
        "title": f"[직접 써봤어요] {keyword} 후기 — {product_name}",
        "body": (
            f"## 왜 {keyword}를 알아보게 됐나요\n"
            f"세차 후 금방 다시 흐려지는 게 스트레스였습니다.\n\n"
            f"## {brand} {product_name} 사용 과정\n"
            f"1. 세차 후 물기 제거\n2. 균일 도포\n3. 24시간 경화\n\n"
            f"## 한 달 사용 소감\n"
            f"발수감과 광택 유지가 눈에 띄었습니다. "
            f"상세페이지 링크는 글 하단에 배치하세요.\n\n"
            f"## 총평\n"
            f"{keyword} 검색하시는 분들에게 과장 없이 경험을 공유하는 톤이 효과적입니다."
        ),
    }


def _meta_tags(keyword, product_name, brand):
    short_name = f"{brand} {product_name} {keyword}"[:50]
    return {
        "workflow": "meta_tags",
        "product_title_suggestion": short_name,
        "tags": list(dict.fromkeys([
            keyword, brand.replace(" ", ""), "셀프코팅", "유리막",
            "자동차코팅", "차량관리", "광택", "발수코팅", "나눔랩",
        ]))[:10],
        "meta_description": _abcd_product_detail(keyword, product_name, brand)["meta_description"],
        "h1_suggestion": f"{product_name} — {keyword} 셀프 코팅 솔루션",
    }


def generate_content(workflow_type, keyword, product_name=None, brand=None, product_id=None):
    keyword = (keyword or "").strip()
    if not keyword:
        return {"success": False, "error": "키워드를 입력하세요."}

    from store_link_builder import append_store_footer_to_content, resolve_listing

    config = load_config()
    brand = brand or config.get("store_name", "나눔랩")
    product_name = product_name or config.get("default_product_name", "퍼마코트")
    listing = resolve_listing(keyword, product_id)

    builders = {
        "product_detail": lambda: _abcd_product_detail(keyword, product_name, brand),
        "blog_review": lambda: _blog_review(keyword, product_name, brand),
        "meta_tags": lambda: _meta_tags(keyword, product_name, brand),
        "comparison": lambda: {
            "workflow": "comparison",
            "title": f"{keyword} 비교 가이드 — 워셔형 vs 전문 코팅",
            "body": (
                f"## {keyword} 선택 시 체크리스트\n"
                f"- 도포 난이도\n- 유지 기간\n- 가격 대비 용량\n- 리뷰 평점\n\n"
                f"## {product_name} 포지션\n"
                f"셀프 작업 가능 + 합리적 가격대를 강조하세요."
            ),
        },
        "howto": lambda: {
            "workflow": "howto",
            "title": f"{product_name} 셀프 코팅 5단계",
            "steps": [
                "세차 및 완전 건조",
                "클레이·폴리싱(선택)",
                "도포량 준비 — 한 패널씩 작업",
                "균일 스프레드 후 15~30분 경화",
                "잔여물 제거 및 24시간 주차",
            ],
        },
        "faq": lambda: {
            "workflow": "faq",
            "items": [
                {"q": f"{keyword} 초보자도 가능한가요?", "a": "예, 동봉 가이드와 영상을 함께 제공하세요."},
                {"q": "유지 기간은?", "a": "사용 환경에 따라 3~6개월, 구체 수치를 명시하세요."},
                {"q": "세차 후 바로 도포?", "a": "물기·오일 잔여물 제거 후 도포를 권장합니다."},
            ],
        },
        "seasonal": lambda: {
            "workflow": "seasonal",
            "title": f"[{datetime.now().month}월] {keyword} 시즌 케어 가이드",
            "body": (
                f"## 이번 시즌 왜 {keyword}인가\n"
                f"장마·여름 강우, 겨울 염분 등 계절 요인으로 도장면 손상이 빨라집니다.\n\n"
                f"## {brand} {product_name} 시즌 포인트\n"
                f"- 발수·방오로 세차 부담 줄이기\n"
                f"- UV·오염으로부터 외장 보호\n"
                f"- 시즌 한정 체험 후기·전후 사진 삽입\n\n"
                f"## CTA\n"
                f"스마트스토어 링크와 시즌 키워드('{keyword}')를 제목·첫 문단에 자연스럽게 넣으세요."
            ),
        },
        "benefit": lambda: {
            "workflow": "benefit",
            "title": f"{product_name} 핵심 혜택 — {keyword}",
            "body": (
                f"## 한 줄 요약\n"
                f"{brand} {product_name}는 '{keyword}' 검색 고객에게 **셀프 코팅 + 발수 + 광택**을 동시에 제안합니다.\n\n"
                f"## 3가지 혜택\n"
                f"1. **시간 절약** — 세차·관리 횟수 감소\n"
                f"2. **비용 절약** — 전문샵 대비 합리적 셀프 솔루션\n"
                f"3. **지속 광택** — 균일 도포 시 3~6개월 유지(환경별 상이)\n\n"
                f"## 블로그 작성 팁\n"
                f"숫자·전후 비교·실사용 사진을 넣고 과장 없는 1인칭 톤을 유지하세요."
            ),
        },
    }

    if workflow_type not in builders and workflow_type not in WORKFLOW_TYPES:
        return {"success": False, "error": f"지원하지 않는 워크플로우: {workflow_type}"}

    if workflow_type in builders:
        content = builders[workflow_type]()
    else:
        content = _abcd_product_detail(keyword, product_name, brand)
        content["workflow"] = workflow_type

    content = append_store_footer_to_content(content, keyword, listing)

    result = {
        "success": True,
        "workflow": workflow_type,
        "workflow_label": WORKFLOW_TYPES.get(workflow_type, workflow_type),
        "keyword": keyword,
        "product_name": product_name,
        "brand": brand,
        "product_id": listing.get("seller_id"),
        "store_url": listing.get("url"),
        "listing_title": listing.get("title"),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "content": content,
    }
    return result


def save_blog_draft_files(result, product_id=None):
    """JSON + 블로그 붙여넣기용 TXT 저장."""
    from store_link_builder import format_blog_copy_paste

    out = _output_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    wf = result.get("workflow", "content")
    pid = product_id or result.get("product_id") or "general"
    json_path = os.path.join(out, f"{pid}_{wf}_{ts}.json")
    txt_path = os.path.join(out, f"{pid}_{wf}_{ts}_blog.txt")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    paste = format_blog_copy_paste(result)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(paste)

    return {"json": json_path, "txt": txt_path}


def save_content(result, product_id=None):
    paths = save_blog_draft_files(result, product_id=product_id)
    return paths.get("json")


def list_workflows():
    return [{"id": k, "label": v} for k, v in WORKFLOW_TYPES.items()]
