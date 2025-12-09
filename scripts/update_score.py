import requests
import pandas as pd
import os
import sys
from datetime import datetime
from pathlib import Path
import io

# -----------------------------------------------------
# 設定
# -----------------------------------------------------
DATA_DIR = Path("data")
CSV_PATH = DATA_DIR / "SCORE.csv"

# 政府資料開放平臺 API (景氣指標及燈號-景氣對策信號)
# Dataset ID: 14603 (這是國發會「景氣指標及燈號-景氣對策信號」的固定 ID)
OPEN_DATA_API = "https://data.gov.tw/api/v2/rest/dataset/14603"

def fetch_score_data():
    print("🚀 [Job: Score] 開始抓取國發會景氣對策信號 (Open Data)...")

    # 1. 確保資料夾存在
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # [步驟 A] 詢問 Open Data API 取得 CSV 下載連結
        print(f"   ...正在查詢資料集資訊: {OPEN_DATA_API}")
        res = requests.get(OPEN_DATA_API, timeout=15)
        res.raise_for_status()
        meta_data = res.json()
        
        # 找到 CSV 格式的資源 ID
        csv_url = None
        if "result" in meta_data and "resources" in meta_data["result"]:
            for resource in meta_data["result"]["resources"]:
                if resource["file_ext"].lower() == "csv":
                    csv_url = resource["resource_url"]
                    break
        
        if not csv_url:
            print("❌ [Job: Score] 找不到 CSV 下載連結 (Open Data 結構可能變更)")
            sys.exit(1)
            
        print(f"   ...找到 CSV 下載點: {csv_url}")

        # [步驟 B] 下載 CSV
        # 這裡有時候會 redirect 到 ws.ndc.gov.tw，requests 會自動處理
        csv_res = requests.get(csv_url, timeout=30)
        csv_res.raise_for_status()
        
        # [步驟 C] 使用 Pandas 讀取 CSV
        # 國發會 CSV 格式通常是: "年月", "景氣對策信號(分)", "燈號"
        # 有時候編碼是 big5 或 utf-8-sig
        try:
            df_raw = pd.read_csv(io.BytesIO(csv_res.content), encoding='utf-8')
        except UnicodeDecodeError:
            df_raw = pd.read_csv(io.BytesIO(csv_res.content), encoding='big5')

    except Exception as e:
        print(f"❌ [Job: Score] 連線或解析失敗: {e}")
        sys.exit(1)

    # 4. 資料清理與標準化
    # 欄位名稱可能會變，我們用位置來抓 (通常第 0 欄是日期，第 1 欄是分數)
    # 假設格式：date, score, light...
    print(f"   ...原始資料欄位: {df_raw.columns.tolist()}")
    
    records = []
    for index, row in df_raw.iterrows():
        try:
            # 處理日期：通常是 "198401" 或 "1984/01" 或 "7301" (民國)
            raw_date = str(row.iloc[0]).strip()
            score = row.iloc[1] # 分數通常在第二欄
            
            # 國發會 Open Data 常見格式處理
            # 格式 A: "198401"
            if len(raw_date) == 6 and raw_date.isdigit():
                dt_obj = datetime.strptime(raw_date, "%Y%m")
            # 格式 B: "1984/01"
            elif "/" in raw_date:
                # 處理民國年 "073/01" -> 1984/01
                parts = raw_date.split('/')
                if len(parts[0]) <= 3: # 民國年
                    year = int(parts[0]) + 1911
                    dt_obj = datetime(year, int(parts[1]), 1)
                else:
                    dt_obj = datetime.strptime(raw_date, "%Y/%m")
            else:
                continue

            fmt_date = dt_obj.strftime("%Y-%m-%d")
            
            # 確保分數是數字
            score = float(score)
            
            records.append({"Date": fmt_date, "Score": score})
        except Exception:
            continue

    if not records:
        print("❌ [Job: Score] 解析後無有效數據，請檢查 CSV 內容")
        sys.exit(1)

    # 5. 存檔
    df = pd.DataFrame(records)
    df = df.set_index("Date")
    df = df.sort_index()
    
    # 移除重複與空值
    df = df.dropna()
    df = df[~df.index.duplicated(keep='last')]
    
    df.to_csv(CSV_PATH)
    print(f"✅ [Job: Score] 更新完成！已儲存至: {CSV_PATH}")
    print(f"   資料區間: {df.index[0]} ~ {df.index[-1]}")
    print(f"   最新分數: {df['Score'].iloc[-1]} 分")

if __name__ == "__main__":
    fetch_score_data()
