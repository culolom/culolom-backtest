"""
HamrLab Backtest Platform main entry.
Main page: Dashboard style layout with Password Protection & Market Signals.
"""

import streamlit as st
import os
import datetime
import pandas as pd
import glob
import auth  # 引入會員驗證模組

# 1. 頁面設定
st.set_page_config(
    page_title="倉鼠量化戰情室 | 白銀小倉鼠專屬福利",
    page_icon="🐹",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------------------------------------------
# 🔒 會員驗證守門員
# ------------------------------------------------------
if not auth.check_password():
    st.stop()

# ------------------------------------------------------
# ✅ 全域配置與工具函式
# ------------------------------------------------------
DATA_DIR = "data"

# ======================================
# 🔧 更新後的動能排行榜標的清單
# ======================================
TARGET_SYMBOLS = [
    "0050.TW", "2330.TW", "00878.TW", "00662.TW", "00646.TW", 
    "00670L.TW", "00647L.TW", "006208.TW", "00631L.TW", "00663L.TW", 
    "00675L.TW", "00685L.TW", "00708L.TW", "00635U.TW", 
    "QQQ", "QLD", "TQQQ", "SPY", "BTC-USD"
]

def find_csv_for_symbol(symbol: str, files: list):
    symbol_lower = symbol.lower()
    for f in files:
        name = os.path.basename(f).lower()
        if symbol_lower in name:
            return f
    return None

def load_price_series(csv_path: str):
    try:
        df = pd.read_csv(csv_path)
        df.iloc[:, 0] = pd.to_datetime(df.iloc[:, 0], errors="coerce")
        df = df.set_index(df.columns[0]).sort_index()
        candidates = ["Adj Close", "Close", "close", "adjclose"]
        for c in candidates:
            if c in df.columns:
                return df[c].astype(float).dropna()
        num_cols = df.select_dtypes(include="number").columns
        return df[num_cols[-1]].astype(float).dropna() if len(num_cols) > 0 else None
    except Exception:
        return None

def classify_trend(price: pd.Series):
    if price is None or len(price) < 200:
        return "資料不足", "⬜"
    ma200 = price.rolling(200).mean().iloc[-1]
    last = price.iloc[-1]
    if pd.isna(ma200) or pd.isna(last):
        return "資料不足", "⬜"
    diff = (last / ma200) - 1.0
    if diff > 0.05: return "多頭", "🟢"
    elif diff > 0: return "偏多", "🟡"
    elif diff > -0.05: return "偏空", "🟠"
    else: return "空頭", "🔴"

def get_momentum_ranking(data_dir="data", symbols=None):
    if not os.path.exists(data_dir):
        return None, "無資料夾"
    today = pd.Timestamp.today()
    this_month_start = today.replace(day=1)
    end_date = this_month_start - pd.Timedelta(days=1)
    start_date = end_date - pd.DateOffset(months=12)
    results = []
    all_files = [f for f in os.listdir(data_dir) if f.endswith(".csv")]

    if symbols:
        use_files = []
        for s in symbols:
            matched = find_csv_for_symbol(s, all_files)
            if matched: use_files.append(os.path.basename(matched))
    else:
        use_files = all_files

    for f in use_files:
        symbol = f.replace(".csv", "")
        try:
            df = pd.read_csv(os.path.join(data_dir, f))
            col_price = "Adj Close" if "Adj Close" in df.columns else "Close"
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date").sort_index()
            df["MA_200"] = df[col_price].rolling(window=200).mean()
            hist_window = df.loc[:end_date]
            if hist_window.empty: continue
            last_valid = hist_window.index[-1]
            p_end = hist_window[col_price].iloc[-1]
            ma_end = df.loc[last_valid, "MA_200"]
            start_window = df.loc[:start_date]
            if start_window.empty: continue
            p_start = start_window[col_price].iloc[-1]
            ret = (p_end - p_start) / p_start
            results.append({"代號": symbol, "12月累積報酬": ret * 100, "收盤價": p_end, "200SMA": ma_end})
        except Exception:
            continue
    if not results: return None, end_date
    df_res = pd.DataFrame(results).sort_values("12月累積報酬", ascending=False).reset_index(drop=True)
    df_res.index += 1
    return df_res, end_date

# ------------------------------------------------------
# 2. 側邊欄
# ------------------------------------------------------
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", width=120)
    else: st.title("🐹") 
    st.title("倉鼠量化戰情室")
    st.caption("v1.2.0 | 白銀小倉鼠限定")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="部落格首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")
    st.divider()
    if st.button("🚪 登出系統"):
        st.session_state["password_correct"] = False
        st.rerun()

# ------------------------------------------------------
# 3. 主畫面
# ------------------------------------------------------
st.title("🚀 戰情室軍火庫")

