"""
seo_strategy_report.py
========================
나눔랩 상품 10위권 진입 전략 HTML 보고서 생성기

기능:
  - 현재 순위 데이터 + 경쟁도 + 키워드 기회 통합 분석
  - 상품별 10위권 진입 가능성 점수 산출
  - 실행 우선순위 자동 도출
  - seo_strategy_report.html 브라우저 보고서 생성

사용법:
    python seo_strategy_report.py
    python seo_strategy_report.py --open    # 생성 후 브라우저 자동 열기
"""

import sys
import os
import json
import re
import time
import argparse
from datetime import datetime
from urllib.parse import quote

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
OPPORTUNITY_REPORT = os.path.join(BASE_DIR, "keyword_opportunity_report.json")
OUTPUT_HTML = os.path.join(BASE_DIR, "seo_strategy_report.html")

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; SM-S928N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
)


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _shopping_url(keyword, start=1):
    return (
        f"https://m.search.naver.com/search.naver?"
        f"query={quote(keyword.strip())}&where=m_shop&start={start}"
    )


def _extract_pids(html):
    ordered = []
    seen = set()
    def add(pid):
        if pid and pid not in seen:
            seen.add(pid)
            ordered.append(pid)
    # 1. smartstore URL matches (support both / and escaped \u002F)
    for pid in re.findall(r'smartstore\.naver\.com(?:/|\\u002F)[^\s"\'\\/]+(?:/|\\u002F)products(?:/|\\u002F)(\d+)', html):
        add(pid)
    # 2. Generic /products/ or \u002Fproducts\u002F matches
    for pid in re.findall(r'(?:/|\\u002F)products(?:/|\\u002F)(\d+)', html):
        add(pid)
    # 3. JSON channelProductId matches
    for pid in re.findall(r'["\']channelProductId["\']?\s*:\s*["\']?(\d+)["\']?', html):
        add(pid)
    # 4. nv_mid / nvMid fallback
    for pid in re.findall(r'[?&]nv_mid=(\d+)', html):
        add(pid)
    for pid in re.findall(r'nvMid["\']?\s*:\s*["\']?(\d+)', html):
        add(pid)
    return ordered



def check_rank_fast(keyword, product_id, max_pages=5):
    """빠른 순위 조회 (최대 5페이지 ≒ 200위)"""
    headers = {"User-Agent": MOBILE_UA, "Accept-Language": "ko-KR,ko;q=0.9"}
    cumulative = 0
    for page in range(1, max_pages + 1):
        try:
            res = requests.get(
                _shopping_url(keyword, start=(page - 1) * 40 + 1),
                headers=headers, timeout=12
            )
            if res.status_code != 200:
                break
            pids = _extract_pids(res.text)
            if not pids:
                break
            for pid in pids:
                cumulative += 1
                if pid == str(product_id):
                    return cumulative
            time.sleep(0.3)
        except Exception:
            break
    return None


def measure_keyword_competition(keyword):
    """키워드 경쟁도 측정"""
    headers = {"User-Agent": MOBILE_UA, "Accept-Language": "ko-KR,ko;q=0.9"}
    try:
        res = requests.get(_shopping_url(keyword), headers=headers, timeout=12)
        if res.status_code != 200:
            return {"product_count": 0, "competition": "unknown", "opportunity_score": 0}
        pids = _extract_pids(res.text)
        count = len(pids)
        if count <= 10:
            score, level = 90, "낮음"
        elif count <= 20:
            score, level = 75, "보통"
        elif count <= 40:
            score, level = 55, "높음"
        else:
            score, level = 30, "매우 높음"
        return {"product_count": count, "competition": level, "opportunity_score": score}
    except Exception:
        return {"product_count": 0, "competition": "오류", "opportunity_score": 0}


