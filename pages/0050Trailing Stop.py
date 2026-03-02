###############################################################
# app.py — 0050 區間極值反轉策略 (趨勢濾網強化版)
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
import sys

###############################################################
# 1. 環境設定與名稱映射
###############################################################

TICKER_NAMES = {
    "0050.TW": "0050 元大台灣50",
    "006208.TW": "006208 富邦台50",
    "00631L.TW": "00631L 元大台灣50正2",
    "00635U.TW": "00635U 元大標普500",
    "00646.TW": "00646 元大標普500",
    "00647L.TW": "00647L 元大標普500正2",
    "00662.TW": "00662 富邦 NASDAQ",
    "00663L.TW": "00663L 國泰台灣加權正2",
    "00670L.TW": "00670L 富邦 NASDAQ 正2",
    "00675L.TW": "00675L 富邦台灣加權正2",
    "00685L.TW": "00685L 群益台灣加權正2",
    "00878.TW": "00878 國泰永續高股息",
    "BTC-USD": "BTC-USD 比特幣"
}

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="區間極值反轉策略", page_icon="📈", layout="wide")

# 🔒 驗證守門員 (如有需要可取消註釋)
# try:
#     sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
#     import auth 
#     if not auth.check_password(): st.stop()
# except: pass 

###############################################################
# 2. 核心計算函數
###############################################################

DATA_DIR = Path("data")

def get_csv_list():
    if not DATA_DIR.exists(): return []
    return sorted([f.stem for f in DATA_DIR.glob("*.csv")])

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    if "Close" in df.columns: df["Price"] = df["Close"]
    return df[["Price"]]

def calc_metrics(series: pd.Series):
    daily = series.dropna()
    if len(daily) <= 1: return np.nan, np.nan, np.nan
    avg, std, downside = daily.mean(), daily.std(), daily[daily < 0].std()
    vol = std * np.sqrt(252)
    sharpe = (avg / std) * np.sqrt(252) if std > 0 else np.nan
    sortino = (avg / downside) * np.sqrt(252) if downside > 0 else np.nan
    return vol, sharpe, sortino

def get_stats(eq, rets, y):
    f_eq = eq.iloc[-1]
    f_ret = f_eq - 1
    cagr = (1 + f_ret)**(1/y) - 1 if y > 0 else 0
    mdd = 1 - (eq / eq.cummax()).min()
    v, sh, so = calc_metrics(rets)
    calmar = cagr / mdd if mdd > 0 else 0
    return f_eq, f_ret, cagr, mdd, v, sh, so, calmar

def fmt_money(v): return f"{v:,.0f} 元"
def fmt_pct(v, d=2): return f"{v:.{d}%}"
def fmt_num(v, d=2): return f"{v:.{d}f}"
def fmt_int(v): return f"{int(v):,}"

###############################################################
# 3. UI 介面
###############################################################

with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

st.markdown("<h1 style='margin-bottom:0.1em;'>📈 區間極值反轉策略 (趨勢過濾版)</h1>", unsafe_allow_html=True)

available_ids = get_csv_list()
if not available_ids:
    st.error("❌ data 資料夾內找不到任何 CSV 檔案"); st.stop()

st.markdown("##### 原型 ETF（訊號來源）")
target_id = st.selectbox(
    "", 
    available_ids, 
    label_visibility="collapsed",
    index=available_ids.index("00631L.TW") if "00631L.TW" in available_ids else 0,
    format_func=lambda x: TICKER_NAMES.get(x, x)
)

ch_name = TICKER_NAMES.get(target_id, target_id)
df_preview = load_csv(target_id)
if df_preview.empty:
    st.error(f"無法載入 {target_id} 的數據"); st.stop()

s_min, s_max = df_preview.index.min().date(), df_preview.index.max().date()
st.info(f"📌 可回測區間：{s_min} ~ {s_max}")

col_p1, col_p2, col_p3 = st.columns(3)
start = col_p1.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5*365)))
end = col_p2.date_input("結束日期", value=s_max)
capital = col_p3.number_input("投入本金", 1000, 10000000, 100000, step=10000)

st.write("---")
st.markdown("### ⚙️ 策略參數設定")

col_set1, col_set2, col_set3, col_set4 = st.columns(4)

with col_set1:
    enable_sma = st.toggle("啟用 SMA 趨勢濾網", value=True, help="開啟後，股價低於 SMA 將強制清倉不進場")
    sma_window = st.number_input("趨勢濾網天數 (SMA)", 10, 300, 200, step=10, disabled=not enable_sma)
with col_set2:
    lookback_window = st.number_input("基準區間 (尋找前高低點)", 5, 240, 20, step=1)
with col_set3:
    buy_pct = st.number_input("進場：自低點反彈 (%)", 1.0, 50.0, 5.0, step=0.5)
with col_set4:
    sell_pct = st.number_input("出場：自高點回落 (%)", 1.0, 50.0, 5.0, step=0.5)

###############################################################
# 4. 回測執行邏輯
###############################################################

