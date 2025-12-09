import requests
import pandas as pd
import os
from datetime import datetime
from pathlib import Path

# -----------------------------------------------------
# 設定路徑
# -----------------------------------------------------
# 假設腳本是從專案根目錄執行 (GitHub Actions 的預設行為)
DATA_DIR = Path("data")
CSV_PATH = DATA_DIR / "SCORE.csv"

# 國發會景氣指標 API
URL = "https://index.ndc.gov.tw/n/json/data/economy/indicator"

def fetch_score_data():
    print("🚀 [Job: Score] 開始抓取國發會景氣對策信號...")

    # 1. 確保 data 資料夾存在
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 2. 發送 POST 請求
    try:
        # sys=10 (景氣指標), cat=15 (景氣對策信號), ind=74 (分數)
        res = requests.post(URL, data={'sys': 10, 'cat': 15, 'ind': 74}, timeout=10)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"❌ [Job: Score] API 連線失敗: {e}")
        return

    # 3. 解析 JSON
    target_data = None
    # 尋找對應的數據線
    for key, val in data.items():
        if isinstance(val, dict) and "lines" in val:
            for line in val["lines"]:
                if "景氣對策信號" in line.get("title", "") and "(分)" in line.get("title", ""):
                    target_data = line["data"]
                    break
        if target_data:
            break
            
    if not target_data:
        print("❌ [Job: Score] 找不到景氣分數資料，API 結構可能已變更。")
        return

    # 4. 整理數據
    records = []
    for item in target_data:
        raw_date = str(item['x'])  # 格式如 "202301"
        score = item['y']
        
        # 轉換日期: 202301 -> 2023-01-01
        try:
            dt_obj = datetime.strptime(raw_date, "%Y%m")
            fmt_date = dt_obj.strftime("%Y-%m-%d")
            records.append({"Date": fmt_date, "Score": score})
        except ValueError:
            continue

    if not records:
        print("⚠️ [Job: Score] 無有效數據。")
        return

    # 5. 存檔
    df = pd.DataFrame(records)
    df = df.set_index("Date")
    df = df.sort_index()
    
    df.to_csv(CSV_PATH)
    print(f"✅ [Job: Score] 更新完成！已儲存至: {CSV_PATH}")
    print(f"   最新數據: {df.index[-1]} -> {df['Score'].iloc[-1]} 分")

if __name__ == "__main__":
    fetch_score_data()
