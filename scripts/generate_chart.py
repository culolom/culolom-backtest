import os
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

def calculate_period_returns():
    # 1. 自動定位專案路徑（支援任何環境執行）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(current_dir)
    data_dir = os.path.join(base_dir, 'data')
    
    # 比較的五檔目標 ETF
    symbols = ['0050.TW', '00631L.TW', '00675L.TW', '00663L.TW', '00685L.TW']
    
    close_trends = {}
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
            
            # 【重要修正】剔除重複日期，避免時間序列 AsOf 對齊時發生錯誤
            df = df[~df.index.duplicated(keep='first')]
            
            latest_date = df.index[-1]
            latest_price = df['Close'].iloc[-1]
            first_date = df.index[0] 
            
            close_trends[sym] = df['Close']
            
            # 定義精準回推的 9 大時間區間
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
                    idx_pos = df.index.get_indexer([target_date], method='asof')[0]
                    if idx_pos == -1:
                        sym_returns[period_name] = "N/A"
                        continue
                        
                    available_date = df.index[idx_pos]
                    base_price = df.loc[available_date, 'Close']
                    
                    if isinstance(base_price, pd.Series):
                        base_price = base_price.iloc[0]
                        
                    ret = ((latest_price / base_price) - 1) * 100
                    sym_returns[period_name] = round(ret, 2)
                except Exception:
                    sym_returns[period_name] = "N/A"
                    
            period_performance[sym.replace('.TW', '')] = sym_returns
            
        except Exception as e:
            print(f"處理 {sym} 時發生非預期錯誤: {e}")
            continue

    # 轉化為整合績效 DataFrame
    df_perf = pd.DataFrame(period_performance)
    
    # 3. 處理 5 年走勢對比數據（歸一化百分比）
    df_trends = pd.DataFrame(close_trends)
    latest_date_str = df_trends.index[-1].strftime('%Y-%m-%d')
    five_years_ago = df_trends.index[-1] - pd.DateOffset(years=5)
    
    df_trends_5y = df_trends.loc[five_years_ago:]
    df_cum_returns = pd.DataFrame(index=df_trends_5y.index)
    
    for col in df_trends_5y.columns:
        first_valid_idx = df_trends_5y[col].first_valid_index()
        if first_valid_idx is not None:
            base_p = df_trends_5y.loc[first_valid_idx, col]
            df_cum_returns[col] = (df_trends_5y[col] / base_p - 1) * 100

    df_cum_returns = df_cum_returns.round(2)
    
    # 4. 使用 Plotly 繪製 5 年累積走勢響應式圖表
    fig = go.Figure()
    colors = {
        '0050.TW': '#7f8c8d', '00631L.TW': '#e74c3c', '00675L.TW': '#3498db', 
        '00663L.TW': '#2ecc71', '00685L.TW': '#f1c40f'
    }
    
    for col in df_cum_returns.columns:
        display_name = col.replace('.TW', '')
        plot_df = df_cum_returns[col].dropna()  # 剔除未上市前的空值，避免線條斷裂
        fig.add_trace(go.Scatter(
            x=plot_df.index,
            y=plot_df.values,
            mode='lines',
            name=display_name,
            line=dict(width=2, color=colors.get(col, '#000000')),
            hovertemplate='%{x}<br><b>' + display_name + '</b>: %{y}%',
        ))
        
    fig.update_layout(
        title=f"0050 與四大正2 ETF 近五年累積報酬率走勢對比 (至 {latest_date_str})",
        xaxis_title="日期",
        yaxis_title="累積報酬率 (%)",
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=70, b=10),
        height=460
    )

    # 5. 建立自適應的 HTML 基金績效表格
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
                # 台股視覺：正報酬為紅、負報酬為綠
                color_style = "color: #d63031; font-weight: 600;" if val >= 0 else "color: #2ed573; font-weight: 600;"
                table_html += f'<td style="padding: 11px; {color_style}">{val:+.2f}%</td>'
        table_html += '</tr>'
    table_html += "</tbody></table></div>"

    # 6. 拼裝完整的網頁視窗
    chart_html = fig.to_html(include_plotlyjs='cdn', full_html=False)
    full_page_html = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ margin: 0; padding: 5px; background-color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }}
            .report-box {{ max-width: 980px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <div class="report-box">
            {table_html}
            {chart_html}
        </div>
    </body>
    </html>
    """

    # 輸出至根目錄下 dist/index.html
    dist_path = os.path.join(base_dir, 'dist')
    os.makedirs(dist_path, exist_ok=True)
    with open(os.path.join(dist_path, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(full_page_html)
    print("✨ index.html 整合網頁生成成功！")

if __name__ == '__main__':
    calculate_period_returns()
