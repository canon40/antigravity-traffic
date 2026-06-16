"""앱 데이터 경로·상품 DB (APK에서 products.json 누락 시 내장 DB 사용)."""
import json
import os

from hub_runtime import uses_ephemeral_disk

EMBEDDED = {
    "store_name": "나눔랩",
    "products": {
        "10713170202": "듀라코트 리빙코트",
        "12639296730": "퍼마코트 자동차 코팅제",
        "12634187514": "나눔랩 코팅 상품",
        "12808787263": "나눔랩 세정·관리제",
        "12808820913": "나눔랩 코팅제 A",
        "12809519826": "나눔랩 코팅제 B",
        "12809532969": "나눔랩 코팅제 C",
        "12809541448": "나눔랩 코팅제 D",
        "12639326305": "나눔랩 관련 상품 E",
    },
}


def get_storage_dir():
    """쓰기 가능한 앱 저장소 (클라우드: /tmp, Android: FLET_APP_STORAGE_DATA)."""
    if uses_ephemeral_disk():
        data = "/tmp/anty-traffic"
        os.makedirs(data, exist_ok=True)
        return data
    data = os.environ.get("FLET_APP_STORAGE_DATA")
    if data:
        os.makedirs(data, exist_ok=True)
        return data
    return os.getcwd()


def _read_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_products():
    candidates = [
        os.path.join(os.getcwd(), "products.json"),
        "products.json",
    ]
    for path in candidates:
        data = _read_json(path)
        if data and data.get("products"):
            return data.get("store_name", "나눔랩"), data["products"]
    return EMBEDDED["store_name"], dict(EMBEDDED["products"])
