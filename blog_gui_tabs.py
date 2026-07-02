# -*- coding: utf-8 -*-
"""GUI 탭 구성: 자동화, 지침, 서이추, 티스토리, 설정. 각 setup_*_tab(app) 함수."""

import tkinter as tk
from tkinter import ttk, scrolledtext

import os
import config as cfg
import sys
from blog_constants import POST_TYPES_GUI, PRODUCT_KEYWORDS, PRODUCT_POST_TYPE
from doc_guidelines import DISTRIBUTION_GUIDELINES  # 배포(blog auto.exe) 시 지침란 기본값 = 사용 설명서


def _default_master_for_gui():
    try:
        from drawer.wiki import load_default_master_guidelines

        return load_default_master_guidelines()
    except Exception:
        from drawer.registry import get_content_gen

        return get_content_gen().DEFAULT_MASTER_GUIDELINES


def _show_vercel_ui() -> bool:
    """독립 실행 모드에서는 Vercel 패널 숨김 (BLOG_VERCEL_UI=1 로 표시)."""
    if os.environ.get("BLOG_VERCEL_UI", "0").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return os.environ.get("BLOG_STANDALONE", "1").strip().lower() not in ("1", "true", "yes", "on")


def setup_automation_tab(app):
    app.auto_frame = tk.Frame(app.body, bg=app.color_bg)

    input_card = tk.Frame(app.auto_frame, bg=app.color_card, bd=0, highlightthickness=1, highlightbackground=app.color_border, padx=25, pady=25)
    input_card.pack(fill="x")

    tk.Label(input_card, text="포스팅 키워드 (쉼표 구분)", font=app.font_bold, bg=app.color_card, fg=app.color_text_dark).grid(row=0, column=0, sticky="w")
    app.entry_keywords = app.create_modern_entry(input_card, "ex) 듀라코트 리빙코트, 욕실코팅제", 50)
    app.entry_keywords.grid(row=1, column=0, columnspan=4, pady=(5, 5), sticky="ew")
    # 배포용 autoblog.exe에서는 기본 키워드 세트를 채우고,
    # 공개용 autoblog2.exe(blog_auto_public)는 비워둬 다른 PC에서 자유롭게 입력하도록 함.
    if not getattr(app, "is_public_mode", False):
        app.entry_keywords.insert(0, "듀라코트 리빙코트, 욕실코팅제, 타일코팅제, 식탁코팅, 원목코팅, 수전코팅, 욕실유리코팅, 싱크대코팅, 가전코팅, 가스레인지, 인덕션코팅, 전자레인지, 곰팡이억제, 유리코팅, 거실장코팅, 고전가구코팅, 색감복원, 발수복원, 피막형성, 유리막코팅제")

    tk.Label(input_card, text="글 유형", font=app.font_bold, bg=app.color_card, fg=app.color_text_dark).grid(row=2, column=0, sticky="w", pady=(10, 0))
    post_types = list(POST_TYPES_GUI)
    app.post_type_var = tk.StringVar(value="제품 홍보")
    app.post_type_combo = ttk.Combobox(input_card, textvariable=app.post_type_var, values=post_types, state="readonly", width=22, font=app.font_main)
    app.post_type_combo.grid(row=3, column=0, columnspan=2, pady=(5, 15), sticky="w")

    target_frame = tk.Frame(input_card, bg=app.color_card)
    target_frame.grid(row=4, column=0, columnspan=4, sticky="w")

    tk.Label(target_frame, text="발행 대상:", font=app.font_bold, bg=app.color_card, fg=app.color_text_dark).pack(side="left")
    app.use_naver1_var = tk.BooleanVar(value=True)
    tk.Checkbutton(target_frame, text="네이버1(hymini1)", variable=app.use_naver1_var,
                  bg=app.color_card, activebackground=app.color_card,
                  fg=app.color_text_dark, selectcolor=app.color_bg).pack(side="left", padx=10)
    app.use_naver2_var = tk.BooleanVar(value=True)
    tk.Checkbutton(target_frame, text="네이버2(hymini11)", variable=app.use_naver2_var,
                  bg=app.color_card, activebackground=app.color_card,
                  fg=app.color_text_dark, selectcolor=app.color_bg).pack(side="left", padx=10)
    app.use_tistory_var = tk.BooleanVar(value=True)
    tk.Checkbutton(target_frame, text="티스토리", variable=app.use_tistory_var,
                  bg=app.color_card, activebackground=app.color_card,
                  fg=app.color_text_dark, selectcolor=app.color_bg).pack(side="left")
    app.use_google_var = tk.BooleanVar(value=False)
    tk.Checkbutton(target_frame, text="구글(Blogger)", variable=app.use_google_var,
                  bg=app.color_card, activebackground=app.color_card,
                  fg=app.color_text_dark, selectcolor=app.color_bg).pack(side="left", padx=10)
    app.enable_intent_planner_var = tk.BooleanVar(value=True)
    tk.Checkbutton(
        target_frame,
        text="검색 의도 자동 분석",
        variable=app.enable_intent_planner_var,
        bg=app.color_card,
        activebackground=app.color_card,
        fg=app.color_text_dark,
        selectcolor=app.color_bg,
    ).pack(side="left", padx=10)
    app.enable_quality_guard_var = tk.BooleanVar(value=True)
    tk.Checkbutton(
        target_frame,
        text="발행 전 품질 검사",
        variable=app.enable_quality_guard_var,
        bg=app.color_card,
        activebackground=app.color_card,
        fg=app.color_text_dark,
        selectcolor=app.color_bg,
    ).pack(side="left", padx=10)

    app.manual_confirm_var = tk.BooleanVar(value=False)
    tk.Checkbutton(target_frame, text="발행 전 수동 확인 (반자동)", variable=app.manual_confirm_var,
                  bg=app.color_card, activebackground=app.color_card, fg="#f97316", font=app.font_bold,
                  selectcolor=app.color_bg).pack(side="left", padx=20)

    tk.Label(input_card, text="발행 개수", font=app.font_bold, bg=app.color_card, fg=app.color_text_dark).grid(row=5, column=0, sticky="w", pady=(15, 0))
    app.spin_count = tk.Spinbox(input_card, from_=1, to=50, width=10, bg=app.color_bg, fg=app.color_text_dark,
                                font=app.font_main, bd=1, relief="flat")
    app.spin_count.grid(row=6, column=0, pady=(5, 0), sticky="w")

    tk.Label(input_card, text="간격 (분)", font=app.font_bold, bg=app.color_card, fg=app.color_text_dark).grid(row=5, column=1, sticky="w", padx=20, pady=(15, 0))
    app.spin_gap = tk.Spinbox(input_card, from_=1, to=1440, width=10, bg=app.color_bg, fg=app.color_text_dark,
                             font=app.font_main, bd=1, relief="flat")
    app.spin_gap.grid(row=6, column=1, pady=(5, 0), sticky="w", padx=20)
    app.spin_gap.delete(0, "end")
    app.spin_gap.insert(0, "1")

    tk.Label(input_card, text="글 생성 엔진", font=app.font_bold, bg=app.color_card, fg=app.color_text_dark).grid(row=7, column=0, sticky="w", pady=(20, 0))
    text_provider_values = [
        "클로드 코드 (Claude Code)",
        "로컬 Ollama (무료)",
        "Gemini API (유료)",
    ]
    app.text_provider_var = tk.StringVar(value=text_provider_values[1])
    app.text_provider_combo = ttk.Combobox(
        input_card, textvariable=app.text_provider_var, values=text_provider_values,
        state="readonly", width=28, font=app.font_main,
    )
    app.text_provider_combo.grid(row=8, column=0, columnspan=2, pady=(5, 0), sticky="w")

    tk.Label(input_card, text="이미지 설정", font=app.font_bold, bg=app.color_card, fg=app.color_text_dark).grid(row=9, column=0, sticky="w", pady=(15, 0))
    img_mode_frame = tk.Frame(input_card, bg=app.color_card)
    img_mode_frame.grid(row=10, column=0, columnspan=2, sticky="w")

    app.img_mode_var = tk.StringVar(value="ai")
    tk.Radiobutton(img_mode_frame, text="AI 생성 이미지", variable=app.img_mode_var, value="ai",
                  bg=app.color_card, activebackground=app.color_card,
                  fg=app.color_text_dark, selectcolor=app.color_bg).pack(side="left")
    tk.Radiobutton(img_mode_frame, text="사용자 이미지 선택", variable=app.img_mode_var, value="custom",
                  bg=app.color_card, activebackground=app.color_card,
                  fg=app.color_text_dark, selectcolor=app.color_bg).pack(side="left", padx=10)

    app.btn_select_img = tk.Button(input_card, text=" 이미지 선택", bg="#1f2937", fg=app.color_text_dark, relief="flat", padx=15,
                                   command=app.select_custom_images)
    app.btn_select_img.grid(row=10, column=2, sticky="w")
    app.lbl_img_count = tk.Label(input_card, text="선택된 이미지: 0개", font=app.font_main, bg=app.color_card, fg=app.color_text_light)
    app.lbl_img_count.grid(row=10, column=3, sticky="w", padx=10)

    tk.Label(input_card, text="AI 이미지 엔진", font=app.font_bold, bg=app.color_card, fg=app.color_text_dark).grid(row=11, column=0, sticky="w", pady=(10, 0))
    image_provider_values = [
        "Gen AI (Gemini 이미지)",
        "자동 (Gen AI → Vertex → 무료)",
        "로컬 무료 (Pollinations)",
        "Pillow 플레이스홀더 (테스트용)",
        "Vertex AI",
    ]
    app.image_provider_var = tk.StringVar(value=image_provider_values[0])
    app.image_provider_combo = ttk.Combobox(input_card, textvariable=app.image_provider_var, values=image_provider_values, state="readonly", width=28, font=app.font_main)
    app.image_provider_combo.grid(row=12, column=0, columnspan=2, pady=(5, 15), sticky="w")

    # --- 스마트스토어 제품 URL 선택 ---
    tk.Label(input_card, text="홍보 상품 / URL", font=app.font_bold, bg=app.color_card, fg=app.color_text_dark).grid(row=13, column=0, sticky="w", pady=(5, 0))
    promo_frame = tk.Frame(input_card, bg=app.color_card)
    promo_frame.grid(row=14, column=0, columnspan=4, sticky="ew", pady=(2, 10))

    app.product_choice_var = tk.StringVar(value="none")

    # 내부 기본 URL 매핑 (필요 시 사용자가 아래 입력창에서 수정 가능)
    app._product_url_map = {
        "auto": "https://smartstore.naver.com/nanumlab/products/12809532969",
        "bike": "https://smartstore.naver.com/nanumlab/products/12639296730",
        "living": "https://smartstore.naver.com/nanumlab/products/10713170202",
    }

    def _set_product_url(key):
        if key == "none":
            url = "auto_detect"
            post_type = None
            keywords = []
        else:
            url = app._product_url_map.get(key, "")
            post_type = PRODUCT_POST_TYPE.get(key)
            keywords = PRODUCT_KEYWORDS.get(key, [])

        app.product_url_entry.delete(0, tk.END)
        app.product_url_entry.insert(0, url)
        
        # 사용자가 수동으로 선택한 글 유형이 있으면 덮어쓰지 않고 보존
        current_pt = app.post_type_var.get() if getattr(app, "post_type_var", None) else ""
        if current_pt in ("자동(매번 랜덤)", ""):
            if post_type and getattr(app, "post_type_var", None):
                app.post_type_var.set(post_type)
        if keywords and getattr(app, "entry_keywords", None):
            app.entry_keywords.delete(0, tk.END)
            app.entry_keywords.insert(0, ", ".join(keywords))

    rb_auto = tk.Radiobutton(
        promo_frame,
        text="자동차 코팅제",
        variable=app.product_choice_var,
        value="auto",
        bg=app.color_card,
        activebackground=app.color_card,
        fg=app.color_text_dark,
        selectcolor=app.color_bg,
        command=lambda: _set_product_url("auto"),
    )
    rb_auto.grid(row=0, column=0, sticky="w")

    rb_bike = tk.Radiobutton(
        promo_frame,
        text="바이크 코팅제",
        variable=app.product_choice_var,
        value="bike",
        bg=app.color_card,
        activebackground=app.color_card,
        fg=app.color_text_dark,
        selectcolor=app.color_bg,
        command=lambda: _set_product_url("bike"),
    )
    rb_bike.grid(row=0, column=1, sticky="w", padx=(10, 0))

    rb_living = tk.Radiobutton(
        promo_frame,
        text="리빙 코팅제",
        variable=app.product_choice_var,
        value="living",
        bg=app.color_card,
        activebackground=app.color_card,
        fg=app.color_text_dark,
        selectcolor=app.color_bg,
        command=lambda: _set_product_url("living"),
    )
    rb_living.grid(row=0, column=2, sticky="w", padx=(10, 0))

    rb_none = tk.Radiobutton(
        promo_frame,
        text="자동 감지 (키워드 매칭)",
        variable=app.product_choice_var,
        value="none",
        bg=app.color_card,
        activebackground=app.color_card,
        fg=app.color_text_dark,
        selectcolor=app.color_bg,
        command=lambda: _set_product_url("none"),
    )
    rb_none.grid(row=0, column=3, sticky="w", padx=(10, 0))

    app.btn_sync_traffic = tk.Button(
        promo_frame,
        text="🛒 트래픽 미노출 키워드 연동",
        bg="#2563eb",
        fg="white",
        font=("Malgun Gothic", 9, "bold"),
        relief="flat",
        padx=10,
        pady=2,
        command=app.sync_traffic_unranked_keywords,
    )
    app.btn_sync_traffic.grid(row=0, column=4, sticky="w", padx=(15, 0))

    tk.Label(
        promo_frame,
        text="선택한 상품 URL:",
        font=app.font_main,
        bg=app.color_card,
        fg=app.color_text_light,
    ).grid(row=1, column=0, sticky="w", pady=(5, 0))

    app.product_url_entry = app.create_modern_entry(promo_frame, "", 70)
    app.product_url_entry.grid(row=1, column=1, columnspan=4, sticky="ew", padx=(5, 0), pady=(5, 0))
    default_promo_url = app._product_url_map.get("auto", "")
    if default_promo_url:
        app.product_url_entry.insert(0, default_promo_url)
    promo_frame.columnconfigure(4, weight=1)

    app.vercel_enabled_var = tk.BooleanVar(value=False)
    app.vercel_on_publish_var = tk.BooleanVar(value=False)
    app.vercel_mode_var = tk.StringVar(value="local")
    app.entry_vercel_api = None
    app.entry_vercel_secret = None
    app.spin_vercel_interval = None
    app.btn_vercel_scheduler = None
    app.lbl_vercel_status = None

    if _show_vercel_ui():
        vercel_card = tk.Frame(
            app.auto_frame,
            bg=app.color_card,
            bd=0,
            highlightthickness=1,
            highlightbackground=app.color_border,
            padx=25,
            pady=18,
        )
        vercel_card.pack(fill="x", pady=(0, 12))

        tk.Label(
            vercel_card,
            text="☁️ Vercel 트래픽 (선택 — 없어도 글 발행 가능)",
            font=app.font_bold,
            bg=app.color_card,
            fg=app.color_text_dark,
        ).grid(row=0, column=0, columnspan=4, sticky="w")

        tk.Label(vercel_card, text="API URL", font=app.font_main, bg=app.color_card, fg=app.color_text_light).grid(
            row=1, column=0, sticky="w", pady=(10, 0)
        )
        app.entry_vercel_api = app.create_modern_entry(
            vercel_card, "https://내프로젝트.vercel.app/api/traffic", 55
        )
        app.entry_vercel_api.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(4, 0))

        tk.Label(vercel_card, text="WEBHOOK_SECRET (선택)", font=app.font_main, bg=app.color_card, fg=app.color_text_light).grid(
            row=3, column=0, sticky="w", pady=(8, 0)
        )
        app.entry_vercel_secret = app.create_modern_entry(vercel_card, "", 40, show="*")
        app.entry_vercel_secret.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        tk.Label(vercel_card, text="주기(분)", font=app.font_main, bg=app.color_card, fg=app.color_text_light).grid(
            row=3, column=2, sticky="w", padx=(12, 0), pady=(8, 0)
        )
        app.spin_vercel_interval = tk.Spinbox(
            vercel_card, from_=5, to=1440, width=8, bg=app.color_bg, fg=app.color_text_dark, font=app.font_main, bd=1, relief="flat"
        )
        app.spin_vercel_interval.grid(row=4, column=2, sticky="w", padx=(12, 0), pady=(4, 0))
        app.spin_vercel_interval.delete(0, "end")
        app.spin_vercel_interval.insert(0, "20")

        vf = tk.Frame(vercel_card, bg=app.color_card)
        vf.grid(row=5, column=0, columnspan=4, sticky="w", pady=(10, 0))
        tk.Checkbutton(
            vf,
            text="트래픽 사용",
            variable=app.vercel_enabled_var,
            bg=app.color_card,
            activebackground=app.color_card,
            fg=app.color_text_dark,
            selectcolor=app.color_bg,
        ).pack(side="left")
        tk.Checkbutton(
            vf,
            text="발행 성공 후 1회",
            variable=app.vercel_on_publish_var,
            bg=app.color_card,
            activebackground=app.color_card,
            fg=app.color_text_dark,
            selectcolor=app.color_bg,
        ).pack(side="left", padx=(14, 0))

        mode_frame = tk.Frame(vercel_card, bg=app.color_card)
        mode_frame.grid(row=6, column=0, columnspan=4, sticky="w", pady=(6, 0))
        for label, value in (("Vercel 클라우드", "cloud"), ("로컬 HTTP", "local"), ("둘 다", "both")):
            tk.Radiobutton(
                mode_frame,
                text=label,
                variable=app.vercel_mode_var,
                value=value,
                bg=app.color_card,
                activebackground=app.color_card,
                fg=app.color_text_dark,
                selectcolor=app.color_bg,
            ).pack(side="left", padx=(0, 10))

        btn_vf = tk.Frame(vercel_card, bg=app.color_card)
        btn_vf.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        tk.Button(
            btn_vf,
            text="헬스체크",
            bg="#1f2937",
            fg="white",
            relief="flat",
            padx=12,
            command=app.vercel_health_check,
        ).pack(side="left")
        tk.Button(
            btn_vf,
            text="트래픽 1회",
            bg="#2563eb",
            fg="white",
            relief="flat",
            padx=12,
            command=app.vercel_trigger_once,
        ).pack(side="left", padx=(8, 0))
        app.btn_vercel_scheduler = tk.Button(
            btn_vf,
            text="주기 실행 시작",
            bg="#7c3aed",
            fg="white",
            relief="flat",
            padx=12,
            command=app.toggle_vercel_scheduler,
        )
        app.btn_vercel_scheduler.pack(side="left", padx=(8, 0))
        app.lbl_vercel_status = tk.Label(
            btn_vf, text="", font=app.font_subtitle, bg=app.color_card, fg=app.color_text_light
        )
        app.lbl_vercel_status.pack(side="left", padx=(12, 0))
        vercel_card.columnconfigure(3, weight=1)

    # 버튼들을 정렬할 프레임 생성 (간격을 가깝게 배치)
    app.btn_action_frame = tk.Frame(input_card, bg=app.color_card)
    app.btn_action_frame.grid(row=6, column=2, columnspan=2, sticky="e", pady=(5, 0))

    app.btn_weekday = tk.Button(
        app.btn_action_frame,
        text="📅 평일 일과",
        bg="#0d9488",
        fg="white",
        font=app.font_bold,
        padx=14,
        pady=10,
        relief="flat",
        command=app.start_daily_weekday,
    )
    app.btn_weekday.pack(side="left", padx=(0, 8))

    app.btn_draft = tk.Button(
        app.btn_action_frame,
        text="✍ 원고+이미지 생성",
        bg="#6366f1",
        fg="white",
        font=app.font_bold,
        padx=15,
        pady=10,
        relief="flat",
        command=app.start_draft_writing,
    )
    app.btn_draft.pack(side="left", padx=(0, 8))

    app.btn_run = tk.Button(
        app.btn_action_frame,
        text="🚀 자동화 시작",
        bg=app.color_accent,
        fg="white",
        font=app.font_bold,
        padx=20,
        pady=10,
        relief="flat",
        command=app.start_processing,
    )
    app.btn_run.pack(side="left")
    tk.Label(
        input_card,
        text="월~금: 글쓰기 → hymini1↔hymini11 서로이웃·답글 → 티스토리",
        font=app.font_subtitle,
        bg=app.color_card,
        fg=app.color_text_light,
    ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(4, 0))

    app.btn_pause = tk.Button(input_card, text="⏸ 일시정지", bg="#f97316", fg="white", font=app.font_bold,
                             padx=20, pady=10, relief="flat", command=app.toggle_pause, state="disabled")
    app.btn_pause.grid(row=8, column=3, sticky="e")
    app.lbl_quality_status = tk.Label(
        input_card,
        text="품질 점수: 아직 없음",
        font=app.font_subtitle,
        bg=app.color_card,
        fg=app.color_text_light,
    )
    app.lbl_quality_status.grid(row=8, column=0, columnspan=3, sticky="w", pady=(6, 0))
    app.lbl_quality_details = tk.Label(
        input_card,
        text="세부 항목: 아직 없음",
        font=("Malgun Gothic", 8),
        bg=app.color_card,
        fg=app.color_text_light,
    )
    app.lbl_quality_details.grid(row=9, column=0, columnspan=3, sticky="w", pady=(2, 0))

    tk.Label(app.auto_frame, text="진행 로그", font=app.font_bold, bg=app.color_bg, fg=app.color_text_dark).pack(anchor="w", pady=(25, 5))
    app.log_area = scrolledtext.ScrolledText(app.auto_frame, bg="#020617", fg="#d1d5db", font=("Consolas", 10),
                                            highlightthickness=1, highlightbackground=app.color_border, bd=0, padx=10, pady=10)
    app.log_area.pack(fill="both", expand=True)

    if hasattr(app, "bootstrap_from_accounts_json"):
        app.bootstrap_from_accounts_json()


