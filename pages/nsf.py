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

# 🔒 認證機制 (保留原有機制)
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
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")

###############################################################
# 2. 歷史資料與參數定義
###############################################################

# 國安基金歷史進退場日期 (更新至 2026/01/12)
NSF_DATES = [
    ("2000-03-15", "2000-03-20"), ("2000-10-02", "2000-11-15"),
    ("2004-05-19", "2004-05-31"), ("2008-09-19", "2008-12-16"),
    ("2011-12-20", "2012-04-20"), ("2015-08-25", "2016-04-12"),
    ("2020-03-19", "2020-10-12"), ("2022-07-13", "2023-04-13"),
    ("2025-04-09", "2026-01-12"),
]

# 槓桿標的選單 (對應您截圖的標的)
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
# 3. UI 佈局 (完全復刻截圖排版)
###############################################################

st.title("🏛️ 國安基金跟單：加碼正2策略回測")

# 第一列：標題選擇 (原型 ETF vs 槓桿 ETF)
col_s1, col_s2 = st.columns(2)
with col_s1:
    base_label = st.selectbox("原型 ETF（訊號來源）", ["0050 元大台灣50", "006208 富邦台50"])
    base_symbol = "0050.TW" if "0050" in base_label else "006208.TW"
with col_s2:
    lev_label = st.selectbox("槓桿 ETF（實際進出場標的）", list(LEV_OPTIONS.keys()))
    lev_symbol = LEV_OPTIONS[lev_label]

# 讀取資料以決定可回測範圍
df_base_raw = load_csv(base_symbol)
df_lev_raw = load_csv(lev_symbol)

if df_base_raw.empty or df_lev_raw.empty:
    st.error("⚠️ 找不到 CSV 資料，請確保 data 資料夾內有對應檔案。"); st.stop()

# 找出兩者重疊的最早與最晚日期
common_start = max(df_base_raw.index.min(), df_lev_raw.index.min())
common_end = min(df_base_raw.index.max(), df_lev_raw.index.max())

# 藍色區間提示框
st.info(f"📌 可回測區間：{common_start.date()} ~ {common_end.date()}")

# 第二列：日期、金額、SMA 設定 (對應截圖)
col_p1, col_p2, col_p3, col_p4 = st.columns(4)
with col_p1:
    start_date = st.date_input("開始日期", value=date(2021, 1, 13), min_value=common_start.date(), max_value=common_end.date())
with col_p2:
    end_date = st.date_input("結束日期", value=common_end.date(), min_value=common_start.date(), max_value=common_end.date())
with col_p3:
    capital = st.number_input("投入本金（元）", value=100000, step=10000)
with col_p4:
    sma_period = st.number_input("均線週期 (SMA)", value=200, step=10) # 預留介面用

###############################################################
# 4. 核心回測運算與三方比較
###############################################################

