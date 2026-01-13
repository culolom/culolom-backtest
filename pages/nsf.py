###############################################################
# app_nsf.py — 國安基金「全時持有 + 護盤加碼正2」回測系統
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path
import sys

###############################################################
# 1. Streamlit 頁面與安全設定
###############################################################

st.set_page_config(
    page_title="國安基金槓桿加碼回測", 
    page_icon="🏛️", 
    layout="wide"
)

# 🔒 認證機制 (如果 auth.py 存在則啟用)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except ImportError:
    st.warning("⚠️ 未偵測到 auth.py，目前處於公開存取模式。")

# --- Sidebar 導覽列 ---
with st.sidebar:
    st.header("⚙️ 系統選單")
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室首頁", icon="🏠")
    st.divider()
    
    st.markdown("### 🛠️ 回測參數")
    target_symbol = st.selectbox("基礎持有標的", ["0050.TW", "006208.TW"])
    lev_symbol = "00631L.TW" # 正2 標的
    capital = st.number_input("初始投入本金 (元)", 1000, 10_000_000, 1_000_000, step=100_000)
    
    # 加入交易成本設定
    st.markdown("### 💸 交易成本設定")
    fee_rate = st.slider("單邊交易成本 (%)", 0.0, 1.0, 0.15, step=0.01) / 100
    
    st.divider()
    st.page_link("https://hamr-lab.com/", label="倉鼠人生官網", icon="🔗")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

###############################################################
# 2. 歷史資料定義
###############################################################

# 國安基金歷史進退場日期 (更新至 2026/01/12)
NSF_DATES = [
    ("2000-03-15", "2000-03-20"),
    ("2000-10-02", "2000-11-15"),
    ("2004-05-19", "2004-05-31"),
    ("2008-09-19", "2008-12-16"),
    ("2011-12-20", "2012-04-20"),
    ("2015-08-25", "2016-04-12"),
    ("2020-03-19", "2020-10-12"),
    ("2022-07-13", "2023-04-13"),
    ("2025-04-09", "2026-01-12"),
]

DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    return df[["Close"]]

###############################################################
# 3. 核心運算與回測邏輯
###############################################################

st.title("🏛️ 國安基金：平時 0050，護盤加碼 正2 策略")

st.info(f"""
**策略邏輯：**
1. **[平時]**：100% 持有 **{target_symbol}**。
2. **[國安進場]**：國安基金公告護盤期間，全數換倉為 **{lev_symbol} (正2)**。
3. **[國安退場]**：護盤結束後，換回 **{target_symbol}**。
*回測已自動考慮單邊 {fee_rate:.2%} 的交易摩擦成本（含換倉手續費與稅）。*
""")

