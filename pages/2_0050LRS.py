###############################################################
# app.py — 0050 雙向乖離動態槓桿 (新增乖離率監控分頁)
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
# 1. 環境設定與字型
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="0050 雙向乖離動態槓桿", page_icon="📈", layout="wide")

# 🔒 驗證守門員
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except ImportError: pass 

###############################################################
# 2. 核心計算函數
###############################################################

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

def nz(x, default=0.0): return float(np.nan_to_num(x, nan=default))
def fmt_money(v): return f"{v:,.0f} 元"
def fmt_pct(v, d=2): return f"{v:.{d}%}"
def fmt_num(v, d=2): return f"{v:.{d}f}"
def fmt_int(v): return f"{int(v):,}"

###############################################################
# 3. UI 與 Sidebar
###############################################################

with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050 雙向乖離動態槓桿系統</h1>", unsafe_allow_html=True)

BASE_ETFS = {"0050 元大台灣50": "0050.TW", "006208 富邦台50": "006208.TW"}
LEV_ETFS = {
    "00631L 元大台灣50正2": "00631L.TW", "00663L 國泰台灣加權正2": "00663L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW", "00685L 群益台灣加權正2": "00685L.TW",
}

def load_csv(symbol: str) -> pd.DataFrame:
    path = Path("data") / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index(); df["Price"] = df["Close"]
    return df[["Price"]]

col1, col2 = st.columns(2)
base_label = col1.selectbox("原型 ETF (趨勢訊號源)", list(BASE_ETFS.keys()))
lev_label = col2.selectbox("槓桿 ETF (實際交易標的)", list(LEV_ETFS.keys()))

df1_tmp, df2_tmp = load_csv(BASE_ETFS[base_label]), load_csv(LEV_ETFS[lev_label])
s_min, s_max = max(df1_tmp.index.min().date(), df2_tmp.index.min().date()), min(df1_tmp.index.max().date(), df2_tmp.index.max().date())

col_p1, col_p2, col_p3, col_p4 = st.columns(4)
start = col_p1.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5*365)))
end = col_p2.date_input("結束日期", value=s_max)
capital = col_p3.number_input("投入本金", 1000, 5000000, 100000, step=10000)
sma_window = col_p4.number_input("均線週期 (SMA)", 10, 240, 200, step=10)

st.write("---")
position_mode = st.radio("初始狀態選擇", ["一開局就全倉槓桿 ETF", "空手起跑 (等待下次金叉)"], index=0)

col_set1, col_set2 = st.columns(2)
with col_set1:
    with st.expander("📉 均線下：負乖離 DCA 加碼設定", expanded=True):
        enable_dca = st.toggle("啟用 DCA 加碼", value=True)
        dca_bias_trigger = st.number_input("加碼觸發乖離率 (%)", max_value=0.0, value=-15.0)
        dca_pct = st.number_input("每次加碼資金比例 (%)", 1, 100, 20)
        dca_cooldown = st.slider("加碼冷卻天數 (CD)", 1, 60, 10)
with col_set2:
    with st.expander("🚀 均線上：高位乖離套利減碼設定", expanded=True):
        enable_arb = st.toggle("啟用套利減碼", value=False)
        arb_bias_trigger = st.number_input("減碼觸發乖離率 (%)", min_value=0.0, value=35.0)
        arb_reduce_pct = st.number_input("每次減碼資金比例 (%)", 1, 100, 100)
        arb_cooldown = st.slider("套利冷卻天數 (CD)", 1, 60, 10)

###############################################################
# 4. 回測執行
###############################################################

