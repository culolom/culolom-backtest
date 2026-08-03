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


# =========================================================
# 國安基金歷次進場與退場資料
# =========================================================
#
# execution_start / execution_end：
# 使用國安基金宣布進場與退場的日曆日期。
#
# 若日期不是台股交易日，程式會自動匹配：
# 「該日期當天或之後的第一個交易日」。
#
# support_calendar_days：
# 採含首尾的日曆天數。
#
NATIONAL_STABILIZATION_FUND = [
    {
        "id": "NSF01",
        "execution_start": "2000-03-15",
        "execution_end": "2000-03-19",
        "support_calendar_days": 5,
        "event": "政黨輪替與台海局勢",
    },
    {
        "id": "NSF02",
        "execution_start": "2000-10-02",
        "execution_end": "2000-11-13",
        "support_calendar_days": 43,
        "event": "網路泡沫、以巴衝突",
    },
    {
        "id": "NSF03",
        "execution_start": "2004-05-19",
        "execution_end": "2004-05-30",
        "support_calendar_days": 12,
        "event": "319槍擊案",
    },
    {
        "id": "NSF04",
        "execution_start": "2008-09-19",
        "execution_end": "2008-12-17",
        "support_calendar_days": 90,
        "event": "金融海嘯",
    },
    {
        "id": "NSF05",
        "execution_start": "2011-12-20",
        "execution_end": "2012-04-17",
        "support_calendar_days": 120,
        "event": "歐債危機",
    },
    {
        "id": "NSF06",
        "execution_start": "2015-08-25",
        "execution_end": "2016-04-12",
        "support_calendar_days": 232,
        "event": "中國股災、人民幣貶值",
    },
    {
        "id": "NSF07",
        "execution_start": "2020-03-19",
        "execution_end": "2020-10-11",
        "support_calendar_days": 207,
        "event": "新冠肺炎疫情",
    },
    {
        "id": "NSF08",
        "execution_start": "2022-07-13",
        "execution_end": "2023-04-13",
        "support_calendar_days": 275,
        "event": "美國聯準會激進升息",
    },
    {
        "id": "NSF09",
        "execution_start": "2025-04-09",
        "execution_end": "2026-01-12",
        "support_calendar_days": 279,
        "event": "關稅衝擊",
    },
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
    """讀取台股指數日資料，建立200SMA。"""
    if not path.exists():
        raise FileNotFoundError(f"找不到資料：{path}")

    df = pd.read_csv(path)

    required = {"Date", "Close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"缺少必要欄位：{sorted(missing)}")

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
        .drop_duplicates("Date", keep="last")
        .reset_index(drop=True)
    )

    df["SMA200"] = (
        df["Close"]
        .rolling(
            SMA_DAYS,
            min_periods=SMA_DAYS,
        )
        .mean()
    )

    df["BelowSMA200"] = (
        df["Close"] < df["SMA200"]
    )

    return (
        df.dropna(subset=["SMA200"])
        .reset_index(drop=True)
    )


def find_first_index_on_or_after(
    df: pd.DataFrame,
    requested_date: pd.Timestamp,
) -> int | None:
    """
    找出指定日期當天或之後的第一個交易日索引。

    例如退場公告日碰到週末，
    就會自動抓下一個有交易資料的日期。
    """
    candidates = df.index[
        df["Date"] >= requested_date
    ]

    if len(candidates) == 0:
        return None

    return int(candidates[0])


def find_events(df: pd.DataFrame) -> pd.DataFrame:
    """找出台股跌破200SMA的歷史事件。"""
    events: list[dict[str, Any]] = []
    i = 1
    event_id = 1

    while i < len(df):
        crossed_below = (
            bool(df.loc[i, "BelowSMA200"])
            and not bool(
                df.loc[i - 1, "BelowSMA200"]
            )
        )

        if not crossed_below:
            i += 1
            continue

        start = i
        end = start

        while (
            end + 1 < len(df)
            and bool(
                df.loc[end + 1, "BelowSMA200"]
            )
        ):
            end += 1

        segment = df.loc[start:end]
        low_idx = int(
            segment["Close"].idxmin()
        )

        peak_start = max(
            0,
            start - PEAK_LOOKBACK_DAYS,
        )
        peak_window = df.loc[
            peak_start:start
        ]
        peak_idx = int(
            peak_window["Close"].idxmax()
        )

        recovery_idx = (
            end + 1
            if end + 1 < len(df)
            else None
        )

        cross_close = float(
            df.loc[start, "Close"]
        )
        low_close = float(
            df.loc[low_idx, "Close"]
        )
        peak_close = float(
            df.loc[peak_idx, "Close"]
        )

        events.append(
            {
                "event_id": event_id,
                "cross_below_date":
                    df.loc[start, "Date"],
                "cross_below_close":
                    cross_close,
                "cross_below_sma200":
                    float(
                        df.loc[start, "SMA200"]
                    ),
                "distance_from_sma_at_cross":
                    cross_close
                    / float(
                        df.loc[start, "SMA200"]
                    )
                    - 1,
                "peak_date":
                    df.loc[peak_idx, "Date"],
                "peak_close":
                    peak_close,
                "lowest_date":
                    df.loc[low_idx, "Date"],
                "lowest_close":
                    low_close,
                "drawdown_from_cross":
                    low_close / cross_close - 1,
                "drawdown_from_peak":
                    low_close / peak_close - 1,
                "days_below_sma":
                    int(end - start + 1),
                "recovery_date":
                    (
                        df.loc[
                            recovery_idx,
                            "Date",
                        ]
                        if recovery_idx
                        is not None
                        else pd.NaT
                    ),
                "recovered":
                    recovery_idx is not None,
            }
        )

        event_id += 1
        i = end + 1

    return pd.DataFrame(events)


def threshold_stats(
    events: pd.DataFrame,
    column: str,
) -> list[dict[str, Any]]:
    total = len(events)
    output = []

    for threshold in THRESHOLDS:
        count = int(
            (
                events[column]
                <= -threshold / 100
            ).sum()
        )

        output.append(
            {
                "threshold_pct": -threshold,
                "count": count,
                "probability_pct": (
                    round(
                        count / total * 100,
                        2,
                    )
                    if total
                    else 0.0
                ),
            }
        )

    return output


def analyze_fund_entries(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    分析每次國安基金從進場到退場的完整護盤期間。

    主要輸出：
    1. 進場日期與收盤價
    2. 退場日期與收盤價
    3. 進場時距離200SMA
    4. 進場時距離前252個交易日高點
    5. 護盤期間最低點與最大回撤
    6. 進場到最低點的交易日與日曆天
    7. 進場後首次打平的交易日與日曆天
    8. 進場到退場的報酬與持有天數

    「打平」定義：
    進場日之後，收盤價首次大於或等於進場收盤價。

    「最低點」統計區間：
    實際進場交易日至實際退場交易日。
    """
    rows: list[dict[str, Any]] = []

    for item in NATIONAL_STABILIZATION_FUND:
        requested_entry_date = pd.Timestamp(
            item["execution_start"]
        )
        requested_exit_date = pd.Timestamp(
            item["execution_end"]
        )

        entry_idx = find_first_index_on_or_after(
            df,
            requested_entry_date,
        )
        exit_idx = find_first_index_on_or_after(
            df,
            requested_exit_date,
        )

        if entry_idx is None:
            print(
                "略過，找不到進場日期之後的資料："
                f"{item['id']} "
                f"{item['execution_start']}"
            )
            continue

        if exit_idx is None:
            print(
                "略過，找不到退場日期之後的資料："
                f"{item['id']} "
                f"{item['execution_end']}"
            )
            continue

        if exit_idx < entry_idx:
            raise ValueError(
                f"{item['id']} 的退場日期早於進場日期"
            )

        entry_row = df.loc[entry_idx]
        exit_row = df.loc[exit_idx]

        entry_date = entry_row["Date"]
        exit_date = exit_row["Date"]

        entry_close = float(
            entry_row["Close"]
        )
        exit_close = float(
            exit_row["Close"]
        )
        entry_sma200 = float(
            entry_row["SMA200"]
        )

        # 進場前最多252個交易日的最高收盤價。
        peak_start_idx = max(
            0,
            entry_idx
            - PEAK_LOOKBACK_DAYS
            + 1,
        )
        peak_window = df.loc[
            peak_start_idx:entry_idx
        ]
        peak_252_idx = int(
            peak_window["Close"].idxmax()
        )
        peak_252_close = float(
            df.loc[peak_252_idx, "Close"]
        )

        # 國安基金實際護盤區間。
        support_window = df.loc[
            entry_idx:exit_idx
        ]

        # 護盤期間最低收盤價。
        lowest_idx = int(
            support_window["Close"].idxmin()
        )
        lowest_row = df.loc[lowest_idx]
        lowest_date = lowest_row["Date"]
        lowest_close = float(
            lowest_row["Close"]
        )

        max_drawdown = (
            lowest_close / entry_close - 1
        )

        trading_days_to_lowest = int(
            lowest_idx - entry_idx
        )
        calendar_days_to_lowest = int(
            (lowest_date - entry_date).days
        )

        # 進場後首次回到進場收盤價。
        # 排除進場當天，避免所有事件都顯示0天。
        after_entry_window = df.loc[
            entry_idx + 1:exit_idx
        ]

        breakeven_candidates = (
            after_entry_window.index[
                after_entry_window["Close"]
                >= entry_close
            ]
        )

        breakeven_before_exit = (
            len(breakeven_candidates) > 0
        )

        if breakeven_before_exit:
            breakeven_idx = int(
                breakeven_candidates[0]
            )
            breakeven_row = df.loc[
                breakeven_idx
            ]
            breakeven_date = (
                breakeven_row["Date"]
            )
            breakeven_close = float(
                breakeven_row["Close"]
            )
            trading_days_to_breakeven = int(
                breakeven_idx - entry_idx
            )
            calendar_days_to_breakeven = int(
                (
                    breakeven_date
                    - entry_date
                ).days
            )
        else:
            breakeven_date = pd.NaT
            breakeven_close = None
            trading_days_to_breakeven = None
            calendar_days_to_breakeven = None

        trading_days_to_exit = int(
            exit_idx - entry_idx
        )
        calendar_days_to_exit = int(
            (exit_date - entry_date).days
        )
        holding_calendar_days_inclusive = (
            calendar_days_to_exit + 1
        )

        return_to_exit = (
            exit_close / entry_close - 1
        )

        # 保留原本「首次站回200SMA」欄位，
        # 避免舊版前端立刻失效。
        recovery_candidates = (
            support_window.index[
                support_window["Close"]
                >= support_window["SMA200"]
            ]
        )
        recovered_to_sma200 = (
            len(recovery_candidates) > 0
        )

        if recovered_to_sma200:
            recovery_idx = int(
                recovery_candidates[0]
            )
            recovery_row = df.loc[
                recovery_idx
            ]
            recovery_date = (
                recovery_row["Date"]
            )
            recovery_close = float(
                recovery_row["Close"]
            )
            recovery_sma200 = float(
                recovery_row["SMA200"]
            )
            trading_days_to_recovery = int(
                recovery_idx - entry_idx
            )
            calendar_days_to_recovery = int(
                (
                    recovery_date
                    - entry_date
                ).days
            )
            return_to_recovery = (
                recovery_close
                / entry_close
                - 1
            )
        else:
            recovery_date = pd.NaT
            recovery_close = None
            recovery_sma200 = None
            trading_days_to_recovery = None
            calendar_days_to_recovery = None
            return_to_recovery = None

        rows.append(
            {
                "id": item["id"],
                "event": item["event"],

                # 公告日期與原始護盤資料
                "execution_start":
                    requested_entry_date,
                "execution_end":
                    requested_exit_date,
                "support_calendar_days_reported":
                    int(
                        item[
                            "support_calendar_days"
                        ]
                    ),

                # 實際匹配到的交易日
                "entry_date":
                    entry_date,
                "entry_close":
                    entry_close,
                "exit_date":
                    exit_date,
                "exit_close":
                    exit_close,

                # 為相容舊版前端保留的欄位名稱
                "matched_trade_date":
                    entry_date,
                "close":
                    entry_close,

                # 進場位置
                "sma200":
                    entry_sma200,
                "distance_from_sma200":
                    float(
                        entry_close
                        / entry_sma200
                        - 1
                    ),
                "peak_252_date":
                    df.loc[
                        peak_252_idx,
                        "Date",
                    ],
                "peak_252_close":
                    peak_252_close,
                "drawdown_from_252d_peak":
                    float(
                        entry_close
                        / peak_252_close
                        - 1
                    ),

                # 護盤期間最低點
                "lowest_date":
                    lowest_date,
                "lowest_close":
                    lowest_close,
                "max_drawdown_after_entry":
                    max_drawdown,
                "trading_days_to_lowest":
                    trading_days_to_lowest,
                "calendar_days_to_lowest":
                    calendar_days_to_lowest,

                # 相容舊版前端
                "lowest_date_after_entry":
                    lowest_date,
                "lowest_close_after_entry":
                    lowest_close,

                # 打平
                "breakeven_before_exit":
                    bool(
                        breakeven_before_exit
                    ),
                "breakeven_date":
                    breakeven_date,
                "breakeven_close":
                    breakeven_close,
                "trading_days_to_breakeven":
                    trading_days_to_breakeven,
                "calendar_days_to_breakeven":
                    calendar_days_to_breakeven,

                # 退場
                "return_to_exit":
                    return_to_exit,
                "trading_days_to_exit":
                    trading_days_to_exit,
                "calendar_days_to_exit":
                    calendar_days_to_exit,
                "holding_calendar_days_inclusive":
                    holding_calendar_days_inclusive,

                # 站回200SMA，保留供舊頁面相容
                "recovered_to_sma200":
                    bool(
                        recovered_to_sma200
                    ),
                "recovery_date":
                    recovery_date,
                "recovery_close":
                    recovery_close,
                "recovery_sma200":
                    recovery_sma200,
                "trading_days_to_recovery":
                    trading_days_to_recovery,
                "calendar_days_to_recovery":
                    calendar_days_to_recovery,
                "return_to_recovery":
                    return_to_recovery,
            }
        )

    return pd.DataFrame(rows)


def strategy_trigger_summary(
    events: pd.DataFrame,
) -> list[dict[str, Any]]:
    results = []

    for strategy in STRATEGIES:
        rows = []
        cash_used_values = []

        for _, event in events.iterrows():
            drawdown_pct = float(
                event["drawdown_from_peak"]
                * 100
            )

            used = sum(
                rule["cash_amount"]
                for rule in strategy["rules"]
                if (
                    drawdown_pct
                    <= rule[
                        "drawdown_from_peak_pct"
                    ]
                )
            )

            used = min(
                used,
                strategy["initial_cash"],
            )

            cash_used_values.append(used)

            rows.append(
                {
                    "event_id":
                        int(event["event_id"]),
                    "drawdown_from_peak_pct":
                        round(
                            drawdown_pct,
                            2,
                        ),
                    "cash_used":
                        used,
                    "cash_remaining":
                        (
                            strategy[
                                "initial_cash"
                            ]
                            - used
                        ),
                }
            )

        results.append(
            {
                "strategy_id":
                    strategy["id"],
                "name":
                    strategy["name"],
                "average_cash_used":
                    (
                        round(
                            sum(
                                cash_used_values
                            )
                            / len(
                                cash_used_values
                            ),
                            2,
                        )
                        if cash_used_values
                        else 0
                    ),
                "average_cash_used_pct":
                    (
                        round(
                            sum(
                                cash_used_values
                            )
                            / len(
                                cash_used_values
                            )
                            / strategy[
                                "initial_cash"
                            ]
                            * 100,
                            2,
                        )
                        if cash_used_values
                        else 0
                    ),
                "events_using_all_cash":
                    int(
                        sum(
                            value
                            >= strategy[
                                "initial_cash"
                            ]
                            for value
                            in cash_used_values
                        )
                    ),
                "event_results":
                    rows,
            }
        )

    return results


def serialize_records(
    df: pd.DataFrame,
) -> list[dict[str, Any]]:
    clean = df.copy()

    for col in clean.columns:
        if pd.api.types.is_datetime64_any_dtype(
            clean[col]
        ):
            clean[col] = clean[col].dt.strftime(
                "%Y-%m-%d"
            )

    clean = clean.where(
        pd.notna(clean),
        None,
    )

    return clean.to_dict(
        orient="records"
    )


def safe_mean(
    series: pd.Series,
) -> float | None:
    clean = pd.to_numeric(
        series,
        errors="coerce",
    ).dropna()

    if clean.empty:
        return None

    return float(clean.mean())


def safe_median(
    series: pd.Series,
) -> float | None:
    clean = pd.to_numeric(
        series,
        errors="coerce",
    ).dropna()

    if clean.empty:
        return None

    return float(clean.median())


def round_optional(
    value: float | None,
    digits: int = 2,
) -> float | None:
    if value is None:
        return None

    return round(float(value), digits)


def build_current_market(
    df: pd.DataFrame,
) -> dict[str, Any]:
    latest = df.iloc[-1]
    recent = df.tail(
        PEAK_LOOKBACK_DAYS
    )

    peak_idx = int(
        recent["Close"].idxmax()
    )
    peak_row = df.loc[peak_idx]

    close = float(
        latest["Close"]
    )
    sma200 = float(
        latest["SMA200"]
    )
    peak_close = float(
        peak_row["Close"]
    )

    distance_from_sma_pct = (
        close / sma200 - 1
    ) * 100

    drawdown_from_peak_pct = (
        close / peak_close - 1
    ) * 100

    below_sma = close < sma200

    triggered_levels = [
        threshold
        for threshold in THRESHOLDS
        if (
            drawdown_from_peak_pct
            <= -threshold
        )
    ]

    return {
        "date":
            latest["Date"].strftime(
                "%Y-%m-%d"
            ),
        "close":
            round(close, 2),
        "sma200":
            round(sma200, 2),
        "distance_from_sma200_pct":
            round(
                distance_from_sma_pct,
                2,
            ),
        "peak_252_date":
            peak_row["Date"].strftime(
                "%Y-%m-%d"
            ),
        "peak_252_close":
            round(peak_close, 2),
        "drawdown_from_252d_peak_pct":
            round(
                drawdown_from_peak_pct,
                2,
            ),
        "below_sma200":
            bool(below_sma),
        "eligible_for_bear_market_plan":
            bool(below_sma),
        "triggered_drawdown_levels":
            triggered_levels,
        "current_trigger_level_pct":
            (
                max(triggered_levels)
                if triggered_levels
                else 0
            ),
    }


def build_fund_summary(
    fund: pd.DataFrame,
) -> dict[str, Any]:
    """建立國安基金進退場摘要。"""
    if fund.empty:
        return {
            "event_count": 0,
        }

    distance_from_sma = (
        fund["distance_from_sma200"]
        * 100
    )
    drawdown_from_peak = (
        fund["drawdown_from_252d_peak"]
        * 100
    )
    max_drawdown = (
        fund["max_drawdown_after_entry"]
        * 100
    )
    return_to_exit = (
        fund["return_to_exit"]
        * 100
    )

    breakeven_rows = fund[
        fund["breakeven_before_exit"]
    ]

    return {
        "event_count":
            int(len(fund)),

        "average_distance_from_sma200_pct":
            round_optional(
                safe_mean(
                    distance_from_sma
                )
            ),
        "median_distance_from_sma200_pct":
            round_optional(
                safe_median(
                    distance_from_sma
                )
            ),

        "average_drawdown_from_252d_peak_pct":
            round_optional(
                safe_mean(
                    drawdown_from_peak
                )
            ),
        "median_drawdown_from_252d_peak_pct":
            round_optional(
                safe_median(
                    drawdown_from_peak
                )
            ),

        "average_max_drawdown_after_entry_pct":
            round_optional(
                safe_mean(max_drawdown)
            ),
        "median_max_drawdown_after_entry_pct":
            round_optional(
                safe_median(max_drawdown)
            ),
        "deepest_max_drawdown_after_entry_pct":
            round(
                float(
                    max_drawdown.min()
                ),
                2,
            ),

        "average_trading_days_to_lowest":
            round_optional(
                safe_mean(
                    fund[
                        "trading_days_to_lowest"
                    ]
                )
            ),
        "median_trading_days_to_lowest":
            round_optional(
                safe_median(
                    fund[
                        "trading_days_to_lowest"
                    ]
                )
            ),

        "breakeven_before_exit_count":
            int(
                fund[
                    "breakeven_before_exit"
                ].sum()
            ),
        "not_breakeven_before_exit_count":
            int(
                (
                    ~fund[
                        "breakeven_before_exit"
                    ]
                ).sum()
            ),
        "average_trading_days_to_breakeven":
            round_optional(
                safe_mean(
                    breakeven_rows[
                        "trading_days_to_breakeven"
                    ]
                )
            ),
        "median_trading_days_to_breakeven":
            round_optional(
                safe_median(
                    breakeven_rows[
                        "trading_days_to_breakeven"
                    ]
                )
            ),

        "average_return_to_exit_pct":
            round_optional(
                safe_mean(return_to_exit)
            ),
        "median_return_to_exit_pct":
            round_optional(
                safe_median(return_to_exit)
            ),
        "best_return_to_exit_pct":
            round(
                float(
                    return_to_exit.max()
                ),
                2,
            ),
        "worst_return_to_exit_pct":
            round(
                float(
                    return_to_exit.min()
                ),
                2,
            ),

        "average_trading_days_to_exit":
            round_optional(
                safe_mean(
                    fund[
                        "trading_days_to_exit"
                    ]
                )
            ),
        "median_trading_days_to_exit":
            round_optional(
                safe_median(
                    fund[
                        "trading_days_to_exit"
                    ]
                )
            ),

        "average_holding_calendar_days_inclusive":
            round_optional(
                safe_mean(
                    fund[
                        "holding_calendar_days_inclusive"
                    ]
                )
            ),
        "median_holding_calendar_days_inclusive":
            round_optional(
                safe_median(
                    fund[
                        "holding_calendar_days_inclusive"
                    ]
                )
            ),
    }


def build_output(
    df: pd.DataFrame,
    events: pd.DataFrame,
    fund: pd.DataFrame,
) -> dict[str, Any]:
    drawdown_cross = (
        events["drawdown_from_cross"]
        * 100
    )
    drawdown_peak = (
        events["drawdown_from_peak"]
        * 100
    )

    current_market = build_current_market(
        df
    )

    return {
        "meta": {
            "title":
                "台股跌破200SMA與國安基金進退場統計",
            "market":
                "TAIEX",
            "symbol":
                "^TWII",
            "data_start":
                df["Date"]
                .min()
                .strftime("%Y-%m-%d"),
            "data_end":
                df["Date"]
                .max()
                .strftime("%Y-%m-%d"),
            "sma_days":
                SMA_DAYS,
            "peak_lookback_days":
                PEAK_LOOKBACK_DAYS,
            "event_definition":
                (
                    "收盤價由200SMA上方跌到下方，"
                    "直到首次收盤站回200SMA為一個事件"
                ),
            "fund_analysis_definition":
                (
                    "國安基金最低點與打平統計，"
                    "以實際進場交易日至實際退場交易日為區間"
                ),
            "breakeven_definition":
                (
                    "進場日之後，收盤價首次大於或等於進場收盤價"
                ),
            "fund_date_matching":
                (
                    "若公告日期不是交易日，"
                    "使用該日當天或之後第一個交易日"
                ),
            "drawdown_primary_basis":
                "跌破日前252個交易日最高收盤價",
            "version":
                "2.0.0",
        },

        "current_market":
            current_market,

        "summary": {
            "total_events":
                int(len(events)),
            "average_drawdown_from_cross_pct":
                round(
                    float(
                        drawdown_cross.mean()
                    ),
                    2,
                ),
            "median_drawdown_from_cross_pct":
                round(
                    float(
                        drawdown_cross.median()
                    ),
                    2,
                ),
            "deepest_drawdown_from_cross_pct":
                round(
                    float(
                        drawdown_cross.min()
                    ),
                    2,
                ),
            "average_drawdown_from_peak_pct":
                round(
                    float(
                        drawdown_peak.mean()
                    ),
                    2,
                ),
            "median_drawdown_from_peak_pct":
                round(
                    float(
                        drawdown_peak.median()
                    ),
                    2,
                ),
            "deepest_drawdown_from_peak_pct":
                round(
                    float(
                        drawdown_peak.min()
                    ),
                    2,
                ),
            "average_days_below_sma":
                round(
                    float(
                        events[
                            "days_below_sma"
                        ].mean()
                    ),
                    2,
                ),
            "median_days_below_sma":
                round(
                    float(
                        events[
                            "days_below_sma"
                        ].median()
                    ),
                    2,
                ),
        },

        "threshold_probability": {
            "from_cross_date":
                threshold_stats(
                    events,
                    "drawdown_from_cross",
                ),
            "from_252d_peak":
                threshold_stats(
                    events,
                    "drawdown_from_peak",
                ),
        },

        "national_stabilization_fund_summary":
            build_fund_summary(fund),

        "strategies":
            STRATEGIES,

        "strategy_trigger_summary":
            strategy_trigger_summary(events),

        "events":
            serialize_records(events),

        "national_stabilization_fund":
            serialize_records(fund),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    df = load_data()
    events = find_events(df)
    fund = analyze_fund_entries(df)

    output = build_output(
        df,
        events,
        fund,
    )

    JSON_PATH.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    events.to_csv(
        EVENTS_CSV_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    fund.to_csv(
        FUND_CSV_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"完成：{JSON_PATH}")
    print(f"完成：{EVENTS_CSV_PATH}")
    print(f"完成：{FUND_CSV_PATH}")
    print(f"跌破200SMA事件：{len(events)} 次")
    print(f"國安基金事件：{len(fund)} 次")


if __name__ == "__main__":
    main()
