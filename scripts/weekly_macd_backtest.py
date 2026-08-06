from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ============================================================
# 基本設定
# ============================================================

SYMBOL = "^TWII"
STRATEGY_NAME = "台灣加權指數週線 MACD 策略"

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

TRADING_DAYS_PER_YEAR = 252

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = PROJECT_ROOT / "data" / "^TWII.csv"
OUTPUT_DIR = PROJECT_ROOT / "output"

JSON_OUTPUT_FILE = OUTPUT_DIR / "twii_weekly_macd.json"
TRADES_CSV_FILE = OUTPUT_DIR / "twii_weekly_macd_trades.csv"
EQUITY_CSV_FILE = OUTPUT_DIR / "twii_weekly_macd_equity.csv"


# ============================================================
# 資料處理
# ============================================================

def load_daily_data(file_path: Path) -> pd.DataFrame:
    """讀取並清理台灣加權指數日線資料。"""

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
        raise ValueError("資料清理後沒有可用行情")

    if (df["Close"] <= 0).any():
        raise ValueError("Close 欄位包含零或負數")

    return df


def convert_to_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    將日線轉成週線。

    每週使用該週最後一個交易日的收盤價。
    若星期五休市，會使用星期四或該週最後交易日。
    """

    source = daily_df.reset_index().copy()
    source["week_period"] = source["Date"].dt.to_period("W-FRI")

    weekly = (
        source.groupby("week_period", observed=True)
        .agg(
            signal_date=("Date", "max"),
            Close=("Close", "last"),
        )
        .reset_index()
    )

    weekly["week_end"] = (
        weekly["week_period"]
        .dt.end_time
        .dt.normalize()
    )

    weekly = (
        weekly.drop(columns=["week_period"])
        .sort_values("signal_date")
        .set_index("week_end")
    )

    return weekly


# ============================================================
# MACD 計算
# ============================================================

def calculate_weekly_macd(
    weekly_df: pd.DataFrame,
) -> pd.DataFrame:
    """計算週線 MACD（12、26、9）。"""

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

    df["macd"] = df["ema_fast"] - df["ema_slow"]

    df["signal"] = (
        df["macd"]
        .ewm(
            span=MACD_SIGNAL,
            adjust=False,
            min_periods=MACD_SIGNAL,
        )
        .mean()
    )

    df["histogram"] = df["macd"] - df["signal"]

    previous_macd = df["macd"].shift(1)
    previous_signal = df["signal"].shift(1)

    valid = (
        df["macd"].notna()
        & df["signal"].notna()
        & previous_macd.notna()
        & previous_signal.notna()
    )

    df["golden_cross"] = (
        valid
        & (df["macd"] > df["signal"])
        & (previous_macd <= previous_signal)
    )

    df["death_cross"] = (
        valid
        & (df["macd"] < df["signal"])
        & (previous_macd >= previous_signal)
    )

    df["signal_type"] = "none"

    df.loc[df["golden_cross"], "signal_type"] = "golden_cross"
    df.loc[df["death_cross"], "signal_type"] = "death_cross"

    return df


# ============================================================
# 成交與交易配對
# ============================================================

def get_next_trading_day(
    daily_df: pd.DataFrame,
    signal_date: pd.Timestamp,
) -> tuple[pd.Timestamp, float] | None:
    """
    訊號在當週最後交易日收盤後確認。

    使用下一個交易日收盤價成交。
    """

    future_data = daily_df.loc[
        daily_df.index > signal_date,
        "Close",
    ]

    if future_data.empty:
        return None

    execution_date = future_data.index[0]
    execution_price = float(future_data.iloc[0])

    return execution_date, execution_price


def calculate_mae_mfe(
    daily_df: pd.DataFrame,
    entry_date: pd.Timestamp,
    end_date: pd.Timestamp,
    entry_price: float,
) -> tuple[float, float]:
    """計算持有期間 MAE 與 MFE。"""

    holding_prices = daily_df.loc[
        (daily_df.index >= entry_date)
        & (daily_df.index <= end_date),
        "Close",
    ]

    if holding_prices.empty:
        return 0.0, 0.0

    returns_from_entry = holding_prices / entry_price - 1.0

    mae = float(returns_from_entry.min())
    mfe = float(returns_from_entry.max())

    return mae, mfe


def build_trades(
    daily_df: pd.DataFrame,
    weekly_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    交易規則：

    1. 黃金交叉後下一交易日收盤買進。
    2. 死亡交叉後下一交易日收盤賣出。
    3. 不放空。
    4. 空手期間現金報酬為零。
    """

    trades: list[dict[str, Any]] = []

    position_open = False
    entry_signal_date: pd.Timestamp | None = None
    entry_date: pd.Timestamp | None = None
    entry_price: float | None = None

    signals = weekly_df.loc[
        weekly_df["signal_type"] != "none"
    ].copy()

    for _, row in signals.iterrows():
        signal_type = str(row["signal_type"])
        signal_date = pd.Timestamp(row["signal_date"])

        execution = get_next_trading_day(
            daily_df,
            signal_date,
        )

        if execution is None:
            continue

        execution_date, execution_price = execution

        if signal_type == "golden_cross" and not position_open:
            position_open = True
            entry_signal_date = signal_date
            entry_date = execution_date
            entry_price = execution_price

        elif signal_type == "death_cross" and position_open:
            if (
                entry_signal_date is None
                or entry_date is None
                or entry_price is None
            ):
                raise RuntimeError("交易狀態異常：缺少買進資料")

            exit_signal_date = signal_date
            exit_date = execution_date
            exit_price = execution_price

            return_rate = exit_price / entry_price - 1.0
            holding_days = int((exit_date - entry_date).days)

            mae, mfe = calculate_mae_mfe(
                daily_df=daily_df,
                entry_date=entry_date,
                end_date=exit_date,
                entry_price=entry_price,
            )

            trades.append(
                {
                    "trade_id": len(trades) + 1,
                    "entry_signal_date": entry_signal_date,
                    "entry_date": entry_date,
                    "entry_price": entry_price,
                    "exit_signal_date": exit_signal_date,
                    "exit_date": exit_date,
                    "exit_price": exit_price,
                    "return_pct": return_rate * 100,
                    "holding_days": holding_days,
                    "holding_weeks": holding_days / 7,
                    "mae_pct": mae * 100,
                    "mfe_pct": mfe * 100,
                    "profit_giveback_pct": (
                        mfe - return_rate
                    ) * 100,
                    "is_winner": return_rate > 0,
                    "status": "closed",
                }
            )

            position_open = False
            entry_signal_date = None
            entry_date = None
            entry_price = None

    # 最後一筆尚未出場，使用最新收盤價計算未實現報酬
    if (
        position_open
        and entry_signal_date is not None
        and entry_date is not None
        and entry_price is not None
    ):
        latest_date = daily_df.index[-1]
        latest_price = float(daily_df["Close"].iloc[-1])

        return_rate = latest_price / entry_price - 1.0
        holding_days = int((latest_date - entry_date).days)

        mae, mfe = calculate_mae_mfe(
            daily_df=daily_df,
            entry_date=entry_date,
            end_date=latest_date,
            entry_price=entry_price,
        )

        trades.append(
            {
                "trade_id": len(trades) + 1,
                "entry_signal_date": entry_signal_date,
                "entry_date": entry_date,
                "entry_price": entry_price,
                "exit_signal_date": pd.NaT,
                "exit_date": pd.NaT,
                "exit_price": np.nan,
                "return_pct": return_rate * 100,
                "holding_days": holding_days,
                "holding_weeks": holding_days / 7,
                "mae_pct": mae * 100,
                "mfe_pct": mfe * 100,
                "profit_giveback_pct": (
                    mfe - return_rate
                ) * 100,
                "is_winner": return_rate > 0,
                "status": "open",
            }
        )

    return pd.DataFrame(trades)