def estimate_top10_probability(current_rank, competition_score, has_blog_content, review_count=0):
    """10위권 진입 가능성 점수 (0~100)"""
    base = 0

    # 현재 순위 기반
    if current_rank is None:
        base = 10  # 미노출 — 기초부터
    elif current_rank <= 10:
        base = 90
    elif current_rank <= 30:
        base = 70
    elif current_rank <= 100:
        base = 45
    elif current_rank <= 300:
        base = 25
    else:
        base = 15

    # 키워드 경쟁도 보정
    comp_bonus = (competition_score - 50) * 0.4 if competition_score else 0

    # 블로그 콘텐츠 유무
    content_bonus = 10 if has_blog_content else 0

    # 리뷰 수
    review_bonus = min(10, review_count * 0.5)

    score = min(99, max(1, base + comp_bonus + content_bonus + review_bonus))
    return round(score)


def calculate_expected_weeks(current_rank, competition):
    """10위권 도달 예상 기간(주)"""
    if current_rank is None:
        base_weeks = 12
    elif current_rank <= 20:
        base_weeks = 2
    elif current_rank <= 50:
        base_weeks = 4
    elif current_rank <= 100:
        base_weeks = 8
    elif current_rank <= 300:
        base_weeks = 16
    else:
        base_weeks = 24

    # 경쟁도 보정
    comp_factor = {"낮음": 0.6, "보통": 1.0, "높음": 1.5, "매우 높음": 2.5}.get(competition, 1.0)
    return round(base_weeks * comp_factor)


def run_analysis():
    """전체 분석 실행 및 데이터 수집"""
    config = load_config()
    products = config.get("products", [])
    keywords_config = config.get("keywords", [])

    # 상품별 키워드 매핑
    product_keywords = {}
    for kw_entry in keywords_config:
        pid = str(kw_entry.get("product_id", ""))
        if pid not in product_keywords:
            product_keywords[pid] = []
        product_keywords[pid].append(kw_entry.get("keyword", ""))

    # keyword_opportunity_report.json 로드 (있으면)
    opportunity_data = {}
    if os.path.exists(OPPORTUNITY_REPORT):
        try:
            with open(OPPORTUNITY_REPORT, "r", encoding="utf-8") as f:
                opp_report = json.load(f)
            for pid, data in opp_report.get("results", {}).items():
                opportunity_data[pid] = data.get("top_keywords", [])
        except Exception:
            pass

    # 블로그 초안 존재 여부 확인
    draft_dir = os.path.join(BASE_DIR, "blog_drafts")

    def has_draft(product_name):
        safe = re.sub(r'[\\/:"*?<>|]', "_", product_name)[:30]
        path = os.path.join(draft_dir, safe)
        return os.path.exists(path) and bool(os.listdir(path))

    print(f"\n{'='*60}")
    print(f"📊 나눔랩 SEO 전략 분석 시작")
    print(f"{'='*60}")

    product_reports = []
    for product in products:
        pid = str(product.get("id", ""))
        name = product.get("name", pid)
        url = product.get("url", "")
        kws = product_keywords.get(pid, [])

        print(f"\n[{name}] 분석 중...")

        keyword_analyses = []
        best_rank = None
        best_keyword = None

        for kw in kws[:3]:  # 상품당 최대 3개 키워드 조회
            print(f"  '{kw}' 순위 조회 중...", end=" ", flush=True)
            rank = check_rank_fast(kw, pid, max_pages=5)
            comp = measure_keyword_competition(kw)

            rank_display = f"{rank}위" if rank else "200위 밖"
            print(f"→ {rank_display} | 경쟁 {comp['competition']}")

            if rank and (best_rank is None or rank < best_rank):
                best_rank = rank
                best_keyword = kw

            keyword_analyses.append({
                "keyword": kw,
                "rank": rank,
                "rank_display": rank_display,
                **comp,
            })
            time.sleep(0.5)

        # 기회 키워드 (opportunity_report 있으면 활용)
        opp_keywords = opportunity_data.get(pid, [])[:5]

        has_blog = has_draft(name)
        best_comp = keyword_analyses[0] if keyword_analyses else {}
        prob = estimate_top10_probability(
            best_rank,
            best_comp.get("opportunity_score", 30),
            has_blog,
        )
        weeks = calculate_expected_weeks(
            best_rank,
            best_comp.get("competition", "높음"),
        )

        product_reports.append({
            "product_id": pid,
            "product_name": name,
            "product_url": url,
            "best_rank": best_rank,
            "best_keyword": best_keyword,
            "keyword_analyses": keyword_analyses,
            "opportunity_keywords": opp_keywords,
            "has_blog_content": has_blog,
            "top10_probability": prob,
            "expected_weeks": weeks,
        })

    # 우선순위 정렬: 확률 높고 예상 기간 짧은 순
    product_reports.sort(
        key=lambda x: (-x["top10_probability"], x["expected_weeks"])
    )

    return product_reports


