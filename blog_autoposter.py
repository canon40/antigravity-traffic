"""
blog_autoposter.py
==================
나눔랩 전용 AI 자동 블로그 포스팅 엔진
- 자동차코팅제 키워드 집중 강화
- Gemini API / Ollama / 내장 템플릿 순서로 fallback
- 티스토리 API 자동 발행 + 네이버 블로그 초안 파일 저장
"""

import os
import time
import random
from datetime import datetime
import json
import re
import requests

# AI 라이브러리 (선택적)
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# ── 설정 ──────────────────────────────────────────────────────
CONFIG = {
    'store_url': 'https://smartstore.naver.com/nanumlab',
    'car_product_url': 'https://smartstore.naver.com/nanumlab/products/12639296730',
    'daily_post_limit': 5,
    'min_interval_minutes': 60,
    'max_interval_minutes': 180,
    'draft_dir': 'blog_drafts',   # 네이버 블로그 초안 저장 폴더
}

# ── 키워드 데이터베이스 (자동차코팅제 집중 강화) ─────────────
MIX_DB = {
    # 메인 키워드 (자동차코팅제 70% 비중)
    'main': [
        "자동차코팅제",        # ★ 집중 공략
        "자동차코팅제",        # ★ 집중 (가중치 2배)
        "자동차 유리막 코팅",  # ★ 집중
        "차량 코팅제",
        "퍼마코트",
        "셀프 유리막 코팅",
        "차 코팅제",
        "유리막코팅제",
    ],
    # 서브 주제 키워드 (검색자의 실제 고민)
    'sub': [
        "세차 후 물때 제거법",
        "장마철 차량 외장 관리법",
        "검은색 차 광택 유지 비결",
        "신차 코팅 패키지 비용 줄이기",
        "자동 세차 후 스크래치 복원",
        "초보자도 쉬운 셀프 코팅 방법",
        "차량 도장면 보호 꿀팁",
        "우천 시 발수 효과 극대화",
        "여름 뙤약볕 차 도장 보호법",
        "자동차 유리막 코팅 지속 기간",
        "DIY 유리막 코팅 vs 전문점 비교",
        "차량 세차 후 코팅 순서와 방법",
    ],
}

# ── 참고 이미지 풀 ────────────────────────────────────────────
REFERENCE_IMAGES = [
    'https://images.unsplash.com/photo-1607860108855-64acf2078ed9?w=700&auto=format&fit=crop',
    'https://images.unsplash.com/photo-1520340356584-f9917d1ecc6f?w=700&auto=format&fit=crop',
    'https://images.unsplash.com/photo-1563720223185-11003d516935?w=700&auto=format&fit=crop',
    'https://images.unsplash.com/photo-1502161254066-6c74afbf07aa?w=700&auto=format&fit=crop',
    'https://images.unsplash.com/photo-1572635196237-14b3f281503f?w=700&auto=format&fit=crop',
]


