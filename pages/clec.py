###############################################################
# app.py — Asset Allocation Flexible Rebalance
# 彈性再平衡：年度 + 現金上限 + 現金下限
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go
from pathlib import Path
import sys

###############################################################
# 字型設定
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = [
        "Microsoft JhengHei",
        "PingFang TC",
        "Heiti TC",
    ]
matplotlib.rcParams["axes.unicode_minus"] = False

###############################################################
# Streamlit 頁面設定
###############################################################

st.set_page_config(
    page_title="資產配置回測 (彈性再平衡)",
    page_icon="⚖️",
    layout="wide",
)

# ------------------------------------------------------
# 🔒 驗證守門員
# ------------------------------------------------------
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import auth 
    if not auth.check_password():
        st.stop() 
except ImportError:
    pass 

# ------------------------------------------------------
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

st.markdown(
    "<h1 style='margin-bottom:0.5em;'>⚖️ 資產配置：彈性再平衡策略</h1>",
    unsafe_allow_html=True,
)

###############################################################
# ETF 名稱清單
###############################################################

BASE_ETFS = {
    "0050 元大台灣50": "0050.TW",
    "006208 富邦台50": "006208.TW",
}

LEV_ETFS = {
    "00631L 元大台灣50正2": "00631L.TW",
    "00663L 國泰台灣加權正2": "00663L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW",
    "00685L 群益台灣加權正2": "00685L.TW",
}

DATA_DIR = Path("data")

###############################################################
# 讀取 CSV
###############################################################

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    df["Price"] = df["Close"]
    return df[["Price"]]


def get_full_range_from_csv(base_symbol: str, lev_symbol: str):
    df1 = load_csv(base_symbol)
    df2 = load_csv(lev_symbol)

    if df1.empty or df2.empty:
        return dt.date(2012, 1, 1), dt.date.today()

    start = max(df1.index.min().date(), df2.index.min().date())
    end = min(df1.index.max().date(), df2.index.max().date())
    return start, end

###############################################################
# 工具函式
###############################################################

def calc_metrics(series: pd.Series):
    daily = series.dropna()
    if len(daily) <= 1:
        return np.nan, np.nan, np.nan
    avg = daily.mean()
    std = daily.std()
    downside = daily[daily < 0].std()
    vol = std * np.sqrt(252)
    sharpe = (avg / std) * np.sqrt(252) if std > 0 else np.nan
    sortino = (avg / downside) * np.sqrt(252) if downside > 0 else np.nan
    return vol, sharpe, sortino

def format_currency(v):
    try: return f"{v:,.0f} 元"
    except: return "—"

def format_percent(v, d=2):
    try: return f"{v*100:.{d}f}%"
    except: return "—"

def format_number(v, d=2):
    try: return f"{v:.{d}f}"
    except: return "—"

###############################################################
# UI 輸入區塊
###############################################################

# 1. 選股與時間
col1, col2 = st.columns(2)
with col1:
    base_label = st.selectbox("原型 ETF", list(BASE_ETFS.keys()))
    base_symbol = BASE_ETFS[base_label]
with col2:
    lev_label = st.selectbox("槓桿 ETF", list(LEV_ETFS.keys()))
    lev_symbol = LEV_ETFS[lev_label]

s_min, s_max = get_full_range_from_csv(base_symbol, lev_symbol)

col3, col4, col5 = st.columns(3)
with col3:
    start = st.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=10 * 365)), min_value=s_min, max_value=s_max)
with col4:
    end = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
with col5:
    capital = st.number_input("投入本金（元）", 1000, 100_000_000, 1_000_000, step=10_000)

st.divider()

# 2. 資產配置目標
st.subheader("🎯 資產配置目標")
col_w1, col_w2, col_w3 = st.columns(3)

with col_w1:
    w_base_pct = st.number_input(f"原型 ({base_label}) %", 0, 100, 40, 5)
with col_w2:
    w_lev_pct = st.number_input(f"槓桿 ({lev_label}) %", 0, 100, 30, 5)

w_cash_pct = 100 - w_base_pct - w_lev_pct

with col_w3:
    st.metric("現金 (Cash) 目標 %", f"{w_cash_pct}%")
    if w_cash_pct < 0:
        st.error("⚠️ 比例超過 100%！")

# 3. 再平衡規則 (Rebalance Triggers)
st.subheader("⚙️ 再平衡觸發規則 (多選)")

