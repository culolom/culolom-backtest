import yfinance as yf
import pandas as pd

def load_price(symbol: str) -> pd.DataFrame:
    """
    統一使用 yfinance auto_adjust=True
    """
    df = yf.download(symbol, auto_adjust=True)
    if df.empty:
        raise ValueError(f"無法下載：{symbol}")

    return df.rename(columns={"Close": "Price"})
