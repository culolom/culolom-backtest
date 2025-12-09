from curl_cffi import requests # 使用支援模擬指紋的 requests
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

# 國發會首頁
PAGE_URL = "https://index.ndc.gov.tw/n/zh_tw/data/eco"
# 資料 API
API_URL = "https://index.ndc.gov.tw/n/json/data/economy/indicator"

# Headers 設定
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://index.ndc.gov.tw/n/zh_tw/data/eco",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://index.ndc.gov.tw"
}

def fetch_score_data():
    print("🚀 [Job: Score] 開始抓取國發會景氣對策信號 (curl_cffi + GET)...")

    # 1. 確保資料夾存在
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # 2. 初始化 Session (impersonate="chrome110")
        s = requests.Session(impersonate="chrome110") 
        s.headers.update(HEADERS)

        # [步驟 A] 造訪首頁取得 Cookie
        print(f"   ...正在造訪頁面: {PAGE_URL}")
        r1 = s.get(PAGE_URL, timeout=15)
        
        # 休息一下
        time.sleep(random.uniform(1, 2))

        # [步驟 B] 請求 API (改成 GET)
        print("   ...正在請求資料 API")
        
        # 參數：sys=10(景氣), cat=15(燈號), ind=74(分數)
        payload = {'sys': 10, 'cat': 15, 'ind': 74}
        
        # 【關鍵修正】這裡改成 get，並且用 params 傳遞參數
        res = s.get(API_URL, params=payload, timeout=15)
        
        # 檢查回應
        if res.status_code != 200:
            print(f"❌ API 回應錯誤: {res.status_code}")
            print(f"   回應內容: {res.text[:200]}") 
            sys.exit(1)
            
        data = res.json()
        
    except Exception as e:
        print(f"❌ [Job: Score] 連線發生例外狀況: {e}")
        sys.exit(1)

    # 3. 解析 JSON
    target_data = None
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
        print("❌ [Job: Score] 找不到資料 (API 結構可能改變)")
        # 印出 Key 來除錯
        print(f"DEBUG Keys: {list(data.keys()) if isinstance(data, dict) else data}")
        sys.exit(1)

    # 4. 整理數據
    records = []
    print(f"   ...取得 {len(target_data)} 筆資料，正在整理...")
    for item in target_data:
        try:
            raw_date = str(item['x'])  # "198401"
            score = item['y']
            
            dt_obj = datetime.strptime(raw_date, "%Y%m")
            fmt_date = dt_obj.strftime("%Y-%m-%d")
            records.append({"Date": fmt_date, "Score": score})
        except:
            continue

    if not records:
        print("❌ [Job: Score] 無有效數據")
        sys.exit(1)

    # 5. 存檔
    df = pd.DataFrame(records)
    df = df.set_index("Date")
    df = df.sort_index()
    
    df.to_csv(CSV_PATH)
    print(f"✅ [Job: Score] 更新完成！已儲存至: {CSV_PATH}")
    print(f"   最新分數: {df.index[-1]} -> {df['Score'].iloc[-1]} 分")

if __name__ == "__main__":
    fetch_score_data()