if st.button("執行深度回測 🚀", use_container_width=True):
    df_base = load_csv(target_symbol)
    df_lev = load_csv(lev_symbol)
    
    if df_base.empty or df_lev.empty:
        st.error(f"⚠️ 資料遺失：請確保 data/ 下有 {target_symbol} 與 {lev_symbol}。")
        st.stop()

    # 對齊日期 (從兩者皆有的日期開始計算，主要是正2掛牌日)
    df = pd.merge(df_base, df_lev, left_index=True, right_index=True, suffixes=('_Base', '_Lev'))
    
    # 標記護盤時間區間
    df["In_NSF"] = 0
    for start, end in NSF_DATES:
        df.loc[start:end, "In_NSF"] = 1
    
    # 計算標的報酬率
    df["Ret_Base"] = df["Close_Base"].pct_change().fillna(0)
    df["Ret_Lev"] = df["Close_Lev"].pct_change().fillna(0)
    
    # 判定換倉信號 (1: 切換至正2, -1: 切回0050)
    df["Signal"] = df["In_NSF"].diff().fillna(0)
    
    # 核心邏輯：計算策略日報酬 (np.where 進行動態分配)
    df["Strategy_Return"] = np.where(df["In_NSF"] == 1, df["Ret_Lev"], df["Ret_Base"])
    
    # 扣除換倉成本 (當信號發生時)
    df["Cost"] = np.where(df["Signal"] != 0, fee_rate, 0)
    df["Net_Strategy_Return"] = (1 + df["Strategy_Return"]) * (1 - df["Cost"]) - 1

    # 計算累積淨值
    df["Equity_Strategy"] = (1 + df["Net_Strategy_Return"]).cumprod()
    df["Equity_BH"] = (1 + df["Ret_Base"]).cumprod()

    # --- 4. 圖表繪製 ---
    fig = go.Figure()
    # 策略曲線
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Equity_Strategy"] * capital,
        name="護盤加碼策略 (正2)", line=dict(color="#FF4B4B", width=3)
    ))
    # 基準曲線
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Equity_BH"] * capital,
        name=f"{target_symbol} Buy & Hold", line=dict(color="#94A3B8", width=1.5, dash='dot')
    ))
    
    # 標記進退場點
    sw_to_lev = df[df["Signal"] == 1]
    sw_to_base = df[df["Signal"] == -1]
    
    fig.add_trace(go.Scatter(
        x=sw_to_lev.index, y=df.loc[sw_to_lev.index, "Equity_Strategy"] * capital,
        mode="markers", name="切換至正2", marker=dict(symbol="triangle-up", size=12, color="#059669")
    ))
    fig.add_trace(go.Scatter(
        x=sw_to_base.index, y=df.loc[sw_to_base.index, "Equity_Strategy"] * capital,
        mode="markers", name="切回 0050", marker=dict(symbol="triangle-down", size=12, color="#D97706")
    ))

    fig.update_layout(
        template="plotly_white", 
        hovermode="x unified", 
        height=550, 
        yaxis_title="資產淨值 (元)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- 5. 績效統計表 ---
    def calculate_stats(equity_series, return_series):
        final_val = equity_series.iloc[-1]
        total_ret = final_val - 1
        days = (equity_series.index[-1] - equity_series.index[0]).days
        cagr = (final_val)**(365/days) - 1 if final_val > 0 else 0
        mdd = (equity_series / equity_series.cummax() - 1).min()
        vol = return_series.std() * np.sqrt(252)
        sharpe = (return_series.mean() / return_series.std() * np.sqrt(252)) if return_series.std() != 0 else 0
        calmar = abs(cagr / mdd) if mdd != 0 else 0
        return [final_val * capital, total_ret, cagr, mdd, vol, sharpe, calmar]

    stats_strat = calculate_stats(df["Equity_Strategy"], df["Net_Strategy_Return"])
    stats_bh = calculate_stats(df["Equity_BH"], df["Ret_Base"])

    st.subheader("🏆 策略績效深度對照")
    metrics = ["期末淨值", "總報酬率", "年化報酬 (CAGR)", "最大回撤 (MDD)", "年化波動率", "夏普比率 (Sharpe)", "卡瑪比率 (Calmar)"]
    
    df_perf = pd.DataFrame({
        "指標名稱": metrics,
        "加碼正2策略": stats_strat,
        f"{target_symbol} 持有": stats_bh
    })

    # 美化表格輸出
    col1, col2, col3 = st.columns(3)
    col1.metric("策略最終資產", f"${stats_strat[0]:,.0f}")
    col2.metric("超越基準報酬", f"{(stats_strat[1]-stats_bh[1])*100:.2f}%")
    col3.metric("總換倉次數", int((df["Signal"] != 0).sum()))

    # HTML 渲染美化表格
    html_table = """
    <style>
        .p-table { width:100%; border-collapse: collapse; font-family: sans-serif; }
        .p-table th { background-color: #f8fafc; padding: 12px; text-align: left; border-bottom: 2px solid #e2e8f0; }
        .p-table td { padding: 12px; border-bottom: 1px solid #f1f5f9; }
        .win { color: #dc2626; font-weight: bold; }
    </style>
    <table class="p-table">
        <thead><tr><th>績效指標</th><th>加碼正2策略</th><th>基準持有</th></tr></thead>
        <tbody>
    """
    for i, m in enumerate(metrics):
        v1, v2 = stats_strat[i], stats_bh[i]
        # 格式化
        if "淨值" in m: fmt1, fmt2 = f"{v1:,.0f}", f"{v2:,.0f}"
        elif any(x in m for x in ["率", "報酬", "MDD"]): fmt1, fmt2 = f"{v1:.2%}", f"{v2:.2%}"
        else: fmt1, fmt2 = f"{v1:.2f}", f"{v2:.2f}"
        
        # 判斷贏家
        is_win = v1 > v2 if m not in ["最大回撤 (MDD)", "年化波動率"] else v1 > v2 # MDD 越接近0(大)越好
        win_class = 'class="win"' if is_win else ''
        
        html_table += f"<tr><td>{m}</td><td {win_class}>{fmt1}</td><td>{fmt2}</td></tr>"
    
    html_table += "</tbody></table>"
    st.write(html_table, unsafe_allow_html=True)

# --- 6. 頁尾免責聲明 ---
st.markdown("---")
st.markdown(
    f"""<div style="text-align:center; color:#64748b; font-size:0.8rem;">
    © 2026 倉鼠人生實驗室 Hamr-Lab. 版權所有<br>
    數據起迄：{NSF_DATES[0][0]} ~ 2026/01/12 | 策略僅供參考，投資盈虧請自負。
    </div>""", unsafe_allow_html=True
)