def setup_guidelines_tab(app):
    app.guidelines_frame = tk.Frame(app.body, bg=app.color_bg)

    card = tk.Frame(app.guidelines_frame, bg=app.color_card, highlightthickness=1,
                   highlightbackground=app.color_border, padx=30, pady=25)
    card.pack(fill="both", expand=True)

    tk.Label(card, text="블로그 글쓰기 마스터 지침", font=app.font_bold,
             bg=app.color_card, fg=app.color_text_dark).pack(anchor="w")
    tk.Label(
        card,
        text="여기에 적은 내용은 모든 자동 글쓰기에서 공통으로 적용됩니다.\n"
             "7:2:1 비율, 판매가 아닌 해결 중심, 카테고리별 작성 가이드, 말투 지침 등을 붙여넣고 '연동/저장'하면\n"
             "자동화 시 해당 지침을 기억해 글에 반영합니다. (표현 금지어, 브랜드 톤, 표 구성 규칙 등)",
        font=app.font_subtitle,
        bg=app.color_card,
        fg=app.color_text_light,
        justify="left",
    ).pack(anchor="w", pady=(5, 10))

    app.master_guidelines_text = scrolledtext.ScrolledText(
        card,
        height=18,
        font=("Malgun Gothic", 9),
        bg="#020617",
        fg=app.color_text_dark,
        highlightthickness=1,
        highlightbackground=app.color_border,
        bd=0,
        padx=10,
        pady=8,
        wrap=tk.WORD,
    )
    # 초기값: exe 배포 시 사용 설명서, 개발 시 마스터 지침 (저장된 값은 load_saved_credentials에서 덮어씀)
    _default_guide = DISTRIBUTION_GUIDELINES if getattr(sys, "frozen", False) else _default_master_for_gui()
    app.master_guidelines_text.insert(tk.END, _default_guide)
    app.master_guidelines_text.pack(fill="both", expand=True)


