"""나눔랩 쇼핑 SEO 매니저 — Flet 모바일 앱 (APK 빌드 가능)"""
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

import flet as ft

from keyword_analyzer import analyze_keyword, load_config, suggest_keywords_for_product
from rank_tracker import build_completion_report, check_product_rank, get_history, track_all_keywords
from seo_content_builder import generate_content, list_workflows, save_content


def main(page: ft.Page):
    page.title = "나눔랩 SEO 매니저"
    page.theme_mode = ft.ThemeMode.DARK
    page.scroll = ft.ScrollMode.ADAPTIVE
    page.padding = 16
    page.bgcolor = "#0f172a"

    config = load_config()
    products = config.get("products", [])

    result_column = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO)
    rank_column = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO)
    content_output = ft.TextField(
        multiline=True,
        min_lines=12,
        max_lines=20,
        read_only=True,
        border_color="#334155",
        bgcolor="#1e293b",
        color="#e2e8f0",
        expand=True,
    )

    product_options = [
        ft.dropdown.Option(key=p["id"], text=f"{p.get('name', p['id'])} ({p['id']})")
        for p in products
    ] or [ft.dropdown.Option(key="", text="config.json에 상품을 등록하세요")]

    product_dd = ft.Dropdown(
        label="분석할 상품",
        options=product_options,
        value=products[0]["id"] if products else None,
        border_color="#3b82f6",
        expand=True,
    )
    keyword_field = ft.TextField(
        label="타겟 키워드",
        hint_text="예: 셀프 유리막 코팅제",
        border_color="#3b82f6",
        expand=True,
    )
    workflow_dd = ft.Dropdown(
        label="콘텐츠 워크플로우",
        options=[ft.dropdown.Option(key=w["id"], text=w["label"]) for w in list_workflows()],
        value="product_detail",
        border_color="#3b82f6",
    )

    loading = ft.ProgressRing(visible=False, width=28, height=28)

    def get_selected_product():
        pid = product_dd.value
        for p in products:
            if str(p.get("id")) == str(pid):
                return p
        return products[0] if products else {"id": "", "name": "퍼마코트"}

    def show_loading(show):
        loading.visible = show
        page.update()

    def on_analyze(e):
        result_column.controls.clear()
        kw = (keyword_field.value or "").strip()
        if not kw:
            result_column.controls.append(ft.Text("키워드를 입력하세요.", color="#ef4444"))
            page.update()
            return

        show_loading(True)
        product = get_selected_product()
        try:
            data = analyze_keyword(kw, product_id=product.get("id"))
        except Exception as ex:
            result_column.controls.append(ft.Text(f"오류: {ex}", color="#ef4444"))
            show_loading(False)
            return

        show_loading(False)
        if not data.get("success"):
            result_column.controls.append(ft.Text(data.get("error", "실패"), color="#ef4444"))
            page.update()
            return

        score_color = "#10b981" if data["opportunity_score"] >= 70 else "#f59e0b"
        result_column.controls.extend([
            ft.Text(f"🔍 '{data['keyword']}' 분석 결과", weight=ft.FontWeight.BOLD, size=16),
            ft.Text(f"• 기회 점수: {data['opportunity_score']}점", color=score_color),
            ft.Text(f"• 경쟁도: {data['competition']} ({data['recommendation']})"),
            ft.Text(f"• 1페이지 상품 수: {data['item_count_page1']}개"),
            ft.Text(f"• 추정 월 검색 관심도: 약 {data['estimated_monthly_searches']:,} (추정치)"),
        ])
        if data.get("rank_info"):
            ri = data["rank_info"]
            result_column.controls.append(
                ft.Text(f"• 현재 노출: {ri['display']} ({ri['rank_text']})", color="#60a5fa")
            )
        if data.get("related_keywords"):
            result_column.controls.append(ft.Text("• 연관 키워드:", weight=ft.FontWeight.W_600))
            for rk in data["related_keywords"][:5]:
                result_column.controls.append(ft.Text(f"  - {rk}", size=12, color="#94a3b8"))
        for tip in data.get("tips", []):
            result_column.controls.append(ft.Text(f"💡 {tip}", size=12, color="#94a3b8"))
        page.update()

    def on_suggest(e):
        result_column.controls.clear()
        product = get_selected_product()
        show_loading(True)
        try:
            suggestions = suggest_keywords_for_product(product.get("name", ""))
        except Exception as ex:
            result_column.controls.append(ft.Text(f"오류: {ex}", color="#ef4444"))
            show_loading(False)
            return
        show_loading(False)
        result_column.controls.append(ft.Text("🏆 추천 키워드 TOP", weight=ft.FontWeight.BOLD, size=16))
        for s in suggestions:
            result_column.controls.append(
                ft.Text(
                    f"• {s['keyword']} — {s['opportunity_score']}점 ({s['competition']})",
                    size=13,
                )
            )
        page.update()

    def on_track_rank(e):
        rank_column.controls.clear()
        kw = (keyword_field.value or "").strip()
        product = get_selected_product()
        if not kw:
            rank_column.controls.append(ft.Text("키워드를 입력하세요.", color="#ef4444"))
            page.update()
            return
        show_loading(True)
        try:
            rank = check_product_rank(kw, product.get("id"))
        except Exception as ex:
            rank_column.controls.append(ft.Text(f"오류: {ex}", color="#ef4444"))
            show_loading(False)
            return
        show_loading(False)
        display = f"{rank}위" if rank and rank < 100 else "100위 밖"
        rank_column.controls.extend([
            ft.Text("📊 순위 조회 결과", weight=ft.FontWeight.BOLD, size=16),
            ft.Text(f"상품: {product.get('name')} ({product.get('id')})"),
            ft.Text(f"키워드: {kw}"),
            ft.Text(f"노출 순위: {display}", size=20, color="#60a5fa", weight=ft.FontWeight.BOLD),
        ])
        page.update()

    def on_track_all(e):
        rank_column.controls.clear()
        show_loading(True)
        try:
            results = track_all_keywords()
            report = build_completion_report(results)
        except Exception as ex:
            rank_column.controls.append(ft.Text(f"오류: {ex}", color="#ef4444"))
            show_loading(False)
            return
        show_loading(False)
        rank_column.controls.append(ft.Text(report["summary"], weight=ft.FontWeight.BOLD))
        for item in report.get("items", []):
            if item.get("status") == "실패":
                rank_column.controls.append(ft.Text(f"✗ {item['keyword']}: 실패", color="#ef4444"))
            else:
                rank_column.controls.append(
                    ft.Text(f"• {item['keyword']}: {item['prev_text']} → {item['rank_text']} ({item['status']})")
                )
        page.update()

    def on_generate_content(e):
        kw = (keyword_field.value or "").strip()
        product = get_selected_product()
        wf = workflow_dd.value or "product_detail"
        if not kw:
            content_output.value = "키워드를 입력하세요."
            page.update()
            return
        show_loading(True)
        try:
            result = generate_content(wf, kw, product.get("name"), config.get("store_name"))
            path = save_content(result, product.get("id"))
        except Exception as ex:
            content_output.value = f"생성 실패: {ex}"
            show_loading(False)
            page.update()
            return
        show_loading(False)
        c = result.get("content", {})
        lines = [f"[{result.get('workflow_label')}] {result.get('generated_at')}", ""]
        if isinstance(c, dict):
            for k, v in c.items():
                if isinstance(v, dict):
                    lines.append(f"## {k}")
                    for sk, sv in v.items():
                        lines.append(f"### {sk}\n{sv}\n")
                elif isinstance(v, list):
                    lines.append(f"## {k}")
                    for item in v:
                        lines.append(str(item))
                else:
                    lines.append(f"{k}: {v}")
        content_output.value = "\n".join(lines) + f"\n\n저장: {path}"
        page.update()

    def on_show_history(e):
        rank_column.controls.clear()
        history = get_history(limit=15)
        if not history:
            rank_column.controls.append(ft.Text("기록이 없습니다."))
        else:
            rank_column.controls.append(ft.Text("📈 최근 순위 기록", weight=ft.FontWeight.BOLD))
            for row in reversed(history[-15:]):
                rank_column.controls.append(
                    ft.Text(
                        f"{row.get('날짜')} | {row.get('키워드')} | {row.get('상세', row.get('순위'))}",
                        size=12,
                    )
                )
        page.update()

    tab_keyword = ft.Column(
        [
            ft.Text("키워드 분석", size=18, weight=ft.FontWeight.BOLD),
            ft.Text("검색량·경쟁도 추정 및 상품 노출 순위 진단", size=12, color="#94a3b8"),
            product_dd,
            keyword_field,
            ft.Row([
                ft.ElevatedButton("키워드 분석", on_click=on_analyze, bgcolor="#3b82f6", color="white"),
                ft.OutlinedButton("추천 키워드", on_click=on_suggest),
            ], spacing=8),
            ft.Divider(color="#334155"),
            result_column,
        ],
        spacing=12,
        expand=True,
    )

    tab_rank = ft.Column(
        [
            ft.Text("순위 모니터링", size=18, weight=ft.FontWeight.BOLD),
            ft.Text("네이버 쇼핑 검색 결과에서 내 상품 위치 추적", size=12, color="#94a3b8"),
            ft.Row([
                ft.ElevatedButton("이 키워드 순위 조회", on_click=on_track_rank, bgcolor="#10b981", color="white"),
                ft.OutlinedButton("전체 키워드 추적", on_click=on_track_all),
            ], spacing=8),
            ft.OutlinedButton("기록 보기", on_click=on_show_history),
            ft.Divider(color="#334155"),
            rank_column,
        ],
        spacing=12,
        expand=True,
    )

    tab_content = ft.Column(
        [
            ft.Text("SEO 콘텐츠 빌더", size=18, weight=ft.FontWeight.BOLD),
            ft.Text("ABCD 구조 상세페이지·블로그·메타 태그 초안 생성", size=12, color="#94a3b8"),
            workflow_dd,
            ft.ElevatedButton(
                "콘텐츠 생성",
                on_click=on_generate_content,
                bgcolor="#f59e0b",
                color="white",
            ),
            content_output,
        ],
        spacing=12,
        expand=True,
    )

    page.add(
        ft.Row([
            ft.Icon(ft.Icons.STORE, color="#60a5fa"),
            ft.Text("나눔랩 쇼핑 SEO 매니저", size=20, weight=ft.FontWeight.BOLD),
            loading,
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Text("합법 SEO · 순위 모니터링 · 콘텐츠 최적화", size=12, color="#94a3b8"),
        ft.Tabs(
            selected_index=0,
            animation_duration=200,
            tabs=[
                ft.Tab(text="키워드", content=ft.Container(content=tab_keyword, padding=8)),
                ft.Tab(text="순위", content=ft.Container(content=tab_rank, padding=8)),
                ft.Tab(text="콘텐츠", content=ft.Container(content=tab_content, padding=8)),
            ],
            expand=True,
        ),
    )


if __name__ == "__main__":
    ft.app(target=main)
