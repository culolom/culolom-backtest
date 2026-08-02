from pathlib import Path
from typing import Optional

import pandas as pd


# ============================================================
# 基本設定
# ============================================================

# 專案根目錄
ROOT_DIR = Path(__file__).resolve().parents[1]

# 台股加權指數資料位置
DATA_PATH = ROOT_DIR / "data" / "^TWII.csv"


# ============================================================
# 讀取與整理資料
# ============================================================

def load_twii_data(csv_path: Path = DATA_PATH) -> pd.DataFrame:
    """
    讀取台股加權指數歷史資料，進行基本清理，
    並計算200日簡單移動平均線。

    必要欄位：
    - Date
    - Close
    """

    if not csv_path.exists():
        raise FileNotFoundError(f"找不到資料檔案：{csv_path}")

    df = pd.read_csv(csv_path)

    required_columns = {"Date", "Close"}
    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"CSV缺少必要欄位：{sorted(missing_columns)}；"
            f"目前欄位為：{list(df.columns)}"
        )

    # 日期轉換
    df["Date"] = pd.to_datetime(
        df["Date"],
        errors="coerce",
    )

    # 收盤價轉換
    df["Close"] = pd.to_numeric(
        df["Close"],
        errors="coerce",
    )

    # 移除日期或收盤價無效的資料
    df = df.dropna(
        subset=["Date", "Close"]
    ).copy()

    # 日期由舊到新排序
    df = df.sort_values("Date").reset_index(drop=True)

    # 若有重複日期，只保留最後一筆
    df = (
        df.drop_duplicates(
            subset=["Date"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    # 計算200日簡單移動平均線
    df["SMA200"] = (
        df["Close"]
        .rolling(
            window=200,
            min_periods=200,
        )
        .mean()
    )

    # 收盤價距離200SMA的百分比
    df["DistanceFromSMA200"] = (
        df["Close"] / df["SMA200"] - 1
    )

    return df


# ============================================================
# 顯示資料摘要
# ============================================================

def print_data_summary(df: pd.DataFrame) -> None:
    """
    顯示台股歷史資料的基本檢查結果。
    """

    print("=" * 80)
    print("台股加權指數資料檢查")
    print("=" * 80)

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

    latest["Close"] = latest["Close"].round(2)
    latest["SMA200"] = latest["SMA200"].round(2)

    latest["DistanceFromSMA200"] = (
        latest["DistanceFromSMA200"] * 100
    ).round(2)

    latest = latest.rename(
        columns={
            "DistanceFromSMA200": "距離200SMA(%)",
        }
    )

    print(latest.to_string(index=False))

    print("=" * 80)


# ============================================================
# 找出跌破200SMA事件
# ============================================================

def find_below_sma_events(df: pd.DataFrame) -> pd.DataFrame:
    """
    找出每一次跌破200SMA的完整事件。

    事件開始：
    - 前一交易日收盤在200SMA以上或等於200SMA
    - 當日收盤跌到200SMA以下

    事件結束：
    - 收盤重新站回200SMA以上或等於200SMA

    每一段均線下方期間只計算一次。
    """

    data = (
        df.dropna(subset=["SMA200"])
        .copy()
        .reset_index(drop=True)
    )

    if data.empty:
        return pd.DataFrame()

    # 是否位於200SMA下方
    data["BelowSMA200"] = (
        data["Close"] < data["SMA200"]
    )

    # 前一日是否位於200SMA下方
    data["PreviousBelowSMA200"] = (
        data["BelowSMA200"]
        .shift(1)
        .fillna(False)
        .astype(bool)
    )

    # 今天在均線下方，昨天不在均線下方
    data["CrossBelow"] = (
        data["BelowSMA200"]
        & ~data["PreviousBelowSMA200"]
    )

    events: list[dict] = []

    event_id = 1
    index = 0

    while index < len(data):

        if not bool(data.loc[index, "CrossBelow"]):
            index += 1
            continue

        start_index = index
        start_row = data.loc[start_index]

        # 找到最後一個仍位於200SMA下方的交易日
        end_index = start_index

        while (
            end_index + 1 < len(data)
            and bool(data.loc[end_index + 1, "BelowSMA200"])
        ):
            end_index += 1

        event_data = data.loc[
            start_index:end_index
        ].copy()

        # 找出事件期間最低收盤價
        lowest_index = event_data["Close"].idxmin()
        lowest_row = data.loc[lowest_index]

        cross_close = float(start_row["Close"])
        cross_sma200 = float(start_row["SMA200"])
        lowest_close = float(lowest_row["Close"])

        # 從跌破200SMA當日收盤價算到最低點
        drawdown_from_cross = (
            lowest_close / cross_close - 1
        )

        # 找跌破日前200個交易日內的最高收盤價
        previous_window_start = max(
            0,
            start_index - 200,
        )

        previous_data = data.loc[
            previous_window_start:start_index,
            ["Date", "Close"],
        ].copy()

        previous_high_index = (
            previous_data["Close"].idxmax()
        )

        previous_high_row = data.loc[
            previous_high_index
        ]

        previous_high_close = float(
            previous_high_row["Close"]
        )

        # 從前波高點算到事件最低點
        drawdown_from_previous_high = (
            lowest_close / previous_high_close - 1
        )

        # 預設為尚未站回200SMA
        recovery_date: Optional[pd.Timestamp] = None
        recovery_close: Optional[float] = None
        recovery_sma200: Optional[float] = None

        # 若事件結束後還有下一筆資料，
        # 下一筆就是重新站回200SMA的日期
        if end_index + 1 < len(data):
            recovery_row = data.loc[end_index + 1]

            recovery_date = recovery_row["Date"]
            recovery_close = float(
                recovery_row["Close"]
            )
            recovery_sma200 = float(
                recovery_row["SMA200"]
            )

        events.append(
            {
                "EventID": event_id,
                "CrossBelowDate": start_row["Date"],
                "CrossBelowClose": cross_close,
                "CrossBelowSMA200": cross_sma200,
                "DistanceFromSMAAtCross": (
                    cross_close / cross_sma200 - 1
                ),
                "PreviousHighDate": previous_high_row["Date"],
                "PreviousHighClose": previous_high_close,
                "LowestDate": lowest_row["Date"],
                "LowestClose": lowest_close,
                "DrawdownFromCross": drawdown_from_cross,
                "DrawdownFromPreviousHigh": (
                    drawdown_from_previous_high
                ),
                "DaysBelowSMA": len(event_data),
                "RecoveryDate": recovery_date,
                "RecoveryClose": recovery_close,
                "RecoverySMA200": recovery_sma200,
                "Recovered": recovery_date is not None,
            }
        )

        event_id += 1

        # 跳到重新站回200SMA的交易日
        index = end_index + 1

    return pd.DataFrame(events)


# ============================================================
# 顯示跌破事件摘要
# ============================================================

def print_event_summary(events: pd.DataFrame) -> None:
    """
    顯示跌破200SMA事件摘要。
    """

    print("\n" + "=" * 120)
    print("跌破200SMA事件統計")
    print("=" * 120)

    if events.empty:
        print("沒有找到跌破200SMA事件。")
        return

    print(f"事件總數：{len(events)}")
    print(f"已重新站回200SMA：{events['Recovered'].sum()}")
    print(
        "尚未重新站回200SMA："
        f"{(~events['Recovered']).sum()}"
    )

    display = events.copy()

    date_columns = [
        "CrossBelowDate",
        "PreviousHighDate",
        "LowestDate",
        "RecoveryDate",
    ]

    for column in date_columns:
        display[column] = pd.to_datetime(
            display[column],
            errors="coerce",
        ).dt.strftime("%Y-%m-%d")

    percentage_columns = [
        "DistanceFromSMAAtCross",
        "DrawdownFromCross",
        "DrawdownFromPreviousHigh",
    ]

    for column in percentage_columns:
        display[column] = (
            display[column] * 100
        ).round(2)

    number_columns = [
        "CrossBelowClose",
        "CrossBelowSMA200",
        "PreviousHighClose",
        "LowestClose",
        "RecoveryClose",
        "RecoverySMA200",
    ]

    for column in number_columns:
        display[column] = pd.to_numeric(
            display[column],
            errors="coerce",
        ).round(2)

    display_columns = [
        "EventID",
        "CrossBelowDate",
        "CrossBelowClose",
        "LowestDate",
        "LowestClose",
        "DrawdownFromCross",
        "DrawdownFromPreviousHigh",
        "DaysBelowSMA",
        "RecoveryDate",
    ]

    display = display.rename(
        columns={
            "EventID": "事件",
            "CrossBelowDate": "跌破日期",
            "CrossBelowClose": "跌破收盤",
            "LowestDate": "最低點日期",
            "LowestClose": "最低收盤",
            "DrawdownFromCross": "跌破後最大跌幅(%)",
            "DrawdownFromPreviousHigh": "前高至最低跌幅(%)",
            "DaysBelowSMA": "均線下天數",
            "RecoveryDate": "站回日期",
        }
    )

    renamed_display_columns = [
        "事件",
        "跌破日期",
        "跌破收盤",
        "最低點日期",
        "最低收盤",
        "跌破後最大跌幅(%)",
        "前高至最低跌幅(%)",
        "均線下天數",
        "站回日期",
    ]

    print(
        display[renamed_display_columns]
        .to_string(index=False)
    )

    print("=" * 120)


# ============================================================
# 顯示整體統計
# ============================================================

def print_drawdown_statistics(
    events: pd.DataFrame,
) -> None:
    """
    顯示跌破200SMA後最大跌幅的基本統計。
    """

    print("\n" + "=" * 80)
    print("跌破200SMA後最大跌幅摘要")
    print("=" * 80)

    if events.empty:
        print("沒有事件可以統計。")
        return

    drawdowns = (
        events["DrawdownFromCross"] * 100
    )

    print(f"平均跌幅：{drawdowns.mean():.2f}%")
    print(f"中位數跌幅：{drawdowns.median():.2f}%")
    print(f"最淺跌幅：{drawdowns.max():.2f}%")
    print(f"最深跌幅：{drawdowns.min():.2f}%")
    print(
        "平均位於200SMA下方天數："
        f"{events['DaysBelowSMA'].mean():.1f}天"
    )
    print(
        "中位數位於200SMA下方天數："
        f"{events['DaysBelowSMA'].median():.1f}天"
    )

    print("=" * 80)


# ============================================================
# 主程式
# ============================================================

def main() -> None:
    try:
        df = load_twii_data()

        print_data_summary(df)

        events = find_below_sma_events(df)

        print_event_summary(events)

        print_drawdown_statistics(events)

    except FileNotFoundError as error:
        print(f"錯誤：{error}")
        raise SystemExit(1) from error

    except ValueError as error:
        print(f"資料格式錯誤：{error}")
        raise SystemExit(1) from error

    except Exception as error:
        print(f"程式執行失敗：{error}")
        raise


if __name__ == "__main__":
    main()
