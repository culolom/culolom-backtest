"""
HamrLab Backtest Platform main entry.
Main page: Dashboard style layout with Password Protection & Market Signals.
"""

import streamlit as st
import os
import datetime
import pandas as pd # 記得 import pandas 來處理數據

# 1. 頁面設定 (必須放在第一行)
st.set_page_config(
    page_title="倉鼠回測平台 | 會員專屬",
    page_icon="🐹",
    layout="wide",
    initial_sidebar_state="expanded"
)



# ------------------------------------------------------
# ✅ 正式內容開始
# ------------------------------------------------------

# 2. 側邊欄：品牌與外部連結
with st.sidebar:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=120)
    else:
        st.title("🐹") 
        
    st.title("倉鼠實驗室")
    st.caption("v1.4.0 Beta | 白銀會員限定")
    
    st.divider()
    
    if st.button("🚪 登出系統"):
        st.session_state["password_correct"] = False
        st.rerun()

    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@HamrLab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")
    st.divider()
    st.info("💡 **提示**\n本平台僅供策略研究與回測驗證，不代表投資建議。")

# 3. 主畫面：歡迎語
st.title("🚀 量化戰情室")

# 數據更新狀態
data_status = "檢查中..."
last_update = "N/A"

try:
    data_dir = "data"
    if os.path.exists(data_dir):
        files = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith(".csv")]
        if files:
            latest_file = max(files, key=os.path.getmtime)
            timestamp = os.path.getmtime(latest_file)
            last_update = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
            data_status = "✅ 系統數據正常"
        else:
            data_status = "⚠️ 無數據文件"
    else:
        data_status = "❌ 找不到數據資料夾"
except Exception as e:
    data_status = "⚠️ 狀態檢測異常"

st.caption(f"{data_status} | 📅 最後更新：{last_update}")

st.markdown("""
歡迎來到 **倉鼠回測平台**！這裡是鼠叔為白銀會員打造的專屬軍火庫。
下方儀表板顯示主要指數的 **200日均線** 狀態，以及 **動能排行榜**，幫助您快速判斷市場水位。
""")

st.divider()

# ==========================================
# 📊 功能 1：市場即時儀表板 (戰情室核心)
# ==========================================
st.markdown("### 🚥 市場多空訊號 (最新收盤)")

def get_signal_status(symbol_csv, window=200):
    """讀取 CSV 並判斷目前是多頭還是空頭"""
    csv_path = os.path.join("data", symbol_csv)
    
    if not os.path.exists(csv_path):
        return None, None, None, "無資料"

    try:
        df = pd.read_csv(csv_path)
        col_price = "Adj Close" if "Adj Close" in df.columns else "Close"
        
        df = df.tail(300).copy()
        df[col_price] = pd.to_numeric(df[col_price], errors='coerce')
        df["MA_200"] = df[col_price].rolling(window=window).mean()
        
        last_row = df.iloc[-1]
        price = last_row[col_price]
        ma = last_row["MA_200"]
        
        if pd.isna(ma):
            return price, None, "資料不足", "off"
            
        if price > ma:
            status = "🟢 多頭 (持有)"
            delta_color = "normal"
        else:
            status = "🔴 空頭 (空手)"
            delta_color = "inverse"
            
        return price, ma, status, delta_color
        
    except Exception as e:
        return None, None, None, "讀取錯誤"

m1, m2, m3 = st.columns(3)

with m1:
    price, ma, status, color = get_signal_status("QQQ.csv")
    if price:
        st.metric(
            label="🇺🇸 QQQ 納斯達克",
            value=f"${price:.2f}",
            delta=status,
            delta_color=color if color == "normal" else "inverse"
        )
        if ma: st.caption(f"200MA: ${ma:.2f}")
    else:
        st.info("尚無 QQQ 數據")

with m2:
    price, ma, status, color = get_signal_status("0050.csv") 
    if price:
        st.metric(
            label="🇹🇼 0050 台灣五十",
            value=f"{price:.2f}",
            delta=status,
            delta_color=color if color == "normal" else "inverse"
        )
        if ma: st.caption(f"200MA: {ma:.2f}")
    else:
        st.info("尚無 0050 數據")

with m3:
    st.container(border=True).markdown("""
    **🚧 更多訊號開發中**
    比特幣 (BTC) 與 總體經濟指標
    即將上線...
    """)

st.divider()

# ==========================================
# 🏆 功能 2：本月動能排行榜 (新增功能)
# ==========================================
st.markdown("### 🏆 本月動能排行榜 (過去 12 個月績效)")

