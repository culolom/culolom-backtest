"""
產生「動能 × 200SMA」歷史座標資料，供 WordPress / Plotly / ECharts
繪製彗星尾、日期滑桿與動畫。

輸入：
    data/*.csv

輸出：
    trend_rotation.json

座標：
    X 軸 = 收盤價相對 200SMA 的乖離率（%）
    Y 軸 = 12 個月累積報酬（%）

執行位置：
    請在 repository 根目錄執行：
    python scripts/update_rotation.py
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd


# ============================================================
# 設定區
# ============================================================

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
OUTPUT_FILE = REPO_ROOT / "trend_rotation.json"

# 第一版先放全球資產。之後可直接增刪。
TARGET_SYMBOLS = [
    "VT",
    "VTI",
    "SPY",
    "QQQ",
    "VXUS",
    "VEA",
    "VWO",
    "TLT",
    "IEF",
    "IEI",
    "BIL",
    "SGOV",
    "GLD",
    "SLV",
    "VNQ",
    "BOXX",
    "BTC-USD",
    "0050.TW",
]

SMA_WINDOW = 200

# 每個標的最多輸出最近幾個有效交易日。
# 500 約兩年，足夠做 5／20／60／120 日彗星尾與歷史播放。
MAX_OUTPUT_POINTS = 500

# 尋找「一年前價格」時，允許實際交易日與目標日期最多相差幾天。
MAX_12M_DATE_GAP_DAYS = 10

# 超過此天數沒有更新，視為資料過舊，但仍保留並加上 stale=true。
STALE_AFTER_DAYS = 35


# ============================================================
# 工具函式
# ============================================================

def safe_float(value: object, digits: int = 4) -> Optional[float]:
    """把數值轉成可寫入 JSON 的 float；NaN / inf 轉成 None。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number):
        return None

    return round(number, digits)


def load_price_csv(file_path: Path) -> Optional[pd.DataFrame]:
    """
    讀取 CSV，標準化成：
        index: DatetimeIndex
        close: float

    價格欄位優先順序：
        Adj Close -> Close
    """
    try:
        df = pd.read_csv(file_path)

        if df.empty:
            print(f"⚠️ 空白檔案：{file_path.name}")
            return None

        # 日期欄位
        if "Date" in df.columns:
            date_col = "Date"
        else:
            date_col = df.columns[0]

        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col])
        df = df.set_index(date_col).sort_index()

        # 避免同一天重複資料
        df = df[~df.index.duplicated(keep="last")]

        if "Adj Close" in df.columns:
            price_col = "Adj Close"
        elif "Close" in df.columns:
            price_col = "Close"
        else:
            print(f"⚠️ 找不到 Adj Close 或 Close：{file_path.name}")
            return None

        close = pd.to_numeric(df[price_col], errors="coerce")
        result = pd.DataFrame({"close": close})
        result = result.dropna(subset=["close"])
        result = result[result["close"] > 0]

        if result.empty:
            print(f"⚠️ 沒有有效價格：{file_path.name}")
            return None

        # 去除時區，避免不同來源日期比較失敗
        if result.index.tz is not None:
            result.index = result.index.tz_localize(None)

        return result

    except Exception as exc:
        print(f"❌ 讀取失敗 {file_path.name}：{exc}")
        return None


def calculate_12m_momentum(close: pd.Series) -> pd.Series:
    """
    用「約一年前最近的交易日」計算 12 個月報酬。

    相較直接 shift(252)，這個算法更接近既有 update_momentum.py
    使用 DateOffset(months=12) 的概念。
    """
    dates = close.index
    values = close.to_numpy()
    output = [float("nan")] * len(close)

    for i, current_date in enumerate(dates):
        target_date = current_date - pd.DateOffset(months=12)

        # 找到 target_date 左右最接近的索引
        insertion = dates.searchsorted(target_date)
        candidates = []

        if insertion < len(dates):
            candidates.append(insertion)
        if insertion > 0:
            candidates.append(insertion - 1)

        if not candidates:
            continue

        nearest_idx = min(
            candidates,
            key=lambda idx: abs((dates[idx] - target_date).days),
        )

        gap_days = abs((dates[nearest_idx] - target_date).days)

        # 不可以拿到當日或未滿一年太多的資料
        if nearest_idx >= i or gap_days > MAX_12M_DATE_GAP_DAYS:
            continue

        old_price = values[nearest_idx]
        current_price = values[i]

        if old_price > 0:
            output[i] = (current_price / old_price - 1.0) * 100.0

    return pd.Series(output, index=dates, name="momentum_12m")


def determine_quadrant(sma_gap: float, momentum_12m: float) -> str:
    """依動能與 200SMA 乖離率判斷象限。"""
    if sma_gap >= 0 and momentum_12m >= 0:
        return "進攻區"
    if sma_gap < 0 <= momentum_12m:
        return "轉弱警戒區"
    if sma_gap < 0 and momentum_12m < 0:
        return "防守區"
    return "復甦觀察區"


