import os
import pandas as pd
from datetime import datetime

def calculate_period_returns():
    # 1. 自動定位專案路徑
    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(current_dir)
    data_dir = os.path.join(base_dir, 'data')
    
    # 比較的五檔目標 ETF
    symbols = ['0050.TW', '00631L.TW', '00675L.TW', '00663L.TW', '00685L.TW']
    
    period_performance = {}

    # 2. 逐一讀取 CSV 並計算各期間報酬率
    for sym in symbols:
        csv_path = os.path.join(data_dir, f"{sym}.csv")
        if not os.path.exists(csv_path):
            print(f"警告：找不到 {csv_path}，跳過此檔案。")
            continue
            
        try:
            df = pd.read_csv(csv_path)
            df.columns = df.columns.str.strip()
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True)
            df.sort_index(inplace=True)
            
            # 剔除重複日期，避免時間序列對齊時發生錯誤
            df = df[~df.index.duplicated(keep='first')]
            
            if df.empty:
                print(f"警告：{sym} 的資料為空，跳過。")
                continue

            # --- 【修正】檢查最新報價是否為空值，若是則往前尋找 ---
            # 找出 'Close' 欄位中最後一個非空值的索引與數值
            valid_closes = df['Close'].dropna()
            if valid_closes.empty:
                print(f"警告：{sym} 沒有任何有效的收盤價，跳過。")
                continue
                
            latest_date = valid_closes.index[-1]
            latest_price = valid_closes.iloc[-1]
            
            # 如果最新日期跟 DataFrame 的最後一筆不一致，說明有往前找
            if latest_date != df.index[-1]:
                print(f"提示：{sym} 最新日期 {df.index[-1].strftime('%Y-%m-%d')} 報價為空，已自動往前採用 {latest_date.strftime('%Y-%m-%d')} 的報價。")
            # ----------------------------------------------------

            first_date = df.index[0] 
            
            # 定義精準回推的 9 大時間區間（以最終決定的 latest_date 為基準回推）
            intervals = {
                '近一週': latest_date - pd.Timedelta(weeks=1),
                '近一月': latest_date - pd.DateOffset(months=1),
                '近三月': latest_date - pd.DateOffset(months=3),
                '今年以來': datetime(latest_date.year, 1, 1),
                '近六月': latest_date - pd.DateOffset(months=6),
                '近一年': latest_date - pd.DateOffset(years=1),
                '近兩年': latest_date - pd.DateOffset(years=2),
                '近三年': latest_date - pd.DateOffset(years=3),
                '近五年': latest_date - pd.DateOffset(years=5)
            }
            
            sym_returns = {}
            for period_name, target_date in intervals.items():
                # 安全機制：若回推日期比該 ETF 上市日還早，直接歸為 N/A
                if target_date < first_date:
                    sym_returns[period_name] = "N/A"
                    continue
                    
                try:
                    # 將 method 改為 'pad'，精準比對歷史交易日
                    idx_pos = df.index.get_indexer([target_date], method='pad')[0]
                    if idx_pos == -1:
                        sym_returns[period_name] = "N/A"
                        continue
                        
                    available_date = df.index[idx_pos]
                    base_price = df.loc[available_date, 'Close']
                    
                    if isinstance(base_price, pd.Series):
                        base_price = base_price.iloc[0]
                        
                    # 如果基準日價格也是空值，同樣往前找
                    if pd.isna(base_price):
                        valid_base_df = df.loc[:available_date, 'Close'].dropna()
                        if not valid_base_df.empty:
                            base_price = valid_base_df.iloc[-1]
                        else:
                            sym_returns[period_name] = "N/A"
                            continue
                            
                    ret = ((latest_price / base_price) - 1) * 100
                    sym_returns[period_name] = round(ret, 2)
                except Exception:
                    sym_returns[period_name] = "N/A"
                    
            period_performance[sym.replace('.TW', '')] = sym_returns
            
        except Exception as e:
            print(f"處理 {sym} 時發生非預期錯誤: {e}")
            continue

    if not period_performance:
        print("錯誤：沒有任何成功的績效數據可以產出。")
        return

    # 轉化為整合績效 DataFrame
    df_perf = pd.DataFrame(period_performance)
    
    # 3. 建立自適應的 HTML 基金績效表格
    columns_order = ['0050', '00631L', '00675L', '00663L', '00685L']
    periods_order = ['近一週', '近一月', '近三月', '今年以來', '近六月', '近一年', '近兩年', '近三年', '近五年']
    
    table_html = f"""
    <div style="overflow-x:auto; margin-bottom: 25px; -webkit-overflow-scrolling: touch;">
        <table style="width:100%; border-collapse: collapse; text-align: center; background: #ffffff; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border-radius: 8px; overflow: hidden; min-width: 620px; font-family: -apple-system, BlinkMacSystemFont, sans-serif;">
            <thead>
                <tr style="background-color: #2c3e50; color: #ffffff; font-size: 14px;">
                    <th style="padding: 13px; text-align: left; font-weight: 600;">期間 / 績效</th>
    """
    for col in columns_order:
        table_html += f'<th style="padding: 13px; font-weight: 600;">{col}</th>'
    table_html += "</tr></thead><tbody>"
    
    for period in periods_order:
        table_html += '<tr style="border-bottom: 1px solid #f1f2f6; font-size: 13px;">'
        table_html += f'<td style="padding: 11px; text-align: left; font-weight: 600; background-color: #fafafa; color: #34495e;">{period}</td>'
        
        for col in columns_order:
            if col in df_perf.columns and period in df_perf.index:
                val = df_perf.loc[period, col]
            else:
                val = "N/A"
                
            if val == "N/A" or pd.isna(val):
                table_html += '<td style="padding: 11px; color: #95a5a6;">-</td>'
            else:
                # 正報酬為紅、負報酬為綠
                color_style = "color: #d63031; font-weight: 600;" if val >= 0 else "color: #2ed573; font-weight: 600;"
                table_html += f'<td style="padding: 11px; {color_style}">{val:+.2f}%</td>'
        table_html += '</tr>'
    table_html += "</tbody></table></div>"

    # 4. 拼裝網頁 (已移除 Plotly 圖表)
    full_page_html = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ margin: 0; padding: 20px; background-color: #f8f9fa; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }}
            .report-box {{ max-width: 980px; margin: 0 auto; }}
            h2 {{ color: #2c3e50; font-size: 18px; margin-bottom: 15px; font-weight: 600; }}
        </style>
    </head>
    <body>
        <div class="report-box">
            <h2>0050 與四大正2 ETF 期間績效對比表</h2>
            {table_html}
        </div>
    </body>
    </html>
    """

    # 5. 儲存網頁
    dist_path = os.path.join(base_dir, 'dist')
    os.makedirs(dist_path, exist_ok=True)
    
    output_path = os.path.join(dist_path, 'tw_0050_leverage.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_page_html)
    print("✨ tw_0050_leverage.html 績效表格網頁生成成功！（已移除圖表）")

if __name__ == '__main__':
    calculate_period_returns()