if st.button("啟動回測引擎 🚀"):
    start_buf = start - dt.timedelta(days=int(sma_window * 2))
    df_base = load_csv(BASE_ETFS[base_label]).loc[start_buf:end]
    df_lev = load_csv(LEV_ETFS[lev_label]).loc[start_buf:end]
    
    if df_base.empty or df_lev.empty: st.error("⚠️ 數據讀取失敗"); st.stop()

    df = pd.DataFrame(index=df_base.index)
    df["Price_base"] = df_base["Price"]
    df = df.join(df_lev["Price"].rename("Price_lev"), how="inner").sort_index()
    df["MA"] = df["Price_base"].rolling(sma_window).mean()
    df["Bias"] = (df["Price_base"] - df["MA"]) / df["MA"]
    df = df.dropna(subset=["MA"]).loc[start:end]
    
    # 策略核心循環 (修正對齊與套利 Bug)
    sigs, pos = [0] * len(df), [0.0] * len(df)
    curr_pos, can_buy = (1.0, True) if "一開局" in position_mode else (0.0, False)
    pos[0], dca_cd, arb_cd = curr_pos, 0, 0

    for i in range(1, len(df)):
        p, m, bias_pct = df["Price_base"].iloc[i], df["MA"].iloc[i], df["Bias"].iloc[i] * 100
        p0, m0 = df["Price_base"].iloc[i-1], df["MA"].iloc[i-1]
        if dca_cd > 0: dca_cd -= 1
        if arb_cd > 0: arb_cd -= 1
        sig = 0

        if p > m:
            if can_buy:
                if p0 <= m0: 
                    curr_pos = 1.0 
                    sig = 1
                if enable_arb and bias_pct >= arb_bias_trigger and arb_cd == 0 and curr_pos > 0:
                    curr_pos = max(0.0, curr_pos - (arb_reduce_pct / 100.0))
                    sig, arb_cd = 3, arb_cooldown
            else: curr_pos = 0.0
            dca_cd = 0
        else:
            can_buy = True 
            if p0 > m0: curr_pos, sig, arb_cd = 0.0, -1, 0
            elif enable_dca and curr_pos < 1.0:
                if bias_pct <= dca_bias_trigger and dca_cd == 0:
                    curr_pos = min(1.0, curr_pos + (dca_pct / 100.0))
                    sig, dca_cd = 2, dca_cooldown
        pos[i], sigs[i] = round(curr_pos, 4), sig

    df["Signal"], df["Position"] = sigs, pos

    # 計算資金曲線與日報酬
    equity_lrs = [1.0]
    for i in range(1, len(df)):
        ret = (df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]) - 1
        equity_lrs.append(equity_lrs[-1] * (1 + (ret * df["Position"].iloc[i-1])))
    
    df["Equity_LRS"] = equity_lrs
    df["Return_LRS"] = df["Equity_LRS"].pct_change().fillna(0)
    df["Equity_BH_Base"] = (df["Price_base"] / df["Price_base"].iloc[0])
    df["Equity_BH_Lev"] = (df["Price_lev"] / df["Price_lev"].iloc[0])
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)
    
    y_len = (df.index[-1] - df.index[0]).days / 365
    sl, sv, sb = get_stats(df["Equity_LRS"], df["Return_LRS"], y_len), \
                 get_stats(df["Equity_BH_Lev"], df["Return_lev"], y_len), \
                 get_stats(df["Equity_BH_Base"], df["Price_base"].pct_change().fillna(0), y_len)

    # ------------------------------------------------------
    # 5. 視覺化：KPI、信號圖
    # ------------------------------------------------------
    st.markdown("""<style>.kpi-card {background: var(--secondary-background-color); border-radius: 16px; padding: 24px; border: 1px solid rgba(128,128,128,0.1); text-align:center;} .kpi-val {font-size:2.2rem; font-weight:900; margin:10px 0;} .delta {color:#21c354; background:#21c3541a; padding:4px 12px; border-radius:12px; font-weight:700;}</style>""", unsafe_allow_html=True)
    kc = st.columns(4)
    kc[0].markdown(f'<div class="kpi-card">期末資產<div class="kpi-val">{fmt_money(sl[0]*capital)}</div><span class="delta">+{ (sl[0]/sv[0]-1):.2%} (vs 槓桿)</span></div>', unsafe_allow_html=True)
    kc[1].markdown(f'<div class="kpi-card">CAGR<div class="kpi-val">{sl[2]:.2%}</div><span class="delta">+{ (sl[2]-sv[2]):.2%}</span></div>', unsafe_allow_html=True)
    kc[2].markdown(f'<div class="kpi-card">年化波動<div class="kpi-val">{sl[4]:.2%}</div></div>', unsafe_allow_html=True)
    kc[3].markdown(f'<div class="kpi-card">最大回撤<div class="kpi-val">{sl[3]:.2%}</div></div>', unsafe_allow_html=True)

    st.markdown("### 📌 策略訊號與執行價格 (雙軸對照)")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name=f"{base_label}(左軸)", line=dict(color="#636EFA")))
    fig.add_trace(go.Scatter(x=df.index, y=df["MA"], name=f"{sma_window} 日 SMA", line=dict(color="#FFA15A")))
    fig.add_trace(go.Scatter(x=df.index, y=df["Price_lev"], name=f"{lev_label}(右軸)", yaxis="y2", line=dict(dash='dot', color="#00CC96"), opacity=0.3))
    
    colors = {1: ("全倉買進", "#00C853", "triangle-up", 12), -1: ("清倉賣出", "#D50000", "triangle-down", 12), 
              2: ("負加碼 DCA", "#2E7D32", "circle", 8), 3: ("套利減碼", "#FF9800", "diamond", 10)}
    for v, (l, c, s, sz) in colors.items():
        pts = df[df["Signal"] == v]
        if not pts.empty: fig.add_trace(go.Scatter(x=pts.index, y=pts["Price_base"], mode="markers", name=l, marker=dict(color=c, size=sz, symbol=s)))
    fig.update_layout(template="plotly_white", height=500, yaxis2=dict(overlaying="y", side="right"), hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # ------------------------------------------------------
    # 6. 分析分頁 (新增乖離率監控分頁)
    # ------------------------------------------------------
    st.markdown("### 📊 深度解析")
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["資金曲線", "回撤比較", "風險雷達", "日報酬分佈", "乖離率與股價"])
    
    with tab1:
        fe = go.Figure()
        fe.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Base"]-1, name="原型BH"))
        fe.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Lev"]-1, name="槓桿BH"))
        fe.add_trace(go.Scatter(x=df.index, y=df["Equity_LRS"]-1, name="雙向乖離槓桿", line=dict(width=3, color="#00D494")))
        fe.update_layout(template="plotly_white", yaxis=dict(tickformat=".0%"), height=450); st.plotly_chart(fe, use_container_width=True)
    
    with tab2:
        fd = go.Figure()
        fd.add_trace(go.Scatter(x=df.index, y=(df["Equity_LRS"]/df["Equity_LRS"].cummax()-1)*100, name="本策略", fill='tozeroy', line=dict(color='red')))
        fd.update_layout(template="plotly_white", height=450, title="最大回撤曲線 (%)"); st.plotly_chart(fd, use_container_width=True)
    
    with tab3:
        cat = ["CAGR", "Sharpe", "Sortino", "-MDD", "波動率(反)"]
        r_l = [nz(sl[2]), nz(sl[5]), nz(sl[6]), nz(-sl[3]), nz(-sl[4])]
        fr = go.Figure(); fr.add_trace(go.Scatterpolar(r=r_l, theta=cat, fill='toself', name='動態槓桿', marker_color="#00D494"))
        fr.update_layout(polar=dict(radialaxis=dict(visible=True)), height=450); st.plotly_chart(fr, use_container_width=True)
    
    with tab4:
        fh = go.Figure()
        fh.add_trace(go.Histogram(x=df["Return_LRS"]*100, name="本策略", marker_color="#00D494", opacity=0.7))
        fh.add_trace(go.Histogram(x=df["Return_lev"]*100, name="槓桿BH", opacity=0.4))
        fh.update_layout(barmode="overlay", template="plotly_white", height=450, title="日報酬率分佈 (%)"); st.plotly_chart(fh, use_container_width=True)

    # --- 新增分頁內容 ---
    with tab5:
        st.markdown("#### 🔍 乖離率監控走勢圖")
        fb = go.Figure()
        
        # 1. 繪製乖離率走勢 (左軸)
        fb.add_trace(go.Scatter(
            x=df.index, y=df["Bias"]*100, name="乖離率 (%)", 
            line=dict(color="#AB63FA", width=2), fill='tozeroy', fillcolor='rgba(171, 99, 250, 0.1)'
        ))
        
        # 2. 繪製參考橫線 (左軸)
        if enable_dca:
            fb.add_hline(y=dca_bias_trigger, line_dash="dash", line_color="green", annotation_text=f"加碼觸發 ({dca_bias_trigger}%)")
        if enable_arb:
            fb.add_hline(y=arb_bias_trigger, line_dash="dash", line_color="orange", annotation_text=f"套利觸發 ({arb_bias_trigger}%)")
        fb.add_hline(y=0, line_color="gray", opacity=0.5)

        # 3. 繪製股價走勢 (右軸)
        fb.add_trace(go.Scatter(
            x=df.index, y=df["Price_lev"], name=f"{lev_label} 股價 (右軸)", 
            yaxis="y2", line=dict(color="#00CC96", width=1.5)
        ))

        fb.update_layout(
            template="plotly_white", height=500,
            hovermode="x unified",
            yaxis=dict(title="乖離率 (%)", side="left", showgrid=True),
            yaxis2=dict(title=f"{lev_label} 股價", side="right", overlaying="y", showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fb, use_container_width=True)

    # ------------------------------------------------------
    # 7. 策略績效總表
    # ------------------------------------------------------
    st.markdown("### 🏆 策略績效總表")
    metrics = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "交易次數"]
    dt_table = {
        f"<b>{lev_label}</b><br>雙向乖離": [sl[0]*capital, sl[1], sl[2], sl[7], sl[3], sl[4], sl[5], (df["Signal"]!=0).sum()],
        f"<b>{lev_label}</b><br>Buy & Hold": [sv[0]*capital, sv[1], sv[2], sv[7], sv[3], sv[4], sv[5], 0],
        f"<b>{base_label}</b><br>Buy & Hold": [sb[0]*capital, sb[1], sb[2], sb[7], sb[3], sb[4], sb[5], 0]
    }
    df_v = pd.DataFrame(dt_table, index=metrics)
    
    html = '<style>.ctable {width:100%; border-collapse:separate; border-spacing:0; border-radius:12px; border:1px solid rgba(128,128,128,0.1); overflow:hidden;} .ctable th {background:var(--secondary-background-color); padding:15px; text-align:center;} .ctable td {padding:12px; text-align:center; border-bottom:1px solid rgba(128,128,128,0.05);} .mname {text-align:left !important; background:var(--secondary-background-color); font-weight:500;}</style>'
    html += '<table class="ctable"><thead><tr><th style="text-align:left">指標</th>'
    for col in df_v.columns: html += f'<th>{col}</th>'
    html += '</tr></thead><tbody>'
    for m in metrics:
        html += f'<tr><td class="mname">{m}</td>'
        rv = df_v.loc[m].values
        best = min(rv) if m in ["最大回撤 (MDD)", "年化波動", "交易次數"] else max(rv)
        for i, v in enumerate(rv):
            is_win = (v == best and m != "交易次數")
            if "資產" in m: txt = fmt_money(v)
            elif any(x in m for x in ["率", "報酬", "波動", "MDD"]): txt = fmt_pct(v)
            elif "次數" in m: txt = fmt_int(v)
            else: txt = fmt_num(v)
            style = 'style="font-weight:bold; color:var(--primary-color);"' if i == 0 else ''
            html += f'<td {style}>{txt} {"🏆" if is_win else ""}</td>'
        html += '</tr>'
    st.write(html + '</tbody></table>', unsafe_allow_html=True)

    # ------------------------------------------------------
    # 8. Footer 免責聲明
    # ------------------------------------------------------
    st.markdown("<br><hr>", unsafe_allow_html=True)
    footer_html = """
    <div style="text-align: center; color: gray; font-size: 0.85rem; line-height: 1.6;">
        <p><b>策略原創開發：0050 雙向乖離動態槓桿系統 (Dual-Bias Dynamic Leverage System)</b></p>
        <p>Copyright © 2025 <a href="https://hamr-lab.com" style="color: gray; text-decoration: none;">hamr-lab.com</a>. All rights reserved.</p>
        <p style="font-style: italic;">免責聲明：本工具僅供策略回測研究參考，不構成任何形式之投資建議。投資必定有風險，過去之績效不保證未來表現，使用者應自行審慎評估風險並自負盈虧。</p>
    </div>
    """
    st.markdown(footer_html, unsafe_allow_html=True)
