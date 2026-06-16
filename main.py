"""
나눔랩 모바일 SEO 매니저 — Flet APK 빌드 엔트리포인트
합법적 순위 모니터링 + 키워드 분석 (인위적 트래픽 없음)
"""
import asyncio
import json
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

import flet as ft

from app_resources import load_products
from keyword_analyzer import analyze_keyword
from rank_tracker import get_all_product_rankings, get_history, test_naver_connection

DEFAULT_KEYWORDS = ["퍼마코트 자동차 코팅제", "퍼마코트", "셀프유리막코팅제", "듀라코트"]


def main(page: ft.Page):
    page.title = "나눔랩 모바일 SEO 매니저"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.scroll = ft.ScrollMode.ADAPTIVE
    page.padding = 20
    page.bgcolor = "#f8fafc"

    store_name, product_map = load_products()
    product_count = len(product_map)

    result_column = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO)
    analysis_column = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO)
    status_text = ft.Text("", size=12, color="#64748b")
    progress = ft.ProgressBar(visible=False)
    busy = {"on": False}

    result_card = ft.Card(
        visible=False,
        content=ft.Container(
            content=ft.Column([
                ft.Text("조회 결과", weight=ft.FontWeight.BOLD, size=16),
                ft.Divider(),
                result_column,
            ]),
            padding=16,
        ),
    )
    analysis_card = ft.Card(
        visible=False,
        content=ft.Container(
            content=ft.Column([
                ft.Text("키워드 분석", weight=ft.FontWeight.BOLD, size=16),
                ft.Divider(),
                analysis_column,
            ]),
            padding=16,
        ),
    )

    keyword_input = ft.TextField(
        label="조회할 키워드",
        hint_text="예: 퍼마코트 자동차 코팅제, 퍼마코트, 듀라코트",
        value="퍼마코트 자동차 코팅제",
        expand=True,
        border_radius=8,
    )

    def snack(msg, color=None):
        page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=color)
        page.snack_bar.open = True
        page.update()

    def set_busy(on, msg=""):
        busy["on"] = on
        progress.visible = on
        if msg:
            status_text.value = msg
        page.update()

    def show_rank_results(keyword, results, error):
        result_column.controls.clear()
        result_column.controls.append(
            ft.Text(f"🔍 '{keyword}' 검색 결과", weight=ft.FontWeight.BOLD)
        )
        result_column.controls.append(
            ft.Text(f"등록 상품 {product_count}개 중 매칭", size=12, color="#64748b")
        )
        result_column.controls.append(ft.Divider())

        if error:
            result_column.controls.append(ft.Text(f"오류: {error}", color="#dc2626"))
        elif not results:
            result_column.controls.append(
                ft.Text(
                    "1페이지에 나눔랩 등록 상품이 없습니다.\n"
                    "• 키워드를 바꿔 보세요 (예: 퍼마코트, 듀라코트)\n"
                    "• 상품명·태그에 키워드가 포함됐는지 확인하세요.",
                    color="#ea580c",
                )
            )
        else:
            for item in sorted(results, key=lambda x: x["rank"]):
                rank_color = "#16a34a" if item["rank"] <= 20 else "#2563eb"
                result_column.controls.append(
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.TRENDING_UP, color=rank_color),
                        title=ft.Text(item["name"], weight=ft.FontWeight.W_600),
                        subtitle=ft.Text(
                            f"ID {item['id']}  ·  {item['display']}",
                            size=13,
                        ),
                    )
                )
        result_card.visible = True
        analysis_card.visible = False

    async def on_search(e):
        if busy["on"]:
            return
        keyword = (keyword_input.value or "").strip()
        if not keyword:
            snack("키워드를 입력해주세요.")
            return

        set_busy(True, "네이버 쇼핑 검색 중…")
        result_card.visible = False
        page.update()

        results, error = await asyncio.to_thread(
            get_all_product_rankings, keyword, product_map
        )
        show_rank_results(keyword, results, error)
        set_busy(False, "완료" if not error else "조회 실패")

    async def on_analyze(e):
        if busy["on"]:
            return
        keyword = (keyword_input.value or "").strip()
        if not keyword:
            snack("키워드를 입력해주세요.")
            return

        set_busy(True, "키워드 분석 중…")
        analysis_card.visible = False
        page.update()

        data = await asyncio.to_thread(analyze_keyword, keyword)
        analysis_column.controls.clear()

        if not data.get("success"):
            analysis_column.controls.append(
                ft.Text(data.get("error", "분석 실패"), color="#dc2626")
            )
        else:
            score = data["opportunity_score"]
            score_color = "#16a34a" if score >= 70 else "#d97706"
            analysis_column.controls.extend([
                ft.Text(f"🔑 '{data['keyword']}'", weight=ft.FontWeight.BOLD),
                ft.Text(
                    f"기회 점수: {score}점",
                    color=score_color,
                    size=18,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(f"경쟁도: {data['competition']} ({data['recommendation']})"),
                ft.Text(f"1페이지 상품 수: {data['item_count_page1']}개"),
                ft.Text(
                    f"추정 검색 관심도: 약 {data['estimated_monthly_searches']:,} (추정치)"
                ),
            ])
            if data.get("related_keywords"):
                analysis_column.controls.append(
                    ft.Text("연관 키워드:", weight=ft.FontWeight.W_600)
                )
                for rk in data["related_keywords"][:5]:
                    analysis_column.controls.append(
                        ft.Text(f"  · {rk}", size=13, color="#64748b")
                    )
            for tip in data.get("tips", [])[:3]:
                analysis_column.controls.append(
                    ft.Text(f"💡 {tip}", size=12, color="#64748b")
                )

        analysis_card.visible = True
        result_card.visible = False
        set_busy(False, "분석 완료")

    async def on_batch(e):
        if busy["on"]:
            return
        set_busy(True, "전체 키워드 순위 리포트 생성 중…")
        result_column.controls.clear()
        result_column.controls.append(
            ft.Text("📋 배치 순위 리포트", weight=ft.FontWeight.BOLD)
        )
        result_column.controls.append(ft.Divider())
        result_card.visible = True
        page.update()

        for kw in DEFAULT_KEYWORDS:
            results, error = await asyncio.to_thread(
                get_all_product_rankings, kw, product_map
            )
            if error:
                result_column.controls.append(
                    ft.Text(f"• {kw}: 오류 — {error}", color="#dc2626", size=13)
                )
            elif not results:
                result_column.controls.append(
                    ft.Text(f"• {kw}: 1페이지 미노출", color="#ea580c", size=13)
                )
            else:
                best = min(results, key=lambda x: x["rank"])
                result_column.controls.append(
                    ft.Text(
                        f"• {kw}: 최고 {best['rank']}위 ({best['name']})",
                        size=13,
                    )
                )
            page.update()

        set_busy(False, "배치 리포트 완료")

    async def on_history(e):
        history = await asyncio.to_thread(get_history, 10)
        result_column.controls.clear()
        result_column.controls.append(ft.Text("📈 최근 순위 기록", weight=ft.FontWeight.BOLD))
        result_column.controls.append(ft.Divider())
        if not history:
            result_column.controls.append(
                ft.Text("저장된 기록이 없습니다.", color="#64748b")
            )
        else:
            for row in reversed(history[-10:]):
                result_column.controls.append(
                    ft.Text(
                        f"{row.get('날짜')} | {row.get('키워드')} | {row.get('상세', row.get('순위'))}",
                        size=12,
                    )
                )
        result_card.visible = True
        page.update()

    async def on_test_connection(e):
        set_busy(True, "네이버 연결 테스트 중…")
        ok, msg = await asyncio.to_thread(test_naver_connection)
        set_busy(False, msg)
        snack(msg, "#16a34a" if ok else "#dc2626")

    page.add(
        ft.Text("📊 나눔랩 상품 순위 진단기", size=22, weight=ft.FontWeight.BOLD),
        ft.Text(
            f"{store_name} · 등록 상품 {product_count}개 · 순위 모니터링 전용",
            size=13,
            color="#64748b",
        ),
        status_text,
        ft.Divider(),
        keyword_input,
        ft.Container(height=8),
        ft.Row(
            [
                ft.ElevatedButton(
                    "실시간 순위 진단",
                    icon=ft.Icons.SEARCH,
                    on_click=on_search,
                    expand=True,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=8),
                        bgcolor="#2563eb",
                        color="white",
                    ),
                ),
                ft.OutlinedButton(
                    "키워드 분석",
                    icon=ft.Icons.ANALYTICS,
                    on_click=on_analyze,
                    expand=True,
                ),
            ],
            spacing=8,
        ),
        ft.Row(
            [
                ft.OutlinedButton(
                    "배치 리포트",
                    icon=ft.Icons.LIST_ALT,
                    on_click=on_batch,
                    expand=True,
                ),
                ft.TextButton(
                    "연결 테스트",
                    icon=ft.Icons.WIFI,
                    on_click=on_test_connection,
                ),
            ],
        ),
        ft.TextButton("최근 기록", icon=ft.Icons.HISTORY, on_click=on_history),
        progress,
        ft.Container(height=12),
        result_card,
        analysis_card,
        ft.Container(height=16),
        ft.Text(
            "※ 네이버 쇼핑 모바일 검색 결과를 조회합니다 (조작·트래픽 자동화 없음).\n"
            "※ '퍼마코트 자동차 코팅제'처럼 실제 노출 키워드를 사용하세요.",
            size=11,
            color="#94a3b8",
        ),
    )


if __name__ == "__main__":
    ft.app(target=main)
