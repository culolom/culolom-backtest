import requests
import pandas as pd
import os
import sys
import io
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# -----------------------------------------------------
# 設定
# -----------------------------------------------------
DATA_DIR = Path("data")
CSV_PATH = DATA_DIR / "SCORE.csv"

# 政府資料開放平臺 API (Dataset ID: 14603)
OPEN_DATA_API = "https://data.gov.tw/api/v2/rest/dataset/14603"

def parse_date(raw_date):
    """ 統一處理民國/西元日期格式 """
    raw_date = str(raw_date).strip()
    try:
        # 格式 A: "198401" (西元年月)
        if len(raw_date) == 6 and raw_date.isdigit():
            return datetime.strptime(raw_date, "%Y%m")
        # 格式 B: "07301" (民國年月 - 3位年+2位月)
        elif len(raw_date) == 5 and raw_date.isdigit():
            year = int(raw_date[:3]) + 1911
            month = int(raw_date[3:])
            return datetime(year, month, 1)
        # 格式 C: "7301" (民國年月 - 2位年+2位月)
        elif len(raw_date) == 4 and raw_date.isdigit():
            year = int(raw_date[:2]) + 1911
            month = int(raw_date[2:])
            return datetime(year, month, 1)
        # 格式 D: "1984/01" 或 "073/01"
        elif "/" in raw_date:
            parts = raw_date.split('/')
            if len(parts[0]) <= 3: # 民國
                year = int(parts[0]) + 1911
            else: # 西元
                year = int(parts[0])
            return datetime(year, int(parts[1]), 1)
    except:
        return None
    return None

def fetch_score_data():
    print("🚀 [Job: Score] 開始抓取國發會景氣對策信號 (Smart Mode)...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 取得資料集 Metadata
    try:
        res = requests.get(OPEN_DATA_API, timeout=15)
        res.raise_for_status()
        meta = res.json()
        resources = meta.get("result", {}).get("resources", [])
        
        if not resources:
            print("❌ API 回傳無資源 (Resources is empty)")
            sys.exit(1)
            
        print(f"   ...發現 {len(resources)} 個資源檔案")
    except Exception as e:
        print(f"❌ 取得 Metadata 失敗: {e}")
        sys.exit(1)

    # 2. 尋找最佳下載點 (優先 CSV > JSON > XML)
    target_resource = None
    
    # 先找 CSV
    for r in resources:
        fmt = (r.get("file_ext") or r.get("format") or "").lower()
        if "csv" in fmt:
            target_resource = (r, "csv")
            break
    
    # 沒 CSV 找 JSON
    if not target_resource:
        for r in resources:
            fmt = (r.get("file_ext") or r.get("format") or "").lower()
            if "json" in fmt:
                target_resource = (r, "json")
                break
                
    # 沒 JSON 找 XML
    if not target_resource:
        for r in resources:
            fmt = (r.get("file_ext") or r.get("format") or "").lower()
            if "xml" in fmt:
                target_resource = (r, "xml")
                break

    if not target_resource:
        print("❌ 找不到支援的格式 (CSV/JSON/XML)")
        # 印出所有可用格式供除錯
        available_fmts = [r.get("file_ext") or r.get("format") for r in resources]
        print(f"   DEBUG: 可用格式: {available_fmts}")
        sys.exit(1)

    resource, file_type = target_resource
    download_url = resource["resource_url"]
    print(f"   ✅ 鎖定資源: [{file_type.upper()}] {download_url}")

    # 3. 下載並解析
    try:
        file_res = requests.get(download_url, timeout=30)
        file_res.raise_for_status()
        
        records = []
        
        # --- 解析 CSV ---
        if file_type == "csv":
            # 嘗試不同編碼
            try:
                df_raw = pd.read_csv(io.BytesIO(file_res.content), encoding='utf-8')
            except:
                df_raw = pd.read_csv(io.BytesIO(file_res.content), encoding='big5') # 政府資料常是 big5
            
            # 假設第0欄是日期，第1欄是分數 (國發會標準格式)
            for _, row in df_raw.iterrows():
                dt = parse_date(row.iloc[0])
                if dt:
                    records.append({"Date": dt.strftime("%Y-%m-%d"), "Score": float(row.iloc[1])})

        # --- 解析 JSON ---
        elif file_type == "json":
            json_data = file_res.json()
            # 國發會 JSON 通常是個 list，或是 {'records': [...]}
            if isinstance(json_data, dict):
                json_data = json_data.get("result", {}).get("records", []) or json_data.get("records", [])
            
            for item in json_data:
                # 嘗試抓取日期與分數欄位 (欄位名稱可能會變，這裡做模糊搜尋)
                date_val = None
                score_val = None
                
                for k, v in item.items():
                    if "年月" in k or "date" in k.lower():
                        date_val = v
                    if "分數" in k or "score" in k.lower() or "信號" in k:
                        # 排除"燈號"文字欄位
                        if isinstance(v, (int, float)) or (isinstance(v, str) and v.replace('.','').isdigit()):
                            score_val = v
                
                if date_val and score_val:
                    dt = parse_date(date_val)
                    if dt:
                        records.append({"Date": dt.strftime("%Y-%m-%d"), "Score": float(score_val)})

        # --- 解析 XML ---
        elif file_type == "xml":
            root = ET.fromstring(file_res.content)
            # 簡單遍歷所有子節點尋找資料
            for child in root:
                date_val = None
                score_val = None
                for sub in child:
                    if sub.text:
                        if "date" in sub.tag.lower() or "年月" in sub.tag:
                            date_val = sub.text
                        if "score" in sub.tag.lower() or "分數" in sub.tag:
                            score_val = sub.text
                
                if date_val and score_val:
                    dt = parse_date(date_val)
                    if dt:
                        records.append({"Date": dt.strftime("%Y-%m-%d"), "Score": float(score_val)})

    except Exception as e:
        print(f"❌ 解析檔案失敗: {e}")
        sys.exit(1)

    # 4. 存檔
    if not records:
        print("❌ 解析後無有效數據，請檢查原始檔案結構")
        sys.exit(1)

    df = pd.DataFrame(records)
    # 移除重複並排序
    df = df.drop_duplicates(subset=["Date"], keep="last")
    df = df.set_index("Date").sort_index()
    
    df.to_csv(CSV_PATH)
    print(f"🎉 [Job: Score] 成功！已儲存 {len(df)} 筆資料至: {CSV_PATH}")
    print(f"   最新一筆: {df.index[-1]} -> {df['Score'].iloc[-1]} 分")

if __name__ == "__main__":
    fetch_score_data()
