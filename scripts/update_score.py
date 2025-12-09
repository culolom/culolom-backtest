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

# 政府資料開放平臺 API (搜尋介面)
SEARCH_API = "https://data.gov.tw/api/v2/rest/dataset"

def parse_taiwan_date(date_str):
    """ 解析日期 (民國/西元) """
    s = str(date_str).strip()
    try:
        # 198401
        if len(s) == 6 and s.isdigit():
            return datetime.strptime(s, "%Y%m")
        # 07301
        elif len(s) == 5 and s.isdigit():
            year = int(s[:3]) + 1911
            month = int(s[3:])
            return datetime(year, month, 1)
        # 1984-01, 1984/01
        elif "-" in s or "/" in s:
            s = s.replace("/", "-")
            parts = s.split("-")
            if len(parts) >= 2:
                year = int(parts[0])
                month = int(parts[1])
                if year < 1911: year += 1911
                return datetime(year, month, 1)
    except:
        pass
    return None

def fetch_score_data():
    print("🚀 [Job: Score] 開始執行：使用 API 搜尋景氣對策信號...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    csv_url = None
    target_title = ""

    # 1. 搜尋資料集
    # 關鍵字設為 "景氣對策信號"，這樣最準
    print("   ...正在呼叫搜尋 API...")
    try:
        # q=關鍵字
        res = requests.get(SEARCH_API, params={"q": "景氣對策信號"}, timeout=30)
        res.raise_for_status()
        data = res.json()
        
        # 檢查是否有搜尋結果
        if not data.get("success"):
            print(f"❌ API 呼叫失敗: {data}")
            sys.exit(1)
            
        datasets = data.get("result", {}).get("records", [])
        if not datasets:
            print("❌ 搜尋不到任何資料集")
            sys.exit(1)
            
        print(f"   ...找到 {len(datasets)} 個資料集，開始篩選 CSV...")

        # 2. 遍歷資料集尋找 CSV
        for ds in datasets:
            # 取得資料集 ID
            ds_id = ds.get("id")
            ds_title = ds.get("title", "")
            
            # 呼叫詳情 API 取得資源列表
            detail_res = requests.get(f"{SEARCH_API}/{ds_id}", timeout=10)
            if detail_res.status_code != 200:
                continue
                
            resources = detail_res.json().get("result", {}).get("resources", [])
            
            for r in resources:
                fmt = str(r.get("file_ext") or r.get("format") or "").lower()
                desc = str(r.get("resource_description") or "")
                
                # 判定是否為 CSV
                if "csv" in fmt or "csv" in desc.lower():
                    csv_url = r.get("resource_url")
                    target_title = ds_title
                    print(f"   ✅ 鎖定資料集: {ds_title}")
                    print(f"   ⬇️ 找到 CSV 資源: {csv_url}")
                    break
            
            if csv_url: break
            
    except Exception as e:
        print(f"❌ API 搜尋過程發生錯誤: {e}")
        sys.exit(1)

    if not csv_url:
        print("❌ 所有搜尋結果中都沒有發現 CSV 格式的檔案")
        sys.exit(1)

    # 3. 下載與處理
    try:
        print(f"   ...開始下載...")
        file_res = requests.get(csv_url, timeout=60)
        file_res.raise_for_status()
        
        # 解碼
        content = file_res.content
        try:
            df_raw = pd.read_csv(io.BytesIO(content), encoding='utf-8')
        except:
            df_raw = pd.read_csv(io.BytesIO(content), encoding='big5')
            
        print(f"   ...解析中 (原始大小 {df_raw.shape})...")
        
        records = []
        # 暴力掃描欄位抓取 日期 & 分數
        for idx, row in df_raw.iterrows():
            date_val = None
            score_val = None
            
            for col in df_raw.columns:
                val = str(row[col]).strip()
                
                # 抓日期
                if date_val is None:
                    dt = parse_taiwan_date(val)
                    if dt: 
                        date_val = dt
                        continue
                
                # 抓分數 (排除日期數字)
                if score_val is None:
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
            print("❌ 解析後無資料，無法識別日期與分數欄位")
            print("DEBUG: 前幾行資料:", df_raw.head())
            sys.exit(1)

        # 5. 存檔
        df = pd.DataFrame(records)
        df = df.drop_duplicates(subset=["Date"], keep="last")
        df = df.set_index("Date").sort_index()
        
        df.to_csv(CSV_PATH)
        print(f"🎉 [Job: Score] 成功！已儲存 {len(df)} 筆資料至: {CSV_PATH}")
        print(f"   最新數據: {df.index[-1]} -> {df['Score'].iloc[-1]} 分")

    except Exception as e:
        print(f"❌ 下載或解析失敗: {e}")
        sys.exit(1)

if __name__ == "__main__":
    fetch_score_data()