if st.button("開始回測 🚀", use_container_width=True):
    # 資料對齊與切片
    df = pd.merge(df_base_raw, df_lev_raw, left_index=True, right_index=True, suffixes=('_Base', '_Lev'))
    df = df.loc[str(start_date):str(end_date)].copy()
    
    # 計算每日報酬率
    df["Ret_Base"] = df["Close_Base"].pct_change().fillna(0)
    df["Ret_Lev"] = df["Close_Lev"].pct_change().fillna(0)
    
    # 標記護盤時間區間
    df["In_NSF"] = 0
    for s, e in NSF_DATES:
        df.loc[s:e, "In_NSF"] = 1
    
    # --- 關鍵邏輯：三方績效計算 ---
    # 1. 策略：護盤期間拿正2報酬，平時拿原型報酬
    df["Strategy_Return"] = np.where(df["In_NSF"] == 1, df["Ret_Lev"], df["Ret_Base"])
    df["Equity_Strategy"] = (1 + df["Strategy_Return"]).cumprod()
    
    # 2. 基準 A：正2 持有到底 (Buy & Hold)
    df["Equity_Lev_BH"] = (1 + df["Ret_Lev"]).cumprod()
    
    # 3. 基準 B：原型 持有到底 (Buy & Hold)
    df["Equity_Base_BH"] = (1 + df["Ret_Base"]).cumprod()

    # --- 績效指標函式 ---
    def get_full_stats(equity_series, return_series):
        final_eq = equity_series.iloc[-1]
        total_ret = final_eq - 1
        days = (equity_series.index[-1] - equity_series.index[0]).days
        cagr = (final_eq)**(365/days) - 1 if final_eq > 0 else 0
        mdd = (equity_series / equity_series.cummax() - 1).min()
        vol = return_series.std() * np.sqrt(252)
        sharpe = (return_series.mean() / return_series.std() * np.sqrt(252)) if return_series.std() != 0 else 0
        
        # Sortino Ratio (僅計算下行波動)
        downside_ret = return_series[return_series < 0]
        sortino = (return_series.mean() * 252) / (downside_ret.std() * np.sqrt(252)) if not downside_ret.empty else 0
        
        # Calmar Ratio
        calmar = abs(cagr / mdd) if mdd != 0 else 0
        
        return [final_eq * capital, total_ret, cagr, calmar, mdd, vol, sharpe, sortino]

    stats_strat = get_full_stats(df["Equity_Strategy"], df["Strategy_Return"])
    stats_lev_bh = get_full_stats(df["Equity_Lev_BH"], df["Ret_Lev"])
    stats_base_bh = get_full_stats(df["Equity_Base_BH"], df["Ret_Base"])

    # --- 5. 顯示頂部指標卡片 (復刻截圖) ---
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("期末資產", f"{stats_strat[0]:,.0f} 元", f"{((stats_strat[0]/stats_lev_bh[0])-1):+.2%} (vs 槓桿)")
    k2.metric("CAGR", f"{stats_strat[2]:.2%}", f"{(stats_strat[2]-stats_lev_bh[2]):+.2%} (vs 槓桿)")
    k3.metric("波動率", f"{stats_strat[5]:.2%}", f"{(stats_strat[5]-stats_lev_bh[5]):+.2%} (vs 槓桿)", delta_color="inverse")
    k4.metric("最大回撤", f"{stats_strat[4]:.2%}", f"{(stats_strat[4]-stats_lev_bh[4]):+.2%} (vs 槓桿)", delta_color="inverse")

    # --- 6. 績效深度對照表 (HTML 渲染) ---
    st.markdown("### 📊 策略績效深度對照")
    
    metrics = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio"]
    
    # 建立表格數據
    df_compare = pd.DataFrame({
        "指標": metrics,
        "策略 (國安加碼)": stats_strat,
        f"{lev_symbol} B&H": stats_lev_bh,
        f"{base_symbol} B&H": stats_base_bh
    })

    # 生成 HTML 表格 (復刻截圖樣式)
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
                <th>{lev_symbol}<br><small>策略 (國安加碼)</small></th>
                <th>{lev_symbol}<br><small>Buy & Hold</small></th>
                <th>{base_symbol}<br><small>Buy & Hold</small></th>
            </tr>
        </thead>
        <tbody>
    """
    
    for i, name in enumerate(metrics):
        v_s, v_l, v_b = stats_strat[i], stats_lev_bh[i], stats_base_bh[i]
        
        # 格式化數值
        if "資產" in name: f_s, f_l, f_b = f"{v_s:,.0f} 元", f"{v_l:,.0f} 元", f"{v_b:,.0f} 元"
        elif any(x in name for x in ["率", "報酬", "MDD", "波動"]): f_s, f_l, f_b = f"{v_s:.2%}", f"{v_l:.2%}", f"{v_b:.2%}"
        else: f_s, f_l, f_b = f"{v_s:.2f}", f"{v_l:.2f}", f"{v_b:.2f}"
        
        # 判定誰是贏家 (MDD 與 波動率 越小越好)
        if name in ["最大回撤 (MDD)", "年化波動"]:
            best = min(v_s, v_l, v_b)
        else:
            best = max(v_s, v_l, v_b)
            
        def get_cls(val): return 'class="winner"' if val == best else ''
        def get_trophy(val): return '<span class="trophy">🏆</span>' if val == best else ''

        html += f"""
            <tr>
                <td class="label-col">{name}</td>
                <td {get_cls(v_s)}>{f_s} {get_trophy(v_s)}</td>
                <td {get_cls(v_l)}>{f_l} {get_trophy(v_l)}</td>
                <td {get_cls(v_b)}>{f_b} {get_trophy(v_b)}</td>
            </tr>
        """
    
    st.write(html + "</tbody></table>", unsafe_allow_html=True)

    # --- 7. 淨值走勢圖 ---
    st.markdown("### 📈 累積淨值比較")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"]*capital, name="國安加碼策略", line=dict(color="#FF4B4B", width=3)))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_Lev_BH"]*capital, name="正2 Buy & Hold", line=dict(color="#94A3B8", width=1.5, dash='dash')))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_Base_BH"]*capital, name="原型 Buy & Hold", line=dict(color="#CBD5E0", width=1.5)))
    
    fig.update_layout(template="plotly_white", hovermode="x unified", height=500, margin=dict(l=0,r=0,t=20,b=0))
    st.plotly_chart(fig, use_container_width=True)

# --- 8. 頁尾免責聲明 ---
st.markdown("---")
st.caption(f"© 2026 倉鼠人生實驗室 | 數據最後更新日期：2026-01-12 | 策略結果僅供研究參考")
