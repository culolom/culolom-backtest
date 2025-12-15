# 檔案位置：scripts/update_momentum.py
import pandas as pd
import json
import os
import glob
import datetime

# ==========================================
# ⚙️ 路徑設定
# ==========================================
# GitHub Actions 會在專案「根目錄」執行此腳本
# 所以直接指向 "data" 即可，不用寫 "../data"
DATA_DIR = "data"           
OUTPUT_FILE = "momentum.json" # JSON 產出在根目錄，方便 WordPress 讀取

# 指定要排行的標的 (若要全部跑，可設為 [])
TARGET_SYMBOLS = ["0050.TW", "GLD", "QQQ", "SPY", "VT", "ACWI", "VOO", 
                  "VXUS", "VEA", "VWO", "BOXX", "VTI", "BIL", "IEF", "IEI"]

def load_price_from_csv(file_path):
    """讀取 CSV 並標準化格式"""
    try:
        df = pd.read_csv(file_path)
        
        # 處理日期欄位 (相容不同格式)
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date").sort_index()
        else:
            df.iloc[:, 0] = pd.to_datetime(df.iloc[:, 0])
            df = df.set_index(df.columns[0]).sort_index()

        # 優先找 Adj Close，沒有才找 Close
        col_price = "Adj Close" if "Adj Close" in df.columns else "Close"
        if col_price not in df.columns:
            return None
            
        return df[col_price].astype(float)
    except Exception as e:
        print(f"❌ 讀取錯誤 {file_path}: {e}")
        return None

def main():
    print("🚀 開始執行每月動能更新 (使用 data/ CSV)...")
    
    results = []
    
    # 確保資料夾存在
    if not os.path.exists(DATA_DIR):
        print(f"❌ 找不到資料夾：{DATA_DIR} (請確認執行目錄是否在 Repo 根目錄)")
        return

    csv_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
    
    if not csv_files:
        print("⚠️ data 資料夾內無 CSV 檔案。")
        return

    today = pd.Timestamp.today()

    for file_path in csv_files:
        filename = os.path.basename(file_path)
        symbol = filename.replace(".csv", "")
        
        # 過濾標的
        if TARGET_SYMBOLS and symbol not in TARGET_SYMBOLS:
            continue

        series = load_price_from_csv(file_path)
        if series is None or series.empty: continue

        try:
            # --- 計算邏輯 ---
            current_price = series.iloc[-1]
            current_date = series.index[-1]
            
            # 檢查資料新鮮度 (超過 35 天沒更新視為過期)
            if (today - current_date).days > 35:
                print(f"⚠️ {symbol} 資料過舊 ({current_date.date()})，跳過。")
                continue

            # 計算 SMA 200
            ma200 = series.rolling(200).mean().iloc[-1] if len(series) >= 200 else 0
            
            # 計算 12 個月動能
            one_year_ago = current_date - pd.DateOffset(months=12)
            # 在 Series 中找最接近一年前的日期
            idx_loc = series.index.get_indexer([one_year_ago], method='nearest')[0]
            
            # 確保找到的日期沒有差太遠 (例如資料有斷層)
            found_date = series.index[idx_loc]
            if abs((found_date - one_year_ago).days) > 30:
                 print(f"⚠️ {symbol} 找不到一年前的資料，跳過。")
                 continue
                 
            price_12m_ago = series.iloc[idx_loc]
            momentum = (current_price - price_12m_ago) / price_12m_ago
            
            results.append({
                "代號": symbol,
                "12月累積報酬": round(momentum * 100, 2),
                "收盤價": round(current_price, 2),
                "200SMA": round(ma200, 2)
            })
            print(f"✅ {symbol} 完成: {round(momentum * 100, 2)}%")
            
        except Exception as e:
            print(f"❌ {symbol} 計算失敗: {e}")
            continue

    # 排序與存檔
    if results:
        df = pd.DataFrame(results)
        df = df.sort_values("12月累積報酬", ascending=False)
        
        output_data = {
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d"),
            "data": df.to_dict(orient="records")
        }
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
        print(f"🎉 JSON 生成成功：{OUTPUT_FILE}")
    else:
        print("⚠️ 無有效數據。")

if __name__ == "__main__":
    main()