def setup_neighbor_tab(app):
    app.neighbor_frame = tk.Frame(app.body, bg=app.color_bg)

    card = tk.Frame(
        app.neighbor_frame,
        bg=app.color_card,
        highlightthickness=1,
        highlightbackground=app.color_border,
        padx=30,
        pady=25,
    )
    card.pack(fill="x")

    tk.Label(
        card,
        text="네이버 이웃 새글 공감 + 댓글",
        font=app.font_bold,
        bg=app.color_card,
        fg=app.color_text_dark,
    ).grid(row=0, column=0, columnspan=2, sticky="w")

    tk.Label(
        card,
        text="선택한 네이버 계정으로 블로그 이웃 새글 목록에서 공감과 댓글을 자동으로 남깁니다.\n"
             "※ 네이버 정책을 고려해 하루 최대 액션 수와 랜덤 딜레이를 적용합니다.",
        font=app.font_subtitle,
        bg=app.color_card,
        fg=app.color_text_light,
        justify="left",
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 15))

    acc_frame = tk.Frame(card, bg=app.color_card)
    acc_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(5, 10))
    tk.Label(
        acc_frame,
        text="사용할 네이버 계정:",
        font=app.font_bold,
        bg=app.color_card,
        fg=app.color_text_dark,
    ).pack(side="left")
    app.neighbor_account_var = tk.StringVar(value="naver1")
    tk.Radiobutton(
        acc_frame,
        text="네이버1 (ID1)",
        variable=app.neighbor_account_var,
        value="naver1",
        bg=app.color_card,
        activebackground=app.color_card,
        fg=app.color_text_dark,
        selectcolor=app.color_bg,
    ).pack(side="left", padx=10)
    tk.Radiobutton(
        acc_frame,
        text="네이버2 (ID2)",
        variable=app.neighbor_account_var,
        value="naver2",
        bg=app.color_card,
        activebackground=app.color_card,
        fg=app.color_text_dark,
        selectcolor=app.color_bg,
    ).pack(side="left", padx=10)

    opt_frame = tk.Frame(card, bg=app.color_card)
    opt_frame.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 5))

    tk.Label(
        opt_frame,
        text="하루 최대 액션 수:",
        font=app.font_main,
        bg=app.color_card,
        fg=app.color_text_light,
    ).grid(row=0, column=0, sticky="w")
    app.neighbor_max_actions = tk.Spinbox(
        opt_frame,
        from_=1,
        to=200,
        width=6,
        bg=app.color_bg,
        fg=app.color_text_dark,
        font=app.font_main,
        bd=1,
        relief="flat",
    )
    app.neighbor_max_actions.grid(row=0, column=1, sticky="w", padx=(5, 20))
    app.neighbor_max_actions.delete(0, tk.END)
    app.neighbor_max_actions.insert(0, "20")

    tk.Label(
        opt_frame,
        text="딜레이(초) 범위:",
        font=app.font_main,
        bg=app.color_card,
        fg=app.color_text_light,
    ).grid(row=0, column=2, sticky="w")
    app.neighbor_min_delay = tk.Spinbox(
        opt_frame,
        from_=1,
        to=30,
        width=4,
        bg=app.color_bg,
        fg=app.color_text_dark,
        font=app.font_main,
        bd=1,
        relief="flat",
    )
    app.neighbor_min_delay.grid(row=0, column=3, sticky="w", padx=(5, 2))
    app.neighbor_min_delay.delete(0, tk.END)
    app.neighbor_min_delay.insert(0, "4")

    tk.Label(
        opt_frame,
        text="~",
        font=app.font_main,
        bg=app.color_card,
        fg=app.color_text_light,
    ).grid(row=0, column=4, sticky="w")
    app.neighbor_max_delay = tk.Spinbox(
        opt_frame,
        from_=2,
        to=60,
        width=4,
        bg=app.color_bg,
        fg=app.color_text_dark,
        font=app.font_main,
        bd=1,
        relief="flat",
    )
    app.neighbor_max_delay.grid(row=0, column=5, sticky="w", padx=(2, 10))
    app.neighbor_max_delay.delete(0, tk.END)
    app.neighbor_max_delay.insert(0, "9")

    tk.Label(
        card,
        text="댓글 문구 (줄바꿈으로 여러 개 입력하면 랜덤 사용)",
        font=app.font_main,
        bg=app.color_card,
        fg=app.color_text_light,
    ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 3))

    app.neighbor_messages_text = scrolledtext.ScrolledText(
        card,
        height=4,
        font=("Malgun Gothic", 9),
        bg="#020617",
        fg=app.color_text_dark,
        highlightthickness=1,
        highlightbackground=app.color_border,
        bd=0,
        padx=8,
        pady=4,
        wrap=tk.WORD,
    )
    app.neighbor_messages_text.grid(row=5, column=0, columnspan=2, sticky="ew")
    app.neighbor_messages_text.insert(
        tk.END,
        "좋은 글 잘 보고 갑니다! 소통해요.\n"
        "포스팅 잘 보고 갑니다. 오늘도 좋은 하루 보내세요!\n"
        "유익한 정보네요. 자주 놀러 올게요!",
    )

    app.btn_neighbor_run = tk.Button(
        card,
        text="🤝 서이추 댓글 자동 실행",
        bg=app.color_accent,
        fg="white",
        font=app.font_bold,
        padx=20,
        pady=10,
        relief="flat",
        command=app.start_neighbor_visit,
    )
    app.btn_neighbor_run.grid(row=6, column=0, sticky="w", pady=(15, 0))

    app.neighbor_status_label = tk.Label(
        card,
        text="대기 중",
        font=app.font_subtitle,
        bg=app.color_card,
        fg=app.color_text_light,
        anchor="w",
    )
    app.neighbor_status_label.grid(row=6, column=1, sticky="e", padx=(10, 0))

    app.neighbor_status_strip = tk.Frame(
        card,
        bg="#1f2937",
        highlightthickness=0,
        padx=16,
        pady=12,
    )
    app.neighbor_status_strip.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(12, 0))
    app.neighbor_status_strip_border = tk.Frame(app.neighbor_status_strip, bg="#4b5563", width=4)
    app.neighbor_status_strip_border.pack(side="left", fill="y")
    app.neighbor_status_strip_border.pack_propagate(False)
    app.neighbor_strip_inner = tk.Frame(app.neighbor_status_strip, bg="#1f2937")
    app.neighbor_strip_inner.pack(side="left", fill="both", expand=True)
    app.neighbor_status_dot_label = tk.Label(
        app.neighbor_strip_inner,
        text="● 대기 중",
        font=("Malgun Gothic", 12, "bold"),
        bg="#1f2937",
        fg="#9ca3af",
        anchor="w",
    )
    app.neighbor_status_dot_label.pack(anchor="w")
    app.neighbor_current_task_label = tk.Label(
        app.neighbor_strip_inner,
        text="현재 작업: —",
        font=app.font_subtitle,
        bg="#1f2937",
        fg=app.color_text_light,
        anchor="w",
    )
    app.neighbor_current_task_label.pack(anchor="w", pady=(4, 0))
    card.columnconfigure(1, weight=1)

    log_section = tk.Frame(app.neighbor_frame, bg=app.color_bg)
    log_section.pack(fill="both", expand=True, pady=(15, 0))
    tk.Label(
        log_section,
        text="서이추 진행 로그",
        font=app.font_bold,
        bg=app.color_bg,
        fg=app.color_text_dark,
    ).pack(anchor="w", pady=(0, 5))
    app.neighbor_log_area = scrolledtext.ScrolledText(
        log_section,
        height=10,
        font=("Consolas", 9),
        bg="#020617",
        fg="#d1d5db",
        highlightthickness=1,
        highlightbackground=app.color_border,
        bd=0,
        padx=10,
        pady=8,
        wrap=tk.WORD,
    )
    app.neighbor_log_area.pack(fill="both", expand=True)

    stats_frame = tk.Frame(app.neighbor_frame, bg=app.color_bg)
    stats_frame.pack(fill="x", pady=(15, 0))

    tk.Label(
        stats_frame,
        text="오늘 서이추 댓글 통계",
        font=app.font_bold,
        bg=app.color_bg,
        fg=app.color_text_dark,
    ).pack(anchor="w")

    toolbar = tk.Frame(stats_frame, bg=app.color_bg)
    toolbar.pack(fill="x", pady=(5, 5))

    app.btn_neighbor_stats = tk.Button(
        toolbar,
        text="🔄 오늘 통계 새로고침",
        bg="#1f2937",
        fg=app.color_text_dark,
        font=app.font_main,
        relief="flat",
        padx=10,
        pady=4,
        command=app.refresh_neighbor_stats,
    )
    app.btn_neighbor_stats.pack(side="left")

    columns = ("account", "success", "fail", "total")
    app.neighbor_stats_tree = ttk.Treeview(
        stats_frame,
        columns=columns,
        show="headings",
        height=4,
    )
    app.neighbor_stats_tree.heading("account", text="계정")
    app.neighbor_stats_tree.heading("success", text="댓글 성공")
    app.neighbor_stats_tree.heading("fail", text="실패/오류")
    app.neighbor_stats_tree.heading("total", text="총 시도")
    app.neighbor_stats_tree.column("account", width=150, anchor="w")
    app.neighbor_stats_tree.column("success", width=80, anchor="e")
    app.neighbor_stats_tree.column("fail", width=80, anchor="e")
    app.neighbor_stats_tree.column("total", width=80, anchor="e")
    app.neighbor_stats_tree.pack(fill="x", pady=(5, 0))


