# 檔案位置：scripts/update_momentum.py
import pandas as pd
import numpy as np  # 新增: 用於計算數學公式
import json
import os
import glob
import datetime

# ==========================================
# ⚙️ 路徑設定
# ==========================================
DATA_DIR = "data"            
OUTPUT_FILE = "momentum.json"

# 指定要排行的標的
TARGET_SYMBOLS = ["0050.TW", "XAUUSD=X", "QQQ", "SPY", "VT", "ACWI", "VOO", 
                  "VXUS", "VEA", "VWO", "BOXX", "VTI", "BIL", "IEF", "IEI"]

def load_price_from_csv(file_path):
    """讀取 CSV 並標準化格式"""
    try:
        df = pd.read_csv(file_path)
        
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date").sort_index()
        else:
            df.iloc[:, 0] = pd.to_datetime(df.iloc[:, 0])
            df = df.set_index(df.columns[0]).sort_index()

        col_price = "Adj Close" if "Adj Close" in df.columns else "Close"
        if col_price not in df.columns:
            return None
            
        return df[col_price].astype(float)
    except Exception as e:
        print(f"❌ 讀取錯誤 {file_path}: {e}")
        return None

def main():
    print("🚀 開始執行每月動能更新 (含動能品質計算)...")
    
    results = []
    
    if not os.path.exists(DATA_DIR):
        print(f"❌ 找不到資料夾：{DATA_DIR}")
        return

    csv_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
    
    if not csv_files:
        print("⚠️ data 資料夾內無 CSV 檔案。")
        return

    today = pd.Timestamp.today()

    for file_path in csv_files:
        filename = os.path.basename(file_path)
        symbol = filename.replace(".csv", "")
        
        if TARGET_SYMBOLS and symbol not in TARGET_SYMBOLS:
            continue

        series = load_price_from_csv(file_path)
        if series is None or series.empty: continue

        try:
            # --- 基本數據 ---
            current_price = series.iloc[-1]
            current_date = series.index[-1]
            
            # 檢查資料新鮮度
            if (today - current_date).days > 35:
                print(f"⚠️ {symbol} 資料過舊 ({current_date.date()})，跳過。")
                continue

            # 計算 SMA 200
            ma200 = series.rolling(200).mean().iloc[-1] if len(series) >= 200 else 0
            
            # --- 計算 12 個月動能 (Speed) ---
            one_year_ago = current_date - pd.DateOffset(months=12)
            idx_loc = series.index.get_indexer([one_year_ago], method='nearest')[0]
            found_date = series.index[idx_loc]
            
            if abs((found_date - one_year_ago).days) > 30:
                 print(f"⚠️ {symbol} 找不到一年前的資料，跳過。")
                 continue
                 
            price_12m_ago = series.iloc[idx_loc]
            momentum_return = (current_price - price_12m_ago) / price_12m_ago
            
            # --- 計算動能品質 (Quality) ---
            # 1. 取得過去一年的價格序列
            subset = series.loc[found_date:current_date]
            
            # 2. 計算日報酬與年化波動率 (Annualized Volatility)
            daily_returns = subset.pct_change().dropna()
            # std * sqrt(252) 是標準的年化波動率公式
            volatility = daily_returns.std() * np.sqrt(252)
            
            # 3. 計算原始品質分數 (Risk-Adjusted Return)
            # 避免分母為 0 的保護機制
            raw_quality_score = momentum_return / volatility if volatility > 0 else 0

            results.append({
                "代號": symbol,
                "12月累積報酬": round(momentum_return * 100, 2),
                "收盤價": round(current_price, 2),
                "200SMA": round(ma200, 2),
                "raw_quality": raw_quality_score  # 暫存原始分數，稍後做標準化
            })
            print(f"✅ {symbol} 完成: 報酬 {round(momentum_return * 100, 2)}% | 品質係數 {round(raw_quality_score, 2)}")
            
        except Exception as e:
            print(f"❌ {symbol} 計算失敗: {e}")
            continue

    # --- 排序、標準化與存檔 ---
    if results:
        df = pd.DataFrame(results)
        
        # 1. 計算標準化分數 (0-100 分)
        # 找出這批名單中的最高分與最低分
        max_q = df['raw_quality'].max()
        min_q = df['raw_quality'].min()
        
        # 防止 max 等於 min (例如只有一筆資料) 導致除以零
        if max_q == min_q:
            df['動能品質'] = 50.0 # 預設中位數
        else:
            # Min-Max Scaling 公式： (x - min) / (max - min) * 100
            df['動能品質'] = ((df['raw_quality'] - min_q) / (max_q - min_q) * 100).round(1)

        # 2. 移除暫存欄位
        df = df.drop(columns=['raw_quality'])

        # 3. 依照「12月累積報酬」排序 (還是以速度為主要排行依據，品質為輔助參考)
        df = df.sort_values("12月累積報酬", ascending=False)
        
        output_data = {
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d"),
            "data": df.to_dict(orient="records")
        }
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
        print(f"🎉 JSON 生成成功 (含動能品質)：{OUTPUT_FILE}")
    else:
        print("⚠️ 無有效數據。")

if __name__ == "__main__":
    main()
