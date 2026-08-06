from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ============================================================
# 基本設定
# ============================================================

STRATEGY_NAME = "週線 MACD 固定比例正2再平衡策略"

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
TRADING_DAYS_PER_YEAR = 252

# 固定配置測試：
# 0.50 = 正2 50%、現金 50%
# 0.60 = 正2 60%、現金 40%
# 0.70 = 正2 70%、現金 30%
TARGET_LEVERAGED_WEIGHTS = [0.50, 0.60, 0.70]

# 初始資金
INITIAL_CAPITAL = 1_000_000.0

# 券商牌告手續費率 0.1425%
BROKER_COMMISSION_RATE = 0.001425

# 手續費折扣，0.28 = 2.8 折
BROKER_COMMISSION_DISCOUNT = 0.28

# ETF 賣出證交稅 0.1%
ETF_TRANSACTION_TAX_RATE = 0.001

# 第一版不計最低手續費；需要時可改成 20
MINIMUM_COMMISSION = 0.0

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TWII_INPUT_FILE = PROJECT_ROOT / "data" / "^TWII.csv"
LEVERAGED_ETF_INPUT_FILE = PROJECT_ROOT / "data" / "00631L.TW.csv"
OUTPUT_DIR = PROJECT_ROOT / "output"

JSON_OUTPUT_FILE = OUTPUT_DIR / "weekly_macd_fixed_rebalance.json"
EQUITY_CSV_FILE = OUTPUT_DIR / "weekly_macd_fixed_rebalance_equity.csv"
REBALANCE_CSV_FILE = OUTPUT_DIR / "weekly_macd_fixed_rebalance_trades.csv"


# ============================================================
# 通用工具
# ============================================================

