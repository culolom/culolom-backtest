import requests
import pandas as pd
import io
import sys
import re
from datetime import datetime
from pathlib import Path

# -----------------------------------------------------
# 設定
# -----------------------------------------------------
DATA_DIR = Path("data")
CSV_PATH = DATA_DIR / "SCORE.csv"

# 政府資料開放平臺「網頁版」搜尋連結 (這是給人看的 HTML，絕對不會 405)
SEARCH_PAGE = "https://data.gov.tw/datasets/search"
# 資料集 API 樣板
DATASET_API = "https://data.gov.tw/api/v2/rest/dataset/{}"

def parse_taiwan_date(date_str):
    """ 解析日期 (支援 11201, 112/01, 202301 等格式) """
    s = str(date_str).strip()
    try:
        # 格式: 198401
        if len(s) == 6 and s.isdigit():
            return datetime.strptime(s, "%Y%m")
        # 格式: 07301 (5位民國年)
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
    print("🚀 [Job: Score] 開始執行：爬取 Open Data 網頁搜尋結果...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------
    # 步驟 1: 爬取搜尋網頁，找出正確的 Dataset ID
    # -----------------------------------------------------------
    target_title = "景氣指標及燈號"
    print(f"   ...正在搜尋: {target_title}")
    
    try:
        # 偽裝 Headers
        headers = {"User-Agent": "Mozilla/5.0"}
        # 搜尋參數
        params = {"title": target_title}
        
        res = requests.get(SEARCH_PAGE, params=params, headers=headers, timeout=15)
        res.raise_for_status()
        html_content = res.text
        
        # 使用 Regex 在 HTML 中尋找 dataset ID
        # 連結通常長這樣: <a href="/dataset/44376">
        # 我們抓第一個出現的 ID
        match = re.search(r'/dataset/(\d+)', html_content)
        
        if match:
            dataset_id = match.group(1)
            print(f"   ✅ 找到最新資料集 ID: {dataset_id}")
        else:
            print("⚠️ 搜尋頁面解析失敗，嘗試使用備用 ID (44376)...")
            dataset_id = "44376" # 這是目前已知的正確 ID，當備案

    except Exception as e:
        print(f"❌ 搜尋頁面連線失敗: {e}")
        sys.exit(1)

    # -----------------------------------------------------------
    # 步驟 2: 呼叫 API 取得 CSV 下載點
    # -----------------------------------------------------------
    api_url = DATASET_API.format(dataset_id)
    print(f"   ...查詢資源列表: {api_url}")
    
    try:
        r = requests.get(api_url, timeout=15)
        r.raise_for_status()
        data = r.json()
        
        resources = data.get("result", {}).get("resources", [])
        csv_url = None
        
        for res in resources:
            fmt = str(res.get("file_ext") or res.get("format") or "").lower()
            desc = str(res.get("resource_description") or "")
            
            # 只要看到 CSV 就抓
            if "csv" in fmt or "csv" in desc.lower():
                csv_url = res.get("resource_url")
                print(f"   ⬇️ 找到 CSV 資源: {csv_url}")
                break
        
        if not csv_url:
            print("❌ 該資料集沒有提供 CSV 格式")
            sys.exit(1)

    except Exception as e:
        print(f"❌ API 查詢失敗: {e}")
        sys.exit(1)

    # -----------------------------------------------------------
    # 步驟 3: 下載並解析 CSV
    # -----------------------------------------------------------
    try:
        # 下載
        file_res = requests.get(csv_url, timeout=60)
        file_res.raise_for_status()
        
        # 處理編碼 (Big5 vs UTF-8)
        content = file_res.content
        try:
            df_raw = pd.read_csv(io.BytesIO(content), encoding='utf-8')
        except UnicodeDecodeError:
            df_raw = pd.read_csv(io.BytesIO(content), encoding='big5')
            
        print(f"   ...下載成功，原始資料 {len(df_raw)} 筆")

        # 資料清洗
        records = []
        for idx, row in df_raw.iterrows():
            date_val = None
            score_val = None
            
            # 暴力掃描每一欄，自動判斷哪個是日期、哪個是分數
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
                    clean_val = val.replace('.', '', 1)
                    if clean_val.isdigit():
                        v = float(val)
                        if 9 <= v <= 55: # 景氣分數合理範圍
                            score_val = v
            
            if date_val and score_val:
                records.append({
                    "Date": date_val.strftime("%Y-%m-%d"),
                    "Score": score_val
                })

        if not records:
            print("❌ CSV 解析失敗：無法識別日期與分數欄位")
            # 印出前幾行幫助除錯
            print(df_raw.head())
            sys.exit(1)

        # 存檔
        df = pd.DataFrame(records)
        df = df.drop_duplicates(subset=["Date"], keep="last")
        df = df.set_index("Date").sort_index()
        
        df.to_csv(CSV_PATH)
        print(f"🎉 [Job: Score] 更新完成！已儲存至: {CSV_PATH}")
        print(f"   最新一筆: {df.index[-1]} -> {df['Score'].iloc[-1]} 分")

    except Exception as e:
        print(f"❌ 下載或解析失敗: {e}")
        sys.exit(1)

if __name__ == "__main__":
    fetch_score_data()
