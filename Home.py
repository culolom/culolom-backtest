"""
HamrLab Backtest Platform main entry.
Main page: Dashboard style layout with Password Protection & Market Signals.
"""

import streamlit as st
import os
import datetime
import pandas as pd
import auth  # <---【修改點 1】引入剛剛建立的 auth.py

# 1. 頁面設定 (必須放在第一行)
st.set_page_config(
    page_title="倉鼠量化戰情室 | 白銀小倉鼠專屬福利",
    page_icon="🐹",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------------------------------------------
# 🔒 會員驗證守門員 (Password Protection)
# ------------------------------------------------------
# 【修改點 2】原本這裡長長的 check_password 函式全部刪除
# 改成直接呼叫 auth 模組裡的函式：

if not auth.check_password():
    st.stop()  # 驗證沒過就停在這裡



# ------------------------------------------------------
# ✅ 正式內容開始
# ------------------------------------------------------

# 共有用：資料夾、工具函式
DATA_DIR = "data"
# ======================================
# 🔧 指定本月動能排行榜要跑哪些標的
#     你想改誰，就改這行
# ======================================
TARGET_SYMBOLS = ["0050.TW", "GLD", "QQQ", "SPY", "VT", "ACWI", "VOO","SPY", "VXUS", "VEA", "VWO", "BOXX", "VTI", "BIL", "IEF", "IEI"]

def find_csv_for_symbol(symbol: str, files: list):
    """在 data/*.csv 中找符合 symbol 的檔名（模糊搜尋）"""
    symbol_lower = symbol.lower()
    for f in files:
        name = os.path.basename(f).lower()
        if symbol_lower in name:
            return f
    return None


def load_price_series(csv_path: str):
    """從 CSV 讀出價格序列（支援 Date + Close / Adj Close）"""
    try:
        df = pd.read_csv(csv_path)

        # 第一欄視為日期欄
        df.iloc[:, 0] = pd.to_datetime(df.iloc[:, 0], errors="coerce")
        df = df.set_index(df.columns[0]).sort_index()

        # 優先 Close → Adj Close → 其他數值欄位
        candidates = ["Close", "Adj Close", "close", "adjclose"]
        for c in candidates:
            if c in df.columns:
                return df[c].astype(float).dropna()

        num_cols = df.select_dtypes(include="number").columns
        if len(num_cols) == 0:
            return None

        return df[num_cols[-1]].astype(float).dropna()

    except Exception:
        return None


def classify_trend(price: pd.Series):
    """用 200 日 + 價格位置簡易判斷趨勢。"""
    if price is None or len(price) < 200:
        return "資料不足", "⬜"
    ma200 = price.rolling(200).mean().iloc[-1]
    last = price.iloc[-1]
    if pd.isna(ma200) or pd.isna(last):
        return "資料不足", "⬜"
    diff = (last / ma200) - 1.0
    if diff > 0.05:
        return "多頭", "🟢"
    elif diff > 0:
        return "偏多", "🟡"
    elif diff > -0.05:
        return "偏空", "🟠"
    else:
        return "空頭", "🔴"


def get_momentum_ranking(data_dir="data", symbols=None):
    """
    symbols: list，例如 ["0050","00631L"]
    若 symbols=None → 使用全部 CSV
    """
    if not os.path.exists(data_dir):
        return None, "無資料夾"

    # 計算日期區間（上個月月底）
    today = pd.Timestamp.today()
    this_month_start = today.replace(day=1)
    end_date = this_month_start - pd.Timedelta(days=1)
    start_date = end_date - pd.DateOffset(months=12)

    results = []

    # 找全部 CSV
    all_files = [f for f in os.listdir(data_dir) if f.endswith(".csv")]

    # 若 symbols 有指定 → 只跑這些 CSV
    if symbols:
        symbols_lower = [s.lower() for s in symbols]
        use_files = [f for f in all_files if f.replace(".csv", "").lower() in symbols_lower]
    else:
        use_files = all_files

    if not use_files:
        return None, end_date

    for f in use_files:
        symbol = f.replace(".csv", "")

        try:
            df = pd.read_csv(os.path.join(data_dir, f))
            if "Date" not in df.columns:
                continue

            col_price = "Adj Close" if "Adj Close" in df.columns else "Close"
            if col_price not in df.columns:
                continue

            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date").sort_index()
            df["MA_200"] = df[col_price].rolling(window=200).mean()

            # 先抓到基準日前資料
            hist_window = df.loc[:end_date]
            if hist_window.empty:
                continue

            last_valid = hist_window.index[-1]
            if (end_date - last_valid).days > 15:
                continue

            p_end = hist_window[col_price].iloc[-1]
            ma_end = df.loc[last_valid, "MA_200"]

            # 抓 12 個月前價格
            start_window = df.loc[:start_date]
            if start_window.empty:
                continue

            p_start = start_window[col_price].iloc[-1]
            ret = (p_end - p_start) / p_start

            results.append({
                "代號": symbol,
                "12月累積報酬": ret * 100,
                "收盤價": p_end,
                "200SMA": ma_end
            })

        except Exception:
            continue

    if not results:
        return None, end_date

    df = pd.DataFrame(results)
    df = df.sort_values("12月累積報酬", ascending=False).reset_index(drop=True)
    df.index += 1
    df.index.name = "排名"

    return df, end_date



# ------------------------------------------------------
# 2. 側邊欄：品牌與外部連結
# ------------------------------------------------------

with st.sidebar:
    # 檢查並顯示 Logo
    if os.path.exists("logo.png"):
        st.image("logo.png", width=120)
    else:
        st.title("🐹") 
        
    st.title("倉鼠量化戰情室")
    st.caption("v1.1.1 Beta | 白銀小倉鼠限定")
    


    st.divider()
    
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="部落格首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@HamrLab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/how-to-read-backtest-metrics/", label="指標怎麼看", icon="📚")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")
    
    st.divider()
    st.info("💡 **提示**\n本平台僅供策略研究與回測驗證，不代表投資建議。")
    st.divider()
    
    # 加入登出按鈕 (清除 Session)
    if st.button("🚪 登出系統"):
        st.session_state["password_correct"] = False
        st.rerun()

