import requests
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

# [修改點 1] 這是您找到的網頁 (商店大門)，我們要先造訪這裡拿通行證
PAGE_URL = "https://index.ndc.gov.tw/n/zh_tw/data/eco"

# 這是實際的資料 API (倉庫)
API_URL = "https://index.ndc.gov.tw/n/json/data/economy/indicator"

# [修改點 2] 偽裝 Headers，讓 Referer 指向正確的頁面
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://index.ndc.gov.tw/n/zh_tw/data/eco",  # 關鍵：告訴伺服器我從這裡來的
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://index.ndc.gov.tw",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
}

def fetch_score_data():
    print("🚀 [Job: Score] 開始抓取國發會景氣對策信號...")

    # 1. 確保資料夾存在
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 2. 初始化 Session (模擬瀏覽器行為)
    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        # [步驟 A] 先造訪您提供的那個網頁，取得該頁面的專屬 Cookie
        print(f"   ...正在造訪頁面取得通行證: {PAGE_URL}")
        session.get(PAGE_URL, timeout=15)
        
        # 休息一下，假裝在看網頁
        time.sleep(random.uniform(1, 3))

        # [步驟 B] 帶著 Cookie 去請求 API
        print("   ...正在請求資料 API")
        # 參數：sys=10(景氣), cat=15(燈號), ind=74(分數)
        payload = {'sys': 10, 'cat': 15, 'ind': 74}
        
        res = session.post(API_URL, data=payload, timeout=15)
        
        # 檢查狀態碼
        res.raise_for_status()
        data = res.json()
        
    except Exception as e:
        print(f"❌ [Job: Score] API 連線失敗: {e}")
        # 印出更多錯誤資訊方便除錯
        if 'res' in locals():
            print(f"   HTTP Status: {res.status_code}")
        sys.exit(1)

    # 3. 解析 JSON 資料結構
    target_data = None
    if isinstance(data, dict):
         for key, val in data.items():
            if isinstance(val, dict) and "lines" in val:
                for line in val["lines"]:
                    title = line.get("title", "")
                    # 模糊比對
                    if "景氣對策信號" in title and "(分)" in title:
                        target_data = line["data"]
                        break
            if target_data: break
            
    if not target_data:
        print("❌ [Job: Score] 找不到景氣分數資料 (API 回傳結構可能改變)")
        print(f"DEBUG keys: {list(data.keys()) if isinstance(data, dict) else 'Not dict'}")
        sys.exit(1)

    # 4. 整理數據
    records = []
    print(f"   ...取得 {len(target_data)} 筆資料，正在整理...")
    for item in target_data:
        try:
            raw_date = str(item['x'])  # 例如 "198401"
            score = item['y']          # 例如 39
            
            # 轉換日期格式: 198401 -> 1984-01-01
            dt_obj = datetime.strptime(raw_date, "%Y%m")
            fmt_date = dt_obj.strftime("%Y-%m-%d")
            records.append({"Date": fmt_date, "Score": score})
        except Exception:
            continue

    if not records:
        print("❌ [Job: Score] 解析後無有效數據")
        sys.exit(1)

    # 5. 存檔
    df = pd.DataFrame(records)
    df = df.set_index("Date")
    df = df.sort_index()
    
    df.to_csv(CSV_PATH)
    print(f"✅ [Job: Score] 更新完成！已儲存至: {CSV_PATH}")
    print(f"   資料區間: {df.index[0]} ~ {df.index[-1]}")
    print(f"   最新分數: {df['Score'].iloc[-1]} 分")

if __name__ == "__main__":
    fetch_score_data()
