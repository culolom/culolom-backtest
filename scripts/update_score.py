import requests
import pandas as pd
import os
import sys  # 用來強制報錯
from datetime import datetime
from pathlib import Path

# -----------------------------------------------------
# 設定
# -----------------------------------------------------
DATA_DIR = Path("data")
CSV_PATH = DATA_DIR / "SCORE.csv"
URL = "https://index.ndc.gov.tw/n/json/data/economy/indicator"

# 【關鍵修改 1】加入 User-Agent 偽裝成瀏覽器
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://index.ndc.gov.tw/n/zh_tw/index",
    "Origin": "https://index.ndc.gov.tw"
}

def fetch_score_data():
    print("🚀 [Job: Score] 開始抓取國發會景氣對策信號...")

    # 確保資料夾存在
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # 發送 POST 請求 (加入 headers)
        res = requests.post(URL, data={'sys': 10, 'cat': 15, 'ind': 74}, headers=HEADERS, timeout=15)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"❌ [Job: Score] API 連線失敗: {e}")
        sys.exit(1) # 【關鍵修改 2】強制讓 Action 失敗亮紅燈

    # 解析 JSON
    target_data = None
    if isinstance(data, dict):
         for key, val in data.items():
            if isinstance(val, dict) and "lines" in val:
                for line in val["lines"]:
                    title = line.get("title", "")
                    # 國發會 API 有時候 title 會變，這裡做模糊比對
                    if "景氣對策信號" in title and "(分)" in title:
                        target_data = line["data"]
                        break
            if target_data: break
            
    if not target_data:
        print("❌ [Job: Score] 找不到景氣分數資料 (API 回傳結構可能改變)")
        # 印出部分資料幫助除錯
        print(f"DEBUG: Data keys received: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
        sys.exit(1) # 強制失敗

    # 整理數據
    records = []
    for item in target_data:
        try:
            raw_date = str(item['x'])  # "202301"
            score = item['y']
            dt_obj = datetime.strptime(raw_date, "%Y%m")
            fmt_date = dt_obj.strftime("%Y-%m-%d")
            records.append({"Date": fmt_date, "Score": score})
        except Exception as e:
            continue

    if not records:
        print("❌ [Job: Score] 解析後無有效數據")
        sys.exit(1)

    # 存檔
    df = pd.DataFrame(records)
    df = df.set_index("Date")
    df = df.sort_index()
    
    df.to_csv(CSV_PATH)
    print(f"✅ [Job: Score] 更新完成！已儲存至: {CSV_PATH}")
    print(f"   最新數據: {df.index[-1]} -> {df['Score'].iloc[-1]} 分")

if __name__ == "__main__":
    fetch_score_data()