# 狀態檢查
files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
last_update = datetime.datetime.fromtimestamp(os.path.getmtime(max(files, key=os.path.getmtime))).strftime("%Y-%m-%d") if files else "N/A"
st.caption(f"✅ 系統數據正常 | 📅 最後更新：{last_update}")

st.markdown("""
歡迎來到 **倉鼠量化戰情室**！下方為白銀小倉鼠專屬的策略實驗室與市場儀表板。
利用 **200日均線趨勢過濾** 與 **動能排行**，在牛市進攻、熊市防守。
""")

st.divider()

# ==========================================
# 🛠️ 策略實驗室 (自動掃描 + 美化)
# ==========================================
st.subheader("🛠️ 選擇你的實驗策略")

HIDE_STRATEGIES = ["temp_test", "old_strategy"]

META_INFO = {
    "1_QQQLRS": {
        "name": "QQQ LRS 動態槓桿",
        "icon": "🦅",
        "tags": ["美股", "Nasdaq", "動態槓桿"],
        "desc": "以 QQQ 200SMA 為訊號，動態切換 QLD (2x) 或 TQQQ (3x)，捕捉科技股長期上升趨勢。"
    },
    "2_0050LRS": {
        "name": "0050 LRS 動態槓桿",
        "icon": "🇹🇼",
        "tags": ["台股", "0050", "曝險調整"],
        "desc": "以台股大盤為訊號源，動態調整正2槓桿比例，追求更優化的風險回報比。"
    },
    "3_Basic0050score": {
        "name": "0050 景氣燈號 (基礎)",
        "icon": "🚦",
        "tags": ["基本面", "景氣循環"],
        "desc": "國發會景氣對策信號簡單策略：藍燈買進、紅燈賣出。"
    },
    "7_50dbdl": {
        "name": "單一標的雙向乖離策略",
        "icon": "⚖️",
        "tags": ["動態定期定額", "抄底套利", "單一標的"],
        "desc": "最新版本！支援 SMA 趨勢過濾開關，透過負乖離 DCA 加碼與高位套利減碼，大幅優化正2長期持有的心理壓力。"
    },
    "8_nsf": {
        "name": "0050 國安基金爆擊法",
        "icon": "🛡️",
        "tags": ["政策盤", "抄底爆擊"],
        "desc": "模擬國安基金進場心理，在極端恐慌時勇敢打出爆擊部位。"
    }
}

pages_dir = "pages"
page_files = sorted(glob.glob(os.path.join(pages_dir, "*.py")))
cols = st.columns(2)
count = 0

for file_path in page_files:
    filename = os.path.basename(file_path).replace(".py", "")
    if filename in HIDE_STRATEGIES: continue
    
    info = META_INFO.get(filename, {
        "name": filename, "icon": "📄", "tags": ["New"], "desc": "策略描述補充中..."
    })
    
    with cols[count % 2]:
        with st.container(border=True):
            st.markdown(f"### {info['icon']} {info['name']}")
            st.markdown(" ".join([f"`{tag}`" for tag in info['tags']]))
            st.write(info['desc'])
            st.page_link(file_path, label="進入策略回測", icon="👉", use_container_width=True)
    count += 1

st.divider()

# ==========================================
# 📊 市場儀表板
# ==========================================
st.subheader("📌 重點市場趨勢 (SMA200)")
summary_cols = st.columns(4)
ASSETS = [
    {"label": "美股科技 (QQQ)", "symbol": "QQQ"},
    {"label": "台股大盤 (0050)", "symbol": "0050.TW"},
    {"label": "比特幣 (BTC)", "symbol": "BTC-USD"},
    {"label": "全球股市 (VT)", "symbol": "VT"},
]

for i, asset in enumerate(ASSETS):
    with summary_cols[i]:
        csv_path = find_csv_for_symbol(asset["symbol"], files)
        if csv_path:
            p = load_price_series(csv_path)
            t_text, t_icon = classify_trend(p)
            st.metric(asset["label"], t_text, t_icon)
        else:
            st.metric(asset["label"], "無資料", "⬜")

# ==========================================
# 🏆 本月動能排行榜
# ==========================================
st.markdown("### 🏆 本月動能排行榜 (過去 12 個月績效)")
rank_df, calc_date = get_momentum_ranking(DATA_DIR, symbols=TARGET_SYMBOLS)

if rank_df is not None:
    st.caption(f"📅 統計基準日：**{calc_date.strftime('%Y-%m-%d')}** (上個月底)")
    st.dataframe(
        rank_df,
        column_config={
            "12月累積報酬": st.column_config.ProgressColumn(
                "12月累積報酬", format="%.2f%%", min_value=-50, max_value=100
            ),
            "收盤價": st.column_config.NumberColumn("收盤價", format="$%.2f"),
            "200SMA": st.column_config.NumberColumn("200SMA", format="$%.2f"),
        },
        use_container_width=True,
    )

st.markdown("---")
st.caption("🚧 更多策略 (MACD、RSI) 與情緒指標開發中，敬請期待！")
