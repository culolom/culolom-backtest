from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT_DIR / "data" / "^TWII.csv"
OUTPUT_DIR = ROOT_DIR / "output"
JSON_PATH = OUTPUT_DIR / "twii_sma_drawdown.json"
EVENTS_CSV_PATH = OUTPUT_DIR / "twii_sma_events.csv"
FUND_CSV_PATH = OUTPUT_DIR / "national_stabilization_fund_analysis.csv"

SMA_DAYS = 200
PEAK_LOOKBACK_DAYS = 252
THRESHOLDS = [10, 20, 30, 40, 50]

NATIONAL_STABILIZATION_FUND = [
    {"id": "NSF01", "execution_start": "2000-03-16", "event": "首次政黨輪替"},
    {"id": "NSF02", "execution_start": "2000-10-03", "event": "網路泡沫"},
    {"id": "NSF03", "execution_start": "2004-05-20", "event": "三一九事件與兩岸緊張"},
    {"id": "NSF04", "execution_start": "2008-09-18", "event": "金融海嘯"},
    {"id": "NSF05", "execution_start": "2011-12-21", "event": "歐債危機"},
    {"id": "NSF06", "execution_start": "2015-08-25", "event": "中國股災與人民幣貶值"},
    {"id": "NSF07", "execution_start": "2020-03-20", "event": "COVID-19疫情"},
    {"id": "NSF08", "execution_start": "2022-07-13", "event": "升息與俄烏戰爭"},
    {"id": "NSF09", "execution_start": "2025-04-09", "event": "對等關稅衝擊"},
]

STRATEGIES = [
    {
        "id": "conservative",
        "name": "保守版",
        "description": "五等份平均投入",
        "initial_total": 1_000_000,
        "initial_leveraged_etf": 500_000,
        "initial_cash": 500_000,
        "rules": [
            {"drawdown_from_peak_pct": -10, "cash_amount": 100_000},
            {"drawdown_from_peak_pct": -20, "cash_amount": 100_000},
            {"drawdown_from_peak_pct": -30, "cash_amount": 100_000},
            {"drawdown_from_peak_pct": -40, "cash_amount": 100_000},
            {"drawdown_from_peak_pct": -50, "cash_amount": 100_000},
        ],
    },
    {
        "id": "cumulative",
        "name": "累積版",
        "description": "跌得越深，投入金額線性增加",
        "initial_total": 1_000_000,
        "initial_leveraged_etf": 500_000,
        "initial_cash": 500_000,
        "rules": [
            {"drawdown_from_peak_pct": -10, "cash_amount": 50_000},
            {"drawdown_from_peak_pct": -20, "cash_amount": 100_000},
            {"drawdown_from_peak_pct": -30, "cash_amount": 150_000},
            {"drawdown_from_peak_pct": -40, "cash_amount": 200_000},
        ],
    },
    {
        "id": "martingale",
        "name": "馬丁版",
        "description": "前段試單，後段集中投入",
        "initial_total": 1_000_000,
        "initial_leveraged_etf": 500_000,
        "initial_cash": 500_000,
        "rules": [
            {"drawdown_from_peak_pct": -10, "cash_amount": 50_000},
            {"drawdown_from_peak_pct": -20, "cash_amount": 100_000},
            {"drawdown_from_peak_pct": -30, "cash_amount": 200_000},
            {"drawdown_from_peak_pct": -40, "cash_amount": 150_000},
        ],
    },
]