def load_price_data(file_path: Path, symbol_name: str) -> pd.DataFrame:
    """讀取並清理價格資料，只保留 Date 與 Close。"""
    if not file_path.exists():
        raise FileNotFoundError(f"找不到 {symbol_name} 資料：{file_path}")

    df = pd.read_csv(file_path)

    required_columns = {"Date", "Close"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(
            f"{symbol_name} CSV 缺少必要欄位：{sorted(missing_columns)}"
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
        raise ValueError(f"{symbol_name} 清理後沒有可用資料")

    if (df["Close"] <= 0).any():
        raise ValueError(f"{symbol_name} Close 包含零或負數")

    return df[["Close"]].copy()


def clean_json_value(value: Any) -> Any:
    """把 pandas、numpy 型別轉成 JSON 可序列化型別。"""
    if value is None:
        return None

    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.strftime("%Y-%m-%d")

    if isinstance(value, np.datetime64):
        return None if pd.isna(value) else pd.Timestamp(value).strftime("%Y-%m-%d")

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None

    if isinstance(value, (np.bool_, bool)):
        return bool(value)

    if isinstance(value, dict):
        return {str(key): clean_json_value(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [clean_json_value(item) for item in value]

    return value


def dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """把 DataFrame 轉成 JSON records。"""
    output = df.reset_index().copy()

    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column]):
            output[column] = output[column].dt.strftime("%Y-%m-%d")

    return clean_json_value(output.to_dict(orient="records"))


# ============================================================
# 週線 MACD
# ============================================================

def convert_to_completed_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    將台灣加權指數日線轉成 W-FRI 週線。

    只有週五已經到來的週資料才算完整週。
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

    weekly["week_end"] = weekly["week_period"].dt.end_time.dt.normalize()

    weekly = (
        weekly.drop(columns=["week_period"])
        .sort_values("signal_date")
        .set_index("week_end")
    )

    latest_daily_date = daily_df.index.max().normalize()
    weekly = weekly.loc[weekly.index <= latest_daily_date].copy()

    return weekly


def calculate_weekly_macd(weekly_df: pd.DataFrame) -> pd.DataFrame:
    """計算週線 MACD 與黃金／死亡交叉。"""
    df = weekly_df.copy()

    df["ema_fast"] = (
        df["Close"]
        .ewm(span=MACD_FAST, adjust=False, min_periods=MACD_FAST)
        .mean()
    )
    df["ema_slow"] = (
        df["Close"]
        .ewm(span=MACD_SLOW, adjust=False, min_periods=MACD_SLOW)
        .mean()
    )
    df["macd"] = df["ema_fast"] - df["ema_slow"]
    df["signal"] = (
        df["macd"]
        .ewm(span=MACD_SIGNAL, adjust=False, min_periods=MACD_SIGNAL)
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


def build_execution_signals(
    weekly_df: pd.DataFrame,
    etf_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    週線訊號確認後，在 00631L 下一個交易日收盤執行再平衡。
    """
    records: list[dict[str, Any]] = []

    signals = weekly_df.loc[weekly_df["signal_type"] != "none"].copy()

    for _, row in signals.iterrows():
        signal_date = pd.Timestamp(row["signal_date"])
        future_dates = etf_df.index[etf_df.index > signal_date]

        if len(future_dates) == 0:
            continue

        execution_date = pd.Timestamp(future_dates[0])

        records.append(
            {
                "signal_date": signal_date,
                "execution_date": execution_date,
                "signal_type": str(row["signal_type"]),
                "twii_close": float(row["Close"]),
                "macd": float(row["macd"]),
                "signal_line": float(row["signal"]),
                "histogram": float(row["histogram"]),
            }
        )

    columns = [
        "signal_date",
        "execution_date",
        "signal_type",
        "twii_close",
        "macd",
        "signal_line",
        "histogram",
    ]

    if not records:
        return pd.DataFrame(columns=columns)

    return (
        pd.DataFrame(records)
        .sort_values("execution_date")
        .drop_duplicates(subset=["execution_date"], keep="last")
        .reset_index(drop=True)
    )


# ============================================================
# 交易成本
# ============================================================

def effective_commission_rate() -> float:
    return BROKER_COMMISSION_RATE * BROKER_COMMISSION_DISCOUNT


def calculate_commission(trade_amount: float) -> float:
    if trade_amount <= 0:
        return 0.0

    proportional_fee = trade_amount * effective_commission_rate()
    return max(proportional_fee, MINIMUM_COMMISSION)


def calculate_sell_tax(sell_amount: float) -> float:
    if sell_amount <= 0:
        return 0.0

    return sell_amount * ETF_TRANSACTION_TAX_RATE


# ============================================================
# 再平衡計算
# ============================================================

def execute_rebalance(
    etf_value_before: float,
    cash_before: float,
    target_weight: float,
) -> dict[str, float | str]:
    """
    只買賣必要差額，並在扣除成本後盡量貼近目標比例。

    假設：
    - 可交易小數股
    - 不考慮滑價
    - 不借款
    """
    if not 0 <= target_weight <= 1:
        raise ValueError("target_weight 必須介於 0 與 1")

    total_before = etf_value_before + cash_before
    if total_before <= 0:
        raise ValueError("帳戶總資產不可小於或等於零")

    commission_rate = effective_commission_rate()
    current_weight = etf_value_before / total_before

    if math.isclose(current_weight, target_weight, rel_tol=0, abs_tol=1e-12):
        return {
            "action": "none",
            "buy_amount": 0.0,
            "sell_amount": 0.0,
            "commission": 0.0,
            "transaction_tax": 0.0,
            "total_cost": 0.0,
            "etf_value_after": etf_value_before,
            "cash_after": cash_before,
            "total_after": total_before,
            "weight_before": current_weight,
            "weight_after": current_weight,
        }

    target_value_before_cost = total_before * target_weight

    if etf_value_before < target_value_before_cost:
        # ETF_after = ETF_before + X
        # Total_after = Total_before - X * fee_rate
        # ETF_after = target_weight * Total_after
        buy_amount = (
            target_weight * total_before - etf_value_before
        ) / (1 + target_weight * commission_rate)

        buy_amount = max(min(buy_amount, cash_before), 0.0)
        commission = calculate_commission(buy_amount)

        if buy_amount + commission > cash_before:
            if commission_rate > 0:
                buy_amount = cash_before / (1 + commission_rate)
            else:
                buy_amount = cash_before
            commission = calculate_commission(buy_amount)

        etf_value_after = etf_value_before + buy_amount
        cash_after = cash_before - buy_amount - commission
        sell_amount = 0.0
        transaction_tax = 0.0
        total_cost = commission
        action = "buy"

    else:
        # ETF_after = ETF_before - X
        # Total_after = Total_before - X * sell_cost_rate
        # ETF_after = target_weight * Total_after
        total_sell_cost_rate = (
            commission_rate + ETF_TRANSACTION_TAX_RATE
        )
        denominator = 1 - target_weight * total_sell_cost_rate

        if denominator <= 0:
            raise ValueError("交易成本參數造成無效分母")

        sell_amount = (
            etf_value_before - target_weight * total_before
        ) / denominator

        sell_amount = max(min(sell_amount, etf_value_before), 0.0)
        commission = calculate_commission(sell_amount)
        transaction_tax = calculate_sell_tax(sell_amount)
        total_cost = commission + transaction_tax

        etf_value_after = etf_value_before - sell_amount
        cash_after = cash_before + sell_amount - total_cost
        buy_amount = 0.0
        action = "sell"

    total_after = etf_value_after + cash_after
    weight_after = etf_value_after / total_after if total_after > 0 else 0.0

    return {
        "action": action,
        "buy_amount": buy_amount,
        "sell_amount": sell_amount,
        "commission": commission,
        "transaction_tax": transaction_tax,
        "total_cost": total_cost,
        "etf_value_after": etf_value_after,
        "cash_after": cash_after,
        "total_after": total_after,
        "weight_before": current_weight,
        "weight_after": weight_after,
    }


# ============================================================
# 策略回測
# ============================================================

def run_fixed_weight_strategy(
    etf_df: pd.DataFrame,
    execution_signals: pd.DataFrame,
    target_weight: float,
    start_date: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    起始日先建立固定配置，之後只在任一 MACD 交叉後再平衡。
    黃金交叉與死亡交叉使用相同配置。
    """
    prices = etf_df.loc[etf_df.index >= start_date].copy()
    if prices.empty:
        raise ValueError("00631L 在回測起始日後沒有資料")

    signal_lookup: dict[pd.Timestamp, list[dict[str, Any]]] = {}

    for _, signal in execution_signals.iterrows():
        execution_date = pd.Timestamp(signal["execution_date"])
        if execution_date < prices.index[0]:
            continue
        signal_lookup.setdefault(execution_date, []).append(signal.to_dict())

    cash = INITIAL_CAPITAL
    shares = 0.0

    equity_records: list[dict[str, Any]] = []
    rebalance_records: list[dict[str, Any]] = []

    previous_close: float | None = None
    cumulative_cost = 0.0
    cumulative_commission = 0.0
    cumulative_tax = 0.0
    rebalance_id = 0

    for current_date, price_row in prices.iterrows():
        close_price = float(price_row["Close"])
        etf_value_before = shares * close_price
        cash_before = cash

        is_initial_date = current_date == prices.index[0]
        signals_today = signal_lookup.get(pd.Timestamp(current_date), [])
        should_rebalance = is_initial_date or bool(signals_today)

        daily_signal_type = "initial" if is_initial_date else "none"
        daily_signal_date = pd.NaT

        if signals_today:
            latest_signal = signals_today[-1]
            daily_signal_type = str(latest_signal["signal_type"])
            daily_signal_date = pd.Timestamp(latest_signal["signal_date"])

        action = "none"
        trade_amount = 0.0
        commission = 0.0
        transaction_tax = 0.0
        total_cost = 0.0

        total_before = etf_value_before + cash_before
        weight_before = (
            etf_value_before / total_before if total_before > 0 else 0.0
        )

        if should_rebalance:
            result = execute_rebalance(
                etf_value_before=etf_value_before,
                cash_before=cash_before,
                target_weight=target_weight,
            )

            action = str(result["action"])
            buy_amount = float(result["buy_amount"])
            sell_amount = float(result["sell_amount"])
            trade_amount = max(buy_amount, sell_amount)
            commission = float(result["commission"])
            transaction_tax = float(result["transaction_tax"])
            total_cost = float(result["total_cost"])

            etf_value_after = float(result["etf_value_after"])
            cash = float(result["cash_after"])
            shares = etf_value_after / close_price

            cumulative_cost += total_cost
            cumulative_commission += commission
            cumulative_tax += transaction_tax

            if action != "none":
                rebalance_id += 1

                rebalance_records.append(
                    {
                        "rebalance_id": rebalance_id,
                        "execution_date": current_date,
                        "signal_date": daily_signal_date,
                        "signal_type": daily_signal_type,
                        "target_etf_weight_pct": target_weight * 100,
                        "target_cash_weight_pct": (1 - target_weight) * 100,
                        "approx_target_exposure_pct": target_weight * 200,
                        "action": action,
                        "etf_close": close_price,
                        "account_value_before": total_before,
                        "etf_value_before": etf_value_before,
                        "cash_before": cash_before,
                        "etf_weight_before_pct": weight_before * 100,
                        "trade_amount": trade_amount,
                        "buy_amount": buy_amount,
                        "sell_amount": sell_amount,
                        "commission": commission,
                        "transaction_tax": transaction_tax,
                        "total_cost": total_cost,
                        "etf_value_after": etf_value_after,
                        "cash_after": cash,
                        "account_value_after": etf_value_after + cash,
                        "etf_weight_after_pct": float(result["weight_after"]) * 100,
                    }
                )

        etf_value_after_close = shares * close_price
        total_equity = etf_value_after_close + cash
        etf_weight = (
            etf_value_after_close / total_equity if total_equity > 0 else 0.0
        )

        daily_return = 0.0
        if equity_records:
            previous_equity = float(equity_records[-1]["equity"])
            if previous_equity > 0:
                daily_return = total_equity / previous_equity - 1.0

        market_return = (
            close_price / previous_close - 1.0
            if previous_close is not None
            else 0.0
        )

        equity_records.append(
            {
                "Date": current_date,
                "Close": close_price,
                "market_return": market_return,
                "signal_type": daily_signal_type,
                "signal_date": daily_signal_date,
                "rebalance": should_rebalance,
                "action": action,
                "trade_amount": trade_amount,
                "commission": commission,
                "transaction_tax": transaction_tax,
                "transaction_cost": total_cost,
                "cumulative_cost": cumulative_cost,
                "cumulative_commission": cumulative_commission,
                "cumulative_tax": cumulative_tax,
                "shares": shares,
                "etf_value": etf_value_after_close,
                "cash": cash,
                "etf_weight": etf_weight,
                "cash_weight": 1.0 - etf_weight,
                "approx_exposure": etf_weight * 2.0,
                "equity": total_equity,
                "daily_return": daily_return,
            }
        )

        previous_close = close_price

    equity_df = pd.DataFrame(equity_records).set_index("Date")
    equity_df["equity_multiple"] = equity_df["equity"] / INITIAL_CAPITAL
    equity_df["drawdown"] = (
        equity_df["equity"] / equity_df["equity"].cummax() - 1.0
    )

    rebalances_df = pd.DataFrame(rebalance_records)
    return equity_df, rebalances_df


def run_buy_and_hold(
    etf_df: pd.DataFrame,
    start_date: pd.Timestamp,
) -> pd.DataFrame:
    """00631L 全程持有，起始買進計入手續費，期末不強制賣出。"""
    prices = etf_df.loc[etf_df.index >= start_date].copy()
    first_price = float(prices["Close"].iloc[0])

    commission_rate = effective_commission_rate()
    buy_amount = INITIAL_CAPITAL / (1 + commission_rate)
    commission = calculate_commission(buy_amount)

    if buy_amount + commission > INITIAL_CAPITAL:
        buy_amount = INITIAL_CAPITAL - commission

    shares = buy_amount / first_price
    cash = INITIAL_CAPITAL - buy_amount - commission

    equity = prices.copy()
    equity["etf_value"] = shares * equity["Close"]
    equity["cash"] = cash
    equity["equity"] = equity["etf_value"] + equity["cash"]
    equity["daily_return"] = equity["equity"].pct_change().fillna(0.0)
    equity["equity_multiple"] = equity["equity"] / INITIAL_CAPITAL
    equity["drawdown"] = equity["equity"] / equity["equity"].cummax() - 1.0
    equity["etf_weight"] = equity["etf_value"] / equity["equity"]
    equity["cash_weight"] = 1.0 - equity["etf_weight"]
    equity["approx_exposure"] = equity["etf_weight"] * 2.0
    equity["transaction_cost"] = 0.0
    equity.iloc[0, equity.columns.get_loc("transaction_cost")] = commission
    equity["cumulative_cost"] = commission
    equity["cumulative_commission"] = commission
    equity["cumulative_tax"] = 0.0

    return equity


def run_static_allocation(
    etf_df: pd.DataFrame,
    start_date: pd.Timestamp,
    target_weight: float,
) -> pd.DataFrame:
    """起始日建立正2／現金配置，之後永不再平衡。"""
    prices = etf_df.loc[etf_df.index >= start_date].copy()
    first_price = float(prices["Close"].iloc[0])

    result = execute_rebalance(
        etf_value_before=0.0,
        cash_before=INITIAL_CAPITAL,
        target_weight=target_weight,
    )

    etf_value = float(result["etf_value_after"])
    cash = float(result["cash_after"])
    commission = float(result["commission"])
    shares = etf_value / first_price

    equity = prices.copy()
    equity["etf_value"] = shares * equity["Close"]
    equity["cash"] = cash
    equity["equity"] = equity["etf_value"] + equity["cash"]
    equity["daily_return"] = equity["equity"].pct_change().fillna(0.0)
    equity["equity_multiple"] = equity["equity"] / INITIAL_CAPITAL
    equity["drawdown"] = equity["equity"] / equity["equity"].cummax() - 1.0
    equity["etf_weight"] = equity["etf_value"] / equity["equity"]
    equity["cash_weight"] = 1.0 - equity["etf_weight"]
    equity["approx_exposure"] = equity["etf_weight"] * 2.0
    equity["transaction_cost"] = 0.0
    equity.iloc[0, equity.columns.get_loc("transaction_cost")] = commission
    equity["cumulative_cost"] = commission
    equity["cumulative_commission"] = commission
    equity["cumulative_tax"] = 0.0

    return equity


# ============================================================
# 績效統計
# ============================================================

def calculate_performance(equity_df: pd.DataFrame) -> dict[str, Any]:
    returns = equity_df["daily_return"].fillna(0.0).astype(float)
    equity = equity_df["equity"].dropna().astype(float)

    if equity.empty:
        raise ValueError("資產曲線為空")

    start_date = equity.index[0]
    end_date = equity.index[-1]
    elapsed_days = max(int((end_date - start_date).days), 1)
    elapsed_years = elapsed_days / 365.25

    final_equity = float(equity.iloc[-1])
    total_return = final_equity / INITIAL_CAPITAL - 1.0

    cagr = (
        (final_equity / INITIAL_CAPITAL) ** (1.0 / elapsed_years) - 1.0
        if final_equity > 0
        else np.nan
    )

    drawdown = equity / equity.cummax() - 1.0
    max_drawdown = float(drawdown.min())

    annual_volatility = float(
        returns.std(ddof=0) * math.sqrt(TRADING_DAYS_PER_YEAR)
    )
    annual_return_arithmetic = float(
        returns.mean() * TRADING_DAYS_PER_YEAR
    )

    sharpe_ratio = (
        annual_return_arithmetic / annual_volatility
        if annual_volatility > 0
        else np.nan
    )

    downside_returns = returns.clip(upper=0.0)
    downside_deviation = float(
        downside_returns.std(ddof=0) * math.sqrt(TRADING_DAYS_PER_YEAR)
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

    cumulative_cost = float(equity_df["cumulative_cost"].iloc[-1])

    return {
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "years": elapsed_years,
        "initial_capital": INITIAL_CAPITAL,
        "final_equity": final_equity,
        "total_return_pct": total_return * 100,
        "cagr_pct": cagr * 100,
        "max_drawdown_pct": max_drawdown * 100,
        "annual_volatility_pct": annual_volatility * 100,
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino_ratio,
        "calmar_ratio": calmar_ratio,
        "average_etf_weight_pct": float(equity_df["etf_weight"].mean()) * 100,
        "average_approx_exposure_pct": (
            float(equity_df["approx_exposure"].mean()) * 100
        ),
        "cumulative_transaction_cost": cumulative_cost,
        "transaction_cost_pct_of_initial": (
            cumulative_cost / INITIAL_CAPITAL * 100
        ),
    }


def calculate_rebalance_statistics(rebalances_df: pd.DataFrame) -> dict[str, Any]:
    if rebalances_df.empty:
        return {
            "rebalance_count": 0,
            "buy_count": 0,
            "sell_count": 0,
            "total_buy_amount": 0.0,
            "total_sell_amount": 0.0,
            "total_turnover": 0.0,
            "total_commission": 0.0,
            "total_transaction_tax": 0.0,
            "total_transaction_cost": 0.0,
        }

    return {
        "rebalance_count": int(len(rebalances_df)),
        "buy_count": int((rebalances_df["action"] == "buy").sum()),
        "sell_count": int((rebalances_df["action"] == "sell").sum()),
        "total_buy_amount": float(rebalances_df["buy_amount"].sum()),
        "total_sell_amount": float(rebalances_df["sell_amount"].sum()),
        "total_turnover": float(rebalances_df["trade_amount"].sum()),
        "total_commission": float(rebalances_df["commission"].sum()),
        "total_transaction_tax": float(
            rebalances_df["transaction_tax"].sum()
        ),
        "total_transaction_cost": float(rebalances_df["total_cost"].sum()),
    }


def get_current_signal(weekly_df: pd.DataFrame) -> dict[str, Any]:
    valid = weekly_df.loc[
        weekly_df["macd"].notna() & weekly_df["signal"].notna()
    ]

    if valid.empty:
        return {}

    latest = valid.iloc[-1]
    crosses = valid.loc[valid["signal_type"] != "none"]

    result: dict[str, Any] = {
        "latest_week_signal_date": pd.Timestamp(
            latest["signal_date"]
        ).strftime("%Y-%m-%d"),
        "latest_twii_close": float(latest["Close"]),
        "macd": float(latest["macd"]),
        "signal_line": float(latest["signal"]),
        "histogram": float(latest["histogram"]),
        "current_week_signal": str(latest["signal_type"]),
    }

    if not crosses.empty:
        last_cross = crosses.iloc[-1]
        last_cross_date = pd.Timestamp(last_cross["signal_date"])
        latest_date = pd.Timestamp(latest["signal_date"])

        result.update(
            {
                "last_cross_type": str(last_cross["signal_type"]),
                "last_cross_date": last_cross_date.strftime("%Y-%m-%d"),
                "weeks_since_last_cross": int(
                    (latest_date - last_cross_date).days // 7
                ),
            }
        )

    return result


# ============================================================
# 主程式
# ============================================================

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    twii = load_price_data(TWII_INPUT_FILE, "^TWII")
    leveraged_etf = load_price_data(LEVERAGED_ETF_INPUT_FILE, "00631L")

    weekly = calculate_weekly_macd(convert_to_completed_weekly(twii))

    valid_macd = weekly.loc[
        weekly["macd"].notna() & weekly["signal"].notna()
    ]
    if valid_macd.empty:
        raise ValueError("週線 MACD 有效資料不足")

    macd_available_date = pd.Timestamp(valid_macd.iloc[0]["signal_date"])
    etf_first_date = pd.Timestamp(leveraged_etf.index[0])

    comparison_start_date = max(macd_available_date, etf_first_date)
    available_dates = leveraged_etf.index[
        leveraged_etf.index >= comparison_start_date
    ]

    if len(available_dates) == 0:
        raise ValueError("沒有共同可回測期間")

    comparison_start_date = pd.Timestamp(available_dates[0])

    execution_signals = build_execution_signals(
        weekly_df=weekly,
        etf_df=leveraged_etf,
    )

    buy_hold_equity = run_buy_and_hold(
        etf_df=leveraged_etf,
        start_date=comparison_start_date,
    )

    combined_equity = pd.DataFrame(index=buy_hold_equity.index)
    combined_equity["00631L_close"] = buy_hold_equity["Close"]
    combined_equity["00631L_buy_hold"] = buy_hold_equity["equity_multiple"]
    combined_equity["00631L_buy_hold_drawdown"] = buy_hold_equity["drawdown"]

    performance: dict[str, Any] = {
        "00631L_buy_and_hold": calculate_performance(buy_hold_equity)
    }
    strategies: dict[str, Any] = {}
    all_rebalances: list[pd.DataFrame] = []

    for target_weight in TARGET_LEVERAGED_WEIGHTS:
        weight_pct = int(round(target_weight * 100))
        cash_pct = 100 - weight_pct

        strategy_key = f"macd_rebalance_{weight_pct}_{cash_pct}"
        static_key = f"static_{weight_pct}_{cash_pct}"

        strategy_equity, rebalances = run_fixed_weight_strategy(
            etf_df=leveraged_etf,
            execution_signals=execution_signals,
            target_weight=target_weight,
            start_date=comparison_start_date,
        )
        static_equity = run_static_allocation(
            etf_df=leveraged_etf,
            start_date=comparison_start_date,
            target_weight=target_weight,
        )

        strategy_performance = calculate_performance(strategy_equity)
        static_performance = calculate_performance(static_equity)
        rebalance_statistics = calculate_rebalance_statistics(rebalances)

        performance[strategy_key] = strategy_performance
        performance[static_key] = static_performance

        combined_equity[strategy_key] = strategy_equity["equity_multiple"]
        combined_equity[f"{strategy_key}_drawdown"] = strategy_equity["drawdown"]
        combined_equity[f"{strategy_key}_etf_weight"] = strategy_equity["etf_weight"]
        combined_equity[f"{strategy_key}_exposure"] = (
            strategy_equity["approx_exposure"]
        )
        combined_equity[static_key] = static_equity["equity_multiple"]
        combined_equity[f"{static_key}_drawdown"] = static_equity["drawdown"]

        if not rebalances.empty:
            rebalances = rebalances.copy()
            rebalances.insert(0, "strategy", strategy_key)
            all_rebalances.append(rebalances)

        strategies[strategy_key] = {
            "strategy_name": (
                f"MACD交叉再平衡：正2 {weight_pct}%／現金 {cash_pct}%"
            ),
            "target_etf_weight_pct": target_weight * 100,
            "target_cash_weight_pct": (1 - target_weight) * 100,
            "approx_target_exposure_pct": target_weight * 200,
            "performance": strategy_performance,
            "rebalance_statistics": rebalance_statistics,
            "static_comparison": {
                "strategy_name": (
                    f"初始正2 {weight_pct}%／現金 {cash_pct}%，之後不再平衡"
                ),
                "performance": static_performance,
            },
            "rebalances": (
                dataframe_to_records(rebalances.set_index("execution_date"))
                if not rebalances.empty
                else []
            ),
        }

    if all_rebalances:
        all_rebalances_df = pd.concat(all_rebalances, ignore_index=True)
    else:
        all_rebalances_df = pd.DataFrame(
            columns=[
                "strategy",
                "rebalance_id",
                "execution_date",
                "signal_date",
                "signal_type",
                "target_etf_weight_pct",
                "target_cash_weight_pct",
                "approx_target_exposure_pct",
                "action",
                "etf_close",
                "account_value_before",
                "etf_value_before",
                "cash_before",
                "etf_weight_before_pct",
                "trade_amount",
                "buy_amount",
                "sell_amount",
                "commission",
                "transaction_tax",
                "total_cost",
                "etf_value_after",
                "cash_after",
                "account_value_after",
                "etf_weight_after_pct",
            ]
        )

    all_rebalances_df.to_csv(
        REBALANCE_CSV_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    combined_equity.index.name = "Date"
    combined_equity.to_csv(EQUITY_CSV_FILE, encoding="utf-8-sig")

    output = {
        "metadata": {
            "strategy_name": STRATEGY_NAME,
            "signal_symbol": "^TWII",
            "trading_symbol": "00631L.TW",
            "signal_rule": (
                "台灣加權指數週線MACD黃金交叉或死亡交叉，"
                "下一個00631L交易日收盤重新平衡"
            ),
            "rebalance_rule": "黃金交叉與死亡交叉使用相同固定配置",
            "comparison_start_date": comparison_start_date.strftime("%Y-%m-%d"),
            "data_end_date": leveraged_etf.index[-1].strftime("%Y-%m-%d"),
            "initial_capital": INITIAL_CAPITAL,
            "macd_parameters": {
                "fast": MACD_FAST,
                "slow": MACD_SLOW,
                "signal": MACD_SIGNAL,
            },
            "target_etf_weights": TARGET_LEVERAGED_WEIGHTS,
            "cost_assumptions": {
                "broker_commission_rate": BROKER_COMMISSION_RATE,
                "broker_commission_discount": BROKER_COMMISSION_DISCOUNT,
                "effective_commission_rate": effective_commission_rate(),
                "etf_transaction_tax_rate": ETF_TRANSACTION_TAX_RATE,
                "minimum_commission": MINIMUM_COMMISSION,
                "fractional_shares_assumed": True,
                "ending_position_liquidated": False,
            },
        },
        "current_signal": get_current_signal(weekly),
        "performance": performance,
        "strategies": strategies,
        "equity_curve": dataframe_to_records(combined_equity),
    }

    with JSON_OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            clean_json_value(output),
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("=" * 72)
    print(STRATEGY_NAME)
    print("=" * 72)
    print(
        f"共同回測期間：{comparison_start_date:%Y-%m-%d} ～ "
        f"{leveraged_etf.index[-1]:%Y-%m-%d}"
    )
    print(
        f"實際手續費率：{effective_commission_rate() * 100:.5f}%"
    )
    print(
        f"ETF 賣出證交稅：{ETF_TRANSACTION_TAX_RATE * 100:.3f}%"
    )
    print()

    benchmark = performance["00631L_buy_and_hold"]
    print(
        "00631L Buy & Hold："
        f"CAGR {benchmark['cagr_pct']:.2f}%｜"
        f"MDD {benchmark['max_drawdown_pct']:.2f}%"
    )

    for target_weight in TARGET_LEVERAGED_WEIGHTS:
        weight_pct = int(round(target_weight * 100))
        cash_pct = 100 - weight_pct
        strategy_key = f"macd_rebalance_{weight_pct}_{cash_pct}"
        static_key = f"static_{weight_pct}_{cash_pct}"

        strategy_result = performance[strategy_key]
        static_result = performance[static_key]
        stats = strategies[strategy_key]["rebalance_statistics"]

        print(
            f"MACD再平衡 {weight_pct}/{cash_pct}："
            f"CAGR {strategy_result['cagr_pct']:.2f}%｜"
            f"MDD {strategy_result['max_drawdown_pct']:.2f}%｜"
            f"成本 {stats['total_transaction_cost']:,.0f} 元"
        )
        print(
            f"靜態配置 {weight_pct}/{cash_pct}："
            f"CAGR {static_result['cagr_pct']:.2f}%｜"
            f"MDD {static_result['max_drawdown_pct']:.2f}%"
        )

    print()
    print(f"JSON：{JSON_OUTPUT_FILE}")
    print(f"資產曲線：{EQUITY_CSV_FILE}")
    print(f"再平衡明細：{REBALANCE_CSV_FILE}")


if __name__ == "__main__":
    main()
