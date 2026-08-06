from pathlib import Path

import pandas as pd


# =========================================================
# 基本設定
# =========================================================

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = PROJECT_ROOT / "data" / "^TWII.csv"

OUTPUT_DIR = PROJECT_ROOT / "output"

SIGNALS_OUTPUT_FILE = (
    OUTPUT_DIR / "twii_weekly_macd_signals.csv"
)

TRADES_OUTPUT_FILE = (
    OUTPUT_DIR / "twii_weekly_macd_trades.csv"
)


# =========================================================
# 讀取與整理資料
# =========================================================

def load_daily_data(file_path: Path) -> pd.DataFrame:
    """
    讀取台灣加權指數日線資料。

    必要欄位：
    - Date
    - Close
    """

    if not file_path.exists():
        raise FileNotFoundError(
            f"找不到資料檔案：{file_path}"
        )

    df = pd.read_csv(file_path)

    required_columns = {"Date", "Close"}
    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"CSV 缺少必要欄位：{sorted(missing_columns)}"
        )

    df["Date"] = pd.to_datetime(
        df["Date"],
        errors="coerce",
    )

    df["Close"] = pd.to_numeric(
        df["Close"],
        errors="coerce",
    )

    df = (
        df.dropna(subset=["Date", "Close"])
        .sort_values("Date")
        .drop_duplicates(
            subset=["Date"],
            keep="last",
        )
        .set_index("Date")
    )

    if df.empty:
        raise ValueError(
            "資料清理後沒有可使用的行情資料"
        )

    return df


