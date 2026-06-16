import sys
import os
import json
import asyncio

# Windows 콘솔 UTF-8 출력 강제
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root to path to import rank_tracker
sys.path.append(r"d:\@code\anty traffic")
from rank_tracker import check_product_rank

def load_config():
    with open(r"d:\@code\anty traffic\config.json", "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    config = load_config()
    keywords = config.get("keywords", [])
    products = {p["id"]: p["name"] for p in config.get("products", [])}
    
    print("=== 실시간 순위 조회 시작 ===")
    
    results = []
    # Deduplicate product + keyword checks
    checked = set()
    for item in keywords:
        kw = item.get("keyword")
        pid = item.get("product_id")
        if not kw or not pid:
            continue
            
        key = (kw, pid)
        if key in checked:
            continue
        checked.add(key)
        
        pname = products.get(pid, pid)
        print(f"🔍 상품: {pname} | 키워드: '{kw}' 조회 중...")
        
        try:
            rank = check_product_rank(kw, pid)
            if rank is None:
                display = "520위 밖 (미발견)"
            else:
                display = f"{rank}위"
            results.append({
                "product_name": pname,
                "keyword": kw,
                "rank": rank,
                "display": display
            })
            print(f"   => 결과: {display}")
        except Exception as e:
            print(f"   => 조회 실패: {e}")
            
    print("\n=== 조회 완료 ===")
    print(json.dumps(results, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
