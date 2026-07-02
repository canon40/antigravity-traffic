# -*- coding: utf-8 -*-
"""스마트스토어 순위 대시보드 이미지(캡처본) 분석 및 일일 비교 보고서 생성기."""
import os
import sys
import json
import mimetypes
import re
from datetime import datetime

# 로컬 모듈 로드
_BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BUNDLE_DIR)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from rank_tracker import get_last_rank, append_history

def load_gemini_key() -> str:
    path = os.path.join(_BUNDLE_DIR, "accounts.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return (data.get("gemini_key") or data.get("vertex_api_key") or "").strip()
        except Exception:
            pass
    return ""

def generate_rank_report(image_path: str):
    print("=" * 60)
    print("🤖 [나눔랩] 순위 대시보드 이미지 분석 및 데일리 비교 보고서 생성")
    print("=" * 60)

    if not os.path.exists(image_path):
        print(f"❌ 오류: 지정된 이미지 파일을 찾을 수 없습니다: {image_path}")
        return

    api_key = load_gemini_key()
    if not api_key:
        print("❌ 오류: accounts.json에서 Gemini API 키를 찾을 수 없습니다.")
        return

    # 1. google-genai 라이브러리 로드 및 설정
    try:
        from google.genai import Client
        from google.genai import types
    except ImportError:
        print("❌ 오류: 'google-genai' 패키지가 필요합니다. 'pip install google-genai'를 실행해 주세요.")
        return

    client = Client(api_key=api_key)
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = "image/png"

    try:
        with open(image_path, "rb") as f:
            image_data = f.read()
    except Exception as e:
        print(f"❌ 이미지 읽기 실패: {e}")
        return

    # 2. 이미지 파싱 프롬프트 및 파트 구성
    prompt = """
You are an expert AI data extraction assistant.
Analyze this Naver Shopping or rank tracker dashboard screenshot.
Extract all keyword ranking records. For each record, identify:
1. The Product Name (if available in the row or context, otherwise use a generic term like "프리미엄 코팅제" or "퍼마코트 자동차 코팅제" based on the product description/image).
2. The Keyword (e.g., "나노코팅", "욕실코팅제", "셀프코팅제", "나노코팅제", "퍼마코트 자동차 코팅제", "듀라코트 리빙코트").
3. The Current Rank (an integer. If it says "1위" or "1위·유지", it is 1. If it is "-" or out of ranking or "이탈", put null or 999).
4. The Change Status (e.g. "+5", "-2", "0", "new", "유지", "진입", "이탈").
5. The Store Name (usually "나눔랩" or "퍼마코트" or "듀라코트").

Format the output strictly as a JSON list, like this:
[
  {
    "product_name": "Product name or description",
    "keyword": "Keyword",
    "current_rank": 111,
    "change": "+5",
    "store_name": "Store name"
  }
]
Do not include any markdown formatting, code block markers, or extra text. Output raw JSON only.
"""

    print("📊 Gemini AI를 통해 이미지 분석 중... 잠시만 기다려 주세요.")
    try:
        image_part = types.Part.from_bytes(data=image_data, mime_type=mime_type)
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=[image_part, prompt]
        )
        raw_text = response.text.strip()
        
        # Markdown JSON 블록 제거
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\n", "", raw_text)
            raw_text = re.sub(r"\n```$", "", raw_text)
            raw_text = raw_text.strip()

        parsed_data = json.loads(raw_text)
    except Exception as e:
        err_msg = str(e)
        print(f"❌ Gemini 분석 실패: {err_msg}")
        if "API_KEY_INVALID" in err_msg or "API key not valid" in err_msg or "400" in err_msg:
            print("\n" + "="*60)
            print("⚠️ [Gemini API 키 설정 안내]")
            print("현재 설정된 Gemini API 키가 만료되었거나 유효하지 않습니다.")
            print("1. 구글 AI 스튜디오 (https://aistudio.google.com/)에 접속합니다.")
            print("2. 무료 API 키를 새로 발급받습니다 (AIzaSy... 로 시작함).")
            print("3. 프로그램의 [설정] 탭 또는 accounts.json 파일의 'gemini_key' 항목에")
            print("   새로 발급받은 키를 붙여넣고 저장해 주세요.")
            print("="*60 + "\n")
        return

    # 3. 데이터 이력 저장 및 비교 분석 진행
    today_str = datetime.now().strftime("%Y-%m-%d")
    report_items = []
    
    for item in parsed_data:
        kw = item.get("keyword", "").strip()
        store = item.get("store_name", "").strip() or "나눔랩"
        rank = item.get("current_rank")
        change_status = str(item.get("change") or "").strip()

        if not kw:
            continue

        # 이전 순위 조회
        prev_rank = get_last_rank(kw, store)
        
        # 순위 정보 정제
        if rank == 999 or rank is None or change_status == "이탈":
            rank = 999  # 이탈 표시
        
        # 이력에 기록
        detail = f"이미지 분석 등록: {rank}위" if rank != 999 else "이미지 분석 등록: 이탈"
        append_history(kw, store, rank, prev_rank, "이미지분석", detail)

        # 비교 보고서용 분석
        status = "유지"
        change_val = 0

        if rank == 999:
            status = "이탈"
        elif prev_rank is None or prev_rank == 999:
            status = "신규"
        elif rank < prev_rank:
            status = "상승"
            change_val = prev_rank - rank
        elif rank > prev_rank:
            status = "하락"
            change_val = rank - prev_rank
        else:
            status = "유지"

        report_items.append({
            "keyword": kw,
            "product_name": item.get("product_name", "코팅제"),
            "current_rank": rank,
            "prev_rank": prev_rank,
            "status": status,
            "change_val": change_val,
            "change_status": change_status
        })

    # 4. Markdown 보고서 파일 작성
    reports_dir = os.path.join(_BUNDLE_DIR, "generated_reports")
    os.makedirs(reports_dir, exist_ok=True)
    report_path = os.path.join(reports_dir, f"rank_report_{today_str}.md")

    lines = []
    lines.append(f"# 📊 데일리 키워드 순위 변동 보고서 ({today_str})")
    lines.append("")
    lines.append("스마트스토어/순위 대시보드 캡처 이미지를 분석하여 어제 대비 변동 내역을 정리한 일일 보고서입니다.")
    lines.append("")

    # 상승 키워드
    lines.append("## 📈 순위 상승 키워드")
    up_items = [i for i in report_items if i["status"] == "상승"]
    if up_items:
        for item in up_items:
            lines.append(f"- **{item['keyword']}**: {item['prev_rank']}위 ➡️ **{item['current_rank']}위** (🔺{item['change_val']}단계 상승)")
    else:
        lines.append("- *순위 상승한 키워드가 없습니다.*")
    lines.append("")

    # 신규 진입
    lines.append("## 🆕 신규 진입 키워드")
    new_items = [i for i in report_items if i["status"] == "신규"]
    if new_items:
        for item in new_items:
            rank_desc = f"**{item['current_rank']}위**" if item['current_rank'] != 999 else "순위권"
            lines.append(f"- **{item['keyword']}**: {rank_desc} (신규 진입! 🎉)")
    else:
        lines.append("- *새로 진입한 키워드가 없습니다.*")
    lines.append("")

    # 하락 및 이탈
    lines.append("## 📉 순위 하락 및 이탈 키워드")
    down_items = [i for i in report_items if i["status"] in ("하락", "이탈")]
    if down_items:
        for item in down_items:
            if item["status"] == "이탈":
                prev_desc = f"(기존 {item['prev_rank']}위)" if item['prev_rank'] else ""
                lines.append(f"- **{item['keyword']}**: {prev_desc} ➡️ **순위권 이탈** ⚠️")
            else:
                lines.append(f"- **{item['keyword']}**: {item['prev_rank']}위 ➡️ **{item['current_rank']}위** (🔻{item['change_val']}단계 하락)")
    else:
        lines.append("- *순위 하락하거나 이탈한 키워드가 없습니다.*")
    lines.append("")

    # 순위 유지
    lines.append("## ➖ 순위 유지 키워드")
    flat_items = [i for i in report_items if i["status"] == "유지"]
    if flat_items:
        for item in flat_items:
            lines.append(f"- **{item['keyword']}**: **{item['current_rank']}위** (순위 유지)")
    else:
        lines.append("- *순위 유지된 키워드가 없습니다.*")
    lines.append("")

    lines.append("---")
    lines.append(f"*보고서 생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

    report_content = "\n".join(lines)

    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"✅ 비교 보고서 생성 완료: {report_path}")
        print("\n" + "=" * 50)
        print(report_content)
        print("=" * 50)
    except Exception as e:
        print(f"❌ 보고서 저장 실패: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("💡 사용법: python rank_ocr_reporter.py [이미지파일경로]")
        sys.exit(1)
    
    img_path = sys.argv[1]
    generate_rank_report(img_path)
