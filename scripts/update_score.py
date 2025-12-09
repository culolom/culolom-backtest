from curl_cffi import requests # 關鍵：使用 curl_cffi 繞過 TLS 指紋偵測
import pandas as pd
import os
import sys
from datetime import datetime
from pathlib import Path
import time
import random

# -----------------------------------------------------
# 設定
# -----------------------------------------------------
DATA_DIR = Path("data")
CSV_PATH = DATA_DIR / "SCORE.csv"

# 部落格提到的 API 網址 (倉庫入口)
API_URL = "https://index.ndc.gov.tw/n/json/data/economy/indicator"
# 國發會首頁 (用來拿通行證)
PAGE_URL = "https://index.ndc.gov.tw/n/zh_tw/data/eco"

# 偽裝成 Chrome 瀏覽器
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://index.ndc.gov.tw",
    "Referer": "https://index.ndc.gov.tw/n/zh_tw/data/eco"
}

def fetch_score_data():
    print("🚀 [Job: Score] 開始執行 (部落格 API 方法 + curl_cffi 偽裝)...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # 1. 初始化偽裝 Session (模擬 Chrome 110)
        s = requests.Session(impersonate="chrome110")
        s.headers.update(HEADERS)

        # [步驟 A] 先去首頁晃一下，拿 Cookie (裝得像真人)
        print(f"   ...正在造訪首頁取得 Cookie: {PAGE_URL}")
        s.get(PAGE_URL, timeout=15)
        time.sleep(random.uniform(1, 2)) # 休息一下

        # [步驟 B] 發送 POST 請求 (這是部落格的核心步驟)
        print("   ...正在發送 POST 請求至 API")
        
        # 這是部落格文章中提到的關鍵參數
        payload = {
            'sys': 10,  # 景氣指標
            'cat': 15,  # 景氣對策信號
            'ind': 74   # 分數
        }
        
        # 使用 POST (因為 GET 會回傳 405)
        res = s.post(API_URL, data=payload, timeout=15)
        
        # 檢查回應
        if res.status_code != 200:
            print(f"❌ API 回應錯誤: {res.status_code}")
            print(f"   回應內容: {res.text[:200]}")
            sys.exit(1)
            
        data = res.json()
        print("   ✅ 成功取得 JSON 資料！")

    except Exception as e:
        print(f"❌ 連線失敗: {e}")
        sys.exit(1)

    # 3. 解析資料 (參考部落格的解析邏輯)
    target_data = None
    
    # 國發會 API 回傳結構通常在 lines 裡面
    # 我們遍歷尋找標題包含 "景氣對策信號" 且包含 "(分)" 的數據
    if isinstance(data, dict):
         for key, val in data.items():
            if isinstance(val, dict) and "lines" in val:
                for line in val["lines"]:
                    title = line.get("title", "")
                    if "景氣對策信號" in title and "(分)" in title:
                        target_data = line["data"]
                        break
            if target_data: break
            
    if not target_data:
        print("❌ 找不到目標數據 (API 結構可能與部落格文章不同)")
        sys.exit(1)

    # 4. 整理數據
    records = []
    print(f"   ...正在整理 {len(target_data)} 筆數據...")
    
    for item in target_data:
        try:
            # item['x'] 是日期 (如 202401)
            # item['y'] 是分數 (如 27)
            raw_date = str(item['x'])
            score = item['y']
            
            dt_obj = datetime.strptime(raw_date, "%Y%m")
            fmt_date = dt_obj.strftime("%Y-%m-%d")
            
            records.append({"Date": fmt_date, "Score": score})
        except:
            continue

    if not records:
        print("❌ 解析後無有效數據")
        sys.exit(1)

    # 5. 存檔
    df = pd.DataFrame(records)
    df = df.set_index("Date")
    df = df.sort_index()
    
    df.to_csv(CSV_PATH)
    print(f"🎉 [Job: Score] 更新完成！已儲存至: {CSV_PATH}")
    print(f"   資料區間: {df.index[0]} ~ {df.index[-1]}")
    print(f"   最新分數: {df['Score'].iloc[-1]} 分")

if __name__ == "__main__":
    fetch_score_data()
