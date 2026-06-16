import sys
import os
import asyncio

# Add agent ai to path
sys.path.append(r"d:\@code\agent ai")

try:
    from blog_agent import BlogAgent
    agent = BlogAgent()
    
    # Windows Event Loop Policy 
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
    print("🚀 다이렉트 실행 모드로 블로그 에이전트를 가동합니다...")
    agent.execute_daily_blog_routine("듀라코트 리빙코트, 식탁코팅제, 타일코팅제")
except Exception as e:
    print(f"Test failed: {e}")
