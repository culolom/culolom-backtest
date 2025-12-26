import streamlit as st
import pandas as pd
import os

# --- 設定資料路徑 ---
DATA_FOLDER = 'data'  # 請確保這個名稱跟你實際的資料夾名稱一樣

# --- 讀取所有股票代碼 ---
# 掃描 data 資料夾，找出所有的 .csv 檔案並去除副檔名
try:
    available_files = [f for f in os.listdir(DATA_FOLDER) if f.endswith('.csv')]
    # 建立代碼選單 (例如: ['0050.TW', '006208.TW'])
    tickers = [f.replace('.csv', '') for f in available_files]
except FileNotFoundError:
    st.error(f"找不到 '{DATA_FOLDER}' 資料夾，請確認路徑是否正確。")
    tickers = []

st.title('📊 歷年報酬率回測看板')

# --- 步驟 1: 下拉式選單 (可複選) ---
selected_tickers = st.multiselect(
    '請選擇股票 (可多選):',
    options=tickers,
    default=tickers[:1] if tickers else None # 預設選第一個，方便預覽
)

if selected_tickers:
    # 用來存放計算結果的字典
    yearly_returns_data = {}

    for ticker in selected_tickers:
        file_path = os.path.join(DATA_FOLDER, f"{ticker}.csv")
        
        # 讀取 CSV
        df = pd.read_csv(file_path)
        
        # --- 關鍵資料處理 ---
        # 1. 確保 Date 是時間格式，並設為 index
        # 假設你的 CSV 時間欄位叫 'Date'，如果叫別的(如 'date')請自行修改
        df['Date'] = pd.to_datetime(df['Date']) 
        df.set_index('Date', inplace=True)
        
        # 2. 處理欄位名稱大小寫問題 (防止 'adj close' vs 'Adj Close')
        # 將所有欄位轉小寫，方便統一抓取
        df.columns = [c.lower() for c in df.columns]
        
        if 'adj close' in df.columns:
            target_col = 'adj close'
        elif 'close' in df.columns:
            st.warning(f"{ticker} 找不到 Adj Close，改用 Close 計算")
            target_col = 'close'
        else:
            st.error(f"{ticker} 資料格式有誤，找不到股價欄位")
            continue

        # 3. 計算年度報酬率
        # 'YE' 代表 Year End (年底)，取該年度最後一天的股價
        yearly_price = df[target_col].resample('YE').last()
        
        # 計算變化百分比 (今年年底 / 去年年底 - 1)
        yearly_return = yearly_price.pct_change()
        
        # 將索引只保留年份 (例如 2020-12-31 變成 2020)
        yearly_return.index = yearly_return.index.year
        
        # 存入字典
        yearly_returns_data[ticker] = yearly_return

    # --- 步驟 2: 整理與顯示結果 ---
    if yearly_returns_data:
        # 合併成一個大表格 (Row是年份, Column是股票)
        result_df = pd.DataFrame(yearly_returns_data)
        
        # 排序年份 (從新到舊 或 從舊到新)
        result_df = result_df.sort_index(ascending=False)

        st.subheader("📝 年度報酬率詳細數據")
        
        # 顯示表格，並使用 Pandas Styler 加上百分比格式和顏色
        st.dataframe(
            result_df.style
            .format("{:.2%}")  # 轉成百分比，保留兩位小數 (例如 0.1234 -> 12.34%)
            .background_gradient(cmap='RdYlGn', vmin=-0.3, vmax=0.3) # 加上紅綠色階 (虧損紅，獲利綠)
            .highlight_null(color='grey') # 第一年通常是 NaN (因為沒有前一年可比)，標示灰色
        )

        st.subheader("📈 趨勢圖表")
        st.line_chart(result_df)

else:
    st.info("👈 請在上方選擇至少一支股票以查看數據")
