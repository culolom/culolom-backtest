"""Data loading utilities for HamrLab backtest platform.

This module centralizes access to CSV price data located in the ``data/``
directory. All strategy pages should rely on these helpers to avoid
inconsistent datasets across environments.
"""
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def list_symbols():
    """Return a sorted list of symbols based on ``data/*.csv`` files."""
    if not DATA_DIR.exists():
        return []
    return sorted(p.stem for p in DATA_DIR.glob("*.csv") if p.is_file())


def load_price(symbol: str) -> pd.DataFrame:
    """Load price data for a symbol from ``data/{symbol}.csv``.

    The CSV must have a date index. ``index_col=0`` and ``parse_dates=True``
    are applied by default. Errors are surfaced as exceptions so callers can
    present friendly messages to the UI.
    """
    csv_path = DATA_DIR / f"{symbol}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)

    if df.empty:
        raise ValueError(f"CSV file is empty: {csv_path}")

    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception as exc:  # pragma: no cover - defensive conversion
            raise ValueError(f"Failed to parse dates in {csv_path}") from exc

    df = df.sort_index()
    return df
