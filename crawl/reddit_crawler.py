import os
import time
import requests
from pathlib import Path

# User-Agent is vital to avoid the 429 block
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def fetch_posts(config: dict) -> list[dict]:
    subreddits = config["farm"]["subreddits"]
    crawl_cfg = config["crawl"]
    
    # Updated Filters
    min_ratio = crawl_cfg.get("min_upvote_ratio", 0.8)
    min_score = 300  # The "Concrete" quality floor
    
    results = []
    
    for sub in subreddits:
        # Changed from /hot to /top with t=week for higher quality material
        print(f"[crawl] Fetching Top of the Week from r/{sub}...")
        url = f"https://www.reddit.com/r/{sub}/top.json?limit=25&t=week"
        
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=10)
            if resp.status_code == 429:
                print(f"[crawl] Rate limited on r/{sub}. Sleeping 30s...")
                time.sleep(30)
                continue
                
            resp.raise_for_status()
            children = resp.json().get("data", {}).get("children", [])
            
            for child in children:
                p = child["data"]
                
                # --- THE FILTER GATE ---
                if not p.get("is_self"): continue 
                if p.get("score", 0) < min_score: continue # Skip low engagement
                if p.get("upvote_ratio", 0) < min_ratio: continue
                if len(p.get("selftext", "")) < 200: continue
                if p.get("stickied"): continue # Skip mod announcements
                
                results.append({
                    "post_id": p["id"],
                    "subreddit": sub,
                    "title": p["title"],
                    "body": p["selftext"],
                    "score": p["score"],
                    "upvote_ratio": p["upvote_ratio"],
                    "created_utc": p["created_utc"]
                })
        except Exception as e:
            print(f"[crawl] Failed to fetch r/{sub}: {e}")
            
        time.sleep(2) # Stay polite
        
    return results

def run(config: dict) -> list[dict]:
    return fetch_posts(config)