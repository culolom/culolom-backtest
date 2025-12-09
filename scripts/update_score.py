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

# 政府資料開放平臺 API 入口
# 我們不寫死 Dataset ID，改用「搜尋」的方式
SEARCH_API = "https://data.gov.tw/api/v2/rest/dataset"

def parse_taiwan_date(date_str):
    """ 解析各種奇奇怪怪的日期格式 (民國/西元/斜線/連字號) """
    s = str(date_str).strip()
    
    # 1. 處理 "198401" (6位數字)
    if len(s) == 6 and s.isdigit():
        return datetime.strptime(s, "%Y%m")
        
    # 2. 處理 "1984-01" 或 "1984/01"
    if "-" in s or "/" in s:
        s = s.replace("/", "-")
        parts = s.split("-")
        if len(parts) >= 2:
            year = int(parts[0])
            month = int(parts[1])
            # 如果年份小於 1911，通常是民國年 (例如 73-01)
            if year < 1911:
                year += 1911
            return datetime(year, month, 1)
            
    # 3. 處理 "07301" (5位數字，民國年)
    if len(s) == 5 and s.isdigit():
        year = int(s[:3]) + 1911
        month = int(s[3:])
        return datetime(year, month, 1)

    return None

def fetch_score_data():
    print("🚀 [Job: Score] 開始執行：自動搜尋並下載景氣對策信號 (Open Data)...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 搜尋資料集
    print("   ...正在搜尋關鍵字: '景氣指標及燈號'")
    try:
        # 搜尋參數
        params = {"q": "景氣指標及燈號"}
        res = requests.get(SEARCH_API, params=params, timeout=30)
        res.raise_for_status()
        data = res.json()
        
        datasets = data.get("result", {}).get("records", [])
        if not datasets:
            print("❌ 搜尋不到任何資料集")
            sys.exit(1)
            
        print(f"   ...找到 {len(datasets)} 個相關資料集，正在尋找 CSV 資源...")

    except Exception as e:
        print(f"❌ 搜尋 API 連線失敗: {e}")
        sys.exit(1)

    # 2. 尋找 CSV 下載連結
    csv_url = None
    target_dataset_title = ""
    
    # 遍歷搜尋結果，找最像的那個
    for dataset in datasets:
        title = dataset.get("title", "")
        # 確保標題包含我們要把關的關鍵字
        if "景氣" in title and "燈號" in title:
            # 取得該資料集底下的所有資源 (Resources)
            dataset_id = dataset.get("id")
            # 再次呼叫 API 取得該 Dataset 的詳細資源列表
            detail_url = f"https://data.gov.tw/api/v2/rest/dataset/{dataset_id}"
            try:
                r_detail = requests.get(detail_url, timeout=10)
                if r_detail.status_code == 200:
                    resources = r_detail.json().get("result", {}).get("resources", [])
                    for res in resources:
                        # 檢查檔案格式
                        fmt = (res.get("file_ext") or res.get("format") or "").lower()
                        if "csv" in fmt:
                            csv_url = res.get("resource_url")
                            target_dataset_title = title
                            break
            except:
                continue
        
        if csv_url:
            break
    
    if not csv_url:
        print("❌ 找不到任何 CSV 格式的下載點 (可能只有 XML/JSON 或 API)")
        sys.exit(1)

    print(f"   ✅ 鎖定資料集: {target_dataset_title}")
    print(f"   ⬇️ 下載連結: {csv_url}")

    # 3. 下載並解析 CSV
    try:
        # 國發會的 CSV 下載點有時候會有轉址，requests 會自動處理
        file_res = requests.get(csv_url, timeout=60)
        file_res.raise_for_status()
        
        # 嘗試解碼 (Big5 或 UTF-8)
        try:
            content = file_res.content.decode('utf-8')
        except UnicodeDecodeError:
            content = file_res.content.decode('big5')
            
        # 讀入 Pandas
        df_raw = pd.read_csv(io.StringIO(content))
        
        # 4. 欄位識別與資料清洗
        # 國發會的 CSV 欄位名稱常變，我們用「內容」來判斷
        # 通常第 1 欄是日期，第 2 欄是分數 (或相反)
        
        records = []
        print(f"   ...正在解析 {len(df_raw)} 筆資料...")
        
        for idx, row in df_raw.iterrows():
            # 暴力搜尋法：找這一行裡面哪個像日期，哪個像分數
            date_val = None
            score_val = None
            
            for col in df_raw.columns:
                val = row[col]
                str_val = str(val).strip()
                
                # 判斷是否為分數 (通常是 9 ~ 50 之間的整數)
                # 排除像年份的數字 (例如 1984, 2023)
                if str_val.isdigit() or (str_val.replace('.', '', 1).isdigit() and '.' in str_val):
                    v_float = float(str_val)
                    if 9 <= v_float <= 55 and score_val is None:
                        score_val = v_float
                        continue
                
                # 判斷是否為日期
                if parse_taiwan_date(str_val) and date_val is None:
                    date_val = parse_taiwan_date(str_val)
            
            if date_val and score_val:
                records.append({
                    "Date": date_val.strftime("%Y-%m-%d"),
                    "Score": score_val
                })

        if not records:
            print("❌ 解析失敗：無法從 CSV 中識別出日期與分數")
            print("DEBUG: 前幾行資料:", df_raw.head())
            sys.exit(1)

        # 5. 存檔
        df = pd.DataFrame(records)
        df = df.drop_duplicates(subset=["Date"], keep="last")
        df = df.set_index("Date").sort_index()
        
        df.to_csv(CSV_PATH)
        print(f"🎉 [Job: Score] 成功更新！已儲存至: {CSV_PATH}")
        print(f"   資料區間: {df.index[0]} ~ {df.index[-1]}")
        print(f"   最新分數: {df['Score'].iloc[-1]} 分")

    except Exception as e:
        print(f"❌ 下載或解析過程發生錯誤: {e}")
        sys.exit(1)

if __name__ == "__main__":
    fetch_score_data()