with st.container(border=True):
    # Rule 1: Annual
    col_r1_a, col_r1_b = st.columns([1, 4])
    with col_r1_a:
        enable_annual = st.checkbox("啟用", value=True, key="chk_annual")
    with col_r1_b:
        st.markdown("**1. 每年定期再平衡** (於每年第一個交易日執行)")

    st.markdown("---")

    # Rule 2: Cash Too Low (Sell Stocks)
    col_r2_a, col_r2_b = st.columns([1, 4])
    with col_r2_a:
        enable_lower = st.checkbox("啟用", value=False, key="chk_lower")
    with col_r2_b:
        c_low_val = st.number_input(
            "2. 當現金「低於」多少 % 時觸發？ (代表股市大漲，停利)", 
            min_value=0.0, max_value=100.0, value=max(0.0, w_cash_pct - 10.0), step=1.0, 
            disabled=not enable_lower
        )
        if enable_lower and c_low_val >= w_cash_pct:
            st.warning(f"⚠️ 邏輯警告：觸發值 ({c_low_val}%) 必須 < 目標值 ({w_cash_pct}%)，否則會無限觸發。")

    st.markdown("---")

    # Rule 3: Cash Too High (Buy Stocks)
    col_r3_a, col_r3_b = st.columns([1, 4])
    with col_r3_a:
        enable_upper = st.checkbox("啟用", value=True, key="chk_upper")
    with col_r3_b:
        c_high_val = st.number_input(
            "3. 當現金「高於」多少 % 時觸發？ (代表股市大跌，加碼)", 
            min_value=0.0, max_value=100.0, value=w_cash_pct + 10.0, step=1.0, 
            disabled=not enable_upper
        )
        if enable_upper and c_high_val <= w_cash_pct:
            st.warning(f"⚠️ 邏輯警告：觸發值 ({c_high_val}%) 必須 > 目標值 ({w_cash_pct}%)，否則會無限觸發。")

###############################################################
# 主程式開始
###############################################################

