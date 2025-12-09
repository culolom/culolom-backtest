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

SEARCH_API = "https://data.gov.tw/api/v2/rest/dataset/search"
DATASET_API = "https://data.gov.tw/api/v2/rest/dataset/{}"


# -----------------------------------------------------
# 工具：解析台灣日期
# -----------------------------------------------------
def parse_taiwan_date(date_str):
    s = str(date_str).strip()
    try:
        # yyyyMM
        if len(s) == 6 and s.isdigit():
            return datetime.strptime(s, "%Y%m")
        # 民國年 5 碼 07301
        elif len(s) == 5 and s.isdigit():
            year = int(s[:3]) + 1911
            month = int(s[3:])
            return datetime(year, month, 1)
        # yyyy/MM 或 yyyy-MM
        elif "-" in s or "/" in s:
            s = s.replace("/", "-")
            parts = s.split("-")
            if len(parts) >= 2:
                year = int(parts[0])
                month = int(parts[1])
                if year < 1911:
                    year += 1911
                return datetime(year, month, 1)
    except:
        pass
    return None


# -----------------------------------------------------
# 主邏輯 → 抓 Score
# -----------------------------------------------------
def fetch_score_data():
    print("🚀 [Job: Score] 開始執行：搜尋資料集 + 下載最新資料...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------
    # 步驟 1：使用官方 API 搜尋 Dataset（絕對不會因 HTML 改版壞掉）
    # -----------------------------------------------------------
    target_title = "景氣指標及燈號"
    print(f"   ...搜尋: {target_title}")

    try:
        r = requests.get(
            SEARCH_API,
            params={"q": target_title},
            timeout=15
        )
        r.raise_for_status()
        search_data = r.json()

        datasets = search_data.get("result", {}).get("results", [])

        dataset_id = None

        # 找第一個 title 有包含「景氣指標及燈號」
        for d in datasets:
            if target_title in d.get("title", ""):
                dataset_id = d.get("identifier")
                break

        # fallback
        if not dataset_id and datasets:
            dataset_id = datasets[0].get("identifier")

        if not dataset_id:
            print("❌ 搜尋 API 找不到任何可用資料集")
            sys.exit(1)

        print(f"   ✅ Dataset ID: {dataset_id}")

    except Exception as e:
        print(f"❌ 搜尋 API 連線錯誤: {e}")
        sys.exit(1)

    # -----------------------------------------------------------
    # 步驟 2：用 API 抓該 Dataset 的資源列表
    # -----------------------------------------------------------
    api_url = DATASET_API.format(dataset_id)
    print(f"   ...取得資源列表: {api_url}")

    try:
        r = requests.get(api_url, timeout=15)
        r.raise_for_status()
        detail = r.json()
        resources = detail.get("result", {}).get("resources", [])
    except Exception as e:
        print(f"❌ 取得 Dataset 詳細資訊失敗: {e}")
        sys.exit(1)

    # -----------------------------------------------------------
    # 步驟 3：找 CSV；沒有 CSV → 找 JSON
    # -----------------------------------------------------------
    csv_url = None
    json_url = None

    for res in resources:
        fmt = str(res.get("file_ext") or res.get("format") or "").lower()
        desc = (res.get("resource_description") or "").lower()

        # 先找 CSV
        if "csv" in fmt or "csv" in desc:
            csv_url = res.get("resource_url")
            print(f"   ⬇️ 找到 CSV：{csv_url}")
            break

        # 找 JSON（備用）
        if ("json" in fmt or "json" in desc) and not json_url:
            json_url = res.get("resource_url")

    # -----------------------------------------------------------
    # 步驟 4：下載 CSV 或 JSON
    # -----------------------------------------------------------
    if csv_url:
        # ---- 下載 CSV ----
        try:
            print("   ...下載 CSV 資料")
            r = requests.get(csv_url, timeout=20)
            r.raise_for_status()

            df = pd.read_csv(io.StringIO(r.text))
            print(f"   📊 CSV 筆數: {len(df)}")

        except Exception as e:
            print(f"❌ CSV 下載失敗: {e}")
            sys.exit(1)

    else:
        # ---- 下載 JSON ----
        if not json_url:
            print("❌ 沒有 CSV 也沒有 JSON，無法下載資料")
            sys.exit(1)

        print(f"⚠️ 無 CSV，改用 JSON：{json_url}")

        try:
            r = requests.get(json_url, timeout=20)
            r.raise_for_status()
            data_json = r.json()

            # 嘗試把 JSON 轉成 DataFrame
            if isinstance(data_json, dict):
                df = pd.DataFrame(data_json.get("result", []))
            else:
                df = pd.DataFrame(data_json)

            print(f"   📊 JSON 筆數: {len(df)}")

        except Exception as e:
            print(f"❌ JSON 下載失敗: {e}")
            sys.exit(1)

    # -----------------------------------------------------------
    # 步驟 5：資料清洗（日期 → datetime）
    # -----------------------------------------------------------
    date_cols = ["日期", "時間", "年月", "月份"]
    found_date_col = None

    for col in df.columns:
        if col in date_cols:
            found_date_col = col
            break

    if found_date_col:
        df["parsed_date"] = df[found_date_col].apply(parse_taiwan_date)
        df = df.dropna(subset=["parsed_date"])
        df = df.sort_values("parsed_date")
        df = df.reset_index(drop=True)
        print(f"   📅 日期欄位解析完成: {found_date_col}")

    # -----------------------------------------------------------
    # 步驟 6：寫入 CSV
    # -----------------------------------------------------------
    df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    print(f"   💾 已儲存至 {CSV_PATH}")

    print("🎉 Score 爬取完成")
    return df


# -----------------------------------------------------
# main
# -----------------------------------------------------
if __name__ == "__main__":
    fetch_score_data()