def setup_tistory_tab(app):
    app.tistory_frame = tk.Frame(app.body, bg=app.color_bg)
    card = tk.Frame(
        app.tistory_frame,
        bg=app.color_card,
        highlightthickness=1,
        highlightbackground=app.color_border,
        padx=30,
        pady=25,
    )
    card.pack(fill="x")
    tk.Label(
        card,
        text="티스토리 구독 + 댓글",
        font=app.font_bold,
        bg=app.color_card,
        fg=app.color_text_dark,
    ).grid(row=0, column=0, columnspan=2, sticky="w")
    tk.Label(
        card,
        text="티스토리 메인(인기글 베스트, 오늘의 티스토리)에서 블로그 구독하기와 글에 댓글을 자동으로 남깁니다.\n"
             "설정 탭에서 입력한 티스토리(카카오) 계정으로 로그인 후 작업합니다.",
        font=app.font_subtitle,
        bg=app.color_card,
        fg=app.color_text_light,
        justify="left",
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 15))
    opt_frame = tk.Frame(card, bg=app.color_card)
    opt_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 5))
    tk.Label(opt_frame, text="최대 액션 수(구독+댓글 합계):", font=app.font_main, bg=app.color_card, fg=app.color_text_light).grid(row=0, column=0, sticky="w")
    app.tistory_max_actions = tk.Spinbox(opt_frame, from_=1, to=50, width=6, bg=app.color_bg, fg=app.color_text_dark, font=app.font_main, bd=1, relief="flat")
    app.tistory_max_actions.grid(row=0, column=1, sticky="w", padx=(5, 20))
    app.tistory_max_actions.delete(0, tk.END)
    app.tistory_max_actions.insert(0, "20")
    tk.Label(opt_frame, text="딜레이(초):", font=app.font_main, bg=app.color_card, fg=app.color_text_light).grid(row=0, column=2, sticky="w")
    app.tistory_min_delay = tk.Spinbox(opt_frame, from_=1, to=30, width=4, bg=app.color_bg, fg=app.color_text_dark, font=app.font_main, bd=1, relief="flat")
    app.tistory_min_delay.grid(row=0, column=3, sticky="w", padx=(5, 2))
    app.tistory_min_delay.delete(0, tk.END)
    app.tistory_min_delay.insert(0, "4")
    tk.Label(opt_frame, text="~", font=app.font_main, bg=app.color_card, fg=app.color_text_light).grid(row=0, column=4, sticky="w")
    app.tistory_max_delay = tk.Spinbox(opt_frame, from_=2, to=60, width=4, bg=app.color_bg, fg=app.color_text_dark, font=app.font_main, bd=1, relief="flat")
    app.tistory_max_delay.grid(row=0, column=5, sticky="w", padx=(2, 10))
    app.tistory_max_delay.delete(0, tk.END)
    app.tistory_max_delay.insert(0, "9")
    tk.Label(card, text="댓글 문구 (줄바꿈으로 여러 개)", font=app.font_main, bg=app.color_card, fg=app.color_text_light).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 3))
    app.tistory_messages_text = scrolledtext.ScrolledText(
        card, height=3, font=("Malgun Gothic", 9), bg="#020617", fg=app.color_text_dark,
        highlightthickness=1, highlightbackground=app.color_border, bd=0, padx=8, pady=4, wrap=tk.WORD,
    )
    app.tistory_messages_text.grid(row=4, column=0, columnspan=2, sticky="ew")
    app.tistory_messages_text.insert(tk.END, "좋은 글 잘 보고 갑니다! 소통해요.\n포스팅 잘 보고 갑니다. 오늘도 좋은 하루 보내세요!\n유익한 정보네요. 자주 놀러 올게요!")
    app.btn_tistory_run = tk.Button(
        card, text="📌 티스토리 구독·댓글 실행",
        bg=app.color_accent, fg="white", font=app.font_bold, padx=20, pady=10, relief="flat",
        command=app.start_tistory_visit,
    )
    app.btn_tistory_run.grid(row=5, column=0, sticky="w", pady=(15, 0))
    app.tistory_status_label = tk.Label(card, text="대기 중", font=app.font_subtitle, bg=app.color_card, fg=app.color_text_light, anchor="w")
    app.tistory_status_label.grid(row=5, column=1, sticky="e", padx=(10, 0))
    app.tistory_status_strip = tk.Frame(card, bg="#1f2937", padx=16, pady=12)
    app.tistory_status_strip.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(12, 0))
    app.tistory_status_strip_border = tk.Frame(app.tistory_status_strip, bg="#4b5563", width=4)
    app.tistory_status_strip_border.pack(side="left", fill="y")
    app.tistory_status_strip_border.pack_propagate(False)
    app.tistory_strip_inner = tk.Frame(app.tistory_status_strip, bg="#1f2937")
    app.tistory_strip_inner.pack(side="left", fill="both", expand=True)
    app.tistory_status_dot_label = tk.Label(app.tistory_strip_inner, text="● 대기 중", font=("Malgun Gothic", 12, "bold"), bg="#1f2937", fg="#9ca3af", anchor="w")
    app.tistory_status_dot_label.pack(anchor="w")
    app.tistory_current_task_label = tk.Label(app.tistory_strip_inner, text="현재 작업: —", font=app.font_subtitle, bg="#1f2937", fg=app.color_text_light, anchor="w")
    app.tistory_current_task_label.pack(anchor="w", pady=(4, 0))
    card.columnconfigure(1, weight=1)
    log_sec = tk.Frame(app.tistory_frame, bg=app.color_bg)
    log_sec.pack(fill="both", expand=True, pady=(15, 0))
    tk.Label(log_sec, text="티스토리 진행 로그", font=app.font_bold, bg=app.color_bg, fg=app.color_text_dark).pack(anchor="w", pady=(0, 5))
    app.tistory_log_area = scrolledtext.ScrolledText(
        log_sec, height=10, font=("Consolas", 9), bg="#020617", fg="#d1d5db",
        highlightthickness=1, highlightbackground=app.color_border, bd=0, padx=10, pady=8, wrap=tk.WORD,
    )
    app.tistory_log_area.pack(fill="both", expand=True)
    app.tistory_log_area.insert(
        tk.END,
        "아래 실행 버튼을 누르면 티스토리 메인(인기글 베스트, 오늘의 티스토리)에서\n"
        "블로그 구독 + 글 댓글을 자동으로 진행합니다. 설정 탭에서 티스토리(카카오) 계정을 입력해 두세요.\n"
    )


