###############################################################
# app_nsf.py — 國安基金跟單：全時持有 + 護盤加碼正2 專業對照版
###############################################################

import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path
import sys
from datetime import date

###############################################################
# 1. 頁面與認證設定
###############################################################

st.set_page_config(
    page_title="國安基金槓桿回測系統", 
    page_icon="🏛️", 
    layout="wide"
)

# 🔒 認證機制 (保留您原有的 auth.py 串接)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except ImportError:
    pass 

# --- Sidebar 導覽列 ---
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

###############################################################
# 2. 歷史資料與參數定義
###############################################################

NSF_DATES = [
    ("2000-03-15", "2000-03-20"), ("2000-10-02", "2000-11-15"),
    ("2004-05-19", "2004-05-31"), ("2008-09-19", "2008-12-16"),
    ("2011-12-20", "2012-04-20"), ("2015-08-25", "2016-04-12"),
    ("2020-03-19", "2020-10-12"), ("2022-07-13", "2023-04-13"),
    ("2025-04-09", "2026-01-12"),
]

LEV_OPTIONS = {
    "00631L 元大台灣50正2": "00631L.TW",
    "00663L 國泰台灣加權正2": "00663L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW",
    "00685L 群益台灣加權正2": "00685L.TW"
}

DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    return df[["Close"]]

###############################################################
# 3. UI 佈局
###############################################################

st.title("🏛️ 國安基金跟單：加碼正2策略回測")

col_s1, col_s2 = st.columns(2)
with col_s1:
    base_label = st.selectbox("原型 ETF（訊號來源）", ["0050 元大台灣50", "006208 富邦台50"])
    base_symbol = "0050.TW" if "0050" in base_label else "006208.TW"
with col_s2:
    lev_label = st.selectbox("槓桿 ETF（實際進出場標的）", list(LEV_OPTIONS.keys()))
    lev_symbol = LEV_OPTIONS[lev_label]

df_base_raw = load_csv(base_symbol)
df_lev_raw = load_csv(lev_symbol)

if df_base_raw.empty or df_lev_raw.empty:
    st.error("⚠️ 找不到 CSV 資料，請確保 data 資料夾內有對應檔案。"); st.stop()

common_start = max(df_base_raw.index.min(), df_lev_raw.index.min())
common_end = min(df_base_raw.index.max(), df_lev_raw.index.max())

st.info(f"📌 可回測區間：{common_start.date()} ~ {common_end.date()}")

col_p1, col_p2, col_p3, col_p4 = st.columns(4)
with col_p1:
    start_date = st.date_input("開始日期", value=date(2021, 1, 13), min_value=common_start.date(), max_value=common_end.date())
with col_p2:
    end_date = st.date_input("結束日期", value=common_end.date(), min_value=common_start.date(), max_value=common_end.date())
with col_p3:
    capital = st.number_input("投入本金（元）", value=100000, step=10000)
with col_p4:
    sma_period = st.number_input("均線週期 (SMA)", value=200, step=10)

###############################################################
# 4. 回測運算
###############################################################

