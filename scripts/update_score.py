import requests
import pandas as pd
import io
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# -----------------------------------------------------
# 設定
# -----------------------------------------------------
DATA_DIR = Path("data")
CSV_PATH = DATA_DIR / "SCORE.csv"

# 政府資料開放平臺 API (鎖定 ID 6099)
DATASET_ID = "6099"
API_URL = f"https://data.gov.tw/api/v2/rest/dataset/{DATASET_ID}"

def parse_taiwan_date(date_str):
    """ 強力解析日期 (支援 11201, 198401, 2023-01) """
    s = str(date_str).strip()
    try:
        # 6位數字: 198401
        if len(s) == 6 and s.isdigit():
            return datetime.strptime(s, "%Y%m")
        # 5位數字 (民國): 07301
        elif len(s) == 5 and s.isdigit():
            year = int(s[:3]) + 1911
            month = int(s[3:])
            return datetime(year, month, 1)
        # 4位數字 (民國簡寫): 7301
        elif len(s) == 4 and s.isdigit():
            year = int(s[:2]) + 1911
            month = int(s[2:])
            return datetime(year, month, 1)
        # 含符號: 1984-01, 1984/01
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
    print(f"🚀 [Job: Score] 開始執行：抓取景氣對策信號 (ID: {DATASET_ID})...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 取得資源列表
    print(f"   ...查詢 API: {API_URL}")
    try:
        res = requests.get(API_URL, timeout=15)
        res.raise_for_status()
        data = res.json()
        resources = data.get("result", {}).get("resources", [])
        
        if not resources:
            print("❌ 無資源檔案")
            sys.exit(1)
    except Exception as e:
        print(f"❌ API 連線失敗: {e}")
        sys.exit(1)

    # 2. 尋找下載點 (優先順序: JSON > CSV > XML)
    target_res = None
    file_type = ""
    
    # 先找 JSON
    for r in resources:
        fmt = str(r.get("file_ext") or r.get("format") or "").lower()
        if "json" in fmt:
            target_res = r
            file_type = "json"
            break
            
    # 沒 JSON 找 CSV
    if not target_res:
        for r in resources:
            fmt = str(r.get("file_ext") or r.get("format") or "").lower()
            if "csv" in fmt:
                target_res = r
                file_type = "csv"
                break
                
    # 沒 CSV 找 XML
    if not target_res:
        for r in resources:
            fmt = str(r.get("file_ext") or r.get("format") or "").lower()
            if "xml" in fmt:
                target_res = r
                file_type = "xml"
                break

    if not target_res:
        print(f"❌ 找不到支援的格式 (JSON/CSV/XML)，可用格式: {[r.get('format') for r in resources]}")
        sys.exit(1)

    download_url = target_res["resource_url"]
    print(f"   ✅ 鎖定資源: [{file_type.upper()}] {download_url}")

    # 3. 下載與解析
    try:
        print(f"   ⬇️ 正在下載...")
        file_res = requests.get(download_url, timeout=60)
        file_res.raise_for_status()
        content = file_res.content
        
        records = []

        # --- 解析 JSON ---
        if file_type == "json":
            json_data = file_res.json()
            # 有時候 JSON 外面會包一層結構，有時候是直接 list
            # 國發會結構通常是 list 或 {'result': {'records': [...]}}
            items = []
            if isinstance(json_data, list):
                items = json_data
            elif isinstance(json_data, dict):
                items = json_data.get("result", {}).get("records", []) or json_data.get("records", [])

            print(f"   ...解析 JSON ({len(items)} 筆)...")
            for item in items:
                # 暴力搜尋 Key
                d_val = None
                s_val = None
                for k, v in item.items():
                    if "年月" in k or "date" in k.lower():
                        d_val = v
                    # 找分數 (排除燈號文字)
                    if ("分數" in k or "信號" in k or "score" in k.lower()) and isinstance(v, (int, float, str)):
                         if str(v).isdigit(): s_val = v
                
                if d_val and s_val:
                    dt = parse_taiwan_date(d_val)
                    if dt:
                        records.append({"Date": dt.strftime("%Y-%m-%d"), "Score": float(s_val)})

        # --- 解析 XML ---
        elif file_type == "xml":
            print("   ...解析 XML...")
            root = ET.fromstring(content)
            # 簡單遍歷所有子節點
            for child in root:
                d_val = None
                s_val = None
                for sub in child:
                    if not sub.text: continue
                    if "年月" in sub.tag or "date" in sub.tag.lower():
                        d_val = sub.text
                    if ("分數" in sub.tag or "信號" in sub.tag) and sub.text.isdigit():
                        s_val = sub.text
                
                if d_val and s_val:
                    dt = parse_taiwan_date(d_val)
                    if dt:
                        records.append({"Date": dt.strftime("%Y-%m-%d"), "Score": float(s_val)})

        # --- 解析 CSV ---
        elif file_type == "csv":
            try:
                df_raw = pd.read_csv(io.BytesIO(content), encoding='utf-8')
            except:
                df_raw = pd.read_csv(io.BytesIO(content), encoding='big5')
            
            for _, row in df_raw.iterrows():
                d_val = None
                s_val = None
                for col in df_raw.columns:
                    val = str(row[col]).strip()
                    if d_val is None:
                        dt = parse_taiwan_date(val)
                        if dt: d_val = dt; continue
                    if s_val is None and val.isdigit() and 9 <= float(val) <= 55:
                        s_val = float(val)
                
                if d_val and s_val:
                    records.append({"Date": d_val.strftime("%Y-%m-%d"), "Score": s_val})

        # 4. 存檔
        if not records:
            print("❌ 解析後無有效數據")
            sys.exit(1)

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
