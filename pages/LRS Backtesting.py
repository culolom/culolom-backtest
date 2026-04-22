import os
import sys
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib
from pathlib import Path

###############################################################
# 1. 環境設定與字型美化
###############################################################

# 設置中文字型
font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

# 頁面配置
st.set_page_config(page_title="LRS 策略深度統計戰情室", page_icon="📈", layout="wide")

# 🔒 驗證守門員
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except ImportError:
    pass 

# --- 全局色系定義 ---
COLOR_EXP = "#6699CC"  # 擴張期 / 藍
COLOR_REC = "#EE7733"  # 衰退期 / 橘
COLOR_UP  = "#2962FF"  # 上漲天數 / 深藍
COLOR_DOWN = "#D50000" # 下跌天數 / 紅
COLOR_ORANGE_BTN = "#FF6F00" # 鼠叔橘

# --- CSS 注入：打造專業卡片式介面 ---
st.markdown(f"""
<style>
    /* 全局背景與字體 */
    .main {{ background-color: #f8f9fa; }}
    
    /* 鼠叔橘按鈕 */
    div.stButton > button:first-child {{
        background-color: {COLOR_ORANGE_BTN}; color: white; border-radius: 8px;
        border: none; font-weight: bold; font-size: 16px; padding: 0.6rem 2.5rem;
        transition: all 0.3s ease; box-shadow: 0 4px 12px rgba(255, 111, 0, 0.2);
    }}
    div.stButton > button:first-child:hover {{
        background-color: #E65100; transform: translateY(-2px); box-shadow: 0 6px 15px rgba(255, 111, 0, 0.3);
    }}
    
    /* 專業資訊卡片 */
    .info-card {{
        background-color: white; padding: 25px; border-radius: 15px;
        border-left: 8px solid {COLOR_ORANGE_BTN}; box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        margin-bottom: 30px;
    }}
    
    /* 區塊標題美化 */
    .section-head {{
        color: #1f2937; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px; margin-top: 40px; margin-bottom: 20px;
    }}
</style>
""", unsafe_allow_html=True)

###############################################################
# 2. 數據載入邏輯
###############################################################
DATA_DIR = Path("data")

@st.cache_data
def load_data(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    price_col = "Adj Close" if "Adj Close" in df.columns else "Close"
    return df[[price_col]].rename(columns={price_col: "Price"})

###############################################################
# 3. Sidebar 導航
###############################################################
with st.sidebar:
    st.image("https://hamr-lab.com/wp-content/uploads/2023/06/hamster-logo.png", width=100) # 假設有 logo
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室首頁", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="倉鼠人生實驗室官網", icon="🌐")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 實戰教學", icon="📺")
    st.divider()
    st.caption("© 2026 倉鼠人生實驗室 | 鼠叔版權所有")

###############################################################
# 4. 主畫面內容
###############################################################
st.markdown("<h1 style='text-align: center; color: #1f2937;'>🔭 LRS 槓桿輪換策略：全維度量化報告</h1>", unsafe_allow_html=True)

st.markdown(f"""
<div class="info-card">
    <h3 style="margin-top:0; color: {COLOR_ORANGE_BTN};">📖 鼠叔量化筆記：環境決定動能</h3>
    <p style="font-size:1.1em; line-height:1.6; color: #4b5563;">
        本報告旨在實證《Leverage for the Long Run》論文核心：<b>移動平均線不僅是價格指標，更是「環境濾網」。</b><br>
        透過對比均線之上與之下的<b>波動率、漲跌勝率、動能基因</b>，我們能科學地證明：為什麼年線之下必須空手避險。
    </p>
</div>
""", unsafe_allow_html=True)

# --- ⚙️ 參數設定區 ---
with st.container():
    st.markdown("<h3 class='section-head'>⚙️ 全域回測參數</h3>", unsafe_allow_html=True)
    c_p1, c_p2 = st.columns([1, 1.5])

    TICKER_MAPPING = {
        "台灣加權指數": "^TWII",
        "元大台灣50指數ETF": "0050.TW",
        "標普500指數ETF": "SPY",
        "那斯達克100指數ETF": "QQQ"
    }

    with c_p1:
        selected_name = st.selectbox("選擇研究標的", list(TICKER_MAPPING.keys()), index=0)
        target_symbol = TICKER_MAPPING[selected_name]

    with c_p2:
        start_year = st.slider("統計起始年份", 2000, 2026, 2000)