if st.button("開始回測 🚀", type="primary"):

    if w_cash_pct < 0:
        st.error("❌ 配置比例錯誤：總和超過 100%")
        st.stop()
    
    # 邏輯防呆檢查
    if enable_lower and c_low_val >= w_cash_pct:
        st.error("❌ 無法執行：現金低於觸發值設定錯誤，請修正。")
        st.stop()
    if enable_upper and c_high_val <= w_cash_pct:
        st.error("❌ 無法執行：現金高於觸發值設定錯誤，請修正。")
        st.stop()

    with st.spinner("計算中..."):
        df_base_raw = load_csv(base_symbol)
        df_lev_raw = load_csv(lev_symbol)

    if df_base_raw.empty or df_lev_raw.empty:
        st.error("⚠️ CSV 資料讀取失敗")
        st.stop()

    # 1. 資料對齊
    df_base_raw = df_base_raw.loc[start:end]
    df_lev_raw = df_lev_raw.loc[start:end]
    df = pd.DataFrame(index=df_base_raw.index)
    df["Price_base"] = df_base_raw["Price"]
    df = df.join(df_lev_raw["Price"].rename("Price_lev"), how="inner").sort_index()

    if df.empty:
        st.error("⚠️ 有效回測區間不足")
        st.stop()

    # 基準報酬
    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)
    
    # 2. 回測核心邏輯
    target_w_base = w_base_pct / 100.0
    target_w_lev = w_lev_pct / 100.0
    target_w_cash = w_cash_pct / 100.0

    equity_curve = []
    val_base_list = []
    val_lev_list = []
    val_cash_list = []
    cash_ratio_list = []
    
    # 紀錄事件: {'date': date, 'type': 'Annual'/'High'/'Low', 'equity': val}
    rebalance_events = [] 

    # 初始進場
    current_cash = capital * target_w_cash
    shares_base = (capital * target_w_base) / df["Price_base"].iloc[0]
    shares_lev = (capital * target_w_lev) / df["Price_lev"].iloc[0]
    last_year = df.index[0].year

    for date, row in df.iterrows():
        p_base = row["Price_base"]
        p_lev = row["Price_lev"]
        
        # 1. 計算當前市值
        val_base = shares_base * p_base
        val_lev = shares_lev * p_lev
        total_equity = val_base + val_lev + current_cash
        curr_cash_pct = (current_cash / total_equity) * 100.0
        
        trigger_type = None

        # --- Check Rule 1: Annual ---
        is_new_year = (date.year != last_year)
        if is_new_year:
            last_year = date.year
            if enable_annual:
                trigger_type = "Annual"

        # --- Check Rule 2: Cash Too Low (Profit Take) ---
        # 只有在尚未觸發 Annual 時才檢查，避免重複觸發
        if not trigger_type and enable_lower:
            if curr_cash_pct < c_low_val:
                trigger_type = "LowCash"

        # --- Check Rule 3: Cash Too High (Buy Dip) ---
        if not trigger_type and enable_upper:
            if curr_cash_pct > c_high_val:
                trigger_type = "HighCash"

        # 3. 執行再平衡
        if trigger_type:
            # 還原至目標配置
            new_val_base = total_equity * target_w_base
            new_val_lev = total_equity * target_w_lev
            new_val_cash = total_equity * target_w_cash
            
            shares_base = new_val_base / p_base
            shares_lev = new_val_lev / p_lev
            current_cash = new_val_cash
            
            # 數值更新
            val_base = new_val_base
            val_lev = new_val_lev
            curr_cash_pct = (current_cash / total_equity) * 100.0
            
            rebalance_events.append({
                'date': date,
                'type': trigger_type,
                'equity': total_equity
            })

        # 4. 紀錄
        equity_curve.append(total_equity)
        val_base_list.append(val_base)
        val_lev_list.append(val_lev)
        val_cash_list.append(current_cash)
        cash_ratio_list.append(curr_cash_pct / 100.0)

    # DataFrame 寫入
    df["Equity_Strategy"] = equity_curve
    df["Val_Base"] = val_base_list
    df["Val_Lev"] = val_lev_list
    df["Val_Cash"] = val_cash_list
    df["Return_Strategy"] = df["Equity_Strategy"].pct_change().fillna(0)
    
    df["Equity_BH_Base"] = capital * (1 + df["Return_base"]).cumprod()
    df["Equity_BH_Lev"] = capital * (1 + df["Return_lev"]).cumprod()

    # ###############################################################
    # 指標與圖表
    # ###############################################################

    years_len = (df.index[-1] - df.index[0]).days / 365
    def calc_core(eq, rets):
        final_eq = eq.iloc[-1]
        final_ret = (final_eq / capital) - 1
        cagr = (final_eq / capital)**(1/years_len) - 1 if years_len > 0 else np.nan
        mdd = 1 - (eq / eq.cummax()).min()
        vol, sharpe, sortino = calc_metrics(rets)
        calmar = cagr / mdd if mdd > 0 else np.nan
        return final_eq, final_ret, cagr, mdd, vol, sharpe, sortino, calmar

    eq_st, ret_st, cagr_st, mdd_st, vol_st, sharpe_st, sort_st, cal_st = calc_core(df["Equity_Strategy"], df["Return_Strategy"])
    eq_lev, ret_lev, cagr_lev, mdd_lev, vol_lev, sharpe_lev, sort_lev, cal_lev = calc_core(df["Equity_BH_Lev"], df["Return_lev"])
    eq_base, ret_base, cagr_base, mdd_base, vol_base, sharpe_base, sort_base, cal_base = calc_core(df["Equity_BH_Base"], df["Return_base"])

    # --- Plot 1: 資金曲線 ---
    st.markdown("### 📈 資金曲線與觸發點")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"], name="策略淨值", line=dict(color="#636EFA", width=3)))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Lev"], name=f"{lev_label} BH", line=dict(color="#EF553B", width=1.5, dash="dot")))
    
    # 分類畫出觸發點
    evt_annual = [e for e in rebalance_events if e['type'] == 'Annual']
    evt_high = [e for e in rebalance_events if e['type'] == 'HighCash'] # 股市跌深
    evt_low = [e for e in rebalance_events if e['type'] == 'LowCash']   # 股市大漲

    if evt_annual:
        fig.add_trace(go.Scatter(
            x=[e['date'] for e in evt_annual], y=[e['equity'] for e in evt_annual],
            mode='markers', name='年度再平衡', marker=dict(symbol='circle', size=8, color='orange')
        ))
    if evt_high:
        fig.add_trace(go.Scatter(
            x=[e['date'] for e in evt_high], y=[e['equity'] for e in evt_high],
            mode='markers', name=f'現金過高 (>{c_high_val}%)', marker=dict(symbol='star', size=12, color='red')
        ))
    if evt_low:
        fig.add_trace(go.Scatter(
            x=[e['date'] for e in evt_low], y=[e['equity'] for e in evt_low],
            mode='markers', name=f'現金過低 (<{c_low_val}%)', marker=dict(symbol='triangle-up', size=10, color='green')
        ))

    fig.update_layout(template="plotly_white", height=450, hovermode="x unified", yaxis_title="總資產")
    st.plotly_chart(fig, use_container_width=True)

    # --- Plot 2: 堆疊圖 ---
    st.markdown("### 🍰 資產佔比堆疊圖")
    df["Pct_Base"] = df["Val_Base"] / df["Equity_Strategy"]
    df["Pct_Lev"] = df["Val_Lev"] / df["Equity_Strategy"]
    df["Pct_Cash"] = df["Val_Cash"] / df["Equity_Strategy"]

    fig_stack = go.Figure()
    fig_stack.add_trace(go.Scatter(x=df.index, y=df["Pct_Base"], stackgroup='one', name='原型 ETF', line=dict(width=0), fillcolor='rgba(99, 110, 250, 0.6)'))
    fig_stack.add_trace(go.Scatter(x=df.index, y=df["Pct_Lev"], stackgroup='one', name='槓桿 ETF', line=dict(width=0), fillcolor='rgba(239, 85, 59, 0.6)'))
    fig_stack.add_trace(go.Scatter(x=df.index, y=df["Pct_Cash"], stackgroup='one', name='現金', line=dict(width=0), fillcolor='rgba(0, 204, 150, 0.4)'))
    
    # 畫出上下限輔助線
    if enable_upper:
        fig_stack.add_hline(y=c_high_val/100, line_dash="dash", line_color="red", annotation_text="現金過高(加碼)")
    if enable_lower:
        fig_stack.add_hline(y=c_low_val/100, line_dash="dash", line_color="green", annotation_text="現金過低(停利)")

    fig_stack.update_layout(template="plotly_white", height=400, yaxis=dict(tickformat=".0%", title="佔比", range=[0,1]))
    st.plotly_chart(fig_stack, use_container_width=True)

    # --- 表格 ---
    st.markdown("### 📊 績效比較")
    
    count_annual = len(evt_annual)
    count_high = len(evt_high)
    count_low = len(evt_low)
    total_rebal = len(rebalance_events)
    
    metrics_order = ["期末資產", "總報酬率", "CAGR (年化)", "最大回撤 (MDD)", "Sharpe Ratio", "總再平衡次數"]
    
    data_dict = {
        "自選策略": {
            "期末資產": eq_st, "總報酬率": ret_st, "CAGR (年化)": cagr_st, 
            "最大回撤 (MDD)": mdd_st, "Sharpe Ratio": sharpe_st, "總再平衡次數": total_rebal
        },
        f"{lev_label} (BH)": {
            "期末資產": eq_lev, "總報酬率": ret_lev, "CAGR (年化)": cagr_lev, 
            "最大回撤 (MDD)": mdd_lev, "Sharpe Ratio": sharpe_lev, "總再平衡次數": -1
        },
        f"{base_label} (BH)": {
            "期末資產": eq_base, "總報酬率": ret_base, "CAGR (年化)": cagr_base, 
            "最大回撤 (MDD)": mdd_base, "Sharpe Ratio": sharpe_base, "總再平衡次數": -1
        }
    }
    
    df_res = pd.DataFrame(data_dict).reindex(metrics_order)
    st.dataframe(df_res.style.format({
        "期末資產": "{:,.0f}", "總報酬率": "{:.2%}", "CAGR (年化)": "{:.2%}", 
        "最大回撤 (MDD)": "{:.2%}", "Sharpe Ratio": "{:.2f}", "總再平衡次數": "{:.0f}"
    }))

    st.info(f"🔎 再平衡細節：年度觸發 {count_annual} 次 | 現金過高(加碼) {count_high} 次 | 現金過低(停利) {count_low} 次")

    # CSV 下載
    csv = df[["Equity_Strategy", "Val_Base", "Val_Lev", "Val_Cash"]].to_csv().encode('utf-8-sig')
    st.download_button("📥 下載詳細回測數據", csv, "flex_rebalance.csv", "text/csv")

    st.markdown("<hr><div style='text-align: center; color: gray; font-size: 0.8rem;'>免責聲明：過去績效不代表未來表現。</div>", unsafe_allow_html=True)