if st.button("啟動回測引擎 🚀"):
    # 預留足夠天數計算指標
    max_lookback = max(sma_window if enable_sma else 0, lookback_window)
    start_buf = start - dt.timedelta(days=int(max_lookback * 2))
    df = load_csv(target_id).loc[start_buf:end]
    
    if df.empty: st.error("⚠️ 數據讀取失敗"); st.stop()

    # 計算技術指標
    if enable_sma:
        df["SMA"] = df["Price"].rolling(sma_window).mean()
    else:
        df["SMA"] = np.nan
        
    df["Period_Min"] = df["Price"].rolling(lookback_window).min().shift(1)
    df["Period_Max"] = df["Price"].rolling(lookback_window).max().shift(1)
    
    # 計算買賣觸發線
    df["Buy_Line"] = df["Period_Min"] * (1 + buy_pct / 100.0)
    df["Sell_Line"] = df["Period_Max"] * (1 - sell_pct / 100.0)
    
    # 裁切資料
    if enable_sma:
        df = df.dropna(subset=["Period_Min", "Period_Max", "SMA"]).loc[start:end]
    else:
        df = df.dropna(subset=["Period_Min", "Period_Max"]).loc[start:end]
    
    sigs, pos = [0] * len(df), [0.0] * len(df)
    in_position = False
    
    # 核心策略循環
    for i in range(1, len(df)):
        p = df["Price"].iloc[i]
        p0 = df["Price"].iloc[i-1]
        p_max = df["Period_Max"].iloc[i]
        early_sell = df["Sell_Line"].iloc[i]
        early_buy = df["Buy_Line"].iloc[i]
        sig = 0
        
        if enable_sma:
            sma = df["SMA"].iloc[i]
            sma0 = df["SMA"].iloc[i-1]
            
            # --- 情況 A: 股價在 SMA 之上 (多頭環境) ---
            if p > sma:
                if not in_position:
                    # 買入條件：1. 剛站回 SMA 或 2. 突破區間最高點
                    if (p0 <= sma0) or (p >= p_max):
                        in_position = True
                        sig = 1
                else:
                    # 出場條件：自區間高點回落設定比例
                    if p < early_sell:
                        in_position = False
                        sig = -1
            
            # --- 情況 B: 股價在 SMA 之下 (空頭環境) ---
            else:
                if in_position:
                    # 只要收盤價跌破 SMA，立即清倉出場
                    in_position = False
                    sig = -1
                # 即使出現反彈訊號也「不進場」，直到股價站回 SMA
        
        else:
            # === 無濾網邏輯 (純區間反轉) ===
            if not in_position:
                if p > early_buy:
                    in_position = True
                    sig = 1
            else:
                if p < early_sell:
                    in_position = False
                    sig = -1

        pos[i] = 1.0 if in_position else 0.0
        sigs[i] = sig

    df["Signal"], df["Position"] = sigs, pos
    
    # 計算資金曲線
    equity = [1.0]
    for i in range(1, len(df)):
        ret = (df["Price"].iloc[i] / df["Price"].iloc[i-1]) - 1
        equity.append(equity[-1] * (1 + (ret * df["Position"].iloc[i-1])))
    
    df["Equity_Strategy"] = equity
    df["Return_Strategy"] = df["Equity_Strategy"].pct_change().fillna(0)
    df["Equity_BH"] = (df["Price"] / df["Price"].iloc[0])
    df["Return_BH"] = df["Price"].pct_change().fillna(0)
    
    y_len = (df.index[-1] - df.index[0]).days / 365
    sl = get_stats(df["Equity_Strategy"], df["Return_Strategy"], y_len)
    sb = get_stats(df["Equity_BH"], df["Return_BH"], y_len)

    # KPI 卡片
    st.markdown("""<style>.kpi-card { background: white; border-radius: 16px; padding: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border: 1px solid #f0f0f0; text-align: left; } .kpi-label { color: #8c8c8c; font-size: 1rem; margin-bottom: 12px; font-weight: 500; } .kpi-val { font-size: 2.3rem; font-weight: 900; color: #1a1a1a; margin-bottom: 15px; } .delta-tag { display: inline-block; padding: 4px 14px; border-radius: 20px; font-size: 0.9rem; font-weight: 700; } .delta-pos { background: #e6f7ed; color: #21c354; } .delta-neg { background: #fff1f0; color: #ff4d4f; } </style> """, unsafe_allow_html=True)
    k_cols = st.columns(4)
    def render_kpi(col, label, val, delta, is_better_if_higher=True):
        is_good = (delta >= 0) if is_better_if_higher else (delta <= 0)
        style = "delta-pos" if is_good else "delta-neg"
        col.markdown(f'<div class="kpi-card"><div class="kpi-label">{label}</div><div class="kpi-val">{val}</div><div class="delta-tag {style}">{delta:+.2%} (vs 標的)</div></div>', unsafe_allow_html=True)
    
    render_kpi(k_cols[0], "期末資產", fmt_money(sl[0]*capital), (sl[0]/sb[0]-1))
    render_kpi(k_cols[1], "CAGR", fmt_pct(sl[2]), (sl[2]-sb[2]))
    render_kpi(k_cols[2], "波動率", fmt_pct(sl[4]), (sl[4]-sb[4]), is_better_if_higher=False)
    render_kpi(k_cols[3], "最大回撤", fmt_pct(sl[3]), (sl[3]-sb[3]), is_better_if_higher=False)

    st.markdown(f"### 🏆 策略績效總表：{ch_name}")
    metrics = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "交易次數"]
    filter_label = f"{sma_window}SMA 趨勢過濾" if enable_sma else "無濾網"
    data_map = { f"<b>{ch_name}</b><br><small>{filter_label}</small>": [sl[0]*capital, sl[1], sl[2], sl[7], sl[3], sl[4], sl[5], (df["Signal"]!=0).sum()], f"<b>{ch_name}</b><br><small>Buy & Hold</small>": [sb[0]*capital, sb[1], sb[2], sb[7], sb[3], sb[4], sb[5], 0] }
    
    html = '<style>.ctable { width: 100%; border-collapse: collapse; border: 1px solid #f0f0f0; margin-top:10px; } .ctable th { background: #ffffff; padding: 20px; border-bottom: 1px solid #f0f0f0; color: #595959; } .ctable td { padding: 18px; text-align: center; border-bottom: 1px solid #f0f0f0; } .m-name { text-align: left !important; font-weight: 500; }</style>'
    html += '<table class="ctable"><thead><tr><th style="text-align:left">指標</th>'
    for col in data_map.keys(): html += f"<th>{col}</th>"
    html += "</tr></thead><tbody>"
    for idx, m in enumerate(metrics):
        html += f"<tr><td class='m-name'>{m}</td>"
        row_vals = [data_map[k][idx] for k in data_map.keys()]
        for i, v in enumerate(row_vals):
            if "資產" in m: txt = fmt_money(v)
            elif any(x in m for x in ["率", "報酬", "MDD", "波動"]): txt = fmt_pct(v)
            elif "次數" in m: txt = fmt_int(v)
            else: txt = fmt_num(v)
            is_win = (i == 0 and ((idx in [0,1,2,3,6] and row_vals[0] >= row_vals[1]) or (idx in [4,5] and row_vals[0] <= row_vals[1])))
            style = "font-weight:800; color:#1a1a1a;" if i == 0 else "color:#595959;"
            html += f"<td style='{style}'>{txt}{' 🏆' if is_win else ''}</td>"
        html += "</tr>"
    st.write(html + "</tbody></table>", unsafe_allow_html=True)

    # ------------------------------------------------------
    # 7. 圖表視覺化
    # ------------------------------------------------------
    st.markdown("### 📈 趨勢狀態與動態觸發線")
    fig_master = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.08,
        subplot_titles=("資金曲線比較", f"價格走勢與 {filter_label}"),
        row_heights=[0.3, 0.7]
    )

    fig_master.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"]-1, name="策略報酬", line=dict(width=2.5, color="#00D494")), row=1, col=1)
    fig_master.add_trace(go.Scatter(x=df.index, y=df["Equity_BH"]-1, name="Buy & Hold", line=dict(color="#FF4D4F", dash='dash')), row=1, col=1)

    if enable_sma:
        fig_master.add_trace(go.Scatter(x=df.index, y=df["SMA"], name=f"{sma_window} SMA 濾網", line=dict(color="#FFA15A", width=2.5)), row=2, col=1)
        # 僅在多頭區域顯示賣出線
        df_bull = df[df["Price"] > df["SMA"]]
        fig_master.add_trace(go.Scatter(x=df_bull.index, y=df_bull["Sell_Line"], mode="markers", name=f"回落賣出線 (-{sell_pct}%)", marker=dict(color="#FF4D4F", size=4, symbol="line-ew")), row=2, col=1)
    else:
        fig_master.add_trace(go.Scatter(x=df.index, y=df["Buy_Line"], name=f"買進線 (+{buy_pct}%)", line=dict(color="#1890FF", width=2, dash='dash')), row=2, col=1)
        fig_master.add_trace(go.Scatter(x=df.index, y=df["Sell_Line"], name=f"賣出線 (-{sell_pct}%)", line=dict(color="#FF4D4F", width=2, dash='dash')), row=2, col=1)

    fig_master.add_trace(go.Scatter(x=df.index, y=df["Price"], name=f"{ch_name} 股價", line=dict(color="#1F2937", width=1.5)), row=2, col=1)
    
    colors = {1: ("觸發買進", "#00C853", "triangle-up"), -1: ("觸發賣出", "#D50000", "triangle-down")}
    for v, (l, c, s) in colors.items():
        pts = df[df["Signal"] == v]
        if not pts.empty:
            fig_master.add_trace(go.Scatter(x=pts.index, y=pts["Price"], mode="markers", name=l, marker=dict(color=c, size=12, symbol=s), showlegend=True), row=2, col=1)

    fig_master.update_layout(height=800, template="plotly_white", hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig_master.update_yaxes(title_text="累積報酬率", tickformat=".0%", row=1, col=1)
    fig_master.update_yaxes(title_text="價格", row=2, col=1)

    st.plotly_chart(fig_master, use_container_width=True)
    st.caption("免責聲明：本工具僅供策略研究參考，投資必有風險。")