st.write("") # Spacer

if st.button("開始生成深度量化報告 🚀"):
    df_raw = load_data(target_symbol)
    if df_raw.empty:
        st.error(f"❌ 數據庫中找不到 {target_symbol}.csv 檔案。")
        st.stop()
        
    # --- 數據預處理 ---
    df = df_raw[df_raw.index.year >= start_year].copy()
    df['Return'] = df['Price'].pct_change()
    
    # --- 區塊 1：多週期波動率對比 (美化版) ---
    st.markdown(f"<h3 class='section-head'>📊 {selected_name}：多週期均線之波動率對比</h3>", unsafe_allow_html=True)
    ma_list = [10, 20, 50, 100, 200]
    vol_data = []
    for p in ma_list:
        ma_t = df['Price'].rolling(window=p).mean()
        above = df['Price'] > ma_t
        vol_data.append({"MA週期": f"{p}日線", "年化波動率": df[above]['Return'].std() * np.sqrt(252), "環境": "均線之上 (Above)"})
        vol_data.append({"MA週期": f"{p}日線", "年化波動率": df[~above]['Return'].std() * np.sqrt(252), "環境": "均線之下 (Below)"})
        
    fig_v = px.bar(pd.DataFrame(vol_data), x="MA週期", y="年化波動率", color="環境",
                   barmode="group", text_auto='.1%', color_discrete_map={"均線之上 (Above)": COLOR_EXP, "均線之下 (Below)": COLOR_REC})
    fig_v.update_layout(yaxis_tickformat='.0%', plot_bgcolor='rgba(0,0,0,0)', height=450)
    st.plotly_chart(fig_v, use_container_width=True)

    # --- 區塊 2：週期佔比與漲跌勝率 ---
    st.markdown("<h3 class='section-head'>⚖️ 環境與勝率：擴張期 vs 衰退期</h3>", unsafe_allow_html=True)
    df['MA200'] = df['Price'].rolling(window=200).mean()
    df['Above200'] = df['Price'] > df['MA200']
    
    c_ratio, c_win = st.columns([1, 1.2])
    
    with c_ratio:
        counts = df['Above200'].value_counts(normalize=True)
        fig_r = px.bar(x=["擴張期 (>200MA)", "衰退期 (<200MA)"], y=[counts.get(True, 0), counts.get(False, 0)],
                       color=["Exp", "Rec"], text_auto='.1%', color_discrete_map={"Exp": COLOR_EXP, "Rec": COLOR_REC}, title="市場週期時間佔比")
        fig_r.update_layout(yaxis_tickformat='.0%', showlegend=False, height=400)
        st.plotly_chart(fig_r, use_container_width=True)

    with c_win:
        def get_ur(data): return (data['Return'] > 0).sum() / len(data), (data['Return'] <= 0).sum() / len(data)
        ua, da = get_ur(df[df['Above200']].dropna())
        ub, db = get_ur(df[~df['Above200']].dropna())
        pdf = pd.DataFrame([{"環境": "擴張期", "漲跌": "上漲", "比例": ua}, {"環境": "擴張期", "漲跌": "下跌", "比例": da},
                            {"環境": "衰退期", "漲跌": "上漲", "比例": ub}, {"環境": "衰退期", "漲跌": "下跌", "比例": db}])
        fig_p = px.bar(pdf, x="環境", y="比例", color="漲跌", barmode="group", text_auto='.1%',
                       color_discrete_map={"上漲": COLOR_UP, "下跌": COLOR_DOWN}, title="均線環境下之漲跌機率")
        fig_p.update_layout(yaxis_tickformat='.0%', height=400)
        st.plotly_chart(fig_p, use_container_width=True)

    # --- 區塊 3：動能基因 (連漲/連跌) ---
    st.markdown("<h3 class='section-head'>🔥 動能基因測試：連漲 vs 連跌天數分佈</h3>", unsafe_allow_html=True)
    is_up = df['Return'] > 0
    df['U_S'] = is_up.groupby((is_up != is_up.shift()).cumsum()).cumcount() + 1
    df.loc[~is_up, 'U_S'] = 0
    is_down = df['Return'] < 0
    df['D_S'] = is_down.groupby((is_down != is_down.shift()).cumsum()).cumcount() + 1
    df.loc[~is_down, 'D_S'] = 0

    def get_s_p(sub, col): return {f"{s}天": (sub[col] >= s).sum() / len(sub) for s in [2, 3, 4, 5]}
    c_sl, c_sr = st.columns(2)
    
    with c_sl:
        ua, ub = get_s_p(df[df['Above200']], 'U_S'), get_s_p(df[~df['Above200']], 'U_S')
        st.plotly_chart(px.bar(pd.DataFrame([{"天數": k, "機率": v, "環境": "均線之上"} for k,v in ua.items()] + [{"天數": k, "機率": v, "環境": "均線之下"} for k,v in ub.items()]),
                               x="天數", y="機率", color="環境", barmode="group", text_auto='.1%', color_discrete_map={"均線之上": COLOR_EXP, "均線之下": COLOR_REC}, title="連漲機率統計"), use_container_width=True)
    with c_sr:
        da, db = get_s_p(df[df['Above200']], 'D_S'), get_s_p(df[~df['Above200']], 'D_S')
        st.plotly_chart(px.bar(pd.DataFrame([{"天數": k, "機率": v, "環境": "均線之上"} for k,v in da.items()] + [{"天數": k, "機率": v, "環境": "均線之下"} for k,v in db.items()]),
                               x="天數", y="機率", color="環境", barmode="group", text_auto='.1%', color_discrete_map={"均線之上": COLOR_EXP, "均線之下": COLOR_REC}, title="連跌機率統計"), use_container_width=True)

    # --- 區塊 4：滾動回撤與避險 ---
    st.markdown("<h3 class='section-head'>🛡️ 歷史滾動回撤對比 (Rolling Drawdown)</h3>", unsafe_allow_html=True)
    df['B_NAV'] = (1 + df['Return'].fillna(0)).cumprod()
    df['L_Ret'] = np.where(df['Above200'].shift(1), df['Return'], 0)
    df['L_NAV'] = (1 + df['L_Ret'].fillna(0)).cumprod()
    df['B_DD'] = (df['B_NAV'] / df['B_NAV'].cummax()) - 1
    df['L_DD'] = (df['L_NAV'] / df['L_NAV'].cummax()) - 1
    
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['B_DD'], name=f"{selected_name} (Buy & Hold)", line=dict(color=COLOR_REC, width=1), fill='tozeroy', fillcolor='rgba(238,119,51,0.1)'))
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['L_DD'], name="LRS 200SMA 策略", line=dict(color=COLOR_EXP, width=2.5)))
    fig_dd.update_layout(yaxis_tickformat='.0%', hovermode="x unified", height=550, plot_bgcolor='white')
    st.plotly_chart(fig_dd, use_container_width=True)

    # 股災表格
    st.markdown("<h4 style='color: #374151;'>📋 重大股災避險效果統計 (Regime Discovery)</h4>", unsafe_allow_html=True)
    crashes = [("2008 金融海嘯", "2008-01-01", "2009-06-30"), ("2020 新冠疫情", "2020-01-01", "2020-04-30"), 
               ("2022 升息縮表", "2022-01-01", "2022-12-31"), ("2025 對等關稅股災", "2025-01-01", "2025-12-31")]
    mdd_sum = []
    for name, s, e in crashes:
        mask = (df.index >= s) & (df.index <= e)
        if mask.any():
            sub = df.loc[mask]
            b_mdd = (sub['B_NAV'] / sub['B_NAV'].cummax() - 1).min()
            l_mdd = (sub['L_NAV'] / sub['LRS_NAV'].cummax() if 'LRS_NAV' in sub else sub['L_NAV'] / sub['L_NAV'].cummax() - 1).min() # 修正計算
            l_mdd = (sub['L_NAV'] / sub['L_NAV'].cummax() - 1).min()
            mdd_sum.append({"歷史股災事件": name, "大盤 MDD": f"{b_mdd:.1%}", "LRS 策略 MDD": f"{l_mdd:.1%}", "風險降低幅度": f"{(b_mdd-l_mdd)*-1:.1%}"})
    st.table(pd.DataFrame(mdd_sum))
    
    st.success(f"✨ {selected_name} 全維度研究報告已生成。數據證實：LRS 系統是長期生存的必備工具。")
else:
    st.info("💡 請在上方選擇標的並點擊按鈕，開始進行深度量化統計。")