def get_momentum_ranking(data_dir="data"):
    """
    計算邏輯：
    1. 基準日(End Date) = 上個月的最後一天 (例如今天是 12/15, 基準日就是 11/30)
    2. 起始日(Start Date) = 基準日回推 12 個月
    3. 報酬率 = (基準日價格 - 起始日價格) / 起始日價格
    """
    if not os.path.exists(data_dir):
        return None, "無資料夾"

    # 計算日期區間
    today = pd.Timestamp.today()
    # 取得本月第一天，再減一天就是上個月最後一天
    this_month_start = today.replace(day=1)
    end_date = this_month_start - pd.Timedelta(days=1)
    # 回推 12 個月
    start_date = end_date - pd.DateOffset(months=12)

    results = []

    for f in os.listdir(data_dir):
        if f.endswith(".csv"):
            symbol = f.replace(".csv", "")
            try:
                # 讀取並處理日期
                df = pd.read_csv(os.path.join(data_dir, f))
                if "Date" not in df.columns: continue
                
                col_price = "Adj Close" if "Adj Close" in df.columns else "Close"
                df["Date"] = pd.to_datetime(df["Date"])
                df = df.set_index("Date").sort_index()

                # 計算 200 SMA (供稍後使用)
                df["MA_200"] = df[col_price].rolling(window=200).mean()

                # 確保在截止日有資料 (或是最接近的一天)
                # 使用 slicing 取得截止日(含)之前的資料
                hist_window = df.loc[:end_date]
                
                if hist_window.empty: continue
                
                # 如果資料太舊(例如最後一筆資料離截止日超過15天)，視為無效
                last_valid_date = hist_window.index[-1]
                if (end_date - last_valid_date).days > 15: continue
                
                p_end = hist_window[col_price].iloc[-1]
                ma_end = df.loc[last_valid_date, "MA_200"] # 取得當天的 200SMA

                # 取得起始日價格 (12個月前)
                start_window = df.loc[:start_date]
                if start_window.empty: continue # 歷史資料不足 12 個月
                
                p_start = start_window[col_price].iloc[-1]

                ret = (p_end - p_start) / p_start
                
                results.append({
                    "代號": symbol,
                    "12月累積報酬": ret * 100, # ✅ 乘上 100 以顯示正確百分比 (58.0%)
                    "收盤價": p_end,
                    "200SMA": ma_end # ✅ 新增 200SMA
                })
            except:
                continue
    
    if not results:
        return None, end_date

    # 轉成 DataFrame 並排序
    res_df = pd.DataFrame(results)
    res_df = res_df.sort_values("12月累積報酬", ascending=False).reset_index(drop=True)
    res_df.index += 1 # 排名從 1 開始
    res_df.index.name = "排名"
    
    return res_df, end_date

# 執行計算與顯示
rank_df, calc_date = get_momentum_ranking()

if rank_df is not None:
    st.caption(f"📅 統計基準日：**{calc_date.strftime('%Y-%m-%d')}** (上個月底) | 過去 12 個月累積報酬")
    
    # 使用 st.dataframe 顯示，並加上 Bar Chart 視覺化
    st.dataframe(
        rank_df,
        column_config={
            "12月累積報酬": st.column_config.ProgressColumn(
                "12月累積報酬 (Momentum)",
                help="過去 12 個月的漲跌幅",
                format="%.2f%%", # Streamlit 會在數字後加上 %，所以我們給 58.0 會顯示 58.00%
                min_value=-50,   # 設定範圍為 -50% ~ 100%
                max_value=100,
            ),
            "收盤價": st.column_config.NumberColumn(
                "收盤價 (Price)",
                format="$%.2f"
            ),
            "200SMA": st.column_config.NumberColumn(
                "200SMA 均線",
                format="$%.2f",
                help="200日移動平均線價格，可用於輔助判斷是否過熱或剛站上趨勢"
            )
        },
        use_container_width=True
    )
else:
    st.info("尚無足夠的歷史資料可計算動能排行。")

st.divider()

# ==========================================
# 🛠️ 策略定義區
# ==========================================
strategies = [
    {
        "name": "QQQ LRS 動態槓桿 (美股)",
        "icon": "🦅",
        "description": "鎖定美股科技巨頭。以 QQQ 200日均線為訊號，動態切換 QLD (2倍) 或 TQQQ (3倍) 槓桿 ETF，捕捉 Nasdaq 長期成長趨勢。",
        "tags": ["美股", "Nasdaq", "動態槓桿"],
        "page_path": "pages/1_QQQLRS.py",
        "btn_label": "進入 QQQ 回測"
    },
    {
        "name": "0050 LRS 動態槓桿 (台股)",
        "icon": "🇹🇼",
        "description": "進階的資金控管策略。以 0050/006208 為訊號，動態調整正2槓桿 ETF 的曝險比例，追求比大盤更高的報酬風險比。",
        "tags": ["台股", "0050", "波段操作"],
        "page_path": "pages/2_0050LRS.py",
        "btn_label": "進入 0050 回測"
    },
]

st.subheader("🛠️ 選擇你的實驗策略")

cols = st.columns(2)

for index, strategy in enumerate(strategies):
    col = cols[index % 2]
    
    with col:
        with st.container(border=True):
            st.markdown(f"### {strategy['icon']} {strategy['name']}")
            st.markdown(" ".join([f"`{tag}`" for tag in strategy['tags']]))
            st.write(strategy['description'])
            st.write("") 
            st.page_link(
                strategy['page_path'], 
                label=strategy['btn_label'], 
                icon="👉", 
                use_container_width=True
            )

# 6. 頁尾
st.markdown("---")
st.caption("🚧 更多策略正在開發中 (MACD 動能、RSI 逆勢交易...)，敬請期待！")
