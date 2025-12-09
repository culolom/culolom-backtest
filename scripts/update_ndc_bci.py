import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

# Output CSV Path
OUT = Path("data/ndc_bci.csv")

def fetch_ndc_bci():
    """Fetch 景氣對策信號（藍黃紅燈）的 API"""
    
    url = "https://www.ndc.gov.tw/ncapi/dig/ods/288/?$format=json"
    resp = requests.get(url)
    resp.raise_for_status()

    data = resp.json()

    df = pd.DataFrame(data)

    # 整理欄位（國發會 API 有點亂）
    df = df.rename(columns={
        "yyyymm": "date",
        "composite_indicator": "score",
        "signal": "signal"
    })

    # 日期處理
    df["date"] = pd.to_datetime(df["date"], format="%Y%m")

    df = df.sort_values("date")
    return df


def main():
    df = fetch_ndc_bci()
    OUT.parent.mkdir(exist_ok=True, parents=True)
    df.to_csv(OUT, index=False)
    print(f"Saved → {OUT}")


if __name__ == "__main__":
    main()
