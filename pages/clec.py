###############################################################
# app.py — Asset Allocation 433 (CLEC Strategy)
# 固定比例配置 + 年度再平衡
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
    page_title="資產配置回測 (433策略)",
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
    "<h1 style='margin-bottom:0.5em;'>⚖️ 資產配置再平衡策略 (433 / 442)</h1>",
    unsafe_allow_html=True,
)

st.info(
    """
    **策略邏輯：**
    1. 設定 **原型 ETF**、**槓桿 ETF** 與 **現金** 的目標比例 (例如 40%:30%:30%)。
    2. **Buy & Hold**：平時持有不動。
    3. **年度再平衡 (Rebalance)**：每年第一個交易日，將資產比例還原至初始設定 (賣出漲多的，買進跌深的)。
    """
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
# UI 輸入
###############################################################

col1, col2 = st.columns(2)
with col1:
    base_label = st.selectbox("原型 ETF", list(BASE_ETFS.keys()))
    base_symbol = BASE_ETFS[base_label]
with col2:
    lev_label = st.selectbox("槓桿 ETF", list(LEV_ETFS.keys()))
    lev_symbol = LEV_ETFS[lev_label]

s_min, s_max = get_full_range_from_csv(base_symbol, lev_symbol)

# 基本參數
col3, col4, col5 = st.columns(3)
with col3:
    start = st.date_input(
        "開始日期",
        value=max(s_min, s_max - dt.timedelta(days=10 * 365)), # 預設拉長一點看長期效果
        min_value=s_min, max_value=s_max,
    )
with col4:
    end = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
with col5:
    capital = st.number_input("投入本金（元）", 1000, 100_000_000, 1_000_000, step=10_000)

# --- 資產配置設定 ---
st.write("---")
st.write("### ⚙️ 資產配置比例設定")

col_w1, col_w2, col_w3 = st.columns(3)

with col_w1:
    w_base_pct = st.number_input(f"原型 ETF ({base_label}) %", min_value=0, max_value=100, value=40, step=5)

with col_w2:
    w_lev_pct = st.number_input(f"槓桿 ETF ({lev_label}) %", min_value=0, max_value=100, value=30, step=5)

# 自動計算現金比例
w_cash_pct = 100 - w_base_pct - w_lev_pct

with col_w3:
    st.metric("現金 (Cash) %", f"{w_cash_pct}%")
    if w_cash_pct < 0:
        st.error("⚠️ 比例總和超過 100%，請修正！")

rebalance_freq = st.radio("再平衡頻率", ["每年 (Annually)"], index=0, horizontal=True)


###############################################################
# 主程式開始
###############################################################

if st.button("開始回測 🚀"):

    if w_cash_pct < 0:
        st.error("❌ 配置比例錯誤：總和超過 100%")
        st.stop()

    with st.spinner("計算中..."):
        df_base_raw = load_csv(base_symbol)
        df_lev_raw = load_csv(lev_symbol)

    if df_base_raw.empty or df_lev_raw.empty:
        st.error("⚠️ CSV 資料讀取失敗，請確認 data/*.csv 是否存在")
        st.stop()

    # 1. 資料對齊
    df_base_raw = df_base_raw.loc[start:end]
    df_lev_raw = df_lev_raw.loc[start:end]

    df = pd.DataFrame(index=df_base_raw.index)
    df["Price_base"] = df_base_raw["Price"]
    df = df.join(df_lev_raw["Price"].rename("Price_lev"), how="inner")
    df = df.sort_index()

    if df.empty:
        st.error("⚠️ 有效回測區間不足")
        st.stop()

    # 計算一般 Buy & Hold 報酬 (用於比較)
    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)
    
    # 2. 回測邏輯：固定比例 + 再平衡
    
    # 權重小數點化
    target_w_base = w_base_pct / 100.0
    target_w_lev = w_lev_pct / 100.0
    target_w_cash = w_cash_pct / 100.0

    # 紀錄序列
    equity_curve = []
    
    # 資產價值紀錄 (用於堆疊圖)
    val_base_list = []
    val_lev_list = []
    val_cash_list = []
    
    rebalance_dates = []

    # 初始進場
    current_cash = capital * target_w_cash
    
    # 計算初始股數 (無條件捨去取整，雖模擬 fractional shares 也可以，但整數較直觀)
    # 這裡為了精確計算淨值，先使用浮點數股數模擬
    shares_base = (capital * target_w_base) / df["Price_base"].iloc[0]
    shares_lev = (capital * target_w_lev) / df["Price_lev"].iloc[0]

    last_year = df.index[0].year

    for date, row in df.iterrows():
        p_base = row["Price_base"]
        p_lev = row["Price_lev"]
        
        # 1. 計算當前總資產
        val_base = shares_base * p_base
        val_lev = shares_lev * p_lev
        total_equity = val_base + val_lev + current_cash
        
        # 2. 判斷是否為「新的一年」(再平衡觸發點)
        # 邏輯：當前年份 != 上一筆年份，代表跨年了，今天是該年第一天
        is_rebalance_day = False
        if date.year != last_year:
            is_rebalance_day = True
            last_year = date.year
            rebalance_dates.append(date)

        # 3. 執行再平衡 (如果是再平衡日)
        if is_rebalance_day:
            # 重新計算目標金額
            new_val_base = total_equity * target_w_base
            new_val_lev = total_equity * target_w_lev
            new_val_cash = total_equity * target_w_cash
            
            # 更新股數與現金
            shares_base = new_val_base / p_base
            shares_lev = new_val_lev / p_lev
            current_cash = new_val_cash
            
            # 更新當下資產價值 (其實總額不變，只是分配變了)
            val_base = new_val_base
            val_lev = new_val_lev

        # 4. 紀錄數據
        equity_curve.append(total_equity)
        val_base_list.append(val_base)
        val_lev_list.append(val_lev)
        val_cash_list.append(current_cash)

    # 寫回 DataFrame
    df["Equity_Strategy"] = equity_curve
    df["Val_Base"] = val_base_list
    df["Val_Lev"] = val_lev_list
    df["Val_Cash"] = val_cash_list
    
    df["Return_Strategy"] = df["Equity_Strategy"].pct_change().fillna(0)
    
    # 建立基準 (Benchmarks)
    df["Equity_BH_Base"] = capital * (1 + df["Return_base"]).cumprod()
    df["Equity_BH_Lev"] = capital * (1 + df["Return_lev"]).cumprod()

    # ###############################################################
    # 指標計算
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

    # 策略
    eq_st_final, final_ret_st, cagr_st, mdd_st, vol_st, sharpe_st, sortino_st, calmar_st = calc_core(
        df["Equity_Strategy"], df["Return_Strategy"]
    )
    # 原型 BH
    eq_base_final, final_ret_base, cagr_base, mdd_base, vol_base, sharpe_base, sortino_base, calmar_base = calc_core(
        df["Equity_BH_Base"], df["Return_base"]
    )
    # 槓桿 BH
    eq_lev_final, final_ret_lev, cagr_lev, mdd_lev, vol_lev, sharpe_lev, sortino_lev, calmar_lev = calc_core(
        df["Equity_BH_Lev"], df["Return_lev"]
    )

    # ###############################################################
    # 圖表區
    # ###############################################################

    # 1. 資金曲線比較
    st.markdown("### 📈 資金曲線比較")
    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"], name=f"配置 ({w_base_pct}/{w_lev_pct}/{w_cash_pct})", line=dict(color="#636EFA", width=3)))
    fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Lev"], name=f"{lev_label} Buy&Hold", line=dict(color="#EF553B", width=1.5, dash="dot")))
    fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Base"], name=f"{base_label} Buy&Hold", line=dict(color="#00CC96", width=1.5, dash="dot")))
    
    # 標記再平衡點
    if rebalance_dates:
        # 取出再平衡日期的淨值
        rebal_y = df.loc[rebalance_dates, "Equity_Strategy"]
        fig_eq.add_trace(go.Scatter(
            x=rebalance_dates, y=rebal_y, 
            mode="markers", name="再平衡日",
            marker=dict(symbol="diamond", size=8, color="orange")
        ))

    fig_eq.update_layout(template="plotly_white", height=450, hovermode="x unified", yaxis_title="總資產 (元)")
    st.plotly_chart(fig_eq, use_container_width=True)

    # 2. 資產堆疊圖 (Area Chart)
    st.markdown("### 🍰 資產佔比變化 (堆疊圖)")
    # 計算百分比
    df["Pct_Base"] = df["Val_Base"] / df["Equity_Strategy"]
    df["Pct_Lev"] = df["Val_Lev"] / df["Equity_Strategy"]
    df["Pct_Cash"] = df["Val_Cash"] / df["Equity_Strategy"]

    fig_stack = go.Figure()
    fig_stack.add_trace(go.Scatter(
        x=df.index, y=df["Pct_Base"], mode='lines', stackgroup='one', name=f'原型 ({base_label})',
        line=dict(width=0), fillcolor='rgba(99, 110, 250, 0.6)'
    ))
    fig_stack.add_trace(go.Scatter(
        x=df.index, y=df["Pct_Lev"], mode='lines', stackgroup='one', name=f'槓桿 ({lev_label})',
        line=dict(width=0), fillcolor='rgba(239, 85, 59, 0.6)'
    ))
    fig_stack.add_trace(go.Scatter(
        x=df.index, y=df["Pct_Cash"], mode='lines', stackgroup='one', name='現金 (Cash)',
        line=dict(width=0), fillcolor='rgba(0, 204, 150, 0.4)'
    ))
    fig_stack.update_layout(
        template="plotly_white", height=400, yaxis=dict(tickformat=".0%", title="資產佔比", range=[0, 1]),
        hovermode="x unified"
    )
    st.plotly_chart(fig_stack, use_container_width=True)

    # 3. 回撤圖
    st.markdown("### 📉 下檔風險 (Drawdown)")
    dd_st = (df["Equity_Strategy"] / df["Equity_Strategy"].cummax() - 1) * 100
    dd_lev = (df["Equity_BH_Lev"] / df["Equity_BH_Lev"].cummax() - 1) * 100
    
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(x=df.index, y=dd_st, name="配置策略", fill="tozeroy", line=dict(color="#636EFA")))
    fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lev, name=f"{lev_label} BH", line=dict(color="gray", width=1)))
    fig_dd.update_layout(template="plotly_white", height=350, yaxis_title="回撤 (%)")
    st.plotly_chart(fig_dd, use_container_width=True)

    # ###############################################################
    # 績效表格
    # ###############################################################
    
    st.markdown("### 📊 績效總結")

    metrics_order = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio"]
    
    data_dict = {
        f"<b>配置策略</b><br><span style='font-size:0.8em; opacity:0.7'>{w_base_pct}/{w_lev_pct}/{w_cash_pct}</span>": {
            "期末資產": eq_st_final, "總報酬率": final_ret_st, "CAGR (年化)": cagr_st, "Calmar Ratio": calmar_st,
            "最大回撤 (MDD)": mdd_st, "年化波動": vol_st, "Sharpe Ratio": sharpe_st, "Sortino Ratio": sortino_st
        },
        f"<b>{lev_label}</b><br><span style='font-size:0.8em; opacity:0.7'>Buy & Hold</span>": {
            "期末資產": eq_lev_final, "總報酬率": final_ret_lev, "CAGR (年化)": cagr_lev, "Calmar Ratio": calmar_lev,
            "最大回撤 (MDD)": mdd_lev, "年化波動": vol_lev, "Sharpe Ratio": sharpe_lev, "Sortino Ratio": sortino_lev
        },
        f"<b>{base_label}</b><br><span style='font-size:0.8em; opacity:0.7'>Buy & Hold</span>": {
            "期末資產": eq_base_final, "總報酬率": final_ret_base, "CAGR (年化)": cagr_base, "Calmar Ratio": calmar_base,
            "最大回撤 (MDD)": mdd_base, "年化波動": vol_base, "Sharpe Ratio": sharpe_base, "Sortino Ratio": sortino_base
        }
    }

    df_vertical = pd.DataFrame(data_dict).reindex(metrics_order)
    
    # 樣式定義
    metrics_config = {
        "期末資產":       {"fmt": format_currency, "invert": False},
        "總報酬率":       {"fmt": format_percent,   "invert": False},
        "CAGR (年化)":    {"fmt": format_percent,   "invert": False},
        "Calmar Ratio":   {"fmt": format_number,    "invert": False},
        "最大回撤 (MDD)": {"fmt": format_percent,   "invert": True},
        "年化波動":       {"fmt": format_percent,   "invert": True},
        "Sharpe Ratio":   {"fmt": format_number,    "invert": False},
        "Sortino Ratio":  {"fmt": format_number,    "invert": False},
    }

    # 產生 HTML 表格
    html_code = """
    <style>
        .comparison-table { width: 100%; border-collapse: separate; border-spacing: 0; border-radius: 12px; border: 1px solid var(--secondary-background-color); font-family: 'Noto Sans TC', sans-serif; margin-bottom: 1rem; font-size: 0.95rem; }
        .comparison-table th { background-color: var(--secondary-background-color); color: var(--text-color); padding: 14px; text-align: center; font-weight: 600; border-bottom: 1px solid rgba(128,128,128, 0.1); }
        .comparison-table td.metric-name { font-weight: 500; text-align: left; padding: 12px 16px; width: 25%; font-size: 0.9rem; border-bottom: 1px solid rgba(128,128,128, 0.1); opacity: 0.9; }
        .comparison-table td.data-cell { text-align: center; padding: 12px; border-bottom: 1px solid rgba(128,128,128, 0.1); }
        .comparison-table td.highlight { background-color: rgba(99, 110, 250, 0.05); font-weight: bold; }
        .trophy { margin-left: 6px; }
    </style>
    <table class="comparison-table"><thead><tr><th style="text-align:left; padding-left:16px;">指標</th>
    """
    
    for col in df_vertical.columns:
        html_code += f"<th>{col}</th>"
    html_code += "</tr></thead><tbody>"

    for metric in df_vertical.index:
        cfg = metrics_config.get(metric, {"fmt": format_number, "invert": False})
        
        # 找冠軍
        vals = [v for v in df_vertical.loc[metric].values if isinstance(v, (int, float)) and not pd.isna(v)]
        target = min(vals) if cfg["invert"] and vals else max(vals) if vals else None

        html_code += f"<tr><td class='metric-name'>{metric}</td>"
        
        for i, col in enumerate(df_vertical.columns):
            val = df_vertical.at[metric, col]
            display = cfg["fmt"](val) if isinstance(val, (int, float)) else "—"
            
            is_winner = (target is not None and val == target)
            trophy = " 🏆" if is_winner else ""
            
            hl_class = "highlight" if i == 0 else ""
            html_code += f"<td class='data-cell {hl_class}'>{display}{trophy}</td>"
        
        html_code += "</tr>"
    
    html_code += "</tbody></table>"
    st.write(html_code, unsafe_allow_html=True)

    # ###############################################################
    # 下載
    # ###############################################################
    
    csv_data = df[["Equity_Strategy", "Val_Base", "Val_Lev", "Val_Cash", "Equity_BH_Lev"]].to_csv(index=True).encode('utf-8-sig')
    st.download_button(
        label="📥 下載回測數據 (CSV)",
        data=csv_data,
        file_name=f"Allocation_{w_base_pct}_{w_lev_pct}_{w_cash_pct}.csv",
        mime="text/csv"
    )

    st.markdown("<br><hr>", unsafe_allow_html=True)
    footer_html = """
    <div style="text-align: center; color: gray; font-size: 0.85rem; line-height: 1.6;">
        <p style="font-style: italic;">免責聲明：本工具僅供策略回測研究參考，不構成任何形式之投資建議。投資必定有風險，過去之績效不保證未來表現。</p>
    </div>
    """
    st.markdown(footer_html, unsafe_allow_html=True)
