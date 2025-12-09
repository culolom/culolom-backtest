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

# 直接使用正確的資料集 ID
DATASET_ID = "11601"
DATASET_API = f"https://data.gov.tw/api/v2/rest/dataset/{DATASET_ID}"

def parse_taiwan_date(date_str):
    s = str(date_str).strip()
    try:
        if len(s) == 6 and s.isdigit():
            return datetime.strptime(s, "%Y%m")
        elif len(s) == 5 and s.isdigit():
            year = int(s[:3]) + 1911
            month = int(s[3:])
            return datetime(year, month, 1)
        elif "-" in s or "/" in s:
            s = s.replace("/", "-")
            year, month = s.split("-")[:2]
            year = int(year)
            month = int(month)
            if year < 1911:
                year += 1911
            return datetime(year, month, 1)
    except:
        pass
    return None

def fetch_score_data():
    print("🚀 [Job: Score] 開始執行：下載景氣指標及燈號（ID=11601）...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------
    # 步驟 1：查 dataset 資源
    # -----------------------------------------------------------
    print(f"   ...查詢資源列表：{DATASET_API}")

    try:
        r = requests.get(DATASET_API, timeout=15)
        r.raise_for_status()
        detail = r.json()
        resources = detail.get("result", {}).get("resources", [])
    except Exception as e:
        print(f"❌ Dataset API 錯誤: {e}")
        sys.exit(1)

    # -----------------------------------------------------------
    # 步驟 2：找 CSV 優先；找不到就找 JSON
    # -----------------------------------------------------------
    csv_url = None
    json_url = None

    for res in resources:
        fmt = str(res.get("file_ext") or res.get("format") or "").lower()
        desc = str(res.get("resource_description") or "").lower()

        if "csv" in fmt or "csv" in desc:
            csv_url = res.get("resource_url")
        if "json" in fmt or "json" in desc:
            json_url = res.get("resource_url")

    if csv_url:
        print(f"   ⬇️ CSV 來源：{csv_url}")
    else:
        print("⚠️ 沒找到 CSV，改抓 JSON")
        if not json_url:
            print("❌ 找不到 CSV/JSON 兩種格式，無法下載")
            sys.exit(1)

    # -----------------------------------------------------------
    # 步驟 3：下載 CSV/JSON
    # -----------------------------------------------------------
    try:
        if csv_url:
            r = requests.get(csv_url, timeout=15)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
        else:
            r = requests.get(json_url, timeout=15)
            r.raise_for_status()
            df = pd.DataFrame(r.json())
    except Exception as e:
        print(f"❌ 資料下載失敗: {e}")
        sys.exit(1)

    # -----------------------------------------------------------
    # 步驟 4：寫入本地 CSV
    # -----------------------------------------------------------
    df.to_csv(CSV_PATH, index=False, e
