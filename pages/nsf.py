###############################################################
# app_nsf.py — 國安基金：平時 0050，護盤加碼 正2 專業版
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
    page_title="國安基金槓桿加碼回測系統", 
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

# --- Sidebar 導覽 ---
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

###############################################################
# 2. 參數與資料定義
###############################################################

# 國安基金歷史進退場日期 (更新至 2026/01/12)
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
# 3. UI 佈局 (參照您的截圖)
###############################################################

st.title("🏛️ 國安基金跟單：加碼正2回測系統")

# 第一列：標的選擇
c1, c2 = st.columns(2)
with c1:
    base_label = st.selectbox("原型 ETF (訊號來源)", ["0050 元大台灣50", "006208 富邦台50"])
    base_symbol = "0050.TW" if "0050" in base_label else "006208.TW"
with c2:
    lev_label = st.selectbox("槓桿 ETF (實際進出場標的)", list(LEV_OPTIONS.keys()))
    lev_symbol = LEV_OPTIONS[lev_label]

# 預載資料以取得可回測日期範圍
df_b_raw = load_csv(base_symbol)
df_l_raw = load_csv(lev_symbol)

if df_b_raw.empty or df_l_raw.empty:
    st.error("⚠️ 找不到 CSV 資料，請確認 data 資料夾檔案是否存在。")
    st.stop()

common_start = max(df_b_raw.index.min(), df_l_raw.index.min())
common_end = min(df_b_raw.index.max(), df_l_raw.index.max())

# 區間提示
st.info(f"📌 可回測區間：{common_start.date()} ~ {common_end.date()}")

# 第二列：回測參數
c3, c4, c5, c6 = st.columns(4)
with c3:
    start_d = st.date_input("開始日期", value=date(2021, 1, 13), min_value=common_start.date(), max_value=common_end.date())
with c4:
    end_d = st.date_input("結束日期", value=common_end.date(), min_value=common_start.date(), max_value=common_end.date())
with c5:
    capital = st.number_input("投入本金 (元)", value=100000, step=10000)
with c6:
    sma_period = st.number_input("均線週期 (SMA)", value=200, step=10) # 預留 UI 介面

###############################################################
# 4. 回測核心邏輯
###############################################################