if st.button("開始回測 🚀", use_container_width=True):
    df = pd.merge(df_base_raw, df_lev_raw, left_index=True, right_index=True, suffixes=('_Base', '_Lev'))
    df = df.loc[str(start_date):str(end_date)].copy()
    
    df["Ret_Base"] = df["Close_Base"].pct_change().fillna(0)
    df["Ret_Lev"] = df["Close_Lev"].pct_change().fillna(0)
    
    df["In_NSF"] = 0
    for s, e in NSF_DATES:
        df.loc[s:e, "In_NSF"] = 1
    
    df["Strategy_Return"] = np.where(df["In_NSF"] == 1, df["Ret_Lev"], df["Ret_Base"])
    df["Equity_Strategy"] = (1 + df["Strategy_Return"]).cumprod()
    df["Equity_Lev_BH"] = (1 + df["Ret_Lev"]).cumprod()
    df["Equity_Base_BH"] = (1 + df["Ret_Base"]).cumprod()

    # --- 績效指標計算 ---
    def get_full_stats(equity_series, return_series):
        final_eq = equity_series.iloc[-1]
        total_ret = final_eq - 1
        days = (equity_series.index[-1] - equity_series.index[0]).days
        cagr = (final_eq)**(365/days) - 1 if final_eq > 0 else 0
        mdd = (equity_series / equity_series.cummax() - 1).min()
        vol = return_series.std() * np.sqrt(252)
        sharpe = (return_series.mean() / return_series.std() * np.sqrt(252)) if return_series.std() != 0 else 0
        down_ret = return_series[return_series < 0]
        sortino = (return_series.mean() * 252) / (down_ret.std() * np.sqrt(252)) if not down_ret.empty else 0
        calmar = abs(cagr / mdd) if mdd != 0 else 0
        return [final_eq * capital, total_ret, cagr, calmar, mdd, vol, sharpe, sortino]

    s_strat = get_full_stats(df["Equity_Strategy"], df["Strategy_Return"])
    s_lev = get_full_stats(df["Equity_Lev_BH"], df["Ret_Lev"])
    s_base = get_full_stats(df["Equity_Base_BH"], df["Ret_Base"])

    # --- 5. 頂部卡片 ---
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("期末資產", f"{s_strat[0]:,.0f} 元", f"{((s_strat[0]/s_lev[0])-1):+.2%} (vs 槓桿)")
    k2.metric("CAGR", f"{s_strat[2]:.2%}", f"{(s_strat[2]-s_lev[2]):+.2%} (vs 槓桿)")
    k3.metric("波動率", f"{s_strat[5]:.2%}", f"{(s_strat[5]-s_lev[5]):+.2%} (vs 槓桿)", delta_color="inverse")
    k4.metric("最大回撤", f"{s_strat[4]:.2%}", f"{(s_strat[4]-s_lev[4]):+.2%} (vs 槓桿)", delta_color="inverse")

    # --- 6. HTML 表格 (關鍵修正點) ---
    st.markdown("### 📊 策略績效深度對照")
    metrics_names = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio"]
    
    html = f"""
    <style>
        .p-table {{ width:100%; border-collapse: collapse; font-family: sans-serif; font-size: 15px; margin-top: 10px; }}
        .p-table th {{ background-color: #f8fafc; padding: 12px; text-align: center; border-bottom: 2px solid #e2e8f0; color: #64748b; font-weight: 600; }}
        .p-table td {{ padding: 12px; text-align: center; border-bottom: 1px solid #f1f5f9; color: #334155; }}
        .label-col {{ text-align: left !important; font-weight: 500; background-color: #fcfcfc; }}
        .winner {{ color: #d97706; font-weight: bold; }}
        .trophy {{ color: #fbbf24; margin-left: 5px; }}
    </style>
    <table class="p-table">
        <thead>
            <tr>
                <th class="label-col">指標</th>
                <th>策略 (國安加碼)<br><small>{lev_symbol}</small></th>
                <th>Buy & Hold<br><small>{lev_symbol}</small></th>
                <th>Buy & Hold<br><small>{base_symbol}</small></th>
            </tr>
        </thead>
        <tbody>
    """
    
    for i, name in enumerate(metrics_names):
        v_s, v_l, v_b = s_strat[i], s_lev[i], s_base[i]
        
        # 贏家判斷 (修正：MDD 越接近 0 (數值越大) 越好，波動率越小越好)
        if name == "年化波動":
            best = min(v_s, v_l, v_b)
        else:
            best = max(v_s, v_l, v_b)
            
        def fmt(val, n):
            if "資產" in n: return f"{val:,.0f} 元"
            if any(x in n for x in ["率", "報酬", "MDD", "波動"]): return f"{val:.2%}"
            return f"{val:.2f}"

        def get_td(val, best_val):
            cls = ' class="winner"' if val == best_val else ''
            trophy = ' <span class="trophy">🏆</span>' if val == best_val else ''
            return f'<td{cls}>{fmt(val, name)}{trophy}</td>'

        html += f"""
            <tr>
                <td class="label-col">{name}</td>
                {get_td(v_s, best)}
                {get_td(v_l, best)}
                {get_td(v_b, best)}
            </tr>
        """
    
    html += "</tbody></table>"
    st.markdown(html, unsafe_allow_html=True)

    # --- 7. 圖表 ---
    st.markdown("### 📈 累積淨值比較")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"]*capital, name="策略 (加碼正2)", line=dict(color="#FF4B4B", width=3)))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_Lev_BH"]*capital, name="正2 Buy & Hold", line=dict(color="#94A3B8", width=1.5, dash='dash')))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_Base_BH"]*capital, name="原型 Buy & Hold", line=dict(color="#CBD5E0", width=1.5)))
    fig.update_layout(template="plotly_white", hovermode="x unified", height=500, margin=dict(l=0,r=0,t=20,b=0))
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.caption(f"© 2026 倉鼠人生實驗室 | 數據最後更新：2026-01-12")