# ============================================================
# 資金曲線
# ============================================================

def build_equity_curve(
    daily_df: pd.DataFrame,
    weekly_df: pd.DataFrame,
    trades_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    建立：

    1. 台灣加權指數買進持有資金曲線。
    2. 週線 MACD 策略資金曲線。

    由於在收盤價成交：
    - 買進當天不取得當日報酬。
    - 賣出當天仍取得當日報酬。
    """

    valid_macd = weekly_df.loc[
        weekly_df["macd"].notna()
        & weekly_df["signal"].notna()
    ]

    if valid_macd.empty:
        raise ValueError("MACD 有效資料不足")

    comparison_start = pd.Timestamp(
        valid_macd.iloc[0]["signal_date"]
    )

    equity = daily_df.loc[
        daily_df.index >= comparison_start,
        ["Close"],
    ].copy()

    if equity.empty:
        raise ValueError("沒有可建立資金曲線的資料")

    equity["market_return"] = (
        equity["Close"]
        .pct_change()
        .fillna(0.0)
    )

    # position_after_close：
    # 當天收盤成交後，帳戶是否持有指數
    equity["position_after_close"] = np.nan

    if not trades_df.empty:
        for _, trade in trades_df.iterrows():
            entry_date = pd.to_datetime(
                trade.get("entry_date"),
                errors="coerce",
            )

            if pd.notna(entry_date) and entry_date in equity.index:
                equity.loc[
                    entry_date,
                    "position_after_close",
                ] = 1.0

            exit_date = pd.to_datetime(
                trade.get("exit_date"),
                errors="coerce",
            )

            if pd.notna(exit_date) and exit_date in equity.index:
                equity.loc[
                    exit_date,
                    "position_after_close",
                ] = 0.0

    equity["position_after_close"] = (
        equity["position_after_close"]
        .ffill()
        .fillna(0.0)
    )

    # 昨日收盤後持有，才承擔今日報酬
    equity["position_for_return"] = (
        equity["position_after_close"]
        .shift(1)
        .fillna(0.0)
    )

    equity["strategy_return"] = (
        equity["market_return"]
        * equity["position_for_return"]
    )

    equity["buy_hold_equity"] = (
        1.0 + equity["market_return"]
    ).cumprod()

    equity["macd_equity"] = (
        1.0 + equity["strategy_return"]
    ).cumprod()

    equity["buy_hold_drawdown"] = (
        equity["buy_hold_equity"]
        / equity["buy_hold_equity"].cummax()
        - 1.0
    )

    equity["macd_drawdown"] = (
        equity["macd_equity"]
        / equity["macd_equity"].cummax()
        - 1.0
    )

    return equity


# ============================================================
# 績效統計
# ============================================================

def calculate_performance(
    returns: pd.Series,
    equity_curve: pd.Series,
    exposure: pd.Series | None = None,
) -> dict[str, float | int | None]:
    """計算策略績效指標。"""

    clean_returns = returns.fillna(0.0).astype(float)
    clean_equity = equity_curve.dropna().astype(float)

    if clean_equity.empty:
        raise ValueError("資金曲線為空")

    total_return = float(clean_equity.iloc[-1] - 1.0)

    start_date = clean_equity.index[0]
    end_date = clean_equity.index[-1]

    elapsed_days = max((end_date - start_date).days, 1)
    elapsed_years = elapsed_days / 365.25

    if clean_equity.iloc[-1] > 0 and elapsed_years > 0:
        cagr = float(
            clean_equity.iloc[-1] ** (1.0 / elapsed_years)
            - 1.0
        )
    else:
        cagr = np.nan

    running_max = clean_equity.cummax()
    drawdown = clean_equity / running_max - 1.0
    max_drawdown = float(drawdown.min())

    annual_volatility = float(
        clean_returns.std(ddof=0)
        * math.sqrt(TRADING_DAYS_PER_YEAR)
    )

    annual_return_arithmetic = float(
        clean_returns.mean()
        * TRADING_DAYS_PER_YEAR
    )

    sharpe_ratio = (
        annual_return_arithmetic / annual_volatility
        if annual_volatility > 0
        else np.nan
    )

    downside_returns = clean_returns.clip(upper=0)
    downside_deviation = float(
        downside_returns.std(ddof=0)
        * math.sqrt(TRADING_DAYS_PER_YEAR)
    )

    sortino_ratio = (
        annual_return_arithmetic / downside_deviation
        if downside_deviation > 0
        else np.nan
    )

    calmar_ratio = (
        cagr / abs(max_drawdown)
        if max_drawdown < 0 and not pd.isna(cagr)
        else np.nan
    )

    exposure_pct = (
        float(exposure.mean() * 100)
        if exposure is not None
        else 100.0
    )

    positive_days = int((clean_returns > 0).sum())
    negative_days = int((clean_returns < 0).sum())

    return {
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "years": round(elapsed_years, 4),
        "total_return_pct": total_return * 100,
        "cagr_pct": cagr * 100,
        "max_drawdown_pct": max_drawdown * 100,
        "annual_volatility_pct": annual_volatility * 100,
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino_ratio,
        "calmar_ratio": calmar_ratio,
        "exposure_pct": exposure_pct,
        "positive_days": positive_days,
        "negative_days": negative_days,
    }


def calculate_max_consecutive_losses(
    closed_trades: pd.DataFrame,
) -> int:
    """計算最長連續虧損交易數。"""

    max_streak = 0
    current_streak = 0

    for return_pct in closed_trades["return_pct"]:
        if return_pct <= 0:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0

    return max_streak


def calculate_trade_statistics(
    trades_df: pd.DataFrame,
) -> dict[str, Any]:
    """計算已平倉交易統計。"""

    if trades_df.empty:
        return {
            "closed_trade_count": 0,
            "open_trade_count": 0,
        }

    closed = trades_df.loc[
        trades_df["status"] == "closed"
    ].copy()

    opened = trades_df.loc[
        trades_df["status"] == "open"
    ].copy()

    result: dict[str, Any] = {
        "closed_trade_count": int(len(closed)),
        "open_trade_count": int(len(opened)),
    }

    if closed.empty:
        return result

    winners = closed.loc[closed["return_pct"] > 0]
    losers = closed.loc[closed["return_pct"] <= 0]

    total_profit = float(
        winners["return_pct"].sum()
    )

    total_loss = abs(
        float(losers["return_pct"].sum())
    )

    profit_factor = (
        total_profit / total_loss
        if total_loss > 0
        else np.nan
    )

    average_win = (
        float(winners["return_pct"].mean())
        if not winners.empty
        else np.nan
    )

    average_loss = (
        float(losers["return_pct"].mean())
        if not losers.empty
        else np.nan
    )

    payoff_ratio = (
        average_win / abs(average_loss)
        if (
            not pd.isna(average_win)
            and not pd.isna(average_loss)
            and average_loss != 0
        )
        else np.nan
    )

    result.update(
        {
            "win_rate_pct": (
                len(winners) / len(closed) * 100
            ),
            "average_return_pct": float(
                closed["return_pct"].mean()
            ),
            "median_return_pct": float(
                closed["return_pct"].median()
            ),
            "average_win_pct": average_win,
            "average_loss_pct": average_loss,
            "payoff_ratio": payoff_ratio,
            "profit_factor": profit_factor,
            "best_trade_pct": float(
                closed["return_pct"].max()
            ),
            "worst_trade_pct": float(
                closed["return_pct"].min()
            ),
            "average_holding_days": float(
                closed["holding_days"].mean()
            ),
            "average_holding_weeks": float(
                closed["holding_weeks"].mean()
            ),
            "average_mae_pct": float(
                closed["mae_pct"].mean()
            ),
            "average_mfe_pct": float(
                closed["mfe_pct"].mean()
            ),
            "average_profit_giveback_pct": float(
                closed["profit_giveback_pct"].mean()
            ),
            "max_consecutive_losses": (
                calculate_max_consecutive_losses(closed)
            ),
        }
    )

    return result


def build_return_distribution(
    trades_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    """建立單筆交易報酬分布。"""

    bins = [
        -np.inf,
        -30,
        -20,
        -10,
        0,
        10,
        20,
        30,
        50,
        100,
        np.inf,
    ]

    labels = [
        "< -30%",
        "-30% ～ -20%",
        "-20% ～ -10%",
        "-10% ～ 0%",
        "0% ～ 10%",
        "10% ～ 20%",
        "20% ～ 30%",
        "30% ～ 50%",
        "50% ～ 100%",
        "> 100%",
    ]

    if trades_df.empty:
        return [
            {"range": label, "count": 0}
            for label in labels
        ]

    closed = trades_df.loc[
        trades_df["status"] == "closed"
    ]

    categories = pd.cut(
        closed["return_pct"],
        bins=bins,
        labels=labels,
        right=False,
    )

    counts = (
        categories.value_counts(sort=False)
        .reindex(labels, fill_value=0)
    )

    return [
        {
            "range": label,
            "count": int(counts.loc[label]),
        }
        for label in labels
    ]


# ============================================================
# 目前訊號
# ============================================================

def get_current_status(
    weekly_df: pd.DataFrame,
    trades_df: pd.DataFrame,
) -> dict[str, Any]:
    """取得最新 MACD 與持倉狀態。"""

    valid = weekly_df.loc[
        weekly_df["macd"].notna()
        & weekly_df["signal"].notna()
    ]

    if valid.empty:
        return {}

    latest = valid.iloc[-1]

    signals = valid.loc[
        valid["signal_type"] != "none"
    ]

    last_signal = signals.iloc[-1] if not signals.empty else None

    has_open_trade = (
        not trades_df.empty
        and (trades_df["status"] == "open").any()
    )

    status = "holding" if has_open_trade else "cash"

    result: dict[str, Any] = {
        "status": status,
        "status_zh": "持有台股" if status == "holding" else "持有現金",
        "latest_week_signal_date": pd.Timestamp(
            latest["signal_date"]
        ).strftime("%Y-%m-%d"),
        "latest_close": float(latest["Close"]),
        "macd": float(latest["macd"]),
        "signal_line": float(latest["signal"]),
        "histogram": float(latest["histogram"]),
        "current_week_signal": str(latest["signal_type"]),
    }

    if last_signal is not None:
        last_signal_date = pd.Timestamp(
            last_signal["signal_date"]
        )

        latest_signal_date = pd.Timestamp(
            latest["signal_date"]
        )

        result.update(
            {
                "last_cross_type": str(
                    last_signal["signal_type"]
                ),
                "last_cross_date": last_signal_date.strftime(
                    "%Y-%m-%d"
                ),
                "weeks_since_last_cross": int(
                    (latest_signal_date - last_signal_date).days
                    // 7
                ),
            }
        )

    return result


# ============================================================
# 輸出工具
# ============================================================

def clean_json_value(value: Any) -> Any:
    """將 NumPy、Pandas 與 NaN 轉成合法 JSON 格式。"""

    if value is None:
        return None

    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.strftime("%Y-%m-%d")

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, (np.integer,)):
        return int(value)

    if isinstance(value, (np.floating, float)):
        if pd.isna(value) or math.isinf(float(value)):
            return None
        return round(float(value), 6)

    if isinstance(value, (np.bool_, bool)):
        return bool(value)

    if pd.isna(value):
        return None

    return value


def dataframe_to_records(
    df: pd.DataFrame,
    date_columns: list[str] | None = None,
) -> list[dict[str, Any]]:
    """將 DataFrame 安全轉為 JSON records。"""

    export_df = df.copy()
    date_columns = date_columns or []

    for column in date_columns:
        if column in export_df.columns:
            export_df[column] = pd.to_datetime(
                export_df[column],
                errors="coerce",
            ).dt.strftime("%Y-%m-%d")

    records = export_df.to_dict(orient="records")

    return [
        {
            key: clean_json_value(value)
            for key, value in row.items()
        }
        for row in records
    ]


def save_csv_outputs(
    trades_df: pd.DataFrame,
    equity_df: pd.DataFrame,
) -> None:
    """輸出交易與資金曲線 CSV，方便人工檢查。"""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    trades_export = trades_df.copy()

    trade_date_columns = [
        "entry_signal_date",
        "entry_date",
        "exit_signal_date",
        "exit_date",
    ]

    for column in trade_date_columns:
        if column in trades_export.columns:
            trades_export[column] = pd.to_datetime(
                trades_export[column],
                errors="coerce",
            ).dt.strftime("%Y-%m-%d")

    numeric_trade_columns = [
        "entry_price",
        "exit_price",
        "return_pct",
        "holding_weeks",
        "mae_pct",
        "mfe_pct",
        "profit_giveback_pct",
    ]

    for column in numeric_trade_columns:
        if column in trades_export.columns:
            trades_export[column] = pd.to_numeric(
                trades_export[column],
                errors="coerce",
            ).round(4)

    trades_export.to_csv(
        TRADES_CSV_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    equity_export = equity_df.reset_index().rename(
        columns={"Date": "date"}
    )

    if "date" not in equity_export.columns:
        equity_export = equity_export.rename(
            columns={equity_export.columns[0]: "date"}
        )

    equity_export["date"] = pd.to_datetime(
        equity_export["date"]
    ).dt.strftime("%Y-%m-%d")

    equity_export.to_csv(
        EQUITY_CSV_FILE,
        index=False,
        encoding="utf-8-sig",
        float_format="%.8f",
    )


def save_json_output(
    daily_df: pd.DataFrame,
    weekly_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    equity_df: pd.DataFrame,
    buy_hold_performance: dict[str, Any],
    macd_performance: dict[str, Any],
    trade_statistics: dict[str, Any],
) -> None:
    """輸出 WordPress 可直接讀取的 JSON。"""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    weekly_export = (
        weekly_df.reset_index()
        .rename(columns={"week_end": "week_end"})
    )

    weekly_columns = [
        "week_end",
        "signal_date",
        "Close",
        "macd",
        "signal",
        "histogram",
        "golden_cross",
        "death_cross",
        "signal_type",
    ]

    weekly_export = weekly_export[
        [
            column
            for column in weekly_columns
            if column in weekly_export.columns
        ]
    ]

    equity_export = equity_df.reset_index()

    first_column = equity_export.columns[0]
    equity_export = equity_export.rename(
        columns={first_column: "date"}
    )

    equity_columns = [
        "date",
        "Close",
        "position_for_return",
        "buy_hold_equity",
        "macd_equity",
        "buy_hold_drawdown",
        "macd_drawdown",
    ]

    equity_export = equity_export[equity_columns]

    json_data = {
        "metadata": {
            "symbol": SYMBOL,
            "strategy_name": STRATEGY_NAME,
            "source_file": "data/^TWII.csv",
            "price_type": "price_index",
            "includes_dividends": False,
            "generated_at": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "data_start_date": daily_df.index[0].strftime(
                "%Y-%m-%d"
            ),
            "data_end_date": daily_df.index[-1].strftime(
                "%Y-%m-%d"
            ),
            "daily_row_count": int(len(daily_df)),
            "weekly_row_count": int(len(weekly_df)),
            "macd_parameters": {
                "fast": MACD_FAST,
                "slow": MACD_SLOW,
                "signal": MACD_SIGNAL,
            },
            "rules": {
                "entry": (
                    "週線 MACD 黃金交叉後，"
                    "下一個交易日收盤買進"
                ),
                "exit": (
                    "週線 MACD 死亡交叉後，"
                    "下一個交易日收盤賣出"
                ),
                "cash_return": 0,
                "short_selling": False,
                "transaction_cost_included": False,
            },
        },
        "current_status": get_current_status(
            weekly_df,
            trades_df,
        ),
        "performance": {
            "buy_and_hold": buy_hold_performance,
            "weekly_macd": macd_performance,
        },
        "trade_statistics": trade_statistics,
        "return_distribution": build_return_distribution(
            trades_df
        ),
        "trades": dataframe_to_records(
            trades_df,
            date_columns=[
                "entry_signal_date",
                "entry_date",
                "exit_signal_date",
                "exit_date",
            ],
        ),
        "weekly_signals": dataframe_to_records(
            weekly_export,
            date_columns=[
                "week_end",
                "signal_date",
            ],
        ),
        "equity_curve": dataframe_to_records(
            equity_export,
            date_columns=["date"],
        ),
    }

    cleaned_json = clean_nested_json(json_data)

    with JSON_OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            cleaned_json,
            file,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )


def clean_nested_json(value: Any) -> Any:
    """遞迴清理 JSON 中的特殊型別與 NaN。"""

    if isinstance(value, dict):
        return {
            key: clean_nested_json(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            clean_nested_json(item)
            for item in value
        ]

    return clean_json_value(value)


# ============================================================
# 終端機摘要
# ============================================================

def print_summary(
    weekly_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    buy_hold: dict[str, Any],
    macd_strategy: dict[str, Any],
    trade_stats: dict[str, Any],
) -> None:
    """顯示回測摘要。"""

    print("\n" + "=" * 68)
    print(STRATEGY_NAME)
    print("=" * 68)

    print(
        f"MACD 參數："
        f"{MACD_FAST}, {MACD_SLOW}, {MACD_SIGNAL}"
    )

    print(
        f"週線期間："
        f"{weekly_df['signal_date'].min().date()} "
        f"至 {weekly_df['signal_date'].max().date()}"
    )

    print("\n【買進持有】")
    print(
        f"累積報酬："
        f"{buy_hold['total_return_pct']:.2f}%"
    )
    print(
        f"年化報酬："
        f"{buy_hold['cagr_pct']:.2f}%"
    )
    print(
        f"最大回撤："
        f"{buy_hold['max_drawdown_pct']:.2f}%"
    )
    print(
        f"Sharpe Ratio："
        f"{buy_hold['sharpe_ratio']:.3f}"
    )

    print("\n【週線 MACD】")
    print(
        f"累積報酬："
        f"{macd_strategy['total_return_pct']:.2f}%"
    )
    print(
        f"年化報酬："
        f"{macd_strategy['cagr_pct']:.2f}%"
    )
    print(
        f"最大回撤："
        f"{macd_strategy['max_drawdown_pct']:.2f}%"
    )
    print(
        f"Sharpe Ratio："
        f"{macd_strategy['sharpe_ratio']:.3f}"
    )
    print(
        f"市場曝險比例："
        f"{macd_strategy['exposure_pct']:.2f}%"
    )

    print("\n【交易統計】")
    print(
        f"已完成交易："
        f"{trade_stats.get('closed_trade_count', 0)} 筆"
    )
    print(
        f"目前未平倉："
        f"{trade_stats.get('open_trade_count', 0)} 筆"
    )

    if trade_stats.get("closed_trade_count", 0) > 0:
        print(
            f"勝率："
            f"{trade_stats['win_rate_pct']:.2f}%"
        )
        print(
            f"平均單筆報酬："
            f"{trade_stats['average_return_pct']:.2f}%"
        )
        print(
            f"最佳單筆："
            f"{trade_stats['best_trade_pct']:.2f}%"
        )
        print(
            f"最差單筆："
            f"{trade_stats['worst_trade_pct']:.2f}%"
        )
        print(
            f"平均持有週數："
            f"{trade_stats['average_holding_weeks']:.1f}"
        )
        print(
            f"最長連續虧損："
            f"{trade_stats['max_consecutive_losses']} 筆"
        )

    print("\n輸出完成：")
    print(f"- {JSON_OUTPUT_FILE}")
    print(f"- {TRADES_CSV_FILE}")
    print(f"- {EQUITY_CSV_FILE}")


# ============================================================
# 主程序
# ============================================================

def main() -> None:
    daily_df = load_daily_data(INPUT_FILE)

    weekly_df = convert_to_weekly(daily_df)
    weekly_df = calculate_weekly_macd(weekly_df)

    trades_df = build_trades(
        daily_df=daily_df,
        weekly_df=weekly_df,
    )

    equity_df = build_equity_curve(
        daily_df=daily_df,
        weekly_df=weekly_df,
        trades_df=trades_df,
    )

    buy_hold_performance = calculate_performance(
        returns=equity_df["market_return"],
        equity_curve=equity_df["buy_hold_equity"],
    )

    macd_performance = calculate_performance(
        returns=equity_df["strategy_return"],
        equity_curve=equity_df["macd_equity"],
        exposure=equity_df["position_for_return"],
    )

    trade_statistics = calculate_trade_statistics(
        trades_df
    )

    save_csv_outputs(
        trades_df=trades_df,
        equity_df=equity_df,
    )

    save_json_output(
        daily_df=daily_df,
        weekly_df=weekly_df,
        trades_df=trades_df,
        equity_df=equity_df,
        buy_hold_performance=buy_hold_performance,
        macd_performance=macd_performance,
        trade_statistics=trade_statistics,
    )

    print_summary(
        weekly_df=weekly_df,
        trades_df=trades_df,
        buy_hold=buy_hold_performance,
        macd_strategy=macd_performance,
        trade_stats=trade_statistics,
    )


if __name__ == "__main__":
    main()