def generate_html_report(product_reports):
    """전략 HTML 보고서 생성"""
    now = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
    total_products = len(product_reports)

    # 통계
    ranked_in_10 = sum(1 for p in product_reports if p["best_rank"] and p["best_rank"] <= 10)
    ranked_in_100 = sum(1 for p in product_reports if p["best_rank"] and p["best_rank"] <= 100)
    unranked = sum(1 for p in product_reports if not p["best_rank"])

    def rank_badge(rank):
        if rank is None:
            return '<span class="badge badge-danger">미노출</span>'
        elif rank <= 10:
            return f'<span class="badge badge-success">{rank}위 🏆</span>'
        elif rank <= 30:
            return f'<span class="badge badge-warning">{rank}위</span>'
        else:
            return f'<span class="badge badge-danger">{rank}위</span>'

    def prob_bar(prob):
        color = "#2db400" if prob >= 60 else "#ff9800" if prob >= 35 else "#f44336"
        return (
            f'<div class="prob-bar-wrap">'
            f'<div class="prob-bar" style="width:{prob}%;background:{color};"></div>'
            f'<span class="prob-label">{prob}%</span>'
            f'</div>'
        )

    def priority_label(i):
        labels = ["🥇 최우선", "🥈 2순위", "🥉 3순위"]
        return labels[i] if i < 3 else f"#{i+1}"

    def action_steps(p):
        steps = []
        if not p["has_blog_content"]:
            steps.append("📝 블로그 초안 생성 필요 (seo_blog_campaign.py 실행)")
        if not p["opportunity_keywords"]:
            steps.append("🔍 틈새 키워드 발굴 필요 (keyword_opportunity_finder.py 실행)")
        if p["best_rank"] is None:
            steps.append("🚀 신규 키워드 공략 — 경쟁 낮은 롱테일 키워드 우선 집중")
        elif p["best_rank"] > 50:
            steps.append("📈 현재 키워드 트래픽 강화 + 블로그 외부 유입 확대")
        elif p["best_rank"] > 10:
            steps.append("⚡ 클릭 수 집중 세션으로 10위권 진입 가속")
        else:
            steps.append("✅ 현재 순위 유지 + 리뷰 확보 전략 병행")
        steps.append("⭐ 구매 리뷰 유도 캠페인 (순위 유지에 핵심)")
        return steps

    # 상품 카드 HTML 생성
    product_cards = ""
    for i, p in enumerate(product_reports):
        kw_rows = ""
        for kw in p["keyword_analyses"]:
            rank_txt = f"{kw['rank']}위" if kw["rank"] else "200위 밖"
            comp_cls = {
                "낮음": "comp-low", "보통": "comp-mid",
                "높음": "comp-high", "매우 높음": "comp-very-high",
            }.get(kw.get("competition", ""), "comp-high")
            kw_rows += f"""
            <tr>
              <td>{kw['keyword']}</td>
              <td>{rank_txt}</td>
              <td><span class="comp-badge {comp_cls}">{kw.get('competition','?')}</span></td>
              <td>{kw.get('opportunity_score', 0)}점</td>
            </tr>"""

        opp_kws_html = ""
        for opp in p["opportunity_keywords"]:
            kw_str = opp.get("keyword", opp) if isinstance(opp, dict) else opp
            opp_kws_html += f'<span class="opp-keyword">{kw_str}</span>'

        steps_html = "".join(
            f'<li>{step}</li>' for step in action_steps(p)
        )

        weeks_txt = f"약 {p['expected_weeks']}주"
        blog_status = "✅ 초안 있음" if p["has_blog_content"] else "❌ 없음"

        product_cards += f"""
        <div class="product-card {'priority-card' if i < 3 else ''}">
          <div class="card-header">
            <div class="card-title-row">
              <span class="priority-label">{priority_label(i)}</span>
              <h3 class="product-title">{p['product_name']}</h3>
              {rank_badge(p['best_rank'])}
            </div>
            <div class="quick-stats">
              <div class="stat">
                <span class="stat-label">10위권 가능성</span>
                {prob_bar(p['top10_probability'])}
              </div>
              <div class="stat">
                <span class="stat-label">예상 기간</span>
                <span class="stat-value">{weeks_txt}</span>
              </div>
              <div class="stat">
                <span class="stat-label">블로그 콘텐츠</span>
                <span class="stat-value">{blog_status}</span>
              </div>
            </div>
          </div>

          <div class="card-body">
            <div class="section-label">📊 키워드별 현황</div>
            <table class="kw-table">
              <thead>
                <tr><th>키워드</th><th>현재 순위</th><th>경쟁도</th><th>기회 점수</th></tr>
              </thead>
              <tbody>{kw_rows}</tbody>
            </table>

            {'<div class="section-label">🎯 발굴된 틈새 키워드</div><div class="opp-keywords">' + opp_kws_html + '</div>' if opp_kws_html else ''}

            <div class="section-label">✅ 실행 액션</div>
            <ul class="action-list">{steps_html}</ul>

            <a href="{p['product_url']}" target="_blank" class="product-link-btn">
              스토어 바로가기 →
            </a>
          </div>
        </div>"""

    # 전체 HTML
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>나눔랩 SEO 전략 보고서 — {now}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');

  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: 'Noto Sans KR', -apple-system, sans-serif;
    background: #0f1117;
    color: #e2e8f0;
    min-height: 100vh;
  }}

  /* ── 헤더 ── */
  .report-header {{
    background: linear-gradient(135deg, #0d2d0d 0%, #1a3d1a 50%, #0d2d0d 100%);
    border-bottom: 1px solid #2db40030;
    padding: 40px 24px 32px;
    text-align: center;
  }}
  .report-header h1 {{
    font-size: 1.8rem; font-weight: 700;
    color: #fff; margin-bottom: 8px;
  }}
  .report-header h1 span {{ color: #2db400; }}
  .report-header .subtitle {{ color: #94a3b8; font-size: 0.95rem; }}
  .report-date {{ font-size: 0.82rem; color: #64748b; margin-top: 6px; }}

  /* ── 요약 통계 ── */
  .summary-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 16px;
    max-width: 900px;
    margin: 32px auto;
    padding: 0 24px;
  }}
  .summary-card {{
    background: #1e2130;
    border: 1px solid #2d3452;
    border-radius: 12px;
    padding: 20px 16px;
    text-align: center;
  }}
  .summary-card .s-num {{
    font-size: 2.2rem; font-weight: 700;
    line-height: 1; margin-bottom: 6px;
  }}
  .summary-card .s-label {{ font-size: 0.82rem; color: #94a3b8; }}
  .s-green {{ color: #2db400; }}
  .s-yellow {{ color: #f59e0b; }}
  .s-red {{ color: #ef4444; }}
  .s-blue {{ color: #3b82f6; }}

  /* ── 전략 배너 ── */
  .strategy-banner {{
    max-width: 900px; margin: 0 auto 32px;
    padding: 0 24px;
  }}
  .strategy-box {{
    background: linear-gradient(135deg, #1a2a1a, #1e2e1e);
    border: 1px solid #2db40050;
    border-radius: 14px;
    padding: 24px 28px;
  }}
  .strategy-box h2 {{
    color: #2db400; font-size: 1.1rem;
    margin-bottom: 16px;
  }}
  .strategy-steps {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 12px;
  }}
  .strategy-step {{
    background: #0f1a0f;
    border-radius: 10px;
    padding: 14px 16px;
    border-left: 3px solid #2db400;
  }}
  .strategy-step .step-num {{
    font-size: 0.75rem; color: #2db400;
    font-weight: 700; margin-bottom: 4px;
  }}
  .strategy-step .step-text {{
    font-size: 0.9rem; color: #cbd5e1; line-height: 1.5;
  }}

  /* ── 상품 카드 ── */
  .products-container {{
    max-width: 900px; margin: 0 auto;
    padding: 0 24px 60px;
    display: flex;
    flex-direction: column;
    gap: 20px;
  }}
  .product-card {{
    background: #1e2130;
    border: 1px solid #2d3452;
    border-radius: 16px;
    overflow: hidden;
    transition: transform 0.2s, box-shadow 0.2s;
  }}
  .product-card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  }}
  .priority-card {{
    border-color: #2db400;
    box-shadow: 0 0 0 1px #2db40030;
  }}
  .card-header {{
    background: linear-gradient(135deg, #161b2e, #1a2035);
    padding: 20px 24px 16px;
    border-bottom: 1px solid #2d3452;
  }}
  .card-title-row {{
    display: flex; align-items: center; gap: 12px;
    flex-wrap: wrap; margin-bottom: 16px;
  }}
  .priority-label {{
    font-size: 0.8rem; font-weight: 700;
    color: #2db400; white-space: nowrap;
  }}
  .product-title {{
    font-size: 1.1rem; font-weight: 700;
    color: #f1f5f9; flex: 1;
  }}

  /* 배지 */
  .badge {{
    padding: 4px 12px; border-radius: 20px;
    font-size: 0.82rem; font-weight: 700;
  }}
  .badge-success {{ background: #14532d; color: #4ade80; }}
  .badge-warning {{ background: #451a03; color: #fb923c; }}
  .badge-danger {{ background: #1c0505; color: #f87171; }}

  /* 빠른 통계 */
  .quick-stats {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px;
  }}
  .stat {{ }}
  .stat-label {{
    font-size: 0.75rem; color: #64748b;
    display: block; margin-bottom: 4px;
  }}
  .stat-value {{ font-size: 0.9rem; color: #e2e8f0; font-weight: 500; }}

  /* 가능성 바 */
  .prob-bar-wrap {{
    background: #0f1117; border-radius: 6px;
    height: 20px; position: relative; overflow: hidden;
  }}
  .prob-bar {{
    height: 100%; border-radius: 6px;
    transition: width 0.8s ease;
  }}
  .prob-label {{
    position: absolute; right: 8px; top: 50%;
    transform: translateY(-50%);
    font-size: 0.78rem; font-weight: 700; color: #fff;
  }}

  /* 카드 본문 */
  .card-body {{ padding: 20px 24px; }}
  .section-label {{
    font-size: 0.82rem; font-weight: 700;
    color: #94a3b8; margin: 16px 0 10px;
    text-transform: uppercase; letter-spacing: 0.5px;
  }}
  .section-label:first-child {{ margin-top: 0; }}

  /* 키워드 테이블 */
  .kw-table {{
    width: 100%; border-collapse: collapse;
    font-size: 0.88rem;
  }}
  .kw-table th {{
    background: #161b2e; color: #64748b;
    padding: 8px 12px; text-align: left;
    font-weight: 500; font-size: 0.78rem;
  }}
  .kw-table td {{
    padding: 8px 12px; border-bottom: 1px solid #1e2130;
    color: #cbd5e1;
  }}
  .kw-table tr:last-child td {{ border-bottom: none; }}

  /* 경쟁도 배지 */
  .comp-badge {{
    padding: 2px 8px; border-radius: 4px;
    font-size: 0.78rem; font-weight: 600;
  }}
  .comp-low {{ background: #14532d; color: #4ade80; }}
  .comp-mid {{ background: #451a03; color: #fb923c; }}
  .comp-high {{ background: #3b1515; color: #f87171; }}
  .comp-very-high {{ background: #2d0a0a; color: #ef4444; }}

  /* 기회 키워드 */
  .opp-keywords {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 4px; }}
  .opp-keyword {{
    background: #0f2218; border: 1px solid #2db40040;
    color: #4ade80; padding: 4px 12px;
    border-radius: 20px; font-size: 0.82rem;
  }}

  /* 액션 리스트 */
  .action-list {{
    list-style: none;
    display: flex; flex-direction: column; gap: 8px;
  }}
  .action-list li {{
    background: #0f1117; border-radius: 8px;
    padding: 10px 14px; font-size: 0.88rem;
    color: #cbd5e1; border-left: 3px solid #2db40060;
  }}

  /* 버튼 */
  .product-link-btn {{
    display: inline-block; margin-top: 16px;
    background: linear-gradient(135deg, #2db400, #00a060);
    color: #fff; padding: 10px 24px;
    border-radius: 8px; text-decoration: none;
    font-size: 0.88rem; font-weight: 700;
    transition: opacity 0.2s;
  }}
  .product-link-btn:hover {{ opacity: 0.85; }}

  /* 푸터 */
  .report-footer {{
    text-align: center; padding: 32px;
    color: #334155; font-size: 0.82rem;
    border-top: 1px solid #1e2130;
  }}

  /* 섹션 타이틀 */
  .section-title {{
    max-width: 900px; margin: 32px auto 16px;
    padding: 0 24px;
    font-size: 1rem; font-weight: 700;
    color: #94a3b8; letter-spacing: 0.5px;
    text-transform: uppercase;
  }}

  @media (max-width: 600px) {{
    .quick-stats {{ grid-template-columns: 1fr 1fr; }}
    .strategy-steps {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<!-- 헤더 -->
<header class="report-header">
  <h1>나눔랩 <span>SEO 전략 보고서</span></h1>
  <p class="subtitle">10위권 진입 로드맵 — 상품별 실행 우선순위</p>
  <p class="report-date">생성: {now} | 네이버 쇼핑 모바일 기준</p>
</header>

<!-- 요약 통계 -->
<div class="summary-grid">
  <div class="summary-card">
    <div class="s-num s-green">{ranked_in_10}</div>
    <div class="s-label">10위권 상품</div>
  </div>
  <div class="summary-card">
    <div class="s-num s-yellow">{ranked_in_100}</div>
    <div class="s-label">100위권 상품</div>
  </div>
  <div class="summary-card">
    <div class="s-num s-red">{unranked}</div>
    <div class="s-label">미노출 상품</div>
  </div>
  <div class="summary-card">
    <div class="s-num s-blue">{total_products}</div>
    <div class="s-label">전체 상품</div>
  </div>
</div>

<!-- 전략 개요 -->
<div class="strategy-banner">
  <div class="strategy-box">
    <h2>🎯 10위권 진입 3단계 전략</h2>
    <div class="strategy-steps">
      <div class="strategy-step">
        <div class="step-num">STEP 1 — 즉시 실행</div>
        <div class="step-text">
          경쟁 낮은 롱테일 키워드 발굴<br>
          <code style="font-size:0.8rem;color:#2db400;">keyword_opportunity_finder.py --apply</code>
        </div>
      </div>
      <div class="strategy-step">
        <div class="step-num">STEP 2 — 주 3회 실행</div>
        <div class="step-text">
          상품별 타겟 블로그 초안 생성 후<br>
          네이버 블로그 / 티스토리 발행
        </div>
      </div>
      <div class="strategy-step">
        <div class="step-num">STEP 3 — 매일 모니터링</div>
        <div class="step-text">
          순위 추적 + 클릭 시그널 강화<br>
          리뷰 유도 캠페인 병행
        </div>
      </div>
    </div>
  </div>
</div>

<!-- 상품별 분석 -->
<div class="section-title">상품별 전략 우선순위 (가능성 높은 순)</div>
<div class="products-container">
{product_cards}
</div>

<footer class="report-footer">
  나눔랩 SEO 전략 보고서 | 자동 생성 {now}<br>
  데이터 기준: 네이버 쇼핑 모바일 검색 실시간 조회
</footer>

</body>
</html>"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ HTML 보고서 생성 완료: {OUTPUT_HTML}")
    return OUTPUT_HTML


def main():
    parser = argparse.ArgumentParser(description="나눔랩 SEO 전략 보고서 생성")
    parser.add_argument("--open", action="store_true", help="생성 후 브라우저 자동 오픈")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("📊 나눔랩 SEO 전략 보고서 생성기")
    print(f"{'='*60}")

    product_reports = run_analysis()
    html_path = generate_html_report(product_reports)

    if args.open or True:  # 항상 자동 오픈
        import webbrowser
        webbrowser.open(f"file:///{html_path.replace(chr(92), '/')}")
        print("🌐 브라우저에서 보고서를 엽니다...")


if __name__ == "__main__":
    main()
