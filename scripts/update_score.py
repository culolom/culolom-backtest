import requests
import pandas as pd
import os
import sys
import io
from datetime import datetime
from pathlib import Path

# -----------------------------------------------------
# 設定
# -----------------------------------------------------
DATA_DIR = Path("data")
CSV_PATH = DATA_DIR / "SCORE.csv"

# 政府資料開放平臺 API (直接鎖定國發會「景氣對策信號」的固定 ID: 14603)
# 這是最穩定的入口，比搜尋更可靠
DATASET_ID = "14603"
API_URL = f"https://data.gov.tw/api/v2/rest/dataset/{DATASET_ID}"

def parse_taiwan_date(date_str):
    """ 強力解析各種民國/西元日期格式 """
    s = str(date_str).strip()
    try:
        # 格式 1: "198401" (6位純數字)
        if len(s) == 6 and s.isdigit():
            return datetime.strptime(s, "%Y%m")
        # 格式 2: "07301" (5位純數字 - 民國)
        elif len(s) == 5 and s.isdigit():
            year = int(s[:3]) + 1911
            month = int(s[3:])
            return datetime(year, month, 1)
        # 格式 3: "1984-01" 或 "1984/01"
        elif "-" in s or "/" in s:
            s = s.replace("/", "-")
            parts = s.split("-")
            if len(parts) >= 2:
                year = int(parts[0])
                month = int(parts[1])
                if year < 1911: year += 1911 # 修正民國年
                return datetime(year, month, 1)
    except:
        pass
    return None

def fetch_score_data():
    print(f"🚀 [Job: Score] 開始抓取國發會景氣對策信號 (ID: {DATASET_ID})...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 呼叫 API 取得 Metadata
    try:
        res = requests.get(API_URL, timeout=15)
        res.raise_for_status()
        meta = res.json()
        
        # 檢查是否成功
        if not meta.get("success"):
            print(f"❌ API 回傳失敗: {meta}")
            sys.exit(1)
            
        resources = meta.get("result", {}).get("resources", [])
        if not resources:
            print("❌ API 回傳成功但「無任何資源檔案」(Resources empty)")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ 連線 API 失敗: {e}")
        sys.exit(1)

    # 2. 暴力尋找 CSV 下載點
    csv_url = None
    print(f"   ...分析 {len(resources)} 個資源檔案...")
    
    # 收集所有格式以供除錯
    found_formats = []
    
    for r in resources:
        # 取得各種可能的格式標籤
        fmt = str(r.get("file_ext") or "").lower()
        fmt2 = str(r.get("format") or "").lower()
        url = str(r.get("resource_url") or "").lower()
        desc = str(r.get("resource_description") or "")
        
        found_formats.append(f"{fmt}/{fmt2}")

        # 判定標準：只要任何一個欄位暗示它是 CSV
        is_csv = "csv" in fmt or "csv" in fmt2 or url.endswith(".csv") or "csv" in desc.lower()
        
        if is_csv:
            csv_url = r.get("resource_url")
            print(f"   ✅ 找到 CSV 資源: {desc} ({csv_url})")
            break
    
    if not csv_url:
        print("❌ 找不到任何 CSV 資源")
        print(f"   DEBUG: 找到的格式列表: {found_formats}")
        print("   建議：國發會可能暫時移除了 CSV，請稍後再試或改用 XML 解析。")
        sys.exit(1)

    # 3. 下載 CSV
    try:
        print(f"   ⬇️ 正在下載: {csv_url}")
        file_res = requests.get(csv_url, timeout=60)
        file_res.raise_for_status()
        
        # 嘗試解碼 (Big5 是政府資料最常用的編碼)
        content = file_res.content
        try:
            df_raw = pd.read_csv(io.BytesIO(content), encoding='utf-8')
        except UnicodeDecodeError:
            df_raw = pd.read_csv(io.BytesIO(content), encoding='big5')
            
        print(f"   ...下載成功，原始資料大小: {df_raw.shape}")

    except Exception as e:
        print(f"❌ 下載或讀取 CSV 失敗: {e}")
        sys.exit(1)

    # 4. 解析資料 (欄位識別)
    records = []
    # 國發會 CSV 欄位名稱常變，我們用「內容」來判斷
    # 策略：每一行都檢查，只要能抓到「日期」和「分數」就收錄
    
    for idx, row in df_raw.iterrows():
        date_val = None
        score_val = None
        
        # 遍歷該行的所有欄位
        for col in df_raw.columns:
            val = str(row[col]).strip()
            
            # 嘗試解析日期
            if date_val is None:
                dt = parse_taiwan_date(val)
                if dt:
                    date_val = dt
                    continue # 這一欄是日期，就不用檢查是不是分數了

            # 嘗試解析分數 (9~55分)
            # 排除看起來像日期的數字 (如 202301)
            if score_val is None and val.replace('.', '', 1).isdigit():
                v_float = float(val)
                # 景氣分數通常在 9 到 55 之間 (紅燈45，但也許有極端值，放寬一點)
                # 同時要避免抓到 "2023" 這種年份
                if 9 <= v_float <= 55:
                    score_val = v_float

        if date_val and score_val:
            records.append({
                "Date": date_val.strftime("%Y-%m-%d"),
                "Score": score_val
            })

    if not records:
        print("❌ 解析失敗：無法從 CSV 中識別出日期與分數")
        print("   DEBUG: 前幾行資料範例：")
        print(df_raw.head().to_string())
        sys.exit(1)

    # 5. 存檔
    df = pd.DataFrame(records)
    df = df.drop_duplicates(subset=["Date"], keep="last")
    df = df.set_index("Date").sort_index()
    
    df.to_csv(CSV_PATH)
    print(f"🎉 [Job: Score] 成功更新！已儲存 {len(df)} 筆資料至: {CSV_PATH}")
    print(f"   資料區間: {df.index[0]} ~ {df.index[-1]}")
    print(f"   最新分數: {df['Score'].iloc[-1]} 分")

if __name__ == "__main__":
    fetch_score_data()