def build_symbol_history(symbol: str, file_path: Path) -> Optional[dict]:
    """計算單一標的的歷史座標。"""
    df = load_price_csv(file_path)

    if df is None or len(df) < SMA_WINDOW:
        print(f"⚠️ {symbol} 資料不足 {SMA_WINDOW} 筆，跳過。")
        return None

    df["sma200"] = df["close"].rolling(
        window=SMA_WINDOW,
        min_periods=SMA_WINDOW,
    ).mean()

    df["sma_gap"] = (df["close"] / df["sma200"] - 1.0) * 100.0
    df["momentum_12m"] = calculate_12m_momentum(df["close"])

    # 只有兩個座標都有效時，才可用來畫象限
    valid = df.dropna(subset=["sma200", "sma_gap", "momentum_12m"]).copy()

    if valid.empty:
        print(f"⚠️ {symbol} 沒有足夠資料產生歷史座標。")
        return None

    valid = valid.tail(MAX_OUTPUT_POINTS)

    points = []
    for date, row in valid.iterrows():
        x = safe_float(row["sma_gap"], 4)
        y = safe_float(row["momentum_12m"], 4)

        if x is None or y is None:
            continue

        points.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "x": x,
                "y": y,
                "close": safe_float(row["close"], 4),
                "sma200": safe_float(row["sma200"], 4),
                "sma_gap": x,
                "momentum_12m": y,
                "quadrant": determine_quadrant(x, y),
            }
        )

    if not points:
        return None

    latest_date = pd.Timestamp(points[-1]["date"])
    today = pd.Timestamp.now().normalize()
    stale = (today - latest_date).days > STALE_AFTER_DAYS

    return {
        "symbol": symbol,
        "latest_date": points[-1]["date"],
        "stale": stale,
        "point_count": len(points),
        "latest": points[-1],
        "history": points,
    }


# ============================================================
# 主程式
# ============================================================

def main() -> None:
    print("🚀 開始產生動能 × 200SMA 歷史座標……")

    if not DATA_DIR.exists():
        raise FileNotFoundError(f"找不到資料夾：{DATA_DIR}")

    assets = {}
    skipped = []

    for symbol in TARGET_SYMBOLS:
        file_path = DATA_DIR / f"{symbol}.csv"

        if not file_path.exists():
            print(f"⚠️ 找不到 {file_path.name}，跳過。")
            skipped.append({"symbol": symbol, "reason": "file_not_found"})
            continue

        try:
            result = build_symbol_history(symbol, file_path)

            if result is None:
                skipped.append({"symbol": symbol, "reason": "insufficient_data"})
                continue

            assets[symbol] = result
            latest = result["latest"]

            print(
                f"✅ {symbol}｜{result['latest_date']}｜"
                f"X={latest['sma_gap']:.2f}%｜"
                f"Y={latest['momentum_12m']:.2f}%｜"
                f"{latest['quadrant']}"
            )

        except Exception as exc:
            print(f"❌ {symbol} 計算失敗：{exc}")
            skipped.append(
                {
                    "symbol": symbol,
                    "reason": "calculation_error",
                    "message": str(exc),
                }
            )

    if not assets:
        raise RuntimeError("沒有任何標的成功產生資料，未輸出 JSON。")

    latest_dates = [
        pd.Timestamp(asset["latest_date"])
        for asset in assets.values()
    ]
    market_latest_date = max(latest_dates).strftime("%Y-%m-%d")

    output = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_market_date": market_latest_date,
        "chart": {
            "name": "雙動能趨勢象限",
            "x_axis": {
                "key": "sma_gap",
                "label": "距離 200SMA 乖離率",
                "unit": "%",
                "center": 0,
            },
            "y_axis": {
                "key": "momentum_12m",
                "label": "12 個月累積報酬",
                "unit": "%",
                "center": 0,
            },
            "quadrants": {
                "top_right": "進攻區",
                "top_left": "轉弱警戒區",
                "bottom_left": "防守區",
                "bottom_right": "復甦觀察區",
            },
            "suggested_tail_lengths": [5, 10, 20, 60, 120],
        },
        "settings": {
            "sma_window": SMA_WINDOW,
            "max_output_points": MAX_OUTPUT_POINTS,
            "max_12m_date_gap_days": MAX_12M_DATE_GAP_DAYS,
        },
        "assets": assets,
        "skipped": skipped,
    }

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )

    file_size_kb = OUTPUT_FILE.stat().st_size / 1024

    print("")
    print(f"🎉 JSON 生成完成：{OUTPUT_FILE}")
    print(f"📦 成功標的：{len(assets)}")
    print(f"⏭️ 跳過標的：{len(skipped)}")
    print(f"💾 檔案大小：{file_size_kb:.1f} KB")


if __name__ == "__main__":
    main()