if st.button("開始回測 🚀", use_container_width=True):
    # 資料準備與切片
    df = pd.merge(df_b_raw, df_l_raw, left_index=True, right_index=True, suffixes=('_Base', '_Lev'))
    df = df.loc[str(start_d):str(end_d)].copy()
    
    df["Ret_Base"] = df["Close_Base"].pct_change().fillna(0)
    df["Ret_Lev"] = df["Close_Lev"].pct_change().fillna(0)
    
    # 標記國安基金進場區間
    df["In_NSF"] = 0
    for s, e in NSF_DATES:
        df.loc[s:e, "In_NSF"] = 1
    
    # 計算策略報酬率 (1 = 槓桿, 0 = 原型)
    df["Strat_Ret"] = np.where(df["In_NSF"] == 1, df["Ret_Lev"], df["Ret_Base"])
    
    # 計算淨值累積
    df["Eq_Strat"] = (1 + df["Strat_Ret"]).cumprod()
    df["Eq_Lev_BH"] = (1 + df["Ret_Lev"]).cumprod()
    df["Eq_Base_BH"] = (1 + df["Ret_Base"]).cumprod()

    # --- 5. 數據指標卡片 ---
    def get_metrics(eq, ret):
        final_val = eq.iloc[-1]
        total_ret = final_val - 1
        days = (eq.index[-1] - eq.index[0]).days
        cagr = (final_val)**(365/days) - 1 if final_val > 0 else 0
        mdd = (eq / eq.cummax() - 1).min()
        vol = ret.std() * np.sqrt(252)
        sharpe = (ret.mean() / ret.std() * np.sqrt(252)) if ret.std() != 0 else 0
        # Sortino Ratio
        down_ret = ret[ret < 0]
        sortino = (ret.mean() * 252) / (down_ret.std() * np.sqrt(252)) if not down_ret.empty else 0
        return [final_val * capital, total_ret, cagr, mdd, vol, sharpe, sortino]

    m_strat = get_metrics(df["Eq_Strat"], df["Strat_Ret"])
    m_lev = get_metrics(df["Eq_Lev_BH"], df["Ret_Lev"])
    m_base = get_metrics(df["Eq_Base_BH"], df["Ret_Base"])

    # 顯示頂部四張統計卡片
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("期末資產", f"{m_strat[0]:,.0f} 元", f"{((m_strat[0]/m_lev[0])-1):+.2%} (vs 槓桿)")
    k2.metric("CAGR", f"{m_strat[2]:.2%}", f"{(m_strat[2]-m_lev[2]):+.2%} (vs 槓桿)")
    k3.metric("波動率", f"{m_strat[4]:.2%}", f"{(m_strat[4]-m_lev[4]):+.2%} (vs 槓桿)", delta_color="inverse")
    k4.metric("最大回撤", f"{m_strat[3]:.2%}", f"{(m_strat[3]-m_lev[3]):+.2%} (vs 槓桿)", delta_color="inverse")

    # --- 6. 績效深度比較表 ---
    st.markdown("### 📊 策略績效深度對照")
    
    metrics_list = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio"]
    
    def calc_calmar(cagr, mdd): return abs(cagr / mdd) if mdd != 0 else 0

    # 組合三方數據
    table_data = []
    for i, name in enumerate(metrics_list):
        if name == "Calmar Ratio":
            v_s, v_l, v_b = calc_calmar(m_strat[2], m_strat[3]), calc_calmar(m_lev[2], m_lev[3]), calc_calmar(m_base[2], m_base[3])
        else:
            idx = i if i < 3 else i - 1
            v_s, v_l, v_b = m_strat[idx], m_lev[idx], m_base[idx]
        table_data.append([name, v_s, v_l, v_b])

    # HTML/CSS 表格渲染
    html_code = f"""
    <style>
        .m-table {{ width:100%; border-collapse: collapse; font-family: sans-serif; font-size: 15px; margin-top: 10px; }}
        .m-table th {{ background-color: #f8fafc; padding: 12px; text-align: center; border-bottom: 2px solid #e2e8f0; color: #64748b; font-weight: 600; }}
        .m-table td {{ padding: 12px; text-align: center; border-bottom: 1px solid #f1f5f9; color: #334155; }}
        .label-col {{ text-align: left !important; font-weight: 500; background-color: #fcfcfc; }}
        .winner {{ color: #d97706; font-weight: bold; }}
        .trophy {{ color: #fbbf24; margin-left: 4px; }}
    </style>
    <table class="m-table">
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
    
    for row in table_data:
        name, s, l, b = row
        # 格式化數值
        if "資產" in name: fs, fl, fb = f"{s:,.0f} 元", f"{l:,.0f} 元", f"{b:,.0f} 元"
        elif any(x in name for x in ["率", "報酬", "MDD", "波動"]): fs, fl, fb = f"{s:.2%}", f"{l:.2%}", f"{b:.2%}"
        else: fs, fl, fb = f"{s:.2f}", f"{l:.2f}", f"{b:.2f}"
        
        # 贏家判斷邏輯
        best_val = min(s, l, b) if name in ["最大回撤 (MDD)", "年化波動"] else max(s, l, b)
        
        def highlight(v): return 'class="winner"' if v == best_val else ''
        def add_trophy(v): return '<span class="trophy">🏆</span>' if v == best_val else ''

        html_code += f"""
            <tr>
                <td class="label-col">{name}</td>
                <td {highlight(s)}>{fs} {add_trophy(s)}</td>
                <td {highlight(l)}>{fl} {add_trophy(l)}</td>
                <td {highlight(b)}>{fb} {add_trophy(b)}</td>
            </tr>
        """
    
    st.write(html_code + "</tbody></table>", unsafe_allow_html=True)

    # --- 7. 淨值走勢圖 ---
    st.markdown("### 📈 累積淨值走勢圖")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Eq_Strat"]*capital, name="國安加碼策略", line=dict(color="#FF4B4B", width=3)))
    fig.add_trace(go.Scatter(x=df.index, y=df["Eq_Lev_BH"]*capital, name="正2 Buy & Hold", line=dict(color="#94A3B8", width=1.5, dash='dash')))
    fig.add_trace(go.Scatter(x=df.index, y=df["Eq_Base_BH"]*capital, name="原型 Buy & Hold", line=dict(color="#CBD5E0", width=1.5)))
    
    fig.update_layout(template="plotly_white", hovermode="x unified", height=500, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig, use_container_width=True)

# --- Footer ---
st.markdown("---")
st.caption(f"© 2026 倉鼠人生實驗室 | 鼠叔專屬回測系統 | 當前時間：{date.today()}")