class BlogAutoContentEngine:
    def __init__(self, logger_func=None):
        self.config = CONFIG.copy()
        self.logger = logger_func if logger_func else print
        self.daily_posted = 0
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.ai_provider = 'none'
        self.gemini_model = None
        self.load_credentials()
        self._init_ai()

        # 초안 저장 폴더 생성
        if not os.path.exists(self.config['draft_dir']):
            os.makedirs(self.config['draft_dir'])

    def log(self, msg):
        self.logger(f"📝 [블로그 엔진] {msg}")

    def load_credentials(self):
        cred_path = os.path.join("security_vault", "credentials.json")
        if os.path.exists(cred_path):
            try:
                with open(cred_path, "r", encoding="utf-8") as f:
                    creds = json.load(f)
                self.config['tistory_access_token'] = creds.get('tistory_access_token', '')
                self.config['tistory_blog_name'] = creds.get('tistory_blog_name', '')
                self.config['gemini_api_key'] = creds.get('gemini_api_key', '')
                self.config['openai_api_key'] = creds.get('openai_api_key', '')
                self.log("보안 설정(credentials.json) 로드 성공")
            except Exception as e:
                self.log(f"보안 설정 로드 오류: {e}")
        else:
            self.log("credentials.json 없음 — 기본 설정 사용")
            self.config['tistory_access_token'] = ''
            self.config['tistory_blog_name'] = ''
            self.config['gemini_api_key'] = ''

    def _init_ai(self):
        """AI 제공자 초기화 (Gemini → Ollama → 내장 템플릿 순 fallback)"""
        # 1순위: Gemini
        gemini_key = self.config.get('gemini_api_key', '').strip()
        if GEMINI_AVAILABLE and gemini_key:
            try:
                genai.configure(api_key=gemini_key)
                self.gemini_model = genai.GenerativeModel('gemini-1.5-flash')
                self.ai_provider = 'gemini'
                self.log(f"✅ AI: Gemini 1.5 Flash 연동 완료")
                return
            except Exception as e:
                self.log(f"⚠️ Gemini 초기화 실패: {e}")

        # 2순위: Ollama (llama3)
        if OLLAMA_AVAILABLE:
            try:
                ollama.list()
                self.ai_provider = 'ollama'
                self.log("✅ AI: Ollama (llama3) 연동 완료")
                return
            except Exception:
                pass

        # 3순위: 내장 템플릿
        self.ai_provider = 'template'
        self.log("💡 AI: 내장 고품질 템플릿 모드 (Gemini/Ollama 미설치)")

    def _build_prompt(self, main_kw: str, sub_kw: str) -> str:
        return (
            f"당신은 '나눔랩' 소속의 15년 차 자동차 코팅제 제조 전문가입니다.\n"
            f"주제: '{sub_kw}'\n"
            f"이 과정에서 '{main_kw}'를 자연스럽게 해결책으로 녹여주세요.\n\n"
            f"**작성 가이드**\n"
            f"1. 제목: SEO 최적화된 30자 이내 제목 (클릭 유도, 광고 느낌 X)\n"
            f"2. 서론: 검색자의 고민에 공감하는 도입\n"
            f"3. 본론: 화학적 원리, 전문가 팁 포함 (타 제품 비교 가능)\n"
            f"4. 결론: '나눔랩 퍼마코트 {main_kw}'로 자연스럽게 마무리\n"
            f"5. 분량: 1,500자 이상\n"
            f"6. 어조: 전문적이지만 친근한 한국어\n\n"
            f"반드시 아래 JSON만 반환 (마크다운 없이):\n"
            '{{\n'
            '  "title": "[생성된 SEO 제목]",\n'
            '  "body": "[HTML 포맷 본문 (h2, p, strong, br 태그 사용)]"\n'
            '}}'
        )

    def call_ai_api(self, main_kw: str, sub_kw: str):
        """AI 글 생성: Gemini → Ollama → 내장 템플릿"""
        self.log(f"AI 글 작성 시작... ('{main_kw}' + '{sub_kw}') [사용 AI: {self.ai_provider}]")
        prompt = self._build_prompt(main_kw, sub_kw)

        # ── Gemini ──
        if self.ai_provider == 'gemini' and self.gemini_model:
            try:
                response = self.gemini_model.generate_content(prompt)
                content = response.text.strip()
                content = re.sub(r'^```json\s*', '', content)
                content = re.sub(r'\s*```$', '', content).strip()
                data = json.loads(content)
                title = data.get('title', '')
                body = data.get('body', '')
                body = self._inject_image_and_link(body, main_kw)
                self.log(f"✅ Gemini 글 생성 완료: {title}")
                return title, body
            except Exception as e:
                self.log(f"⚠️ Gemini 실패, Ollama로 전환: {e}")

        # ── Ollama ──
        if OLLAMA_AVAILABLE:
            try:
                response = ollama.chat(
                    model='llama3',
                    messages=[{'role': 'user', 'content': prompt}]
                )
                content = response['message']['content'].strip()
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                data = json.loads(content)
                title = data.get('title', '')
                body = data.get('body', '')
                body = self._inject_image_and_link(body, main_kw)
                self.log(f"✅ Ollama 글 생성 완료: {title}")
                return title, body
            except Exception as e:
                self.log(f"⚠️ Ollama 실패, 내장 템플릿 사용: {e}")

        # ── 내장 고품질 템플릿 ──
        return self._generate_template(main_kw, sub_kw)

    def _inject_image_and_link(self, body_html: str, main_kw: str) -> str:
        """이미지 및 스토어 링크 자동 삽입"""
        img_url = random.choice(REFERENCE_IMAGES)
        img_tag = (
            f'<br><img src="{img_url}" alt="나눔랩 {main_kw} 시공 사례" '
            f'style="max-width:100%;border-radius:10px;margin:16px 0;">'
            f'<p style="font-size:0.85em;color:#888;text-align:center;">'
            f'나눔랩 {main_kw} 전문가 시공 과정</p><br>'
        )
        # 첫 번째 </h2> 뒤에 이미지 삽입
        if '</h2>' in body_html:
            body_html = body_html.replace('</h2>', f'</h2>{img_tag}', 1)
        else:
            body_html = img_tag + body_html

        # 스토어 링크 마무리
        store_link = (
            f'<br><div style="text-align:center;margin:24px 0;">'
            f'<a href="{self.config["car_product_url"]}" target="_blank" '
            f'style="display:inline-block;background:linear-gradient(135deg,#2db400,#00a060);'
            f'color:#fff;padding:14px 28px;text-decoration:none;border-radius:8px;'
            f'font-weight:bold;font-size:1.1em;box-shadow:0 4px 12px rgba(0,0,0,0.2);">'
            f'👉 나눔랩 퍼마코트 {main_kw} 공식 스토어 바로가기</a></div>'
        )
        body_html += store_link
        return body_html

    def _generate_template(self, main_kw: str, sub_kw: str):
        """고품질 내장 템플릿 (AI 없을 때)"""
        img_url = random.choice(REFERENCE_IMAGES)
        today = datetime.now().strftime("%Y년 %m월 %d일")
        title = f"{sub_kw}? {main_kw} 전문가가 알려주는 완벽 해결법"

        body_html = f"""
<div style="line-height:1.9;font-family:'Noto Sans KR',sans-serif;color:#333;max-width:720px;margin:0 auto;">

  <h2 style="color:#1a1a1a;border-left:4px solid #2db400;padding-left:12px;margin-top:32px;">
    {sub_kw}, 정말 제대로 해결하고 싶다면?
  </h2>

  <p>안녕하세요. <strong>나눔랩</strong> 연구개발팀입니다. ({today} 기준)</p>
  <p>
    고객분들께 가장 많이 받는 질문 중 하나가 바로 "<em>{sub_kw}</em>"입니다.
    세차를 열심히 해도 며칠 만에 다시 더러워지거나 광택이 사라지는 이유,
    사실 <strong>{main_kw}</strong> 선택이 잘못됐기 때문일 수 있습니다.
  </p>

  <br>
  <img src="{img_url}" alt="나눔랩 {main_kw} 전문가 시공" style="max-width:100%;border-radius:10px;margin:16px 0;">
  <p style="font-size:0.85em;color:#888;text-align:center;">나눔랩 퍼마코트 시공 전·후 비교 테스트</p>
  <br>

  <h2 style="color:#1a1a1a;border-left:4px solid #2db400;padding-left:12px;margin-top:32px;">
    일반 왁스와 유리막 코팅의 결정적 차이
  </h2>
  <p>
    시중 마트에서 파는 일반 물왁스는 <strong>표면에 얹히는 방식</strong>이라 
    세차 1~2회면 보호막이 사라집니다. 반면 나눔랩의 <strong>퍼마코트 {main_kw}</strong>는
    <strong>나노 실록산(SiO₂) 기반</strong>으로 도장면 미세 기공에 깊숙이 침투하여 
    단단한 유리막 코팅층을 형성합니다.
  </p>
  <p>
    이 화학적 결합의 차이가 바로 <strong>6~12개월의 지속력</strong>과 
    뛰어난 <strong>발수·방오 효과</strong>를 만들어냅니다.
  </p>

  <h2 style="color:#1a1a1a;border-left:4px solid #2db400;padding-left:12px;margin-top:32px;">
    집에서 직접 할 수 있는 셀프 시공 순서
  </h2>
  <ol style="line-height:2.2;">
    <li><strong>세차 및 탈지</strong> — 도장면의 오염물, 왁스 잔여물 완전 제거</li>
    <li><strong>점토 클리닝</strong> — 철분, 물때 등 미세 오염물 물리적 제거</li>
    <li><strong>폴리싱(선택)</strong> — 스크래치나 수분 자국이 있을 경우 광택 복원</li>
    <li><strong>퍼마코트 도포</strong> — 전용 스펀지로 얇고 고르게 도포</li>
    <li><strong>경화 대기</strong> — 12~24시간 완전 건조 (직사광선/수분 차단)</li>
  </ol>

  <p>
    무엇보다 <strong>셀프 시공이 가능</strong>하다는 점이 퍼마코트의 최대 강점입니다.
    전문점에 맡기면 수십만 원이 드는 유리막 코팅을, 
    나눔랩 퍼마코트 {main_kw} 하나로 집에서 동일한 효과를 낼 수 있습니다.
  </p>

  <h2 style="color:#1a1a1a;border-left:4px solid #2db400;padding-left:12px;margin-top:32px;">
    실제 사용 고객 후기
  </h2>
  <blockquote style="background:#f4f4f4;border-left:4px solid #2db400;padding:16px 20px;border-radius:4px;margin:16px 0;">
    <em>"도포하고 나서 타월이 미끄러지는 슬릭감이 전혀 다르더라고요. 
    비 온 다음 날 물방울이 또르르 굴러가는 게 눈에 확 보였어요. 
    강추합니다!"</em>
    <br><strong style="color:#2db400;">— 실제 구매 고객 ★★★★★</strong>
  </blockquote>

  <div style="text-align:center;margin:32px 0;">
    <a href="{self.config['car_product_url']}" target="_blank"
       style="display:inline-block;background:linear-gradient(135deg,#2db400,#00a060);
              color:#fff;padding:16px 32px;text-decoration:none;border-radius:8px;
              font-weight:bold;font-size:1.1em;box-shadow:0 4px 12px rgba(0,0,0,0.2);">
      👉 나눔랩 퍼마코트 {main_kw} 공식 스토어 바로가기
    </a>
  </div>

</div>
"""
        return title, body_html

    def post_to_tistory(self, title: str, content: str) -> bool:
        """티스토리 Open API로 발행"""
        token = self.config.get('tistory_access_token', '').strip()
        blog_name = self.config.get('tistory_blog_name', '').strip()

        if not token:
            self.log("⚠️ Tistory 토큰 없음 — 초안 파일로만 저장합니다.")
            return False

        self.log(f"📡 티스토리 발행 중: '{title}'")
        try:
            res = requests.post(
                "https://www.tistory.com/apis/post/write",
                data={
                    "access_token": token,
                    "output": "json",
                    "blogName": blog_name,
                    "title": title,
                    "content": content,
                    "visibility": 3,
                    "category": "0",
                },
                timeout=20
            )
            result = res.json()
            if res.status_code == 200 and result.get('tistory', {}).get('status') == '200':
                post_url = result['tistory'].get('url', '')
                self.log(f"✅ 티스토리 발행 완료: {post_url}")
                return True
            else:
                self.log(f"❌ 티스토리 API 에러: {result}")
                return False
        except Exception as e:
            self.log(f"❌ 발행 오류: {e}")
            return False

    def save_draft(self, title: str, content: str):
        """네이버 블로그용 초안 HTML 파일 저장"""
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)[:50]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(self.config['draft_dir'], f"{timestamp}_{safe_title}.html")

        html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>body{{font-family:'Noto Sans KR',sans-serif;max-width:720px;margin:40px auto;padding:0 20px;}}</style>
