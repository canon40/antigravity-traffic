import asyncio
import os
import re
import sys
import threading
import json
import csv
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime

import config as cfg
from blog_theme import THEME, FONT_MAIN, FONT_BOLD, FONT_TITLE, FONT_SUBTITLE
from blog_gui_tabs import (
    setup_automation_tab,
    setup_guidelines_tab,
    setup_neighbor_tab,
    setup_store_tab,
    setup_tistory_tab,
    setup_settings_tab,
)
from doc_guidelines import DISTRIBUTION_GUIDELINES


def _content_gen():
    from drawer.registry import get_content_gen

    return get_content_gen()


def _run_main_loop():
    from drawer.registry import get_automation_flow

    return get_automation_flow().run_main_loop


def _lazy_tabs_enabled() -> bool:
    try:
        from drawer.light import lazy_tabs

        return lazy_tabs()
    except ImportError:
        return False


class CanonAutoGUI:
    def __init__(self, root):
        self.root = root
        exe_name = os.path.basename(sys.argv[0]).lower()
        # autoblog2.exe / blog_auto_public 모드에서는 API 키·키워드 기본값을 비워서 배포용으로 사용
        self.is_public_mode = ("autoblog2" in exe_name) or ("blog_auto_public" in exe_name)

        self.root.title("canon4040's Autoblog")
        self.root.geometry("1100x850")
        self.root.configure(bg=THEME["color_sidebar"])

        self.font_main = FONT_MAIN
        self.font_bold = FONT_BOLD
        self.font_title = FONT_TITLE
        self.font_subtitle = FONT_SUBTITLE

        self.color_sidebar = THEME["color_sidebar"]
        self.color_bg = THEME["color_bg"]
        self.color_active_tab = THEME["color_active_tab"]
        self.color_text_dark = THEME["color_text_dark"]
        self.color_text_light = THEME["color_text_light"]
        self.color_accent = THEME["color_accent"]
        self.color_border = THEME["color_border"]
        self.color_card = THEME["color_card"]
        
        # 상태 변수
        self.current_tab = "automation"
        self.is_connected = False 
        self.is_paused = False
        self.is_processing = False
        self._vercel_scheduler = None
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.image_dir = os.path.join(self.base_dir, "generated_images")
        if not os.path.exists(self.image_dir): os.makedirs(self.image_dir)

        # 계정/설정 자동 저장 파일 경로 (스크립트 폴더 우선, 없으면 현재 작업 폴더)
        self.cred_file = os.path.abspath(os.path.join(self.base_dir, "accounts.json"))
        if not os.path.exists(self.cred_file):
            cwd_json = os.path.abspath(os.path.join(os.getcwd(), "accounts.json"))
            if os.path.exists(cwd_json):
                self.cred_file = cwd_json
        
        # 사용자 정의 이미지 경로
        self.custom_img_paths = []

        self._tabs_loaded = set()
        self.setup_layout()
        self.switch_tab("automation")

    @staticmethod
    def _default_master_guidelines() -> str:
        try:
            from drawer.wiki import load_default_master_guidelines

            return load_default_master_guidelines()
        except Exception:
            return _content_gen().DEFAULT_MASTER_GUIDELINES

    def setup_layout(self):
        # 1. 사이드바 (Sidebar)
        self.sidebar = tk.Frame(self.root, bg=self.color_sidebar, width=220)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        
        # 브랜드 로고
        logo_frame = tk.Frame(self.sidebar, bg=self.color_sidebar, pady=30, padx=20)
        logo_frame.pack(fill="x")
        tk.Label(logo_frame, text="canon4040", font=self.font_title, fg="white", bg=self.color_sidebar, anchor="w").pack(fill="x")
        tk.Label(logo_frame, text="오토 블로그", font=self.font_subtitle, fg="#888888", bg=self.color_sidebar, anchor="w").pack(fill="x")
        
        # 메뉴 버튼 컨테이너
        menu_frame = tk.Frame(self.sidebar, bg=self.color_sidebar, pady=10)
        menu_frame.pack(fill="x", expand=True, anchor="n")
        
        self.btn_tab_auto = self.create_menu_item(menu_frame, "📥 자동화", "automation")
        self.btn_tab_store = self.create_menu_item(menu_frame, "🛒 스마트스토어", "store")
        self.btn_tab_guide = self.create_menu_item(menu_frame, "🧾 지침", "guidelines")
        self.btn_tab_neighbor = self.create_menu_item(menu_frame, "🤝 서이추 댓글", "neighbor")
        self.btn_tab_tistory = self.create_menu_item(menu_frame, "📌 티스토리 서이추", "tistory")
        self.btn_tab_set = self.create_menu_item(menu_frame, "⚙ 설정", "settings")
        
        # 하단 상태 바
        status_card = tk.Frame(self.sidebar, bg="#020617", padx=15, pady=15)
        status_card.pack(side="bottom", fill="x", padx=10, pady=20)
        tk.Label(status_card, text="계정 연동 상태", font=("Malgun Gothic", 9), fg=self.color_text_light, bg="#020617", anchor="w").pack(fill="x")
        self.lbl_conn_status = tk.Label(status_card, text="ⓧ 연동 안됨", font=("Malgun Gothic", 10, "bold"), fg="#f97373", bg="#020617", anchor="w")
        self.lbl_conn_status.pack(fill="x", pady=(5,0))
        tk.Label(self.sidebar, text="버전 1.1", font=("Consolas", 8), fg="#4b5563", bg=self.color_sidebar).pack(side="bottom", pady=5)

        # 2. 메인 콘텐츠 영역
        self.main_area = tk.Frame(self.root, bg=self.color_bg)
        self.main_area.pack(side="right", fill="both", expand=True)
        
        # 헤더 (Header)
        self.header = tk.Frame(self.main_area, bg=self.color_card, height=80, padx=40, pady=20)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)
        self.lbl_header_title = tk.Label(self.header, text="설정", font=("Malgun Gothic", 16, "bold"), bg=self.color_card, fg=self.color_text_dark)
        self.lbl_header_title.pack(side="left")
        self.lbl_header_desc = tk.Label(self.header, text="LLM API 및 블로그 계정을 설정합니다", font=self.font_subtitle, bg=self.color_card, fg=self.color_text_light)
        self.lbl_header_desc.pack(side="left", padx=15, pady=(3,0))
        # 현재 시간 표시 (우측, 1초마다 갱신)
        self.lbl_clock = tk.Label(self.header, text="", font=("Consolas", 12), bg=self.color_card, fg=self.color_text_light)
        self.lbl_clock.pack(side="right")
        self._update_clock()
        
        # 구분선
        tk.Frame(self.main_area, bg=self.color_border, height=1).pack(fill="x")
        self._setup_body_and_tabs()

    def _update_clock(self):
        """헤더 현재 시간을 1초마다 갱신."""
        try:
            self.lbl_clock.config(text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            pass
        self.root.after(1000, self._update_clock)

    def _ensure_tab(self, tab_id: str) -> None:
        """서랍 모드: 탭을 처음 열 때만 UI를 생성."""
        if tab_id in self._tabs_loaded:
            return
        builders = {
            "automation": setup_automation_tab,
            "store": setup_store_tab,
            "guidelines": setup_guidelines_tab,
            "neighbor": setup_neighbor_tab,
            "tistory": setup_tistory_tab,
            "settings": setup_settings_tab,
        }
        fn = builders.get(tab_id)
        if fn:
            fn(self)
            self._tabs_loaded.add(tab_id)

    def _setup_body_and_tabs(self):
        """본문 프레임 및 탭 초기화 (setup_layout에서 호출)."""
        self.body = tk.Frame(self.main_area, bg=self.color_bg, padx=40, pady=30)
        self.body.pack(fill="both", expand=True)
        if _lazy_tabs_enabled():
            setup_automation_tab(self)
            self._tabs_loaded.add("automation")
        else:
            for tid, fn in (
                ("automation", setup_automation_tab),
                ("store", setup_store_tab),
                ("guidelines", setup_guidelines_tab),
                ("neighbor", setup_neighbor_tab),
                ("tistory", setup_tistory_tab),
                ("settings", setup_settings_tab),
            ):
                fn(self)
                self._tabs_loaded.add(tid)

    def create_menu_item(self, parent, text, tab_id):
        btn = tk.Label(parent, text=text, font=self.font_bold, fg=self.color_text_light, bg=self.color_sidebar, 
                      padx=20, pady=15, anchor="w", cursor="hand2")
        btn.pack(fill="x", padx=10, pady=2)
        btn.bind("<Button-1>", lambda e: self.switch_tab(tab_id))
        return btn

    def switch_tab(self, tab_id):
        self.current_tab = tab_id
        self._ensure_tab(tab_id)
        # 버튼 UI 업데이트
        for tid, btn in [
            ("automation", self.btn_tab_auto),
            ("store", self.btn_tab_store),
            ("guidelines", self.btn_tab_guide),
            ("neighbor", self.btn_tab_neighbor),
            ("tistory", self.btn_tab_tistory),
            ("settings", self.btn_tab_set),
        ]:
            if tid == tab_id:
                btn.config(bg=self.color_active_tab, fg=self.color_text_dark)
            else:
                btn.config(bg=self.color_sidebar, fg=self.color_text_light)
        
        # 화면 전환
        if tab_id == "automation":
            self.lbl_header_title.config(text="자동화")
            self.lbl_header_desc.config(text="블로그 포스팅 자동화를 실행하고 상태를 모니터링합니다")
            if hasattr(self, "store_frame"):
                self.store_frame.pack_forget()
            if hasattr(self, "guidelines_frame"):
                self.guidelines_frame.pack_forget()
            if hasattr(self, "neighbor_frame"):
                self.neighbor_frame.pack_forget()
            if hasattr(self, "tistory_frame"):
                self.tistory_frame.pack_forget()
            self.auto_frame.pack(fill="both", expand=True)
            # 설정 팝업 숨기기
            if hasattr(self, "settings_window"):
                self.settings_window.withdraw()
        elif tab_id == "store":
            self.lbl_header_title.config(text="스마트스토어")
            self.lbl_header_desc.config(text="네이버 SEO 가이드 + 키워드 기반 상품명·태그·카피 생성")
            self.auto_frame.pack_forget()
            if hasattr(self, "guidelines_frame"):
                self.guidelines_frame.pack_forget()
            if hasattr(self, "neighbor_frame"):
                self.neighbor_frame.pack_forget()
            if hasattr(self, "tistory_frame"):
                self.tistory_frame.pack_forget()
            if hasattr(self, "settings_window"):
                self.settings_window.withdraw()
            self.store_frame.pack(fill="both", expand=True)
        elif tab_id == "guidelines":
            self.lbl_header_title.config(text="지침")
            self.lbl_header_desc.config(text="블로그 글쓰기 마스터 지침을 관리합니다")
            self.auto_frame.pack_forget()
            if hasattr(self, "store_frame"):
                self.store_frame.pack_forget()
            self.guidelines_frame.pack(fill="both", expand=True)
            if hasattr(self, "neighbor_frame"):
                self.neighbor_frame.pack_forget()
            if hasattr(self, "tistory_frame"):
                self.tistory_frame.pack_forget()
            if hasattr(self, "settings_window"):
                self.settings_window.withdraw()
        elif tab_id == "neighbor":
            self.lbl_header_title.config(text="서이추 댓글")
            self.lbl_header_desc.config(text="네이버 이웃 새글에서 공감과 댓글을 자동으로 남깁니다")
            self.auto_frame.pack_forget()
            if hasattr(self, "store_frame"):
                self.store_frame.pack_forget()
            if hasattr(self, "guidelines_frame"):
                self.guidelines_frame.pack_forget()
            if hasattr(self, "tistory_frame"):
                self.tistory_frame.pack_forget()
            if hasattr(self, "settings_window"):
                self.settings_window.withdraw()
            self.neighbor_frame.pack(fill="both", expand=True)
        elif tab_id == "tistory":
            self.lbl_header_title.config(text="티스토리 서이추")
            self.lbl_header_desc.config(text="티스토리 메인에서 인기 블로그 구독 + 글에 댓글을 자동으로 남깁니다")
            self.auto_frame.pack_forget()
            if hasattr(self, "store_frame"):
                self.store_frame.pack_forget()
            if hasattr(self, "guidelines_frame"):
                self.guidelines_frame.pack_forget()
            if hasattr(self, "neighbor_frame"):
                self.neighbor_frame.pack_forget()
            if hasattr(self, "settings_window"):
                self.settings_window.withdraw()
            self.tistory_frame.pack(fill="both", expand=True)
            self.tistory_frame.update_idletasks()
        else:  # settings
            self.lbl_header_title.config(text="설정")
            self.lbl_header_desc.config(text="LLM API 및 블로그 계정을 설정합니다")
            self.auto_frame.pack_forget()
            if hasattr(self, "store_frame"):
                self.store_frame.pack_forget()
            if hasattr(self, "guidelines_frame"):
                self.guidelines_frame.pack_forget()
            if hasattr(self, "neighbor_frame"):
                self.neighbor_frame.pack_forget()
            if hasattr(self, "tistory_frame"):
                self.tistory_frame.pack_forget()
            # 설정은 팝업 창으로 표시
            if hasattr(self, "settings_window"):
                self.settings_window.deiconify()
                self.settings_window.lift()
                try:
                    self.settings_window.focus_force()
                except Exception:
                    pass

    def create_modern_entry(self, parent, placeholder, width=None, show=None):
        entry = tk.Entry(parent, font=self.font_main, bg=self.color_bg, fg=self.color_text_dark,
                        highlightthickness=1, highlightbackground=self.color_border,
                        highlightcolor=self.color_accent, bd=0, insertbackground=self.color_text_dark, show=show)
        if width:
            entry.config(width=width)
        return entry

    def load_saved_credentials(self):
        """accounts.json에 저장된 계정/설정 정보를 읽어와 입력란에 반영."""
        data = self._read_accounts_json()
        if data:
            self._apply_accounts_data(data)
        else:
            self._sync_connection_status()

    def bootstrap_from_accounts_json(self) -> None:
        """lazy 탭 모드: 설정 탭 없이도 accounts.json → 자동화 탭 + 연동 상태 반영."""
        data = self._read_accounts_json()
        if data:
            self._apply_accounts_data(data)
        else:
            self._sync_connection_status()

    def _apply_accounts_data(self, data: dict) -> None:
        def _set(entry_attr: str, key: str) -> None:
            entry = getattr(self, entry_attr, None)
            if entry is None:
                return
            val = data.get(key)
            if val is not None:
                try:
                    entry.delete(0, tk.END)
                    entry.insert(0, val)
                except Exception:
                    pass

        _set("entry_gemini_key", "gemini_key")
        _set("entry_t_id", "tistory_id")
        _set("entry_t_pw", "tistory_pw")
        _set("entry_n_id1", "naver_id1")
        _set("entry_n_pw1", "naver_pw1")
        _set("entry_n_id2", "naver_id2")
        _set("entry_n_pw2", "naver_pw2")
        for key, var_name in (
            ("use_naver1", "use_naver1_var"),
            ("use_naver2", "use_naver2_var"),
            ("use_tistory", "use_tistory_var"),
            ("use_google", "use_google_var"),
            ("enable_intent_planner", "enable_intent_planner_var"),
            ("enable_quality_guard", "enable_quality_guard_var"),
        ):
            if key in data and hasattr(self, var_name):
                getattr(self, var_name).set(bool(data[key]))
        _set("entry_proj_id", "vertex_project_id")
        _set("entry_vx_key", "vertex_api_key")
        if hasattr(self, "entry_g_id"):
            _set("entry_g_id", "google_id")
        if hasattr(self, "entry_g_pw"):
            _set("entry_g_pw", "google_pw")

        mg = data.get("master_guidelines")
        if hasattr(self, "master_guidelines_text"):
            self.master_guidelines_text.delete("1.0", tk.END)
            if mg and mg.strip():
                self.master_guidelines_text.insert(tk.END, mg)
            else:
                default_guide = DISTRIBUTION_GUIDELINES if getattr(sys, "frozen", False) else self._default_master_guidelines()
                self.master_guidelines_text.insert(tk.END, default_guide)
        if hasattr(self, "text_provider_var"):
            tp = data.get("text_provider")
            legacy_tp = {
                "Gemini API (유료·현재 기본)": "Gemini API (유료)",
                "자동 (Ollama → Gemini)": "로컬 Ollama (무료)",
                "gemini": "Gemini API (유료)",
                "ollama": "로컬 Ollama (무료)",
                "claude": "클로드 코드 (Claude Code)",
            }
            allowed = (
                "클로드 코드 (Claude Code)",
                "로컬 Ollama (무료)",
                "Gemini API (유료)",
            )
            if tp in allowed:
                self.text_provider_var.set(tp)
            elif tp in legacy_tp:
                self.text_provider_var.set(legacy_tp[tp])
            elif isinstance(tp, str) and tp.strip():
                self.text_provider_var.set(legacy_tp.get(tp.strip().lower(), "로컬 Ollama (무료)"))
            else:
                self.text_provider_var.set("Gemini API (유료)")
        if hasattr(self, "entry_keywords"):
            kws = data.get("keywords")
            if isinstance(kws, list):
                kws = ", ".join(str(x).strip() for x in kws if str(x).strip())
            if isinstance(kws, str) and kws.strip():
                self.entry_keywords.delete(0, tk.END)
                self.entry_keywords.insert(0, kws.strip())
        if hasattr(self, "post_type_var") and data.get("post_type"):
            try:
                self.post_type_var.set(str(data["post_type"]))
            except Exception:
                pass
        if getattr(self, "product_choice_var", None) and data.get("product_choice"):
            try:
                self.product_choice_var.set(str(data["product_choice"]))
            except Exception:
                pass
        if getattr(self, "product_url_entry", None):
            if data.get("product_url"):
                try:
                    self.product_url_entry.delete(0, tk.END)
                    self.product_url_entry.insert(0, str(data["product_url"]).strip())
                except Exception:
                    pass
            elif getattr(self, "_product_url_map", None):
                choice = (data.get("product_choice") or "auto").strip()
                fallback = self._product_url_map.get(choice) or self._product_url_map.get("auto", "")
                if fallback and not self.product_url_entry.get().strip():
                    try:
                        self.product_url_entry.delete(0, tk.END)
                        self.product_url_entry.insert(0, fallback)
                    except Exception:
                        pass
        if hasattr(self, "spin_count") and data.get("count") is not None:
            try:
                self.spin_count.delete(0, tk.END)
                self.spin_count.insert(0, str(int(data["count"])))
            except Exception:
                pass
        if getattr(self, "entry_vercel_api", None):
            for key, widget in (
                ("vercel_api_url", self.entry_vercel_api),
                ("vercel_webhook_secret", self.entry_vercel_secret),
            ):
                val = data.get(key)
                if val is not None:
                    widget.delete(0, tk.END)
                    widget.insert(0, str(val))
        if getattr(self, "spin_vercel_interval", None) and data.get("vercel_interval_minutes") is not None:
            try:
                self.spin_vercel_interval.delete(0, tk.END)
                self.spin_vercel_interval.insert(0, str(int(data["vercel_interval_minutes"])))
            except Exception:
                pass
        if getattr(self, "vercel_enabled_var", None) and "vercel_enabled" in data:
            self.vercel_enabled_var.set(bool(data["vercel_enabled"]))
        if getattr(self, "vercel_on_publish_var", None) and "vercel_on_publish" in data:
            self.vercel_on_publish_var.set(bool(data["vercel_on_publish"]))
        if getattr(self, "vercel_mode_var", None) and data.get("vercel_mode"):
            self.vercel_mode_var.set(str(data["vercel_mode"]))
        if hasattr(self, "image_provider_var"):
            ip = data.get("image_provider")
            legacy_ip = {
                "Gen AI": "Gen AI (Gemini 이미지)",
                "자동 (Gen AI → Vertex)": "자동 (Gen AI → Vertex → 무료)",
                "로컬 무료 (Pollinations → Pillow)": "로컬 무료 (Pollinations)",
                "Pillow 플레이스홀더": "Pillow 플레이스홀더 (테스트용)",
            }
            allowed_ip = (
                "Gen AI (Gemini 이미지)",
                "자동 (Gen AI → Vertex → 무료)",
                "로컬 무료 (Pollinations)",
                "Pillow 플레이스홀더 (테스트용)",
                "Vertex AI",
            )
            if ip in allowed_ip:
                self.image_provider_var.set(ip)
            elif ip in legacy_ip:
                self.image_provider_var.set(legacy_ip[ip])
            else:
                self.image_provider_var.set("Gen AI (Gemini 이미지)")

        self._sync_connection_status()

    def _sync_connection_status(self):
        """Gemini 키 또는 (Ollama/Claude + 네이버 계정)이면 자동화 시작 가능."""
        has_key = bool(self._get_entry_or_accounts("entry_gemini_key", "gemini_key"))
        has_key = has_key or bool(self._get_entry_or_accounts("entry_vx_key", "vertex_api_key"))
        tp = ""
        if getattr(self, "text_provider_var", None):
            try:
                tp = self.text_provider_var.get() or ""
            except Exception:
                tp = ""
        use_gemini = "Gemini" in tp and "Ollama" not in tp.split("→")[0]
        claude_only = "클로드" in tp or "Claude Code" in tp
        ollama_only = "Ollama" in tp and not use_gemini and not claude_only
        has_naver = bool(self._get_entry_or_accounts("entry_n_id1", "naver_id1")) or bool(
            self._get_entry_or_accounts("entry_n_id2", "naver_id2")
        )
        if use_gemini and has_key:
            self.is_connected = True
            self.lbl_conn_status.config(text="● Gemini 연동", fg="#00C73C")
        elif claude_only and has_naver:
            self.is_connected = True
            self.lbl_conn_status.config(text="● Claude Code 준비", fg="#00C73C")
        elif ollama_only and has_naver:
            self.is_connected = True
            self.lbl_conn_status.config(text="● Ollama(로컬) 준비", fg="#00C73C")
        elif has_key:
            self.is_connected = True
            self.lbl_conn_status.config(text="● 연동 성공", fg="#00C73C")
        else:
            self.is_connected = False
            self.lbl_conn_status.config(text="ⓧ 연동 안됨", fg="#f97373")

    def _update_quality_status(self, report: dict | None) -> None:
        if not getattr(self, "lbl_quality_status", None):
            return
        try:
            from blog_quality_guard import (
                has_quality_report,
                quality_color,
                summarize_quality_badge,
                summarize_quality_details,
            )

            valid = has_quality_report(report)
            text = summarize_quality_badge(report if valid else None)
            details = summarize_quality_details(report if valid else None)
            after = (report or {}).get("after", report or {}) if valid else {}
            score = int(after.get("score", 0)) if valid else 0
            color = quality_color(score) if valid else self.color_text_light
        except Exception:
            text = "품질 점수: 확인 불가"
            details = "세부 항목: 확인 불가"
            color = self.color_text_light
        self.lbl_quality_status.config(text=text)
        self.lbl_quality_status.config(fg=color)
        if getattr(self, "lbl_quality_details", None):
            self.lbl_quality_details.config(text=details)

    def select_custom_images(self):
        files = filedialog.askopenfilenames(
            title="포스팅에 사용할 이미지 선택",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp")]
        )
        if files:
            self.custom_img_paths = list(files)
            self.lbl_img_count.config(text=f"선택된 이미지: {len(files)}개", fg="#007bff")
            self.log(f"      📁 사용자 이미지 {len(files)}개 선택됨")
        else:
            self.custom_img_paths = []
            self.lbl_img_count.config(text="선택된 이미지: 0개", fg="#666666")

    def sync_traffic_unranked_keywords(self):
        """D:/@code/traffic/traffic_config.json 파일에서 현재 미노출 키워드를 가져와서 GUI 입력창에 넣어줍니다."""
        import json
        from pathlib import Path
        
        product_choice = self.product_choice_var.get()
        traffic_path = Path("D:/@code/traffic/traffic_config.json")
        if not traffic_path.exists():
            # 상대 경로로 시도 (D:/@code/antigravity/blogauto/login2 기준 2단계 상위 -> D:/@code/traffic)
            traffic_path = Path(self.base_dir).resolve().parents[2] / "traffic" / "traffic_config.json"

        if not traffic_path.exists():
            messagebox.showerror("오류", f"트래픽 프로그램 설정 파일을 찾을 수 없습니다.\n경로: {traffic_path}")
            return

        try:
            with open(traffic_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            tasks = data.get("keyword_tasks") or []
            unranked = []

            for t in tasks:
                pkey = t.get("product_key", "")
                rank = t.get("last_rank")
                kw = t.get("keyword", "")

                # 상품군 분류 매칭
                is_match = False
                if product_choice == "none":
                    # 자동 감지 모드일 때는 모든 카테고리의 키워드를 불러옵니다.
                    is_match = True
                elif product_choice == "auto":
                    if pkey in ("permacoat", "coating_a", "coating_b", "coating_c", "coating_d", "coating_general"):
                        is_match = True
                elif product_choice == "bike":
                    if pkey == "bike_coating":
                        is_match = True
                elif product_choice == "living":
                    if pkey in ("living", "cleaner") or "리빙" in kw or "가구" in kw or "싱크" in kw or "욕실" in kw:
                        is_match = True

                if is_match:
                    # 미노출/520위 밖 조건
                    if rank is None or rank == 0 or rank > 500 or str(rank).strip() in ("", "None"):
                        unranked.append(kw)

            # 중복 제거
            unranked = sorted(list(set(unranked)))

            if unranked:
                self.entry_keywords.delete(0, tk.END)
                self.entry_keywords.insert(0, ", ".join(unranked))
                self.log(f"      🔄 트래픽 미노출 키워드 {len(unranked)}개 동기화 완료: {', '.join(unranked)}")
                messagebox.showinfo("성공", f"현재 트래픽 프로그램에서 '미노출' 상태인 키워드 {len(unranked)}개를 자동으로 불러와서 본문에 설정했습니다.\n\n불러온 키워드: {', '.join(unranked)}")
            else:
                self.log(f"      ⚠️ 트래픽 미노출 키워드를 찾지 못했습니다. (선택된 상품: {product_choice})")
                messagebox.showinfo("알림", "트래픽 프로그램에서 해당 상품의 '미노출' 상태 키워드를 찾지 못했습니다. 모든 키워드가 순위권에 진입해 있거나 아직 1회 이상 탐색(check)이 실행되지 않았을 수 있습니다.")

        except Exception as e:
            self.log(f"❌ 트래픽 키워드 동기화 실패: {e}")
            messagebox.showerror("오류", f"동기화 도중 오류가 발생했습니다: {e}")

    def _flush_accounts_json(self) -> None:
        """평일 일과·배치 실행 전 GUI 값을 accounts.json에 저장."""
        data = {
            "gemini_key": self._get_entry_or_accounts("entry_gemini_key", "gemini_key"),
            "tistory_id": self._get_entry_or_accounts("entry_t_id", "tistory_id"),
            "tistory_pw": self._get_entry_or_accounts("entry_t_pw", "tistory_pw"),
            "naver_id1": self._get_entry_or_accounts("entry_n_id1", "naver_id1"),
            "naver_pw1": self._get_entry_or_accounts("entry_n_pw1", "naver_pw1"),
            "naver_id2": self._get_entry_or_accounts("entry_n_id2", "naver_id2"),
            "naver_pw2": self._get_entry_or_accounts("entry_n_pw2", "naver_pw2"),
            "vertex_project_id": self._get_entry_or_accounts("entry_proj_id", "vertex_project_id"),
            "vertex_api_key": self._get_entry_or_accounts("entry_vx_key", "vertex_api_key"),
            "master_guidelines": self.master_guidelines_text.get("1.0", tk.END).strip()
            if hasattr(self, "master_guidelines_text")
            else "",
            "text_provider": getattr(self, "text_provider_var", None).get()
            if getattr(self, "text_provider_var", None)
            else "로컬 Ollama (무료)",
            "image_provider": getattr(self, "image_provider_var", None).get()
            if getattr(self, "image_provider_var", None)
            else "Gen AI (Gemini 이미지)",
            "use_naver1": bool(getattr(self, "use_naver1_var", None) and self.use_naver1_var.get()),
            "use_naver2": bool(getattr(self, "use_naver2_var", None) and self.use_naver2_var.get()),
            "use_tistory": bool(getattr(self, "use_tistory_var", None) and self.use_tistory_var.get()),
            "use_google": bool(getattr(self, "use_google_var", None) and self.use_google_var.get()),
            "enable_intent_planner": bool(getattr(self, "enable_intent_planner_var", None) and self.enable_intent_planner_var.get()),
            "enable_quality_guard": bool(getattr(self, "enable_quality_guard_var", None) and self.enable_quality_guard_var.get()),
            "keywords": self.entry_keywords.get().strip() if hasattr(self, "entry_keywords") else "",
            "post_type": (self.post_type_var.get() or "제품 홍보").strip()
            if hasattr(self, "post_type_var")
            else "제품 홍보",
            "product_choice": self.product_choice_var.get()
            if getattr(self, "product_choice_var", None)
            else "duracoat",
            "product_url": self.product_url_entry.get().strip()
            if getattr(self, "product_url_entry", None)
            else "",
            "vercel_api_url": self.entry_vercel_api.get().strip()
            if getattr(self, "entry_vercel_api", None)
            else "",
            "vercel_webhook_secret": self.entry_vercel_secret.get().strip()
            if getattr(self, "entry_vercel_secret", None)
            else "",
            "vercel_enabled": bool(getattr(self, "vercel_enabled_var", None) and self.vercel_enabled_var.get()),
            "vercel_on_publish": bool(getattr(self, "vercel_on_publish_var", None) and self.vercel_on_publish_var.get()),
            "vercel_interval_minutes": int(self.spin_vercel_interval.get())
            if getattr(self, "spin_vercel_interval", None)
            else 20,
            "vercel_mode": self.vercel_mode_var.get()
            if getattr(self, "vercel_mode_var", None)
            else "local",
            "count": int(self.spin_count.get()) if hasattr(self, "spin_count") else 1,
        }
        try:
            with open(self.cred_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"⚠️ accounts.json 저장 실패: {e}")

    def save_and_link(self):
        tp_label = ""
        if getattr(self, "text_provider_var", None):
            try:
                tp_label = self.text_provider_var.get() or ""
            except Exception:
                tp_label = ""
        use_gemini_text = "Gemini" in tp_label and "Ollama" not in tp_label.split("→")[0]
        use_claude = "클로드" in tp_label or "Claude Code" in tp_label
        gemini_key = self.entry_gemini_key.get().strip()
        has_naver = bool(self.entry_n_id1.get().strip()) or bool(self.entry_n_id2.get().strip())

        if use_gemini_text and not gemini_key:
            messagebox.showwarning("주의", "Gemini API 키를 입력해 주세요.")
            return
        if not gemini_key and not has_naver:
            messagebox.showwarning("주의", "네이버 계정 정보를 입력하거나 Gemini API 키를 입력해 주세요.")
            return

        if gemini_key or has_naver or use_claude:
            # 계정 및 주요 설정 자동 저장
            data = {
                "gemini_key": gemini_key,
                "tistory_id": self.entry_t_id.get().strip(),
                "tistory_pw": self.entry_t_pw.get().strip(),
                "naver_id1": self.entry_n_id1.get().strip(),
                "naver_pw1": self.entry_n_pw1.get().strip(),
                "naver_id2": self.entry_n_id2.get().strip(),
                "naver_pw2": self.entry_n_pw2.get().strip(),
                "vertex_project_id": self.entry_proj_id.get().strip(),
                "vertex_api_key": self.entry_vx_key.get().strip(),
                # 구글 계정 메모용 저장 (Blogger OAuth에는 직접 사용되지 않음)
                "google_id": getattr(self, "entry_g_id", None).get().strip() if hasattr(self, "entry_g_id") else "",
                "google_pw": getattr(self, "entry_g_pw", None).get().strip() if hasattr(self, "entry_g_pw") else "",
                # 공통 글쓰기 마스터 지침
                "master_guidelines": self.master_guidelines_text.get("1.0", tk.END).strip()
                if hasattr(self, "master_guidelines_text") else "",
                "text_provider": getattr(self, "text_provider_var", None).get() if getattr(self, "text_provider_var", None) else "로컬 Ollama (무료)",
                "image_provider": getattr(self, "image_provider_var", None).get() if getattr(self, "image_provider_var", None) else "Gen AI (Gemini 이미지)",
                "use_naver1": getattr(self, "use_naver1_var", None).get() if getattr(self, "use_naver1_var", None) else True,
                "use_naver2": getattr(self, "use_naver2_var", None).get() if getattr(self, "use_naver2_var", None) else True,
                "use_tistory": getattr(self, "use_tistory_var", None).get() if getattr(self, "use_tistory_var", None) else True,
                "use_google": getattr(self, "use_google_var", None).get() if getattr(self, "use_google_var", None) else False,
                "enable_intent_planner": getattr(self, "enable_intent_planner_var", None).get() if getattr(self, "enable_intent_planner_var", None) else True,
                "enable_quality_guard": getattr(self, "enable_quality_guard_var", None).get() if getattr(self, "enable_quality_guard_var", None) else True,
                "keywords": self.entry_keywords.get().strip() if hasattr(self, "entry_keywords") else "",
                "post_type": (self.post_type_var.get() or "제품 홍보").strip()
                if hasattr(self, "post_type_var")
                else "제품 홍보",
                "product_choice": self.product_choice_var.get()
                if getattr(self, "product_choice_var", None)
                else "none",
                "product_url": self.product_url_entry.get().strip()
                if getattr(self, "product_url_entry", None)
                else "",
                "vercel_api_url": self.entry_vercel_api.get().strip()
                if getattr(self, "entry_vercel_api", None)
                else "",
                "vercel_webhook_secret": self.entry_vercel_secret.get().strip()
                if getattr(self, "entry_vercel_secret", None)
                else "",
                "vercel_enabled": bool(getattr(self, "vercel_enabled_var", None) and self.vercel_enabled_var.get()),
                "vercel_on_publish": bool(getattr(self, "vercel_on_publish_var", None) and self.vercel_on_publish_var.get()),
                "vercel_interval_minutes": int(self.spin_vercel_interval.get())
                if getattr(self, "spin_vercel_interval", None)
                else 20,
                "vercel_mode": self.vercel_mode_var.get()
                if getattr(self, "vercel_mode_var", None)
                else "cloud",
                "count": int(self.spin_count.get()) if hasattr(self, "spin_count") else 1,
            }
            try:
                with open(self.cred_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

            # --- Blogger 브라우저 자동화용 환경 변수도 함께 설정 ---
            try:
                import os as _os
                if hasattr(self, "entry_g_id"):
                    _os.environ["BLOGGER_ACCOUNT_EMAIL"] = self.entry_g_id.get().strip()
                if hasattr(self, "entry_g_pw"):
                    _os.environ["BLOGGER_PASSWORD"] = self.entry_g_pw.get().strip()
            except Exception:
                # 환경 변수 설정 실패는 치명적이지 않으므로 무시
                pass

            self._sync_connection_status()

            def _after_save_verify():
                tp = data.get("text_provider") or ""
                use_gemini = "Gemini" in tp and "Ollama" not in tp.split("→")[0]
                use_claude_save = "클로드" in tp or "Claude Code" in tp
                if use_claude_save:
                    async def _check_claude():
                        return await _content_gen().verify_claude_code()

                    try:
                        ok, msg = asyncio.run(_check_claude())
                    except Exception as e:
                        ok, msg = False, str(e)
                    if ok:
                        messagebox.showinfo(
                            "성공",
                            "계정 정보가 저장되었습니다.\n"
                            "글 생성: Claude Code CLI\n\n"
                            "자동화 탭에서 [🚀 자동화 시작] 버튼을 눌러 작업을 시작해 주세요.",
                        )
                    else:
                        messagebox.showwarning(
                            "Claude Code 확인",
                            f"설정은 저장되었으나 Claude Code 연동 확인에 실패했습니다.\n{msg[:300]}",
                        )
                    return
                if not use_gemini or _content_gen()._api_sparing_enabled():
                    engine = "로컬 Ollama" if "Ollama" in tp else "로컬 엔진"
                    messagebox.showinfo(
                        "성공",
                        f"계정 정보가 저장되었습니다.\n"
                        f"글 생성: {engine} (유료 Gemini API 사용 안 함)\n\n"
                        "자동화 탭에서 [🚀 자동화 시작] 버튼을 눌러 작업을 시작해 주세요.",
                    )
                    return

                keys = []
                for field in ("gemini_key", "vertex_api_key"):
                    k = (data.get(field) or "").strip()
                    if k and k not in keys:
                        keys.append(k)

                async def _check():
                    return await _content_gen().verify_gemini_api_keys(keys)

                try:
                    ok, msg = asyncio.run(_check())
                except Exception as e:
                    ok, msg = False, str(e)

                if ok:
                    messagebox.showinfo(
                        "성공",
                        f"계정 및 API 정보가 저장되었습니다.\n{msg}\n\n"
                        "자동화 탭에서 [🚀 자동화 시작] 버튼을 눌러 작업을 시작해 주세요.",
                    )
                elif "429" in msg or "prepayment" in msg.lower() or "resource_exhausted" in msg.lower():
                    messagebox.showwarning(
                        "Gemini 크레딧 없음",
                        "등록한 Gemini API 키는 저장되었지만 선불 크레딧이 없습니다.\n\n"
                        "같은 Google 프로젝트에서 새로 만든 키도 크레딧을 공유합니다.\n"
                        "AI Studio(https://aistudio.google.com)에서 충전하거나\n"
                        "다른 계정/프로젝트의 API 키를 입력한 뒤 다시 저장해 주세요.\n\n"
                        "자동화는 로컬 Ollama로 글 작성을 시도합니다.",
                    )
                else:
                    messagebox.showwarning(
                        "Gemini 연동 확인 실패",
                        f"키 저장은 완료되었으나 API 호출에 실패했습니다.\n{msg[:240]}",
                    )
            threading.Thread(target=_after_save_verify, daemon=True).start()

    def log(self, msg, level="info"):
        """스레드 안전: 백그라운드 스레드에서 호출 시 main thread로 전달하여 GUI 멈춤 방지"""
        def _do_log():
            now = datetime.now().strftime("%H:%M:%S")
            line = f"[{now}] {msg}"
            try:
                log_path = os.path.join(self.base_dir, "_automation.log")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass
            if not hasattr(self, "log_area"):
                return
            self.log_area.insert(tk.END, line + "\n")
            self.log_area.see(tk.END)
            try:
                self.log_area.update_idletasks()
            except Exception:
                pass
        try:
            if threading.current_thread() is threading.main_thread():
                _do_log()
            else:
                self.root.after(0, _do_log)
        except Exception:
            pass

    def log_neighbor(self, msg):
        """서이추 탭 전용 진행 로그 (스레드 안전). 화면에 바로 반영되도록 update_idletasks 호출."""
        if not hasattr(self, "neighbor_log_area"):
            return
        def _do():
            try:
                now = datetime.now().strftime("%H:%M:%S")
                self.neighbor_log_area.insert(tk.END, f"[{now}] {msg}\n")
                self.neighbor_log_area.see(tk.END)
                self.neighbor_log_area.update_idletasks()
            except Exception:
                pass
        try:
            if threading.current_thread() is threading.main_thread():
                _do()
            else:
                self.root.after(0, _do)
        except Exception:
            pass

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.btn_pause.config(text="▶ 재개하기", bg="#27ae60")
            self.log("⏸ [일시정지] 작업이 멈췄습니다. 수동 수정 후 '재개하기'를 눌러주세요.")
        else:
            self.btn_pause.config(text="⏸ 일시정지", bg="#f39c12")
            self.log("▶ [재개] 완료! 다음 단계로 진행합니다.")

    def _ask_yesno_on_main(self, title, message):
        """messagebox.askyesno를 메인 스레드에서 실행 (데드락 방지). 결과 반환."""
        result = [None]  # mutable container for closure
        evt = threading.Event()
        def _show():
            try:
                result[0] = messagebox.askyesno(title, message)
            finally:
                evt.set()
        self.root.after(0, _show)
        evt.wait(timeout=120)  # 최대 2분
        return result[0] if result[0] is not None else False

    def refresh_neighbor_stats(self):
        """neighbor_actions.csv에서 오늘 날짜 기준 서이추 통계를 읽어와 테이블에 표시."""
        # 테이블 초기화
        for item in self.neighbor_stats_tree.get_children():
            self.neighbor_stats_tree.delete(item)

        csv_path = os.path.join(self.base_dir, "neighbor_actions.csv")
        if not os.path.exists(csv_path):
            self.log("ℹ️ [서이추 통계] neighbor_actions.csv 파일이 없습니다.")
            self.log_neighbor("ℹ️ [서이추 통계] neighbor_actions.csv 파일이 없습니다.")
            return

        today = datetime.now().date()
        stats = {}  # account -> {"success": int, "fail": int}

        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                # 기대 헤더: timestamp,account,action_type,page,index,post_url,author,title,ok,error
                for row in reader:
                    if len(row) < 9:
                        continue
                    try:
                        ts = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        continue
                    if ts.date() != today:
                        continue
                    account = row[1] or "-"
                    ok_flag = row[8] == "1"
                    if account not in stats:
                        stats[account] = {"success": 0, "fail": 0}
                    if ok_flag:
                        stats[account]["success"] += 1
                    else:
                        stats[account]["fail"] += 1
        except Exception as e:
            self.log(f"❌ [서이추 통계] CSV 읽기 오류: {e}")
            self.log_neighbor(f"❌ [서이추 통계] CSV 읽기 오류: {e}")
            return

        # 계정별 행 추가
        total_success = 0
        total_fail = 0
        for account, data in stats.items():
            s = data["success"]
            f = data["fail"]
            total_success += s
            total_fail += f
            self.neighbor_stats_tree.insert(
                "",
                tk.END,
                values=(account, s, f, s + f),
            )

        # 전체 합계 행
        if stats:
            self.neighbor_stats_tree.insert(
                "",
                tk.END,
                values=("전체", total_success, total_fail, total_success + total_fail),
            )
        else:
            self.log("ℹ️ [서이추 통계] 오늘 날짜의 기록이 없습니다.")
            self.log_neighbor("ℹ️ [서이추 통계] 오늘 날짜의 기록이 없습니다.")

    def _set_neighbor_running(self, running: bool, task_msg: str | None = None):
        """서이추 실행 상태 바를 육안으로 구분되게 갱신 (실행 중=초록, 대기=회색)."""
        if not hasattr(self, "neighbor_status_strip_border"):
            return
        if running:
            self.neighbor_status_strip_border.config(bg="#22c55e")
            for w in (self.neighbor_status_strip, self.neighbor_strip_inner, self.neighbor_status_dot_label, self.neighbor_current_task_label):
                try: w.config(bg="#0f172a")
                except Exception: pass
            self.neighbor_status_dot_label.config(text="● 실행 중", fg="#22c55e", bg="#0f172a")
            self.neighbor_current_task_label.config(bg="#0f172a")
        else:
            self.neighbor_status_strip_border.config(bg="#4b5563")
            for w in (self.neighbor_status_strip, self.neighbor_strip_inner, self.neighbor_status_dot_label, self.neighbor_current_task_label):
                try: w.config(bg="#1f2937")
                except Exception: pass
            self.neighbor_status_dot_label.config(text="● 대기 중", fg="#9ca3af", bg="#1f2937")
            self.neighbor_current_task_label.config(text="현재 작업: —", bg="#1f2937")
        if task_msg is not None and hasattr(self, "neighbor_current_task_label"):
            self.neighbor_current_task_label.config(text="현재 작업: " + task_msg)

    def _set_neighbor_task(self, msg: str):
        """현재 작업 내용만 갱신 (자동화 스레드에서 콜백으로 호출)."""
        if hasattr(self, "neighbor_current_task_label"):
            self.neighbor_current_task_label.config(text="현재 작업: " + msg)

    def start_neighbor_visit(self):
        """서이추 댓글 자동화를 별도 쓰레드에서 실행. 서이추 탭에서만 동작."""
        if self.current_tab != "neighbor":
            messagebox.showinfo("서이추 댓글", "서이추 실행은 서이추 댓글 탭에서만 가능합니다.")
            self.switch_tab("neighbor")
            return
        if not self.is_connected:
            messagebox.showwarning("오류", "먼저 설정 탭에서 네이버 계정을 연동해 주세요.")
            self.switch_tab("settings")
            return

        # 계정 선택
        acc_key = self.neighbor_account_var.get()
        if acc_key == "naver1":
            nid = self.entry_n_id1.get().strip()
            npw = self.entry_n_pw1.get().strip()
        else:
            nid = self.entry_n_id2.get().strip()
            npw = self.entry_n_pw2.get().strip()

        if not nid or not npw:
            messagebox.showwarning("오류", "선택한 네이버 계정의 ID / PW가 비어 있습니다.")
            return

        # 리스크/딜레이 값
        try:
            max_actions = int(self.neighbor_max_actions.get())
        except Exception:
            max_actions = 20
        try:
            min_delay = float(self.neighbor_min_delay.get())
        except Exception:
            min_delay = 4.0
        try:
            max_delay = float(self.neighbor_max_delay.get())
        except Exception:
            max_delay = 9.0
        if max_delay < min_delay:
            max_delay = min_delay + 1.0

        # 댓글 문구 리스트
        raw_msgs = self.neighbor_messages_text.get("1.0", tk.END).strip()
        msgs = [m.strip() for m in raw_msgs.splitlines() if m.strip()] if raw_msgs else None

        def neighbor_logger(msg):
            self.log(msg)
            self.log_neighbor(msg)

        self.log(f"🤝 [서이추 댓글] 계정 '{nid}'으로 이웃 새글 공감/댓글 자동화를 시작합니다.")
        self.log_neighbor("브라우저를 시작합니다. Chrome 창이 곧 나타납니다. 진행 로그는 아래에 실시간으로 표시됩니다.")
        self.log_neighbor(f"🤝 [서이추 댓글] 계정 '{nid}'으로 이웃 새글 공감/댓글 자동화를 시작합니다.")
        self.btn_neighbor_run.config(state="disabled", text="실행 중...")
        self.neighbor_status_label.config(text="브라우저 실행 중...", fg="#38bdf8")
        self._set_neighbor_running(True, "크롬 실행 중…")

        def status_cb(msg):
            self.root.after(0, lambda m=msg: self._set_neighbor_task(m))

        def worker():
            status_msg = "작업 완료"
            status_color = "#22c55e"
            try:
                from blog_automation_visit import run_blog_automation_for_account
                asyncio.run(
                    run_blog_automation_for_account(
                        naver_id=nid,
                        naver_pw=npw,
                        logger=neighbor_logger,
                        max_actions=max_actions,
                        min_delay=min_delay,
                        max_delay=max_delay,
                        messages=msgs,
                        status_callback=status_cb,
                    )
                )
            except Exception as e:
                err = str(e)
                self.log(f"❌ [서이추 댓글] 오류 발생: {err}")
                self.log_neighbor(f"❌ [서이추 댓글] 오류 발생: {err}")
                if "winerror 2" in err.lower() or "지정된 파일을 찾을 수 없습니다" in err:
                    self.log("   💡 run_fix_playwright.bat 실행 후 다시 시도하세요.")
                    self.log_neighbor("   💡 run_fix_playwright.bat 실행 후 다시 시도하세요.")
                status_msg = "오류 발생 – 로그를 확인하세요"
                status_color = "#f97373"
            finally:
                def _ui_update():
                    self._set_neighbor_running(False, None)
                    self.btn_neighbor_run.config(state="normal", text="🤝 서이추 댓글 자동 실행")
                    self.neighbor_status_label.config(text=status_msg, fg=status_color)
                self.root.after(0, _ui_update)

        threading.Thread(target=worker, daemon=True).start()

    def log_tistory(self, msg):
        """티스토리 탭 전용 진행 로그 (스레드 안전)."""
        if not hasattr(self, "tistory_log_area"):
            return
        def _do():
            try:
                now = datetime.now().strftime("%H:%M:%S")
                self.tistory_log_area.insert(tk.END, f"[{now}] {msg}\n")
                self.tistory_log_area.see(tk.END)
                self.tistory_log_area.update_idletasks()
            except Exception:
                pass
        try:
            if threading.current_thread() is threading.main_thread():
                _do()
            else:
                self.root.after(0, _do)
        except Exception:
            pass

    def _set_tistory_running(self, running: bool, task_msg: str | None = None):
        if not hasattr(self, "tistory_status_strip_border"):
            return
        if running:
            for w in (self.tistory_status_strip, self.tistory_strip_inner, self.tistory_status_dot_label, self.tistory_current_task_label):
                try: w.config(bg="#0f172a")
                except Exception: pass
            self.tistory_status_strip_border.config(bg="#22c55e")
            self.tistory_status_dot_label.config(text="● 실행 중", fg="#22c55e", bg="#0f172a")
            self.tistory_current_task_label.config(bg="#0f172a")
        else:
            for w in (self.tistory_status_strip, self.tistory_strip_inner, self.tistory_status_dot_label, self.tistory_current_task_label):
                try: w.config(bg="#1f2937")
                except Exception: pass
            self.tistory_status_strip_border.config(bg="#4b5563")
            self.tistory_status_dot_label.config(text="● 대기 중", fg="#9ca3af", bg="#1f2937")
            self.tistory_current_task_label.config(text="현재 작업: —", bg="#1f2937")
        if task_msg and hasattr(self, "tistory_current_task_label"):
            self.tistory_current_task_label.config(text="현재 작업: " + task_msg)

    def start_tistory_visit(self):
        """티스토리 구독·댓글 자동화를 별도 스레드에서 실행."""
        if self.current_tab != "tistory":
            messagebox.showinfo("티스토리 서이추", "티스토리 실행은 티스토리 서이추 탭에서만 가능합니다.")
            self.switch_tab("tistory")
            return
        t_id = (self.entry_t_id.get() or "").strip()
        t_pw = (self.entry_t_pw.get() or "").strip()
        if not t_id or not t_pw:
            messagebox.showwarning("오류", "설정 탭에서 티스토리(카카오) 이메일과 비밀번호를 입력해 주세요.")
            self.switch_tab("settings")
            return
        try:
            max_actions = int(self.tistory_max_actions.get())
        except Exception:
            max_actions = 20
        try:
            min_delay = float(self.tistory_min_delay.get())
        except Exception:
            min_delay = 4.0
        try:
            max_delay = float(self.tistory_max_delay.get())
        except Exception:
            max_delay = 9.0
        if max_delay < min_delay:
            max_delay = min_delay + 1.0
        raw_msgs = self.tistory_messages_text.get("1.0", tk.END).strip()
        msgs = [m.strip() for m in raw_msgs.splitlines() if m.strip()] if raw_msgs else None
        def tistory_logger(msg):
            self.log(msg)
            self.log_tistory(msg)
        self.log_tistory("티스토리 구독·댓글 자동화를 시작합니다. 브라우저가 곧 열립니다.")
        self.btn_tistory_run.config(state="disabled", text="실행 중...")
        self.tistory_status_label.config(text="브라우저 실행 중...", fg="#38bdf8")
        self._set_tistory_running(True, "티스토리 실행 중…")
        def status_cb(msg):
            self.root.after(0, lambda m=msg: self._set_tistory_task(m))
        def worker():
            try:
                from tistory_visit import run_tistory_neighbor_comment
                asyncio.run(run_tistory_neighbor_comment(
                    t_id=t_id, t_pw=t_pw, logger=tistory_logger,
                    status_callback=status_cb, max_actions=max_actions,
                    min_delay=min_delay, max_delay=max_delay, messages=msgs,
                ))
                status_msg, status_color = "작업 완료", "#22c55e"
            except Exception as e:
                err = str(e)
                self.log(f"❌ [티스토리] 오류: {err}")
                self.log_tistory(f"❌ [티스토리] 오류: {err}")
                if "winerror 2" in err.lower() or "지정된 파일을 찾을 수 없습니다" in err:
                    self.log("   💡 run_fix_playwright.bat 실행 후 다시 시도하세요.")
                    self.log_tistory("   💡 run_fix_playwright.bat 실행 후 다시 시도하세요.")
                status_msg, status_color = "오류 발생 – 로그 확인", "#f97373"
            finally:
                def _ui():
                    self._set_tistory_running(False, None)
                    self.btn_tistory_run.config(state="normal", text="📌 티스토리 구독·댓글 실행")
                    self.tistory_status_label.config(text=status_msg, fg=status_color)
                self.root.after(0, _ui)
        threading.Thread(target=worker, daemon=True).start()

    def _set_tistory_task(self, msg: str):
        if hasattr(self, "tistory_current_task_label"):
            self.tistory_current_task_label.config(text="현재 작업: " + msg)

    async def check_pause(self):
        # 일시정지 중이면 해제될 때까지 대기 (폴링 방식이 스레드 안전함)
        while self.is_paused:
            await asyncio.sleep(0.5)

    async def wait_with_pause(self, seconds):
        """일시정지 체크를 포함한 정밀 대기 (0.5초 단위로 쪼개어 체크)"""
        steps = int(seconds * 2)
        for _ in range(steps):
            await self.check_pause()
            await asyncio.sleep(0.5)
        if seconds % 0.5 > 0:
            await self.check_pause()
            await asyncio.sleep(seconds % 0.5)

    def _store_log(self, msg: str) -> None:
        if not hasattr(self, "store_result_area"):
            return
        def _ui():
            self.store_result_area.insert(tk.END, msg + "\n")
            self.store_result_area.see(tk.END)
        self.root.after(0, _ui)

    def run_store_marketing(self):
        """스마트스토어 마케팅 파이프라인 실행 (백그라운드)."""
        if getattr(self, "_store_running", False):
            messagebox.showinfo("안내", "이미 마케팅 에이전트가 실행 중입니다.")
            return
        api_key = ""
        if hasattr(self, "entry_gemini_key"):
            api_key = self.entry_gemini_key.get().strip()
        if not api_key:
            messagebox.showwarning("API 키 필요", "설정 탭에서 Gemini API 키를 입력한 뒤 저장해 주세요.")
            self.switch_tab("settings")
            return

        category = self.store_category_var.get().strip()
        concept = self.store_concept_text.get("1.0", tk.END).strip()
        seeds = [s.strip() for s in self.store_seed_entry.get().split(",") if s.strip()]
        do_crawl = self.store_crawl_var.get()
        use_pw = self.store_playwright_var.get()

        self._store_running = True
        self.btn_store_run.config(state="disabled", text="생성 중...")
        self.btn_store_apply.config(state="disabled")
        self.store_result_area.delete("1.0", tk.END)
        self._store_log("=== 스마트스토어 마케팅 에이전트 시작 ===")

        def worker():
            import asyncio
            from store_pipeline import run_store_pipeline

            try:
                result = asyncio.run(
                    run_store_pipeline(
                        concept,
                        category,
                        seed_keywords=seeds or None,
                        crawl=do_crawl,
                        use_playwright=use_pw,
                        api_key=api_key,
                        log_fn=self._store_log,
                    )
                )
            except Exception as e:
                result = {"ok": False, "error": str(e)}

            def _done():
                self._store_running = False
                self.btn_store_run.config(state="normal", text="🛒 마케팅 리포트 생성")
                if not result.get("ok"):
                    self._store_log(f"오류: {result.get('error', '알 수 없음')}")
                    messagebox.showerror("실패", result.get("error", "생성 실패"))
                    return
                report = result.get("report", "")
                self.store_result_area.delete("1.0", tk.END)
                self.store_result_area.insert(tk.END, report)
                tags = result.get("tags_for_blog", "")
                self._store_last_tags = tags
                if tags:
                    self._store_log(f"\n[블로그 키워드 추천] {tags}")
                    self.btn_store_apply.config(state="normal")
                self._store_log("\n=== 완료 ===")

            self.root.after(0, _done)

        threading.Thread(target=worker, daemon=True).start()

    def apply_store_tags_to_automation(self):
        """생성된 태그를 자동화 탭 키워드 입력란에 병합."""
        tags = getattr(self, "_store_last_tags", "") or ""
        if not tags and hasattr(self, "store_result_area"):
            from store_marketing_agent import parse_tags_from_report
            tags = parse_tags_from_report(self.store_result_area.get("1.0", tk.END))
        if not tags:
            messagebox.showinfo("안내", "반영할 태그가 없습니다. 먼저 리포트를 생성하세요.")
            return
        if hasattr(self, "entry_keywords"):
            cur = self.entry_keywords.get().strip()
            merged = tags if not cur else f"{cur}, {tags}"
            self.entry_keywords.delete(0, tk.END)
            self.entry_keywords.insert(0, merged)
        self.switch_tab("automation")
        self.log(f"🛒 스마트스토어 태그를 키워드에 반영했습니다: {tags[:80]}...")

    def _read_accounts_json(self) -> dict:
        try:
            if os.path.exists(self.cred_file):
                with open(self.cred_file, encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    def _get_entry_or_accounts(self, entry_attr: str, accounts_key: str, default: str = "") -> str:
        entry = getattr(self, entry_attr, None)
        if entry is not None:
            try:
                val = entry.get().strip()
                if val:
                    return val
            except Exception:
                pass
        return str(self._read_accounts_json().get(accounts_key) or default).strip()

    def _effective_master_guidelines(self, post_type: str | None = None) -> str:
        """GUI·accounts.json·Wiki 슬라이스를 글 유형에 맞게 병합."""
        user = ""
        if hasattr(self, "master_guidelines_text"):
            try:
                user = self.master_guidelines_text.get("1.0", tk.END).strip()
            except Exception:
                user = ""
        if not user:
            user = str(self._read_accounts_json().get("master_guidelines") or "").strip()
        pt = post_type
        if pt is None and hasattr(self, "post_type_var"):
            try:
                pt = self.post_type_var.get()
            except Exception:
                pt = ""
        try:
            from drawer.wiki import load_guidelines_for_task

            return load_guidelines_for_task(pt or "", user_master=user)
        except Exception:
            return user or self._default_master_guidelines()

    def _build_automation_config(self) -> dict:
        """자동화·원고 생성에 공통으로 쓰는 설정 dict (설정 탭 미방문 시 accounts.json 폴백)."""
        naver_ids: list[str] = []
        naver_pws: list[str] = []

        use_n1 = bool(getattr(self, "use_naver1_var", None) and self.use_naver1_var.get())
        use_n2 = bool(getattr(self, "use_naver2_var", None) and self.use_naver2_var.get())
        if use_n1:
            uid = self._get_entry_or_accounts("entry_n_id1", "naver_id1")
            upw = self._get_entry_or_accounts("entry_n_pw1", "naver_pw1")
            if uid:
                naver_ids.append(uid)
                naver_pws.append(upw)
        if use_n2:
            uid = self._get_entry_or_accounts("entry_n_id2", "naver_id2")
            upw = self._get_entry_or_accounts("entry_n_pw2", "naver_pw2")
            if uid:
                naver_ids.append(uid)
                naver_pws.append(upw)

        product_choice = "none"
        if getattr(self, "product_choice_var", None):
            try:
                product_choice = self.product_choice_var.get()
            except Exception:
                product_choice = "none"
        product_url = ""
        if getattr(self, "product_url_entry", None):
            try:
                product_url = self.product_url_entry.get().strip()
            except Exception:
                product_url = ""

        raw_keywords = [k.strip() for k in self.entry_keywords.get().split(",")]
        keywords = [k for k in raw_keywords if k]
        dedup_keywords = list(dict.fromkeys(keywords))

        post_type = "제품 홍보"
        if hasattr(self, "post_type_var") and getattr(self, "post_type_var", None):
            try:
                post_type = (self.post_type_var.get() or "").strip() or "제품 홍보"
            except Exception:
                pass

        tp_label = "로컬 Ollama (무료)"
        if getattr(self, "text_provider_var", None):
            try:
                tp_label = self.text_provider_var.get() or tp_label
            except Exception:
                pass
        ip_label = "Gen AI (Gemini 이미지)"
        if getattr(self, "image_provider_var", None):
            try:
                ip_label = self.image_provider_var.get() or ip_label
            except Exception:
                pass

        master = self._effective_master_guidelines(post_type)

        return {
            "gemini_key": self._get_entry_or_accounts("entry_gemini_key", "gemini_key"),
            "naver_ids": naver_ids,
            "naver_pws": naver_pws,
            "n2_id": self._get_entry_or_accounts("entry_n_id2", "naver_id2"),
            "n2_pw": self._get_entry_or_accounts("entry_n_pw2", "naver_pw2"),
            "tistory_id": self._get_entry_or_accounts("entry_t_id", "tistory_id"),
            "tistory_pw": self._get_entry_or_accounts("entry_t_pw", "tistory_pw"),
            "use_naver1": use_n1,
            "use_naver2": use_n2,
            "use_tistory": bool(getattr(self, "use_tistory_var", None) and self.use_tistory_var.get()),
            "use_google": bool(getattr(self, "use_google_var", None) and self.use_google_var.get()),
            "enable_intent_planner": bool(getattr(self, "enable_intent_planner_var", None) and self.enable_intent_planner_var.get()),
            "enable_quality_guard": bool(getattr(self, "enable_quality_guard_var", None) and self.enable_quality_guard_var.get()),
            "manual_confirm": bool(getattr(self, "manual_confirm_var", None) and self.manual_confirm_var.get()),
            "vertex_api_key": self._get_entry_or_accounts("entry_vx_key", "vertex_api_key", cfg.VERTEX_API_KEY),
            "vertex_project_id": self._get_entry_or_accounts("entry_proj_id", "vertex_project_id", cfg.VERTEX_PROJECT_ID),
            "vertex_json": cfg.VERTEX_JSON_PATH,
            "keywords": dedup_keywords,
            "post_type": post_type,
            "product_choice": product_choice,
            "product_url": product_url,
            "text_provider": {
                "Gemini API (유료)": "gemini",
                "Gemini API (유료·현재 기본)": "gemini",
                "로컬 Ollama (무료)": "ollama",
                "클로드 코드 (Claude Code)": "claude",
                "자동 (Ollama → Gemini)": "auto",
            }.get(tp_label, "ollama"),
            "image_provider": {
                "Gen AI (Gemini 이미지)": "genai",
                "Gen AI": "genai",
                "자동 (Gen AI → Vertex → 무료)": "auto",
                "자동 (Gen AI → Vertex)": "auto",
                "로컬 무료 (Pollinations)": "free",
                "로컬 무료 (Pollinations → Pillow)": "free",
                "Pillow 플레이스홀더 (테스트용)": "pillow",
                "Pillow 플레이스홀더": "pillow",
                "Vertex AI": "vertex",
            }.get(ip_label, "genai"),
            "mode": "immediate",
            "count": int(self.spin_count.get()),
            "gap": int(self.spin_gap.get()),
            "writing_guidelines": "",
            "master_guidelines": master,
        }

    def _get_vercel_config_from_ui(self) -> dict:
        from vercel_traffic_client import load_vercel_config

        cfg = load_vercel_config(self.cred_file)
        if getattr(self, "entry_vercel_api", None):
            cfg["vercel_api_url"] = self.entry_vercel_api.get().strip()
        if getattr(self, "entry_vercel_secret", None):
            cfg["vercel_webhook_secret"] = self.entry_vercel_secret.get().strip()
        if getattr(self, "vercel_enabled_var", None):
            cfg["vercel_enabled"] = bool(self.vercel_enabled_var.get())
        if getattr(self, "vercel_on_publish_var", None):
            cfg["vercel_on_publish"] = bool(self.vercel_on_publish_var.get())
        if getattr(self, "spin_vercel_interval", None):
            try:
                cfg["vercel_interval_minutes"] = int(self.spin_vercel_interval.get())
            except Exception:
                pass
        if getattr(self, "vercel_mode_var", None):
            cfg["vercel_mode"] = self.vercel_mode_var.get() or "local"
        else:
            cfg["vercel_mode"] = cfg.get("vercel_mode") or "local"
        if getattr(self, "product_url_entry", None):
            cfg["product_url"] = self.product_url_entry.get().strip()
        return cfg

    def on_automation_complete(self, config: dict, *, success: bool = True) -> None:
        """발행 성공 후에만(선택) Vercel 트래픽 실행."""
        if not success:
            return
        self._run_vercel_traffic_after_publish(config)

    def _update_vercel_status_label(self, text: str) -> None:
        if getattr(self, "lbl_vercel_status", None):
            self.lbl_vercel_status.config(text=text)

    def vercel_health_check(self) -> None:
        def _worker():
            from vercel_traffic_client import health_check

            self._flush_accounts_json()
            cfg = self._get_vercel_config_from_ui()
            try:
                result = health_check(cfg)
                if result.get("ok"):
                    body = result.get("body") or {}
                    msg = body.get("message") or "정상"
                    self.root.after(0, lambda: self.log(f"   ☁️ Vercel 헬스체크 OK — {msg}"))
                    self.root.after(0, lambda: self._update_vercel_status_label("헬스: 정상"))
                else:
                    self.root.after(0, lambda: self.log(f"   ⚠️ Vercel 헬스체크 실패: {result}"))
                    self.root.after(0, lambda: self._update_vercel_status_label("헬스: 실패"))
            except Exception as exc:
                self.root.after(0, lambda: self.log(f"   ❌ Vercel 헬스체크 오류: {exc}"))
                self.root.after(0, lambda: self._update_vercel_status_label("헬스: 오류"))

        threading.Thread(target=_worker, daemon=True).start()

    def vercel_trigger_once(self) -> None:
        def _worker():
            from vercel_traffic_client import trigger_traffic

            self._flush_accounts_json()
            cfg = self._get_vercel_config_from_ui()
            try:
                outcome = trigger_traffic(config=cfg, log=self.log)
                if outcome.get("ok"):
                    self.root.after(0, lambda: self.log("   ✅ Vercel 트래픽 1회 완료"))
                    self.root.after(0, lambda: self._update_vercel_status_label("최근: 성공"))
                else:
                    self.root.after(0, lambda: self.log(f"   ⚠️ Vercel 트래픽 실패: {outcome}"))
                    self.root.after(0, lambda: self._update_vercel_status_label("최근: 실패"))
            except Exception as exc:
                self.root.after(0, lambda: self.log(f"   ❌ Vercel 트래픽 오류: {exc}"))
                self.root.after(0, lambda: self._update_vercel_status_label("최근: 오류"))

        threading.Thread(target=_worker, daemon=True).start()

    def toggle_vercel_scheduler(self) -> None:
        from vercel_traffic_client import VercelTrafficScheduler

        if self._vercel_scheduler and self._vercel_scheduler.running:
            self._vercel_scheduler.stop()
            self._vercel_scheduler = None
            if getattr(self, "btn_vercel_scheduler", None):
                self.btn_vercel_scheduler.config(text="주기 실행 시작")
            self._update_vercel_status_label("주기: 중지")
            self.log("   ☁️ Vercel 주기 실행 중지")
            return

        self._flush_accounts_json()
        cfg = self._get_vercel_config_from_ui()
        if not cfg.get("vercel_enabled"):
            messagebox.showwarning("Vercel", "먼저 '트래픽 사용'을 켜 주세요.")
            return
        mode = (cfg.get("vercel_mode") or "local").lower()
        if mode in ("cloud", "both") and not cfg.get("vercel_api_url"):
            messagebox.showwarning("Vercel", "API URL을 입력해 주세요.")
            return

        self._vercel_scheduler = VercelTrafficScheduler(
            get_config=self._get_vercel_config_from_ui,
            get_target_url=lambda: self.product_url_entry.get().strip()
            if getattr(self, "product_url_entry", None)
            else "",
            log=self.log,
        )
        self._vercel_scheduler.start()
        if getattr(self, "btn_vercel_scheduler", None):
            self.btn_vercel_scheduler.config(text="주기 실행 중지")
        mins = cfg.get("vercel_interval_minutes", 20)
        self._update_vercel_status_label(f"주기: {mins}분")
        self.log(f"   ☁️ Vercel 주기 실행 시작 ({mins}분 간격)")

    def _run_vercel_traffic_after_publish(self, config: dict) -> None:
        cfg = self._get_vercel_config_from_ui()
        if not cfg.get("vercel_enabled") or not cfg.get("vercel_on_publish"):
            return
        target = (config.get("product_url") or cfg.get("product_url") or "").strip()
        if not target:
            return
        mode = str(cfg.get("vercel_mode") or "local").lower()
        if mode in ("cloud", "both") and not str(cfg.get("vercel_api_url") or "").strip():
            self.log("   ☁️ Vercel 클라우드 모드 — API URL 없음, 트래픽 생략")
            return

        def _worker():
            from vercel_traffic_client import trigger_traffic

            try:
                self.log(f"   ☁️ 발행 연동 트래픽: {target}")
                outcome = trigger_traffic(target, config=cfg, log=self.log)
                if outcome.get("ok"):
                    self.log("   ✅ 발행 연동 Vercel 트래픽 완료")
                else:
                    self.log(f"   ⚠️ 발행 연동 Vercel 트래픽 실패: {outcome}")
            except Exception as exc:
                self.log(f"   ❌ 발행 연동 Vercel 트래픽 오류: {exc}")

        threading.Thread(target=_worker, daemon=True).start()

    def start_draft_writing(self):
        """네이버·Playwright 없이 원고+이미지만 생성해 drafts/에 저장."""
        if self.is_processing:
            self.log("      ⚠️ 이미 작업 중입니다.")
            return
        raw = [k.strip() for k in self.entry_keywords.get().split(",") if k.strip()]
        if not raw:
            messagebox.showwarning("오류", "키워드를 입력해 주세요.")
            return
        keyword = raw[0]
        config = self._build_automation_config()
        config["keywords"] = [keyword]
        config["count"] = 1

        self.switch_tab("automation")
        self.log(f"=== 원고+이미지 생성 (발행 없음): '{keyword}' ===")
        self.log(f"   글 유형: {config.get('post_type')}")
        self.log(f"   텍스트: {config.get('text_provider')} | 이미지: {config.get('image_provider')}")
        self._update_quality_status(None)

        self.is_processing = True
        self.btn_run.config(state="disabled")
        if hasattr(self, "btn_draft"):
            self.btn_draft.config(state="disabled", text="원고 생성 중...")

        def _reset():
            self.is_processing = False
            self.btn_run.config(state="normal")
            if hasattr(self, "btn_draft"):
                self.btn_draft.config(state="normal", text="✍ 원고+이미지 생성")

        def _worker():
            try:
                asyncio.run(self._async_run_draft(keyword, config))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"❌ 원고 생성 오류: {e}"))
            finally:
                self.root.after(0, _reset)

        threading.Thread(target=_worker, daemon=True).start()

    async def _async_run_draft(self, keyword: str, config: dict):
        from draft_blog import save_draft

        gen = _content_gen()
        if config.get("text_provider") == "ollama":
            await gen.ollama_warmup(self.log)

        self.log("   [1/3] 제목·개요·이미지 장면 설명...")
        title, outline, image_desc = await self.generate_outline(config, keyword, keyword)
        self.log(f"   제목: {title}")
        if image_desc:
            self.log(f"   이미지 장면: {image_desc[:120]}...")

        self.log("   [2/3] 본문 작성...")
        body, tags = await self.generate_body_from_outline(
            config, title, outline, keyword, keyword
        )
        self.log(f"   본문 길이: {len(body)}자")

        self.log("   [3/3] 키워드·개요 맞춤 AI 이미지...")
        paths = await self.generate_images(
            config, keyword, keyword, title=title, image_desc=image_desc
        )
        if paths:
            self.log(f"   이미지 저장: {paths[0]}")
        else:
            self.log("   ⚠️ 이미지 없음 — 설정 탭 Gemini API 키 또는 Pillow 플레이스홀더 엔진 사용")

        md_path = save_draft(
            keyword=keyword,
            title=title,
            outline=outline,
            body=body,
            tags=tags,
            image_desc=image_desc or "",
            image_paths=paths or [],
        )
        self.log(f"✅ 초안 저장: {md_path}")
        self.root.after(
            0,
            lambda: messagebox.showinfo("완료", f"원고가 저장되었습니다.\n\n{md_path}"),
        )

    def start_daily_weekday(self):
        """월~금: 글쓰기 + hymini1↔hymini11 서로이웃·답글 + 티스토리."""
        if self.is_processing:
            self.log("      ⚠️ 이미 작업 중입니다.")
            return
        if not self.is_connected:
            messagebox.showwarning("오류", "먼저 설정 탭에서 계정을 연동해 주세요.")
            self.switch_tab("settings")
            return

        from datetime import datetime

        if datetime.now().weekday() >= 5:
            if not messagebox.askyesno(
                "평일 일과",
                "오늘은 주말입니다.\n그래도 평일 일과(글쓰기·서로이웃·답글)를 실행할까요?",
            ):
                return

        self._flush_accounts_json()
        self.switch_tab("automation")
        self.log("=== 📅 평일 일과 시작 (월~금 루틴) ===")
        self.log("   1) hymini1 · hymini11 · 티스토리 글 발행")
        self.log("   2) 네이버 서로이웃 + 상대 최신 글 답글")
        self.log("   3) 티스토리 피드 구독·댓글")

        self.is_processing = True
        self.btn_run.config(state="disabled")
        if hasattr(self, "btn_weekday"):
            self.btn_weekday.config(state="disabled", text="평일 일과 실행 중…")

        def _reset():
            self.is_processing = False
            self.btn_run.config(state="normal")
            if hasattr(self, "btn_weekday"):
                self.btn_weekday.config(state="normal", text="📅 평일 일과")

        def _worker():
            try:
                from blog_daily_weekday import run_daily_weekday

                code = run_daily_weekday(force=True)
                self.root.after(
                    0,
                    lambda: self.log(
                        "✅ 평일 일과 완료" if code == 0 else f"⚠️ 평일 일과 종료 (코드 {code})"
                    ),
                )
            except Exception as e:
                self.root.after(0, lambda: self.log(f"❌ 평일 일과 오류: {e}"))
            finally:
                self.root.after(0, _reset)

        import threading

        threading.Thread(target=_worker, daemon=True).start()

    def start_processing(self):
        if self.is_processing:
            self.log("      ⚠️ 이미 자동화가 실행 중입니다. 중복 실행을 건너뜁니다.")
            return
        if not self.is_connected:
            messagebox.showwarning("오류", "먼저 설정 탭에서 계정을 연동해 주세요.")
            self.switch_tab("settings")
            return

        config = self._build_automation_config()
        from blog_constants import validate_automation_subject

        ok, err = validate_automation_subject(config)
        if not ok:
            messagebox.showwarning("주제 선택 필요", err)
            self.log(f"      ⚠️ {err}")
            return
        
        self.switch_tab("automation")
        self.log("=== 자동화 시작 요청 ===")
        self.log(f"   발행 대상: 네이버1={self.use_naver1_var.get()}, 네이버2={self.use_naver2_var.get()}, 티스토리={self.use_tistory_var.get()}, 구글={self.use_google_var.get()}")
        self.log(
            f"   최적화 옵션: 의도분석={bool(getattr(self, 'enable_intent_planner_var', None) and self.enable_intent_planner_var.get())}, "
            f"품질검사={bool(getattr(self, 'enable_quality_guard_var', None) and self.enable_quality_guard_var.get())}"
        )
        tp_label = getattr(self, "text_provider_var", None).get() if getattr(self, "text_provider_var", None) else "Gemini"
        self.log(f"   글 생성 엔진: {tp_label} (Ollama 선택 시 원고 생성에 수 분 걸릴 수 있습니다)")
        self._update_quality_status(None)

        import os as _os

        tp_engine = config.get("text_provider") or "gemini"
        if tp_engine == "gemini":
            _os.environ["BLOG_API_SPARING"] = "0"
            _os.environ["BLOG_TEXT_PROVIDER"] = "gemini"
        elif tp_engine == "ollama":
            _os.environ["BLOG_TEXT_PROVIDER"] = "ollama"
        elif tp_engine == "claude":
            _os.environ["BLOG_TEXT_PROVIDER"] = "claude"
        self._flush_accounts_json()

        self.is_processing = True
        self.btn_run.config(state='disabled', text="작업 중...")
        if hasattr(self, "btn_draft"):
            self.btn_draft.config(state="disabled")
        self.btn_pause.config(state='normal')

        def _automation_worker():
            try:
                asyncio.run(_run_main_loop()(self, config))
            except Exception as exc:
                self.root.after(0, lambda: self.log(f"❌ 자동화 스레드 오류: {exc}"))
            finally:
                def _reset_ui():
                    self.is_processing = False
                    self.btn_run.config(state="normal", text="🚀 자동화 시작")
                    if hasattr(self, "btn_draft"):
                        self.btn_draft.config(state="normal", text="✍ 원고+이미지 생성")
                    if hasattr(self, "btn_pause"):
                        self.btn_pause.config(state="disabled")

                self.root.after(0, _reset_ui)

        threading.Thread(target=_automation_worker, daemon=True).start()

    async def generate_images(self, config, required_keyword, extra_keyword=None, title=None, image_desc=None):
        gen = _content_gen()
        return await gen.generate_images(config, required_keyword, extra_keyword, self.log, self.image_dir, title=title, image_desc=image_desc)

    async def generate_outline(self, config, required_keyword, extra_keyword=None):
        master = config.get("master_guidelines") if isinstance(config, dict) and config.get("master_guidelines") else None
        if not master:
            master = self._effective_master_guidelines(
                (config or {}).get("post_type") if isinstance(config, dict) else None
            )
        return await _content_gen().generate_outline(config, required_keyword, extra_keyword, self.log, master)

    async def generate_body_from_outline(self, config, title, outline_str, required_keyword, extra_keyword=None, account_id=None):
        master = config.get("master_guidelines") if isinstance(config, dict) and config.get("master_guidelines") else None
        if not master:
            master = self._effective_master_guidelines(
                (config or {}).get("post_type") if isinstance(config, dict) else None
            )
        result = await _content_gen().generate_body_from_outline(
            config, title, outline_str, required_keyword, extra_keyword, self.log, master, account_id
        )
        if isinstance(config, dict):
            report = config.get("_quality_report")
            try:
                from blog_quality_guard import has_quality_report

                if has_quality_report(report):
                    self.root.after(0, lambda r=report: self._update_quality_status(r))
            except Exception:
                if report:
                    self.root.after(0, lambda r=report: self._update_quality_status(r))
        return result

    async def generate_content(self, config, required_keyword, extra_keyword=None, account_id=None):
        master = config.get("master_guidelines") if isinstance(config, dict) and config.get("master_guidelines") else None
        if not master:
            master = self._effective_master_guidelines(
                (config or {}).get("post_type") if isinstance(config, dict) else None
            )
        return await _content_gen().generate_content(config, required_keyword, extra_keyword, self.log, master, account_id)

def _append_launch_log(base_dir: str, message: str) -> None:
    try:
        path = os.path.join(base_dir, "_gui_launch.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass


if __name__ == "__main__":
    from blog_single_instance import acquire_single_instance

    _base = os.path.dirname(os.path.abspath(__file__))
    _append_launch_log(_base, f"Autoblog GUI 시작 (pid={os.getpid()})")

    if not acquire_single_instance():
        _append_launch_log(_base, "중복 실행 — 기존 창 사용")
        sys.exit(0)
    try:
        root = tk.Tk()
        app = CanonAutoGUI(root)
        root.mainloop()
    except Exception as exc:
        _append_launch_log(_base, f"GUI 오류: {exc}")
        raise
