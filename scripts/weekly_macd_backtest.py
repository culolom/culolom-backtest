from pathlib import Path

import pandas as pd


# =========================================================
# 基本設定
# =========================================================

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9


# 取得專案根目錄
PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = PROJECT_ROOT / "data" / "^TWII.csv"
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_FILE = OUTPUT_DIR / "twii_weekly_macd_signals.csv"


def load_daily_data(file_path: Path) -> pd.DataFrame:
    """
    讀取台灣加權指數日線資料。
    必要欄位：
    - Date
    - Close
    """

    if not file_path.exists():
        raise FileNotFoundError(f"找不到資料檔案：{file_path}")

    df = pd.read_csv(file_path)

    required_columns = {"Date", "Close"}
    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"CSV 缺少必要欄位：{sorted(missing_columns)}"
        )

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")

    df = (
        df.dropna(subset=["Date", "Close"])
        .sort_values("Date")
        .drop_duplicates(subset=["Date"], keep="last")
        .set_index("Date")
    )

    if df.empty:
        raise ValueError("資料清理後沒有可使用的行情資料")

    return df


def convert_to_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    將日線資料轉成週線。

    使用 W-FRI：
    每週以星期五作為週期標籤。
    如果星期五休市，會取該週最後一個交易日。
    """

    weekly = daily_df[["Close"]].resample("W-FRI").last()

    weekly = weekly.dropna(subset=["Close"]).copy()

    return weekly


def calculate_macd(weekly_df: pd.DataFrame) -> pd.DataFrame:
    """
    計算週線 MACD（12, 26, 9）。
    """

    df = weekly_df.copy()

    df["ema_fast"] = df["Close"].ewm(
        span=MACD_FAST,
        adjust=False
    ).mean()

    df["ema_slow"] = df["Close"].ewm(
        span=MACD_SLOW,
        adjust=False
    ).mean()

    df["macd"] = df["ema_fast"] - df["ema_slow"]

    df["signal"] = df["macd"].ewm(
        span=MACD_SIGNAL,
        adjust=False
    ).mean()

    df["histogram"] = df["macd"] - df["signal"]

    return df


def detect_crossovers(macd_df: pd.DataFrame) -> pd.DataFrame:
    """
    判斷黃金交叉與死亡交叉。

    黃金交叉：
    本週 MACD > Signal，
    上週 MACD <= Signal。

    死亡交叉：
    本週 MACD < Signal，
    上週 MACD >= Signal。
    """

    df = macd_df.copy()

    previous_macd = df["macd"].shift(1)
    previous_signal = df["signal"].shift(1)

    df["golden_cross"] = (
        (df["macd"] > df["signal"])
        & (previous_macd <= previous_signal)
    )

    df["death_cross"] = (
        (df["macd"] < df["signal"])
        & (previous_macd >= previous_signal)
    )

    df["signal_type"] = "none"

    df.loc[df["golden_cross"], "signal_type"] = "golden_cross"
    df.loc[df["death_cross"], "signal_type"] = "death_cross"

    return df


def print_summary(result_df: pd.DataFrame) -> None:
    """
    在執行畫面顯示基本檢查結果。
    """

    golden_crosses = result_df[result_df["golden_cross"]]
    death_crosses = result_df[result_df["death_cross"]]

    print("=" * 60)
    print("台灣加權指數週線 MACD 訊號")
    print("=" * 60)

    print(f"週線資料起點：{result_df.index.min().date()}")
    print(f"週線資料終點：{result_df.index.max().date()}")
    print(f"週線資料筆數：{len(result_df):,}")
    print(f"黃金交叉次數：{len(golden_crosses):,}")
    print(f"死亡交叉次數：{len(death_crosses):,}")

    print("\n最近 10 次交叉：")

    recent_signals = result_df[
        result_df["signal_type"] != "none"
    ][
        [
            "Close",
            "macd",
            "signal",
            "histogram",
            "signal_type",
        ]
    ].tail(10)

    if recent_signals.empty:
        print("目前沒有偵測到交叉訊號")
    else:
        print(recent_signals.to_string())

    latest = result_df.iloc[-1]

    print("\n目前最新週線：")
    print(f"日期：{result_df.index[-1].date()}")
    print(f"收盤指數：{latest['Close']:.2f}")
    print(f"MACD：{latest['macd']:.2f}")
    print(f"Signal：{latest['signal']:.2f}")
    print(f"柱狀體：{latest['histogram']:.2f}")
    print(f"本週訊號：{latest['signal_type']}")


def save_signals(result_df: pd.DataFrame, output_file: Path) -> None:
    """
    暫時輸出成 CSV，方便先檢查 MACD 訊號是否正確。

    下一步確認結果後，再改成正式 JSON。
    """

    output_file.parent.mkdir(parents=True, exist_ok=True)

    export_df = result_df.reset_index()

    export_df["Date"] = export_df["Date"].dt.strftime("%Y-%m-%d")

    numeric_columns = [
        "Close",
        "ema_fast",
        "ema_slow",
        "macd",
        "signal",
        "histogram",
    ]

    export_df[numeric_columns] = export_df[numeric_columns].round(4)

    export_df.to_csv(
        output_file,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"\n輸出完成：{output_file}")


def main() -> None:
    daily_df = load_daily_data(INPUT_FILE)

    weekly_df = convert_to_weekly(daily_df)

    macd_df = calculate_macd(weekly_df)

    result_df = detect_crossovers(macd_df)

    print_summary(result_df)

    save_signals(result_df, OUTPUT_FILE)


if __name__ == "__main__":
    main()
