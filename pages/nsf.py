###############################################################
# app_nsf.py — 國安基金加碼系統 (修正 HTML 渲染與加入買賣點)
###############################################################

import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path
import sys
from datetime import date

# 1. 頁面與認證
st.set_page_config(page_title="國安基金槓桿回測系統", page_icon="🏛️", layout="wide")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except ImportError: pass 

# 2. 參數定義
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

# 3. UI 佈局
st.title("🏛️ 國安基金跟單：加碼正2策略回測")

c1, c2 = st.columns(2)
with c1:
    base_label = st.selectbox("原型 ETF（訊號來源）", ["0050 元大台灣50", "006208 富邦台50"])
    base_symbol = "0050.TW" if "0050" in base_label else "006208.TW"
with c2:
    lev_label = st.selectbox("槓桿 ETF（實際進出場標的）", list(LEV_OPTIONS.keys()))
    lev_symbol = LEV_OPTIONS[lev_label]

df_b_raw = load_csv(base_symbol)
df_l_raw = load_csv(lev_symbol)

if df_b_raw.empty or df_l_raw.empty:
    st.error("⚠️ 找不到 CSV 資料，請確認 data 資料夾檔案是否存在。"); st.stop()

common_start = max(df_b_raw.index.min(), df_l_raw.index.min())
common_end = min(df_b_raw.index.max(), df_l_raw.index.max())

st.info(f"📌 可回測區間：{common_start.date()} ~ {common_end.date()}")

c3, c4, c5, c6 = st.columns(4)
with c3:
    start_d = st.date_input("開始日期", value=date(2021, 1, 13), min_value=common_start.date(), max_value=common_end.date())
with c4:
    end_d = st.date_input("結束日期", value=common_end.date(), min_value=common_start.date(), max_value=common_end.date())
with c5:
    capital = st.number_input("投入本本金（元）", value=100000, step=10000)
with c6:
    sma_period = st.number_input("均線週期 (SMA)", value=200, step=10)