</head>
<body>
<h1>{title}</h1>
<hr>
{content}
</body>
</html>"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html)
        self.log(f"💾 초안 저장 완료: {filename}")
        return filename

    def check_daily_limit(self) -> bool:
        today = datetime.now().strftime("%Y-%m-%d")
        if self.current_date != today:
            self.current_date = today
            self.daily_posted = 0
            self.log(f"🌅 날짜 변경 — 발행 카운터 초기화")
        if self.daily_posted >= self.config['daily_post_limit']:
            self.log(f"🛑 일일 한도 도달({self.config['daily_post_limit']}건)")
            return False
        return True

    def run_single_cycle(self) -> bool:
        """1회 발행 주기"""
        if not self.check_daily_limit():
            return False

        main_kw = random.choice(MIX_DB['main'])
        sub_kw = random.choice(MIX_DB['sub'])

        title, content = self.call_ai_api(main_kw, sub_kw)

        # 초안 저장 (항상)
        draft_path = self.save_draft(title, content)

        # 티스토리 발행 시도
        posted = self.post_to_tistory(title, content)

        if posted:
            self.daily_posted += 1
            self.log(f"📈 오늘 발행: {self.daily_posted}/{self.config['daily_post_limit']}건")
            return True
        else:
            self.log(f"💡 초안 파일({draft_path})을 네이버 블로그에 수동 복붙하세요!")
            self.daily_posted += 1  # 초안 생성도 카운트
            return True

    def engine_start(self):
        """무한 자동 포스팅 엔진"""
        self.log("=" * 50)
        self.log("📝 [나눔랩] AI 자동 블로그 포스팅 엔진 가동")
        self.log(f"   - 일일 한도: {self.config['daily_post_limit']}건")
        self.log(f"   - 간격: {self.config['min_interval_minutes']}~{self.config['max_interval_minutes']}분")
        self.log(f"   - AI 제공자: {self.ai_provider}")
        self.log("=" * 50)

        while True:
            self.run_single_cycle()
            wait = random.randint(
                self.config['min_interval_minutes'],
                self.config['max_interval_minutes']
            )
            self.log(f"😴 {wait}분 대기 후 다음 글 발행...")
            time.sleep(wait * 60)


def run_once():
    """1개 글만 즉시 생성 (테스트/수동 실행용)"""
    engine = BlogAutoContentEngine()
    engine.run_single_cycle()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="나눔랩 블로그 자동 포스팅 엔진")
    parser.add_argument('--once', action='store_true', help='글 1개만 즉시 생성')
    parser.add_argument('--engine', action='store_true', help='무한 자동 발행 모드')
    args = parser.parse_args()

    if args.engine:
        BlogAutoContentEngine().engine_start()
    else:
        print("💡 글 1개 즉시 생성 모드")
        run_once()
