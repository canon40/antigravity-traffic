import json
import re

transcript_path = r"C:\Users\hymin\.gemini\antigravity\brain\f7d3c34a-97de-493e-8c4c-a19f2a00c6d5\.system_generated\logs\transcript.jsonl"
try:
    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            content = obj.get("content", "")
            # check if content contains 'naver_blog_id' or 'config.json' or 'naver_search_keywords'
            if any(x in content for x in ["naver_blog_id", "naver_search_keywords"]):
                print(f"Step {obj.get('step_index')} (Source: {obj.get('source')}):")
                print(content[:500] + "\n" + "-"*50)
except Exception as e:
    print(f"Error: {e}")