# 4. 回測運算
if st.button("開始回測 🚀", use_container_width=True):
    df = pd.merge(df_b_raw, df_l_raw, left_index=True, right_index=True, suffixes=('_Base', '_Lev'))
    df = df.loc[str(start_d):str(end_d)].copy()
    
    df["Ret_Base"] = df["Close_Base"].pct_change().fillna(0)
    df["Ret_Lev"] = df["Close_Lev"].pct_change().fillna(0)
    
    df["In_NSF"] = 0
    for s, e in NSF_DATES:
        df.loc[s:e, "In_NSF"] = 1
    
    # 策略：護盤買正2，其餘買原型
    df["Strat_Ret"] = np.where(df["In_NSF"] == 1, df["Ret_Lev"], df["Ret_Base"])
    df["Eq_Strat"] = (1 + df["Strat_Ret"]).cumprod()
    df["Eq_Lev_BH"] = (1 + df["Ret_Lev"]).cumprod()
    df["Eq_Base_BH"] = (1 + df["Ret_Base"]).cumprod()
    
    # 判定進退場信號（用於繪製標記）
    df["Signal"] = df["In_NSF"].diff()

    # --- 績效指標計算 ---
    def get_stats(eq, ret):
        final = eq.iloc[-1]
        total = final - 1
        days = (eq.index[-1] - eq.index[0]).days
        cagr = (final)**(365/days) - 1 if final > 0 else 0
        mdd = (eq / eq.cummax() - 1).min()
        vol = ret.std() * np.sqrt(252)
        sharpe = (ret.mean() / ret.std() * np.sqrt(252)) if ret.std() != 0 else 0
        down_ret = ret[ret < 0]
        sortino = (ret.mean() * 252) / (down_ret.std() * np.sqrt(252)) if not down_ret.empty else 0
        calmar = abs(cagr / mdd) if mdd != 0 else 0
        return [final * capital, total, cagr, calmar, mdd, vol, sharpe, sortino]

    s_strat = get_stats(df["Eq_Strat"], df["Strat_Ret"])
    s_lev = get_stats(df["Eq_Lev_BH"], df["Ret_Lev"])
    s_base = get_stats(df["Eq_Base_BH"], df["Ret_Base"])

    # 5. 指標卡片
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("期末資產", f"{s_strat[0]:,.0f} 元", f"{((s_strat[0]/s_lev[0])-1):+.2%} (vs 槓桿)")
    k2.metric("CAGR", f"{s_strat[2]:.2%}", f"{(s_strat[2]-s_lev[2]):+.2%} (vs 槓桿)")
    k3.metric("波動率", f"{s_strat[5]:.2%}", f"{(s_strat[5]-s_lev[5]):+.2%} (vs 槓桿)", delta_color="inverse")
    k4.metric("最大回撤", f"{s_strat[4]:.2%}", f"{(s_strat[4]-s_lev[4]):+.2%} (vs 槓桿)", delta_color="inverse")

    # 6. HTML 表格渲染 (修正版)
    st.markdown("### 📊 策略績效深度對照")
    m_names = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio"]
    
    html = """
    <style>
        .p-table { width:100%; border-collapse: collapse; font-family: sans-serif; font-size: 15px; margin-top: 10px; }
        .p-table th { background-color: #f8fafc; padding: 12px; text-align: center; border-bottom: 2px solid #e2e8f0; color: #64748b; }
        .p-table td { padding: 12px; text-align: center; border-bottom: 1px solid #f1f5f9; }
        .label-col { text-align: left !important; font-weight: 500; background-color: #fcfcfc; }
        .winner { color: #d97706; font-weight: bold; }
        .trophy { color: #fbbf24; margin-left: 5px; }
    </style>
    <table class="p-table">
        <thead>
            <tr>
                <th class="label-col">指標</th>
                <th>策略 (國安加碼)</th>
                <th>Buy & Hold (正2)</th>
                <th>Buy & Hold (原型)</th>
            </tr>
        </thead>
        <tbody>
    """
    
    for i, name in enumerate(m_names):
        v_s, v_l, v_b = s_strat[i], s_lev[i], s_base[i]
        best = min(v_s, v_l, v_b) if name in ["最大回撤 (MDD)", "年化波動"] else max(v_s, v_l, v_b)
        
        def fmt(v, n):
            if "資產" in n: return f"{v:,.0f} 元"
            if any(x in n for x in ["率", "報酬", "MDD", "波動", "CAGR"]): return f"{v:.2%}"
            return f"{v:.2f}"

        def get_td(val, best_val):
            cls = ' class="winner"' if val == best_val else ''
            t = ' <span class="trophy">🏆</span>' if val == best_val else ''
            return f'<td{cls}>{fmt(val, name)}{t}</td>'

        html += f"<tr><td class='label-col'>{name}</td>{get_td(v_s, best)}{get_td(v_l, best)}{get_td(v_b, best)}</tr>"
    
    html += "</tbody></table>"
    st.markdown(html, unsafe_allow_html=True)

    # 7. 淨值走勢圖 (含國安基金進退場點)
    st.markdown("### 📈 累積淨值比較與進退場訊號")
    fig = go.Figure()
    
    # 淨值線
    fig.add_trace(go.Scatter(x=df.index, y=df["Eq_Strat"]*capital, name="策略 (加碼正2)", line=dict(color="#FF4B4B", width=3)))
    fig.add_trace(go.Scatter(x=df.index, y=df["Eq_Lev_BH"]*capital, name="正2 持有", line=dict(color="#94A3B8", width=1.5, dash='dash')))
    fig.add_trace(go.Scatter(x=df.index, y=df["Eq_Base_BH"]*capital, name="原型 持有", line=dict(color="#CBD5E0", width=1.5)))
    
    # 標記：國安進場 (換成正2)
    entry_pts = df[df["Signal"] == 1]
    fig.add_trace(go.Scatter(
        x=entry_pts.index, y=df.loc[entry_pts.index, "Eq_Strat"]*capital,
        mode="markers+text", name="國安進場 (切換正2)",
        text=["進場"]*len(entry_pts), textposition="top center",
        marker=dict(symbol="triangle-up", size=12, color="#059669")
    ))
    
    # 標記：國安退場 (切回原型)
    exit_pts = df[df["Signal"] == -1]
    fig.add_trace(go.Scatter(
        x=exit_pts.index, y=df.loc[exit_pts.index, "Eq_Strat"]*capital,
        mode="markers+text", name="國安退場 (切回原型)",
        text=["退場"]*len(exit_pts), textposition="bottom center",
        marker=dict(symbol="triangle-down", size=12, color="#D97706")
    ))

    fig.update_layout(template="plotly_white", hovermode="x unified", height=600)
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.caption("© 2026 倉鼠人生實驗室 Hamr-Lab.com")
