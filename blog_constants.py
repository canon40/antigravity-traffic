# -*- coding: utf-8 -*-
"""GUI·라우터용 경량 상수 — blog_content_gen(무거움) 없이 import."""

# 글 유형 (GUI 드롭다운 = blog_content_gen.POST_TYPES 와 동기화)
AUTO_POST_TYPE = "자동(매번 랜덤)"

POST_TYPES = (
    AUTO_POST_TYPE,
    "취미글",
    "알림글",
    "코팅제 정보",
    "자동차 정보",
    "바이크 정보",
    "맛집/일상",
    "정보성 팁",
    "NAEO·AI 트렌드",
    "제품 홍보",
)

# GUI 드롭다운: 사용자가 주제를 직접 선택 (자동 랜덤 제외)
POST_TYPES_GUI = tuple(x for x in POST_TYPES if x != AUTO_POST_TYPE)
IGNORE_KEYWORDS_POST_TYPES = ("맛집/일상", "취미글", "알림글", "NAEO·AI 트렌드")


def validate_automation_subject(config) -> tuple[bool, str]:
    """글 유형·키워드가 사용자 선택인지 확인. (False, 메시지) 또는 (True, '')."""
    post_type = (config.get("post_type") or "").strip()
    if not post_type or post_type == AUTO_POST_TYPE:
        return False, "글 유형(주제)을 선택해 주세요. 혼자 주제를 정하는 '자동(매번 랜덤)'은 사용할 수 없습니다."
    keywords = config.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]
    if not keywords and post_type not in IGNORE_KEYWORDS_POST_TYPES:
        return False, "포스팅 키워드를 입력해 주세요."
    return True, ""


PRODUCT_LABELS = {
    "auto": "자동차 코팅제",
    "bike": "바이크 코팅제",
    "living": "리빙 코팅제",
}
PRODUCT_POST_TYPE = {
    "auto": "자동차 정보",
    "bike": "바이크 정보",
    "living": "제품 홍보",
}
PRODUCT_KEYWORDS = {
    "auto": [
        "Permacoat 퀵", "Permacoat 티탄", "Permacoat 레진", "자동차 유리막 코팅",
        "발수 복원", "전용 건식 관리제", "차량 광택 유지", "셀프 차량 코팅",
    ],
    "bike": [
        "바이크 코팅제", "오토바이 유리막 코팅", "바이크 레진", "머플러 크롬 코팅",
        "배기 열 코팅", "바이크 발수", "Permacoat 바이크", "바이크 디테일링",
    ],
    "living": [
        "듀라코트 리빙코트", "욕실코팅제", "타일코팅", "싱크대코팅",
        "가구 코팅", "발수코팅", "곰팡이억제", "유리막코팅제",
    ],
}

# drawer 모듈 ID (서랍)
DRAWER_MODULES = (
    "blog",       # 블로그 자동 포스팅
    "store",      # 스마트스토어 마케팅
    "neighbor",   # 서이추
    "verify",     # API/계정 검증만
    "wiki",       # 지침 조회만
    "idle",       # 아무 것도 안 함
)
