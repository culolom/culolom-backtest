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

# 政府資料開放平臺「網頁版」搜尋連結 (給人看的)
SEARCH_PAGE = "https://data.gov.tw/datasets/search"

# 用來查詢詳情的 API 樣板
DATASET_API_TEMPLATE = "https://data.gov.tw/api/v2/rest/dataset/{}"

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

def get_latest_dataset_id():
    """ 爬取網頁搜尋結果，找出最新的資料集 ID """
    print("   ...正在爬取 data.gov.tw 搜尋頁面...")
    
    # 搜尋關鍵字：景氣指標及燈號
    # 我們針對這個標題搜尋，準確度最高
    params = {"title": "景氣指標及燈號"}
    
    try:
        # 偽裝成瀏覽器
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        res = requests.get(SEARCH_PAGE, params=params, headers=headers, timeout=15)
        res.raise_for_status()
        html = res.text
        
        # 使用 Regex 尋找 dataset ID
        # 網頁連結通常長這樣: /dataset/14603
        # 我們找出現的第一個匹配項
        match = re.search(r'/dataset/(\d+)', html)
        
        if match:
            found_id = match.group(1)
            print(f"   ✅ 找到最新資料集 ID: {found_id}")
            return found_id
        else:
            print("❌ 在搜尋結果頁面找不到 Dataset ID")
            # 印出一點 HTML 除錯
            print(f"DEBUG HTML: {html[:500]}...")
            return None
            
    except Exception as e:
        print(f"❌ 爬取搜尋頁面失敗: {e}")
        return None

def fetch_score_data():
    print("🚀 [Job: Score] 開始執行 (網頁爬蟲 + API 下載)...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 自動抓取 ID
    dataset_id = get_latest_dataset_id()
    
    # 如果真的抓不到，有一個備用方案 (這是目前已知的另一個 ID)
    if not dataset_id:
        print("⚠️ 無法自動取得 ID，嘗試使用備用 ID (44376)...")
        dataset_id = "44376"

    # 2. 呼叫 API 取得下載點
    api_url = DATASET_API_TEMPLATE.format(dataset_id)
    print(f"   ...正在查詢 API: {api_url}")
    
    try:
        res = requests.get(api_url, timeout=15)
        res.raise_for_status()
        meta = res.json()
        
        resources = meta.get("result", {}).get("resources", [])
        if not resources:
            print("❌ API 回傳資源為空 (Resources empty)")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ API 連線失敗: {e}")
        sys.exit(1)

    # 3. 尋找 CSV
    csv_url = None
    for r in resources:
        fmt = str(r.get("file_ext") or "").lower()
        if "csv" in fmt:
            csv_url = r.get("resource_url")
            print(f"   ✅ 找到 CSV 資源: {r.get('resource_description')} ({csv_url})")
            break
            
    if not csv_url:
        print("❌ 該資料集沒有 CSV 格式")
        sys.exit(1)

    # 4. 下載與處理
    try:
        print(f"   ⬇️ 正在下載 CSV...")
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
                    # 移除小數點後檢查是否為數字
                    clean_val = val.replace('.', '', 1)
                    if clean_val.isdigit():
                        v = float(val)
                        # 景氣分數特徵：9 ~ 55 分
                        if 9 <= v <= 55:
                            score_val = v
            
            if date_val and score_val:
                records.append({
                    "Date": date_val.strftime("%Y-%m-%d"),
                    "Score": score_val
                })

        if not records:
            print("❌ 解析後無資料，無法識別日期與分數欄位")
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