def setup_store_tab(app):
    """스마트스토어 SEO 마케팅 에이전트 탭."""
    try:
        from rank_persistence import supabase_enabled
    except ImportError:
        def supabase_enabled() -> bool:  # type: ignore[misc]
            return False

    app.store_frame = tk.Frame(app.body, bg=app.color_bg)

    card = tk.Frame(
        app.store_frame, bg=app.color_card, highlightthickness=1,
        highlightbackground=app.color_border, padx=25, pady=20,
    )
    card.pack(fill="x")

    tk.Label(
        card, text="스마트스토어 마케팅 에이전트",
        font=app.font_bold, bg=app.color_card, fg=app.color_text_dark,
    ).grid(row=0, column=0, columnspan=4, sticky="w")

    backend = "Supabase" if supabase_enabled() else "로컬 JSON (data/store_keywords.json)"
    app.store_backend_label = tk.Label(
        card, text=f"키워드 저장소: {backend}",
        font=app.font_main, bg=app.color_card, fg=app.color_text_light,
    )
    app.store_backend_label.grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 12))

    tk.Label(card, text="카테고리", font=app.font_bold, bg=app.color_card, fg=app.color_text_dark).grid(row=2, column=0, sticky="w")
    app.store_category_var = tk.StringVar(value="자동차용품")
    store_cats = ("자동차용품", "리빙", "바이크용품")
    ttk.Combobox(
        card, textvariable=app.store_category_var, values=store_cats,
        width=22, font=app.font_main,
    ).grid(row=3, column=0, sticky="w", pady=(4, 10))

    tk.Label(card, text="시드 키워드 (쉼표, 선택)", font=app.font_bold, bg=app.color_card, fg=app.color_text_dark).grid(row=2, column=1, sticky="w", padx=(20, 0))
    app.store_seed_entry = app.create_modern_entry(card, "유리막 코팅제, 자가시공", 40)
    app.store_seed_entry.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(20, 0), pady=(4, 10))

    tk.Label(card, text="상품 컨셉 / 스펙", font=app.font_bold, bg=app.color_card, fg=app.color_text_dark).grid(row=4, column=0, columnspan=4, sticky="w")
    app.store_concept_text = scrolledtext.ScrolledText(
        card, height=4, font=app.font_main, bg=app.color_bg, fg=app.color_text_dark,
        highlightthickness=1, highlightbackground=app.color_border, bd=0, wrap=tk.WORD,
    )
    app.store_concept_text.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(4, 10))
    app.store_concept_text.insert(
        tk.END,
        "자가시공이 가능한 고순도 폴리시라잔 성분의 프리미엄 차량용 유리막 코팅제 (지속력 1년 이상)",
    )

    opt_frame = tk.Frame(card, bg=app.color_card)
    opt_frame.grid(row=6, column=0, columnspan=4, sticky="w", pady=(0, 10))
    app.store_crawl_var = tk.BooleanVar(value=True)
    tk.Checkbutton(
        opt_frame, text="실행 전 키워드 수집(크롤)", variable=app.store_crawl_var,
        bg=app.color_card, activebackground=app.color_card, fg=app.color_text_dark, selectcolor=app.color_bg,
    ).pack(side="left")
    app.store_playwright_var = tk.BooleanVar(value=True)
    tk.Checkbutton(
        opt_frame, text="Playwright 네이버 연관검색어", variable=app.store_playwright_var,
        bg=app.color_card, activebackground=app.color_card, fg=app.color_text_dark, selectcolor=app.color_bg,
    ).pack(side="left", padx=(15, 0))

    btn_row = tk.Frame(card, bg=app.color_card)
    btn_row.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(5, 0))
    app.btn_store_run = tk.Button(
        btn_row, text="🛒 마케팅 리포트 생성", bg=app.color_accent, fg="white",
        font=app.font_bold, padx=16, pady=8, relief="flat", command=app.run_store_marketing,
    )
    app.btn_store_run.pack(side="left")
    app.btn_store_apply = tk.Button(
        btn_row, text="→ 자동화 탭 키워드에 반영", bg="#1f2937", fg=app.color_text_dark,
        font=app.font_main, padx=12, pady=8, relief="flat", command=app.apply_store_tags_to_automation,
        state="disabled",
    )
    app.btn_store_apply.pack(side="left", padx=(10, 0))

    card.columnconfigure(1, weight=1)

    tk.Label(app.store_frame, text="생성 결과", font=app.font_bold, bg=app.color_bg, fg=app.color_text_dark).pack(anchor="w", pady=(18, 5))
    app.store_result_area = scrolledtext.ScrolledText(
        app.store_frame, height=18, font=("Consolas", 10), bg="#020617", fg="#d1d5db",
        highlightthickness=1, highlightbackground=app.color_border, bd=0, padx=10, pady=10, wrap=tk.WORD,
    )
    app.store_result_area.pack(fill="both", expand=True)

    app._store_last_tags = ""