def convert_to_weekly(
    daily_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    將日線資料轉成週線。

    weekly_period：
    該週所屬的星期五。

    signal_date：
    該週實際最後一個交易日。
    """

    source = daily_df.reset_index().copy()

    source["weekly_period"] = (
        source["Date"].dt.to_period("W-FRI")
    )

    weekly = (
        source.groupby("weekly_period")
        .agg(
            signal_date=("Date", "max"),
            Close=("Close", "last"),
        )
        .reset_index()
    )

    weekly["week_end"] = (
        weekly["weekly_period"]
        .dt.end_time
        .dt.normalize()
    )

    weekly = weekly.drop(
        columns=["weekly_period"]
    )

    weekly = (
        weekly.sort_values("signal_date")
        .set_index("week_end")
    )

    return weekly


# =========================================================
# 計算 MACD
# =========================================================

def calculate_macd(
    weekly_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    計算週線 MACD（12, 26, 9）。

    使用 min_periods，避免資料剛開始時
    EMA 尚未成熟就產生假交叉。
    """

    df = weekly_df.copy()

    df["ema_fast"] = (
        df["Close"]
        .ewm(
            span=MACD_FAST,
            adjust=False,
            min_periods=MACD_FAST,
        )
        .mean()
    )

    df["ema_slow"] = (
        df["Close"]
        .ewm(
            span=MACD_SLOW,
            adjust=False,
            min_periods=MACD_SLOW,
        )
        .mean()
    )

    df["macd"] = (
        df["ema_fast"] - df["ema_slow"]
    )

    df["signal"] = (
        df["macd"]
        .ewm(
            span=MACD_SIGNAL,
            adjust=False,
            min_periods=MACD_SIGNAL,
        )
        .mean()
    )

    df["histogram"] = (
        df["macd"] - df["signal"]
    )

    return df


def detect_crossovers(
    macd_df: pd.DataFrame,
) -> pd.DataFrame:
    """
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

    valid_current = (
        df["macd"].notna()
        & df["signal"].notna()
    )

    valid_previous = (
        previous_macd.notna()
        & previous_signal.notna()
    )

    df["golden_cross"] = (
        valid_current
        & valid_previous
        & (df["macd"] > df["signal"])
        & (previous_macd <= previous_signal)
    )

    df["death_cross"] = (
        valid_current
        & valid_previous
        & (df["macd"] < df["signal"])
        & (previous_macd >= previous_signal)
    )

    df["signal_type"] = "none"

    df.loc[
        df["golden_cross"],
        "signal_type",
    ] = "golden_cross"

    df.loc[
        df["death_cross"],
        "signal_type",
    ] = "death_cross"

    return df


# =========================================================
# 找下一個交易日
# =========================================================

def get_next_trading_day(
    daily_df: pd.DataFrame,
    signal_date: pd.Timestamp,
):
    """
    訊號於當週最後交易日收盤後確認。

    因此使用 signal_date 之後的
    下一個交易日收盤價成交。
    """

    future_data = daily_df[
        daily_df.index > signal_date
    ]

    if future_data.empty:
        return None

    next_date = future_data.index[0]
    next_close = float(
        future_data.iloc[0]["Close"]
    )

    return next_date, next_close


# =========================================================
# 建立交易紀錄
# =========================================================

def calculate_trade_excursions(
    daily_df: pd.DataFrame,
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
    entry_price: float,
):
    """
    計算持有期間：

    MFE：
    Maximum Favorable Excursion，
    最大有利變動。

    MAE：
    Maximum Adverse Excursion，
    最大不利變動。
    """

    holding_data = daily_df.loc[
        (daily_df.index >= entry_date)
        & (daily_df.index <= exit_date),
        "Close",
    ]

    if holding_data.empty:
        return 0.0, 0.0

    daily_returns_from_entry = (
        holding_data / entry_price - 1
    )

    mfe = float(
        daily_returns_from_entry.max()
    )

    mae = float(
        daily_returns_from_entry.min()
    )

    return mae, mfe


def build_trades(
    daily_df: pd.DataFrame,
    signal_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    將黃金交叉與下一個死亡交叉配對。

    規則：
    - 黃金交叉後下一交易日收盤買進
    - 死亡交叉後下一交易日收盤賣出
    - 不放空
    - 持有期間不重複買進
    """

    trades = []

    position_open = False

    entry_signal_date = None
    entry_date = None
    entry_price = None

    signal_rows = signal_df[
        signal_df["signal_type"] != "none"
    ].copy()

    for _, row in signal_rows.iterrows():

        signal_type = row["signal_type"]
        signal_date = pd.Timestamp(
            row["signal_date"]
        )

        execution = get_next_trading_day(
            daily_df=daily_df,
            signal_date=signal_date,
        )

        if execution is None:
            continue

        execution_date, execution_price = execution

        # 黃金交叉：建立新部位
        if (
            signal_type == "golden_cross"
            and not position_open
        ):
            position_open = True

            entry_signal_date = signal_date
            entry_date = execution_date
            entry_price = execution_price

        # 死亡交叉：平倉
        elif (
            signal_type == "death_cross"
            and position_open
        ):
            exit_signal_date = signal_date
            exit_date = execution_date
            exit_price = execution_price

            return_rate = (
                exit_price / entry_price - 1
            )

            holding_days = (
                exit_date - entry_date
            ).days

            holding_weeks = (
                holding_days / 7
            )

            mae, mfe = (
                calculate_trade_excursions(
                    daily_df=daily_df,
                    entry_date=entry_date,
                    exit_date=exit_date,
                    entry_price=entry_price,
                )
            )

            trades.append(
                {
                    "trade_id": len(trades) + 1,
                    "entry_signal_date":
                        entry_signal_date,
                    "entry_date":
                        entry_date,
                    "entry_price":
                        entry_price,
                    "exit_signal_date":
                        exit_signal_date,
                    "exit_date":
                        exit_date,
                    "exit_price":
                        exit_price,
                    "return_pct":
                        return_rate * 100,
                    "holding_days":
                        holding_days,
                    "holding_weeks":
                        holding_weeks,
                    "mae_pct":
                        mae * 100,
                    "mfe_pct":
                        mfe * 100,
                    "is_winner":
                        return_rate > 0,
                    "status":
                        "closed",
                }
            )

            position_open = False

            entry_signal_date = None
            entry_date = None
            entry_price = None

    # 最後一筆仍未出場
    if position_open:
        latest_date = daily_df.index[-1]

        latest_price = float(
            daily_df.iloc[-1]["Close"]
        )

        unrealized_return = (
            latest_price / entry_price - 1
        )

        holding_days = (
            latest_date - entry_date
        ).days

        holding_weeks = (
            holding_days / 7
        )

        mae, mfe = (
            calculate_trade_excursions(
                daily_df=daily_df,
                entry_date=entry_date,
                exit_date=latest_date,
                entry_price=entry_price,
            )
        )

        trades.append(
            {
                "trade_id": len(trades) + 1,
                "entry_signal_date":
                    entry_signal_date,
                "entry_date":
                    entry_date,
                "entry_price":
                    entry_price,
                "exit_signal_date":
                    pd.NaT,
                "exit_date":
                    pd.NaT,
                "exit_price":
                    None,
                "return_pct":
                    unrealized_return * 100,
                "holding_days":
                    holding_days,
                "holding_weeks":
                    holding_weeks,
                "mae_pct":
                    mae * 100,
                "mfe_pct":
                    mfe * 100,
                "is_winner":
                    unrealized_return > 0,
                "status":
                    "open",
            }
        )

    return pd.DataFrame(trades)


# =========================================================
# 顯示回測摘要
# =========================================================

def print_trade_summary(
    trades_df: pd.DataFrame,
) -> None:
    """
    顯示交易層級的基本統計。
    """

    if trades_df.empty:
        print("\n沒有可配對的交易")
        return

    closed_trades = trades_df[
        trades_df["status"] == "closed"
    ].copy()

    open_trades = trades_df[
        trades_df["status"] == "open"
    ].copy()

    print("\n" + "=" * 60)
    print("週線 MACD 交易摘要")
    print("=" * 60)

    print(
        f"已完成交易：{len(closed_trades)} 筆"
    )

    print(
        f"尚未平倉：{len(open_trades)} 筆"
    )

    if closed_trades.empty:
        return

    winning_trades = closed_trades[
        closed_trades["return_pct"] > 0
    ]

    losing_trades = closed_trades[
        closed_trades["return_pct"] <= 0
    ]

    win_rate = (
        len(winning_trades)
        / len(closed_trades)
        * 100
    )

    average_return = (
        closed_trades["return_pct"].mean()
    )

    median_return = (
        closed_trades["return_pct"].median()
    )

    average_holding_weeks = (
        closed_trades["holding_weeks"].mean()
    )

    best_trade = (
        closed_trades["return_pct"].max()
    )

    worst_trade = (
        closed_trades["return_pct"].min()
    )

    print(f"勝率：{win_rate:.2f}%")
    print(f"平均單筆報酬：{average_return:.2f}%")
    print(f"單筆報酬中位數：{median_return:.2f}%")
    print(f"平均持有週數：{average_holding_weeks:.1f}")
    print(f"最佳單筆交易：{best_trade:.2f}%")
    print(f"最差單筆交易：{worst_trade:.2f}%")

    print("\n最近 5 筆交易：")

    display_columns = [
        "trade_id",
        "entry_date",
        "entry_price",
        "exit_date",
        "exit_price",
        "return_pct",
        "holding_weeks",
        "mae_pct",
        "mfe_pct",
        "status",
    ]

    print(
        trades_df[display_columns]
        .tail(5)
        .to_string(index=False)
    )


# =========================================================
# 輸出檔案
# =========================================================

def save_signals(
    result_df: pd.DataFrame,
    output_file: Path,
) -> None:

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    export_df = (
        result_df.reset_index()
        .copy()
    )

    date_columns = [
        "week_end",
        "signal_date",
    ]

    for column in date_columns:
        export_df[column] = (
            pd.to_datetime(
                export_df[column]
            )
            .dt.strftime("%Y-%m-%d")
        )

    numeric_columns = [
        "Close",
        "ema_fast",
        "ema_slow",
        "macd",
        "signal",
        "histogram",
    ]

    export_df[numeric_columns] = (
        export_df[numeric_columns]
        .round(4)
    )

    export_df.to_csv(
        output_file,
        index=False,
        encoding="utf-8-sig",
    )


def save_trades(
    trades_df: pd.DataFrame,
    output_file: Path,
) -> None:

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    export_df = trades_df.copy()

    date_columns = [
        "entry_signal_date",
        "entry_date",
        "exit_signal_date",
        "exit_date",
    ]

    for column in date_columns:
        export_df[column] = (
            pd.to_datetime(
                export_df[column]
            )
            .dt.strftime("%Y-%m-%d")
        )

    numeric_columns = [
        "entry_price",
        "exit_price",
        "return_pct",
        "holding_weeks",
        "mae_pct",
        "mfe_pct",
    ]

    for column in numeric_columns:
        export_df[column] = (
            pd.to_numeric(
                export_df[column],
                errors="coerce",
            )
            .round(4)
        )

    export_df.to_csv(
        output_file,
        index=False,
        encoding="utf-8-sig",
    )


# =========================================================
# 主程序
# =========================================================

def main() -> None:

    daily_df = load_daily_data(
        INPUT_FILE
    )

    weekly_df = convert_to_weekly(
        daily_df
    )

    macd_df = calculate_macd(
        weekly_df
    )

    signal_df = detect_crossovers(
        macd_df
    )

    trades_df = build_trades(
        daily_df=daily_df,
        signal_df=signal_df,
    )

    save_signals(
        result_df=signal_df,
        output_file=SIGNALS_OUTPUT_FILE,
    )

    save_trades(
        trades_df=trades_df,
        output_file=TRADES_OUTPUT_FILE,
    )

    print_trade_summary(
        trades_df
    )

    print("\n輸出完成：")

    print(
        f"- {SIGNALS_OUTPUT_FILE}"
    )

    print(
        f"- {TRADES_OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
