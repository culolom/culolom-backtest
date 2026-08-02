from pathlib import Path

import pandas as pd


# 專案根目錄
ROOT_DIR = Path(__file__).resolve().parents[1]

# 台股加權指數資料位置
DATA_PATH = ROOT_DIR / "data" / "^TWII.csv"


def load_twii_data(csv_path: Path = DATA_PATH) -> pd.DataFrame:
    """
    讀取台股加權指數歷史資料，並進行基本清理。
    """

    if not csv_path.exists():
        raise FileNotFoundError(f"找不到資料檔案：{csv_path}")

    df = pd.read_csv(csv_path)

    required_columns = {"Date", "Close"}
    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"CSV 缺少必要欄位：{sorted(missing_columns)}；"
            f"目前欄位為：{list(df.columns)}"
        )

    # 日期轉換
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    # 收盤價轉換
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")

    # 移除無效資料
    df = df.dropna(subset=["Date", "Close"])

    # 日期由舊到新排序
    df = df.sort_values("Date").reset_index(drop=True)

    # 移除重複日期，只保留最後一筆
    df = df.drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)

    # 計算200日簡單移動平均線
    df["SMA200"] = df["Close"].rolling(
        window=200,
        min_periods=200
    ).mean()

    # 收盤價和200SMA的距離
    df["DistanceFromSMA200"] = df["Close"] / df["SMA200"] - 1

    return df


def print_data_summary(df: pd.DataFrame) -> None:
    """
    顯示資料檢查結果。
    """

    print("=" * 60)
    print("台股加權指數資料檢查")
    print("=" * 60)

    print(f"資料筆數：{len(df):,}")
    print(f"起始日期：{df['Date'].min().date()}")
    print(f"結束日期：{df['Date'].max().date()}")
    print(f"最低收盤：{df['Close'].min():,.2f}")
    print(f"最高收盤：{df['Close'].max():,.2f}")
    print(f"重複日期：{df['Date'].duplicated().sum()}")
    print(f"空白收盤價：{df['Close'].isna().sum()}")
    print(f"可計算200SMA筆數：{df['SMA200'].notna().sum():,}")

    print("\n最新5筆資料：")

    display_columns = [
        "Date",
        "Close",
        "SMA200",
        "DistanceFromSMA200",
    ]

    latest = df[display_columns].tail(5).copy()

    latest["Date"] = latest["Date"].dt.strftime("%Y-%m-%d")
    latest["DistanceFromSMA200"] = (
        latest["DistanceFromSMA200"] * 100
    ).round(2)

    print(latest.to_string(index=False))

    print("=" * 60)


def main() -> None:
    df = load_twii_data()
    print_data_summary(df)


if __name__ == "__main__":
    main()