def setup_settings_tab(app):
    app.settings_window = tk.Toplevel(app.root)
    app.settings_window.title("설정")
    app.settings_window.configure(bg=app.color_bg)
    app.settings_window.geometry("900x700")
    app.settings_window.withdraw()

    app.settings_frame = tk.Frame(app.settings_window, bg=app.color_bg)
    app.settings_frame.pack(fill="both", expand=True)

    llm_card = tk.Frame(app.settings_frame, bg=app.color_card, highlightthickness=1, highlightbackground=app.color_border, padx=30, pady=25)
    llm_card.pack(fill="x", pady=(0, 20))

    tk.Label(llm_card, text="LLM API 설정", bg=app.color_card, fg=app.color_text_dark, font=("Malgun Gothic", 12, "bold")).pack(anchor="w")

    prov_frame = tk.Frame(llm_card, bg=app.color_card, pady=15)
    prov_frame.pack(fill="x")
    tk.Label(prov_frame, text="LLM Provider *", font=app.font_main, bg=app.color_card, fg=app.color_text_light).pack(side="left")
    app.btn_prov_chatgpt = tk.Button(prov_frame, text="ChatGPT", bg="#1f2937", fg=app.color_text_dark, relief="flat", padx=15)
    app.btn_prov_chatgpt.pack(side="left", padx=10)
    app.btn_prov_gemini = tk.Button(prov_frame, text="Gemini", bg=app.color_accent, fg="white", relief="flat", padx=15)
    app.btn_prov_gemini.pack(side="left")

    tk.Label(llm_card, text="Unified Google API Key *", font=app.font_main, bg=app.color_card, fg=app.color_text_light).pack(anchor="w")
    app.entry_gemini_key = app.create_modern_entry(llm_card, "AIzaSy...", 60, show="*")
    app.entry_gemini_key.pack(fill="x", pady=(5, 10))
    # autoblog.exe에서는 config 값으로 기본 채움, autoblog2.exe(public)는 빈 값으로 시작
    if not getattr(app, "is_public_mode", False):
        default_key = cfg.GOOGLE_API_KEY if cfg.GOOGLE_API_KEY != "YOUR_API_KEY_HERE" else cfg.GEMINI_API_KEY
        if default_key and default_key != "YOUR_API_KEY_HERE":
            app.entry_gemini_key.insert(0, default_key)

    blog_card = tk.Frame(app.settings_frame, bg=app.color_card, highlightthickness=1, highlightbackground=app.color_border, padx=30, pady=25)
    blog_card.pack(fill="x")

    tk.Label(blog_card, text="블로그 계정 설정", font=("Malgun Gothic", 12, "bold"), bg=app.color_card, fg=app.color_text_dark).pack(anchor="w")

    acc_frame = tk.Frame(blog_card, bg=app.color_card, pady=15)
    acc_frame.pack(fill="x")

    t_frame = tk.Frame(acc_frame, bg=app.color_card)
    t_frame.pack(side="left", fill="both", expand=True, padx=(0, 20))
    tk.Label(t_frame, text="티스토리 (카카오 이메일)", bg=app.color_card, fg=app.color_text_light).pack(anchor="w")
    app.entry_t_id = app.create_modern_entry(t_frame, "example@kakao.com")
    app.entry_t_id.pack(fill="x", pady=(5, 10))
    app.entry_t_id.insert(0, cfg.TISTORY_ID)
    tk.Label(t_frame, text="티스토리 비밀번호", bg=app.color_card, fg=app.color_text_light).pack(anchor="w")
    app.entry_t_pw = app.create_modern_entry(t_frame, "", show="*")
    app.entry_t_pw.pack(fill="x", pady=(5, 0))
    app.entry_t_pw.insert(0, cfg.TISTORY_PW)

    n_frame = tk.Frame(acc_frame, bg=app.color_card)
    n_frame.pack(side="left", fill="both", expand=True)

    tk.Label(n_frame, text="네이버 계정 1 (ID)", bg=app.color_card, fg=app.color_text_light).pack(anchor="w")
    app.entry_n_id1 = app.create_modern_entry(n_frame, "naver_id1")
    app.entry_n_id1.pack(fill="x", pady=(2, 5))
    app.entry_n_id1.insert(0, cfg.NAVER_ACCOUNTS[0]["id"] if len(cfg.NAVER_ACCOUNTS) > 0 else "")

    tk.Label(n_frame, text="네이버 계정 1 (PW)", bg=app.color_card, fg=app.color_text_light).pack(anchor="w")
    app.entry_n_pw1 = app.create_modern_entry(n_frame, "", show="*")
    app.entry_n_pw1.pack(fill="x", pady=(2, 10))
    app.entry_n_pw1.insert(0, cfg.NAVER_ACCOUNTS[0]["pw"] if len(cfg.NAVER_ACCOUNTS) > 0 else "")

    tk.Label(n_frame, text="네이버 계정 2 (ID)", bg=app.color_card, fg=app.color_text_light).pack(anchor="w")
    app.entry_n_id2 = app.create_modern_entry(n_frame, "naver_id2")
    app.entry_n_id2.pack(fill="x", pady=(2, 5))
    n2_id = cfg.NAVER_ACCOUNTS[1]["id"] if len(cfg.NAVER_ACCOUNTS) > 1 else ""
    n2_pw = cfg.NAVER_ACCOUNTS[1]["pw"] if len(cfg.NAVER_ACCOUNTS) > 1 else ""
    app.entry_n_id2.insert(0, n2_id)

    tk.Label(n_frame, text="네이버 계정 2 (PW)", bg=app.color_card, fg=app.color_text_light).pack(anchor="w")
    app.entry_n_pw2 = app.create_modern_entry(n_frame, "", show="*")
    app.entry_n_pw2.pack(fill="x", pady=(2, 10))
    app.entry_n_pw2.insert(0, n2_pw)

    g_frame = tk.Frame(acc_frame, bg=app.color_card)
    g_frame.pack(side="left", fill="both", expand=True, padx=(20, 0))
    tk.Label(g_frame, text="구글 계정 (이메일)", bg=app.color_card, fg=app.color_text_light).pack(anchor="w")
    app.entry_g_id = app.create_modern_entry(g_frame, "user@gmail.com")
    app.entry_g_id.pack(fill="x", pady=(2, 5))
    tk.Label(g_frame, text="구글 계정 (PW, 메모용)", bg=app.color_card, fg=app.color_text_light).pack(anchor="w")
    app.entry_g_pw = app.create_modern_entry(g_frame, "", show="*")
    app.entry_g_pw.pack(fill="x", pady=(2, 0))

    vx_card = tk.Frame(app.settings_frame, bg=app.color_card, highlightthickness=1, highlightbackground=app.color_border, padx=30, pady=15)
    vx_card.pack(fill="x", pady=20)
    tk.Label(vx_card, text="이미지 생성(Vertex AI) 설정 (선택)", font=app.font_bold, bg=app.color_card, fg=app.color_text_dark).pack(anchor="w")
    vx_sub = tk.Frame(vx_card, bg=app.color_card, pady=5)
    vx_sub.pack(fill="x")
    app.entry_proj_id = app.create_modern_entry(vx_sub, "Project ID", 30)
    app.entry_proj_id.pack(side="left", padx=(0, 10))
    app.entry_proj_id.insert(0, cfg.VERTEX_PROJECT_ID)
    app.entry_vx_key = app.create_modern_entry(vx_sub, "Vertex API Key (Optional Override)", 40)
    app.entry_vx_key.pack(side="left")
    app.entry_vx_key.insert(0, cfg.VERTEX_API_KEY)

    app.btn_save = tk.Button(app.settings_frame, text="💾 설정 저장 및 연동", bg="black", fg="white",
                             font=app.font_bold, padx=40, pady=12, relief="flat", command=app.save_and_link)
    app.btn_save.pack(pady=10)

    app.load_saved_credentials()