# ------------------------------------------------------
# 3. 主畫面：歡迎語 + 資料狀態
# ------------------------------------------------------
st.title("🚀 戰情室主頁面")

data_status = "檢查中..."
last_update_str = "N/A"
files = []

try:
    data_dir = DATA_DIR
    if os.path.exists(data_dir):
        files = [
            os.path.join(data_dir, f)
            for f in os.listdir(data_dir)
            if f.endswith(".csv")
        ]
        if files:
            latest_file = max(files, key=os.path.getmtime)
            timestamp = os.path.getmtime(latest_file)
            last_update_str = datetime.datetime.fromtimestamp(
                timestamp
            ).strftime("%Y-%m-%d")
            data_status = "✅ 系統數據正常"
        else:
            data_status = "⚠️ 無數據文件"
    else:
        data_status = "❌ 找不到數據資料夾"
except Exception:
    data_status = "⚠️ 狀態檢測異常"

st.caption(f"{data_status} | 📅 最後更新：{last_update_str}")

st.markdown("""
歡迎來到 **倉鼠量化戰情室**！這裡是鼠叔為白銀小倉鼠打造的專屬軍火庫。  
下方儀表板顯示主要指數的 200日均線狀態，以及 動能排行榜，幫助你快速判斷市場水位。
""")

st.divider()

# ==========================================
# 🛠️ 策略定義區 (自動掃描版)
# ==========================================
import glob

st.subheader("🛠️ 選擇你的實驗策略")

# 1. 自動掃描 pages 資料夾下的所有 .py 檔案
#    這行會找出 pages/ 下面所有的 Python 檔，並依照檔名排序 (1_, 2_, 3_...)
pages_dir = "pages"
page_files = sorted(glob.glob(os.path.join(pages_dir, "*.py")))

