import requests
import pandas as pd
import io
import sys
from datetime import datetime
from pathlib import Path

# -----------------------------------------------------
# 設定
# -----------------------------------------------------
DATA_DIR = Path("data")
CSV_PATH = DATA_DIR / "SCORE.csv"

# 政府資料開放平臺 API (直接鎖定正確的 ID: 6099)
DATASET_ID = "6099"
API_URL = f"https://data.gov.tw/api/v2/rest/dataset/{DATASET_ID}"

def parse_taiwan_date(date_str):
    """ 解析日期 (支援 11201, 112/01, 202301, 2023-01 等格式) """
    s = str(date_str).strip()
    try:
        # 格式: 198401 (6位數字)
        if len(s) == 6 and s.isdigit():
            return datetime.strptime(s, "%Y%m")
        # 格式: 07301 (5位數字 - 民國)
        elif len(s) == 5 and s.isdigit():
            year = int(s[:3]) + 1911
            month = int(s[3:])
            return datetime(year, month, 1)
        # 格式: 1984-01 或 1984/01
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
    print(f"🚀 [Job: Score] 開始執行：抓取景氣對策信號 (ID: {DATASET_ID})...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 呼叫 API 取得資源列表
    print(f"   ...正在查詢 API: {API_URL}")
    try:
        res = requests.get(API_URL, timeout=15)
        res.raise_for_status()
        data = res.json()
        
        if not data.get("success"):
            print(f"❌ API 呼叫失敗: {data}")
            sys.exit(1)
            
        resources = data.get("result", {}).get("resources", [])
        if not resources:
            print("❌ 此資料集 ID 下無任何檔案資源")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ API 連線失敗: {e}")
        sys.exit(1)

    # 2. 尋找 CSV 下載連結
    csv_url = None
    target_desc = ""
    
    for r in resources:
        fmt = str(r.get("file_ext") or r.get("format") or "").lower()
        desc = str(r.get("resource_description") or "")
        
        # 關鍵判斷：找 CSV，且通常是「景氣對策信號」相關的檔案
        if "csv" in fmt:
            csv_url = r.get("resource_url")
            target_desc = desc
            print(f"   ✅ 找到 CSV 資源: {desc} ({csv_url})")
            break
            
    if not csv_url:
        print("❌ 在此資料集中找不到 CSV 格式檔案")
        # 印出所有可用格式供參考
        print(f"   DEBUG: 可用資源: {[r.get('format') for r in resources]}")
        sys.exit(1)

    # 3. 下載並解析
    try:
        print(f"   ⬇️ 正在下載...")
        file_res = requests.get(csv_url, timeout=60)
        file_res.raise_for_status()
        
        # 處理編碼 (Big5 vs UTF-8)
        content = file_res.content
        try:
            df_raw = pd.read_csv(io.BytesIO(content), encoding='utf-8')
        except UnicodeDecodeError:
            df_raw = pd.read_csv(io.BytesIO(content), encoding='big5')
            
        print(f"   ...下載成功，原始資料大小: {df_raw.shape}")

        # 4. 資料清洗 (暴力掃描欄位)
        records = []
        for idx, row in df_raw.iterrows():
            date_val = None
            score_val = None
            
            for col in df_raw.columns:
                val = str(row[col]).strip()
                
                # 找日期
                if date_val is None:
                    dt = parse_taiwan_date(val)
                    if dt: 
                        date_val = dt
                        continue
                
                # 找分數 (9-55分)
                if score_val is None:
                    # 去除小數點檢查是否為數字
                    clean_val = val.replace('.', '', 1)
                    if clean_val.isdigit():
                        v = float(val)
                        if 9 <= v <= 55: # 合理分數範圍
                            score_val = v
            
            if date_val and score_val:
                records.append({
                    "Date": date_val.strftime("%Y-%m-%d"),
                    "Score": score_val
                })

        if not records:
            print("❌ CSV 解析失敗：無法識別日期與分數欄位")
            print("DEBUG: 前幾行資料:", df_raw.head())
            sys.exit(1)

        # 5. 存檔
        df = pd.DataFrame(records)
        df = df.drop_duplicates(subset=["Date"], keep="last")
        df = df.set_index("Date").sort_index()
        
        df.to_csv(CSV_PATH)
        print(f"🎉 [Job: Score] 成功更新！已儲存 {len(df)} 筆資料至: {CSV_PATH}")
        print(f"   最新數據: {df.index[-1]} -> {df['Score'].iloc[-1]} 分")

    except Exception as e:
        print(f"❌ 下載或解析失敗: {e}")
        sys.exit(1)

if __name__ == "__main__":
    fetch_score_data()