def load_data(path: Path = DATA_PATH) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"找不到資料：{path}")

    df = pd.read_csv(path)
    required = {"Date", "Close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"缺少必要欄位：{sorted(missing)}")

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = (
        df.dropna(subset=["Date", "Close"])
        .sort_values("Date")
        .drop_duplicates("Date", keep="last")
        .reset_index(drop=True)
    )
    df["SMA200"] = df["Close"].rolling(SMA_DAYS, min_periods=SMA_DAYS).mean()
    df["BelowSMA200"] = df["Close"] < df["SMA200"]
    return df.dropna(subset=["SMA200"]).reset_index(drop=True)


def find_events(df: pd.DataFrame) -> pd.DataFrame:
    events: list[dict[str, Any]] = []
    i = 1
    event_id = 1

    while i < len(df):
        crossed_below = bool(df.loc[i, "BelowSMA200"]) and not bool(df.loc[i - 1, "BelowSMA200"])
        if not crossed_below:
            i += 1
            continue

        start = i
        end = start
        while end + 1 < len(df) and bool(df.loc[end + 1, "BelowSMA200"]):
            end += 1

        segment = df.loc[start:end]
        low_idx = int(segment["Close"].idxmin())

        peak_start = max(0, start - PEAK_LOOKBACK_DAYS)
        peak_window = df.loc[peak_start:start]
        peak_idx = int(peak_window["Close"].idxmax())

        recovery_idx = end + 1 if end + 1 < len(df) else None

        cross_close = float(df.loc[start, "Close"])
        low_close = float(df.loc[low_idx, "Close"])
        peak_close = float(df.loc[peak_idx, "Close"])

        events.append(
            {
                "event_id": event_id,
                "cross_below_date": df.loc[start, "Date"],
                "cross_below_close": cross_close,
                "cross_below_sma200": float(df.loc[start, "SMA200"]),
                "distance_from_sma_at_cross": cross_close / float(df.loc[start, "SMA200"]) - 1,
                "peak_date": df.loc[peak_idx, "Date"],
                "peak_close": peak_close,
                "lowest_date": df.loc[low_idx, "Date"],
                "lowest_close": low_close,
                "drawdown_from_cross": low_close / cross_close - 1,
                "drawdown_from_peak": low_close / peak_close - 1,
                "days_below_sma": int(end - start + 1),
                "recovery_date": df.loc[recovery_idx, "Date"] if recovery_idx is not None else pd.NaT,
                "recovered": recovery_idx is not None,
            }
        )

        event_id += 1
        i = end + 1

    return pd.DataFrame(events)


def threshold_stats(events: pd.DataFrame, column: str) -> list[dict[str, Any]]:
    total = len(events)
    output = []
    for threshold in THRESHOLDS:
        count = int((events[column] <= -threshold / 100).sum())
        output.append(
            {
                "threshold_pct": -threshold,
                "count": count,
                "probability_pct": round(count / total * 100, 2) if total else 0.0,
            }
        )
    return output


def analyze_fund_entries(df: pd.DataFrame) -> pd.DataFrame:
    """分析國安基金進場後，首次站回200SMA所需時間與報酬。"""
    rows: list[dict[str, Any]] = []

    for item in NATIONAL_STABILIZATION_FUND:
        requested_date = pd.Timestamp(item["execution_start"])
        candidates = df.index[df["Date"] >= requested_date]
        if len(candidates) == 0:
            continue

        idx = int(candidates[0])
        entry_row = df.loc[idx]
        history = df.loc[:idx]

        peak_252_window = history.tail(PEAK_LOOKBACK_DAYS)
        peak_252_idx = int(peak_252_window["Close"].idxmax())

        entry_close = float(entry_row["Close"])
        entry_sma200 = float(entry_row["SMA200"])

        future = df.loc[idx:]
        recovery_candidates = future.index[
            future["Close"] >= future["SMA200"]
        ]

        recovered = len(recovery_candidates) > 0
        recovery_idx = int(recovery_candidates[0]) if recovered else None

        if recovered and recovery_idx is not None:
            recovery_row = df.loc[recovery_idx]
            tracking_window = df.loc[idx:recovery_idx]
            recovery_date = recovery_row["Date"]
            recovery_close = float(recovery_row["Close"])
            recovery_sma200 = float(recovery_row["SMA200"])
            trading_days_to_recovery = int(recovery_idx - idx)
            calendar_days_to_recovery = int((recovery_date - entry_row["Date"]).days)
            return_to_recovery = recovery_close / entry_close - 1
        else:
            tracking_window = df.loc[idx:]
            recovery_date = pd.NaT
            recovery_close = None
            recovery_sma200 = None
            trading_days_to_recovery = None
            calendar_days_to_recovery = None
            return_to_recovery = None

        lowest_idx = int(tracking_window["Close"].idxmin())
        lowest_close_after_entry = float(df.loc[lowest_idx, "Close"])
        lowest_date_after_entry = df.loc[lowest_idx, "Date"]
        max_drawdown_after_entry = lowest_close_after_entry / entry_close - 1

        rows.append(
            {
                "id": item["id"],
                "event": item["event"],
                "execution_start": requested_date,
                "matched_trade_date": entry_row["Date"],
                "close": entry_close,
                "sma200": entry_sma200,
                "distance_from_sma200": float(entry_close / entry_sma200 - 1),
                "peak_252_date": df.loc[peak_252_idx, "Date"],
                "peak_252_close": float(df.loc[peak_252_idx, "Close"]),
                "drawdown_from_252d_peak": float(entry_close / float(df.loc[peak_252_idx, "Close"]) - 1),
                "recovered_to_sma200": bool(recovered),
                "recovery_date": recovery_date,
                "recovery_close": recovery_close,
                "recovery_sma200": recovery_sma200,
                "trading_days_to_recovery": trading_days_to_recovery,
                "calendar_days_to_recovery": calendar_days_to_recovery,
                "return_to_recovery": return_to_recovery,
                "lowest_date_after_entry": lowest_date_after_entry,
                "lowest_close_after_entry": lowest_close_after_entry,
                "max_drawdown_after_entry": max_drawdown_after_entry,
            }
        )

    return pd.DataFrame(rows)


def strategy_trigger_summary(events: pd.DataFrame) -> list[dict[str, Any]]:
    results = []

    for strategy in STRATEGIES:
        rows = []
        cash_used_values = []

        for _, event in events.iterrows():
            drawdown_pct = float(event["drawdown_from_peak"] * 100)
            used = sum(
                rule["cash_amount"]
                for rule in strategy["rules"]
                if drawdown_pct <= rule["drawdown_from_peak_pct"]
            )
            used = min(used, strategy["initial_cash"])
            cash_used_values.append(used)
            rows.append(
                {
                    "event_id": int(event["event_id"]),
                    "drawdown_from_peak_pct": round(drawdown_pct, 2),
                    "cash_used": used,
                    "cash_remaining": strategy["initial_cash"] - used,
                }
            )

        results.append(
            {
                "strategy_id": strategy["id"],
                "name": strategy["name"],
                "average_cash_used": round(sum(cash_used_values) / len(cash_used_values), 2)
                if cash_used_values
                else 0,
                "average_cash_used_pct": round(
                    sum(cash_used_values) / len(cash_used_values) / strategy["initial_cash"] * 100, 2
                )
                if cash_used_values
                else 0,
                "events_using_all_cash": int(sum(v >= strategy["initial_cash"] for v in cash_used_values)),
                "event_results": rows,
            }
        )

    return results


def serialize_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    clean = df.copy()
    for col in clean.columns:
        if pd.api.types.is_datetime64_any_dtype(clean[col]):
            clean[col] = clean[col].dt.strftime("%Y-%m-%d")
    clean = clean.where(pd.notna(clean), None)
    return clean.to_dict(orient="records")



def build_current_market(df: pd.DataFrame) -> dict[str, Any]:
    latest = df.iloc[-1]
    recent = df.tail(PEAK_LOOKBACK_DAYS)
    peak_idx = int(recent["Close"].idxmax())
    peak_row = df.loc[peak_idx]

    close = float(latest["Close"])
    sma200 = float(latest["SMA200"])
    peak_close = float(peak_row["Close"])
    distance_from_sma_pct = (close / sma200 - 1) * 100
    drawdown_from_peak_pct = (close / peak_close - 1) * 100
    below_sma = close < sma200

    triggered_levels = [
        threshold
        for threshold in THRESHOLDS
        if drawdown_from_peak_pct <= -threshold
    ]

    return {
        "date": latest["Date"].strftime("%Y-%m-%d"),
        "close": round(close, 2),
        "sma200": round(sma200, 2),
        "distance_from_sma200_pct": round(distance_from_sma_pct, 2),
        "peak_252_date": peak_row["Date"].strftime("%Y-%m-%d"),
        "peak_252_close": round(peak_close, 2),
        "drawdown_from_252d_peak_pct": round(drawdown_from_peak_pct, 2),
        "below_sma200": bool(below_sma),
        "eligible_for_bear_market_plan": bool(below_sma),
        "triggered_drawdown_levels": triggered_levels,
        "current_trigger_level_pct": max(triggered_levels) if triggered_levels else 0,
    }


def build_output(df: pd.DataFrame, events: pd.DataFrame, fund: pd.DataFrame) -> dict[str, Any]:
    drawdown_cross = events["drawdown_from_cross"] * 100
    drawdown_peak = events["drawdown_from_peak"] * 100

    fund_distance = fund["distance_from_sma200"] * 100
    fund_drawdown = fund["drawdown_from_252d_peak"] * 100

    current_market = build_current_market(df)

    return {
        "meta": {
            "title": "台股跌破200SMA後跌幅與國安基金進場位置統計",
            "market": "TAIEX",
            "symbol": "^TWII",
            "data_start": df["Date"].min().strftime("%Y-%m-%d"),
            "data_end": df["Date"].max().strftime("%Y-%m-%d"),
            "sma_days": SMA_DAYS,
            "peak_lookback_days": PEAK_LOOKBACK_DAYS,
            "event_definition": "收盤價由200SMA上方跌到下方，直到首次收盤站回200SMA為一個事件",
            "drawdown_primary_basis": "跌破日前252個交易日最高收盤價",
            "version": "1.1.0",
        },
        "current_market": current_market,
        "summary": {
            "total_events": int(len(events)),
            "average_drawdown_from_cross_pct": round(float(drawdown_cross.mean()), 2),
            "median_drawdown_from_cross_pct": round(float(drawdown_cross.median()), 2),
            "deepest_drawdown_from_cross_pct": round(float(drawdown_cross.min()), 2),
            "average_drawdown_from_peak_pct": round(float(drawdown_peak.mean()), 2),
            "median_drawdown_from_peak_pct": round(float(drawdown_peak.median()), 2),
            "deepest_drawdown_from_peak_pct": round(float(drawdown_peak.min()), 2),
            "average_days_below_sma": round(float(events["days_below_sma"].mean()), 2),
            "median_days_below_sma": round(float(events["days_below_sma"].median()), 2),
        },
        "threshold_probability": {
            "from_cross_date": threshold_stats(events, "drawdown_from_cross"),
            "from_252d_peak": threshold_stats(events, "drawdown_from_peak"),
        },
        "national_stabilization_fund_summary": {
            "event_count": int(len(fund)),
            "recovered_event_count": int(fund["recovered_to_sma200"].sum()),
            "unrecovered_event_count": int((~fund["recovered_to_sma200"]).sum()),
            "average_distance_from_sma200_pct": round(float(fund_distance.mean()), 2),
            "median_distance_from_sma200_pct": round(float(fund_distance.median()), 2),
            "shallowest_distance_from_sma200_pct": round(float(fund_distance.max()), 2),
            "deepest_distance_from_sma200_pct": round(float(fund_distance.min()), 2),
            "average_drawdown_from_252d_peak_pct": round(float(fund_drawdown.mean()), 2),
            "median_drawdown_from_252d_peak_pct": round(float(fund_drawdown.median()), 2),
            "average_trading_days_to_recovery": round(float(fund.loc[fund["recovered_to_sma200"], "trading_days_to_recovery"].mean()), 2),
            "median_trading_days_to_recovery": round(float(fund.loc[fund["recovered_to_sma200"], "trading_days_to_recovery"].median()), 2),
            "average_calendar_days_to_recovery": round(float(fund.loc[fund["recovered_to_sma200"], "calendar_days_to_recovery"].mean()), 2),
            "median_calendar_days_to_recovery": round(float(fund.loc[fund["recovered_to_sma200"], "calendar_days_to_recovery"].median()), 2),
            "average_return_to_recovery_pct": round(float(fund.loc[fund["recovered_to_sma200"], "return_to_recovery"].mean() * 100), 2),
            "median_return_to_recovery_pct": round(float(fund.loc[fund["recovered_to_sma200"], "return_to_recovery"].median() * 100), 2),
            "average_max_drawdown_after_entry_pct": round(float(fund["max_drawdown_after_entry"].mean() * 100), 2),
            "deepest_max_drawdown_after_entry_pct": round(float(fund["max_drawdown_after_entry"].min() * 100), 2),
        },
        "strategies": STRATEGIES,
        "strategy_trigger_summary": strategy_trigger_summary(events),
        "events": serialize_records(events),
        "national_stabilization_fund": serialize_records(fund),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = load_data()
    events = find_events(df)
    fund = analyze_fund_entries(df)
    output = build_output(df, events, fund)

    JSON_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    events.to_csv(EVENTS_CSV_PATH, index=False, encoding="utf-8-sig")
    fund.to_csv(FUND_CSV_PATH, index=False, encoding="utf-8-sig")

    print(f"完成：{JSON_PATH}")
    print(f"完成：{EVENTS_CSV_PATH}")
    print(f"完成：{FUND_CSV_PATH}")
    print(f"跌破200SMA事件：{len(events)} 次")
    print(f"國安基金事件：{len(fund)} 次")


if __name__ == "__main__":
    main()