# 2. 定義「美化資訊」 (這是為了讓卡片漂亮，有 icon 和描述)
#    🔑 之後新增策略，想改圖示或文字，只要來這裡加一行就好。
#    🔑 如果沒加，程式會用預設值顯示，不會報錯，不用擔心。
META_INFO = {
    "1_QQQLRS": {
        "name": "QQQ LRS 動態槓桿 (美股)",
        "icon": "🦅",
        "tags": ["美股", "Nasdaq", "動態槓桿"],
        "desc": "鎖定美股科技巨頭。以 QQQ 200日均線為訊號，動態切換 QLD (2倍) 或 TQQQ (3倍)，捕捉 Nasdaq 長期成長趨勢。"
    },
    "2_0050LRS": {
        "name": "0050 LRS 動態槓桿 (台股)",
        "icon": "🇹🇼",
        "tags": ["台股", "0050", "波段操作"],
        "desc": "進階的資金控管策略。以 0050/006208 為訊號，動態調整正2槓桿 ETF 的曝險比例，追求比大盤更高的報酬風險比。"
    },
    "3_0050score": {
        "name": "0050 景氣對策信號",
        "icon": "⚖️",
        "tags": ["0050", "波段操作", "台股"],
        "desc": "國發會景氣燈號策略 藍燈(低分)分批買進，紅燈(高分)分批賣出"
    },
    "4_0050score_basic": {
        "name": "0050 景氣對策信號基本",
        "icon": "⚖️",
        "tags": ["0050", "波段操作", "台股"],
        "desc": "國發會景氣燈號策略 藍燈(低分)買進，紅燈(高分)賣出 "
}

cols = st.columns(2)

# 3. 自動迴圈產生卡片
#    這裡會根據掃描到的檔案數量，自動生成對應的卡片
count = 0
for file_path in page_files:
    # 取得檔名 (不含路徑與副檔名)，例如 "3_0050score"
    filename = os.path.basename(file_path).replace(".py", "")
    
    # 嘗試從 META_INFO 抓取漂亮的資訊，抓不到就用預設值
    info = META_INFO.get(filename, {
        "name": filename,           # 預設名稱：直接顯示檔名
        "icon": "📄",               # 預設圖示
        "tags": ["New Strategy"],   # 預設標籤
        "desc": "此策略尚未設定描述，請至 Home.py 的 META_INFO 補充資訊。" 
    })
    
    # 排版 (左右兩欄)
    col = cols[count % 2]
    with col:
        with st.container(border=True):
            st.markdown(f"### {info['icon']} {info['name']}")
            st.markdown(" ".join([f"`{tag}`" for tag in info['tags']]))
            st.write(info['desc'])
            st.write("") # 空一行排版
            
            # 建立按鈕連結 (直接連到該檔案路徑)
            st.page_link(
                file_path, 
                label="進入策略回測", 
                icon="👉",
                use_container_width=True
            )
    count += 1

# 如果 pages 資料夾是空的 (預防性措施)
if not page_files:
    st.info("⚠️ 目前 pages 資料夾中沒有任何策略檔案。")

# ==========================================
# 📊 功能 1：市場即時儀表板 (戰情室核心)
# ==========================================
st.subheader("📌 今日市場摘要")

summary_cols = st.columns(4)

# 定義常見指標／資產
ASSET_CONFIG = [
    {"label": "美股科技", "symbol": "QQQ"},
    {"label": "美股大盤", "symbol": "SPY"},
    {"label": "台股大盤", "symbol": "0050"},
    {"label": "全球股市", "symbol": "VT"},
    {"label": "長天期債券", "symbol": "TLT"},
    {"label": "比特幣", "symbol": "BTC"},
]

if not files:
    st.info("目前找不到任何 CSV 數據檔案，市場摘要會先顯示為占位內容。請在 data 資料夾放入價格歷史 CSV。")
else:
    for i, asset in enumerate(ASSET_CONFIG[:4]):  # 先顯示 4 個重點
        with summary_cols[i]:
            csv_path = find_csv_for_symbol(asset["symbol"], files)
            if csv_path is None:
                st.metric(asset["label"], "資料不存在", "⬜")
            else:
                price = load_price_series(csv_path)
                trend_text, trend_icon = classify_trend(price)
                st.metric(asset["label"], trend_text, trend_icon)

st.caption("註：以上為簡易 SMA200 趨勢判讀，只作為戰情室參考，不作為買賣訊號。")

st.markdown("---")


# ==========================================
# 🏆 功能 2：本月動能排行榜 (過去 12 個月績效)
# ==========================================
# ==========================================
# 🏆 本月動能排行榜（依照 TARGET_SYMBOLS 指定標的）
# ==========================================
st.markdown("### 🏆 本月動能排行榜（過去 12 個月績效）")

rank_df, calc_date = get_momentum_ranking(DATA_DIR, symbols=TARGET_SYMBOLS)

if rank_df is not None and not isinstance(calc_date, str):
    st.caption(f"📅 統計基準日：**{calc_date.strftime('%Y-%m-%d')}**（上個月底） | 過去 12 個月累積報酬")

    st.dataframe(
        rank_df,
        column_config={
            "12月累積報酬": st.column_config.ProgressColumn(
                "12月累積報酬 (Momentum)",
                help="過去 12 個月的漲跌幅",
                format="%.2f%%",
                min_value=-50,
                max_value=100,
            ),
            "收盤價": st.column_config.NumberColumn(
                "收盤價 (Price)",
                format="$%.2f",
            ),
            "200SMA": st.column_config.NumberColumn(
                "200 日均線",
                format="$%.2f",
            ),
        },
        use_container_width=True,
    )
else:
    st.info("❗ 尚無足夠資料可計算動能排行，請確認 data/ 資料夾內容。")



# 6. 頁尾
st.markdown("---")
st.caption("🚧 更多策略正在開發中 (MACD 動能、RSI 逆勢交易...)，敬請期待！")
