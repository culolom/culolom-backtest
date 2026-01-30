import pandas as pd
import numpy as np
import json
import os
import glob
import datetime

# ==========================================
# ⚙️ 設定區
# ==========================================
DATA_DIR = "data"             
OUTPUT_FILE = "momentum.json"

# 指定要排行的標的
TARGET_SYMBOLS = ["0050.TW", "GLD", "QQQ", "SPY", "VT", "ACWI", "VOO", 
                  "VXUS", "VEA", "VWO", "BOXX", "VTI", "BIL", "IEF", "IEI"]

def load_price_from_csv(file_path):
    """
    讀取 CSV 並標準化格式
    回傳: Series (Index=Date, Value=Price)
    """
    try:
        df = pd.read_csv(file_path)
        
        # 處理日期索引
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date").sort_index()
        else:
            # 嘗試把第一欄當作日期
            df.iloc[:, 0] = pd.to_datetime(df.iloc[:, 0])
            df = df.set_index(df.columns[0]).sort_index()

        # 優先使用 Adj Close，沒有才用 Close
        col_price = "Adj Close" if "Adj Close" in df.columns else "Close"
        if col_price not in df.columns:
            return None
            
        return df[col_price].astype(float)
    except Exception as e:
        print(f"❌ 讀取錯誤 {file_path}: {e}")
        return None

def main():
    print("🚀 開始執行每月動能更新 (計算 200MA 乖離率與 1M/12M 報酬)...")
    
    results = []
    
    # 檢查資料夾是否存在
    if not os.path.exists(DATA_DIR):
        print(f"❌ 找不到資料夾：{DATA_DIR}")
        return

    csv_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
    
    if not csv_files:
        print("⚠️ data 資料夾內無 CSV 檔案。")
        return

    today = pd.Timestamp.today()

    for file_path in csv_files:
        # 從檔名取得代號 (例如 GLD.csv -> GLD)
        filename = os.path.basename(file_path)
        symbol = filename.replace(".csv", "")
        
        # 如果有指定名單，非名單內的跳過
        if TARGET_SYMBOLS and symbol not in TARGET_SYMBOLS:
            continue

        series = load_price_from_csv(file_path)
        if series is None or series.empty: continue

        try:
            # --- 1. 取得基本數據 ---
            current_price = series.iloc[-1]
            current_date = series.index[-1]
            
            # 檢查資料新鮮度 (超過35天沒更新視為過期)
            if (today - current_date).days > 35:
                print(f"⚠️ {symbol} 資料過舊 ({current_date.date()})，跳過。")
                continue

            # --- 2. 計算 200日均線 (SMA) ---
            ma200 = series.rolling(200).mean().iloc[-1] if len(series) >= 200 else 0
            
            # --- 3. 計算 12 個月動能 (12-Month Momentum) ---
            one_year_ago = current_date - pd.DateOffset(months=12)
            idx_loc_12m = series.index.get_indexer([one_year_ago], method='nearest')[0]
            found_date_12m = series.index[idx_loc_12m]
            
            # 如果上市時間不足 12 個月，跳過
            if abs((found_date_12m - one_year_ago).days) > 30:
                 print(f"⚠️ {symbol} 找不到一年前的資料 (上市時間不足)，跳過。")
                 continue
                 
            price_12m_ago = series.iloc[idx_loc_12m]
            momentum_return_12m = (current_price - price_12m_ago) / price_12m_ago

            # --- 4. 計算 1 個月報酬 (1-Month Return) --- 新增的部分
            one_month_ago = current_date - pd.DateOffset(months=1)
            idx_loc_1m = series.index.get_indexer([one_month_ago], method='nearest')[0]
            price_1m_ago = series.iloc[idx_loc_1m]
            momentum_return_1m = (current_price - price_1m_ago) / price_1m_ago
            
            # --- 5. 計算乖離率 (Bias) ---
            if ma200 > 0:
                bias_val = (current_price - ma200) / ma200
            else:
                bias_val = 0

            # --- 6. 存入結果 ---
            results.append({
                "代號": symbol,
                "12月累積報酬": round(momentum_return_12m * 100, 2),
                "1月累積報酬": round(momentum_return_1m * 100, 2), # 新增
                "收盤價": round(current_price, 2),
                "200SMA": round(ma200, 2),
                "乖離率": round(bias_val * 100, 2)
            })
            
            print(f"✅ {symbol} | 12M: {round(momentum_return_12m * 100, 2)}% | 1M: {round(momentum_return_1m * 100, 2)}% | 乖離率: {round(bias_val * 100, 2)}%")
            
        except Exception as e:
            print(f"❌ {symbol} 計算失敗: {e}")
            continue

    # --- 輸出 JSON ---
    if results:
        df = pd.DataFrame(results)
        
        # 依照「12月累積報酬」高低排序
        df = df.sort_values("12月累積報酬", ascending=False)
        
        output_data = {
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d"),
            "data": df.to_dict(orient="records")
        }
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
            
        print(f"🎉 JSON 生成成功：{OUTPUT_FILE}")
    else:
        print("⚠️ 無有效數據，未生成檔案。")

if __name__ == "__main__":
    main()
