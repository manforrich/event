import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import timedelta

st.set_page_config(page_title="事件驅動分析", layout="wide")
st.title("📅 特斯拉「利多出盡」事件回測")

# --- 1. 設定事件日曆 (這是量化的靈魂) ---
# 這裡手動輸入過去幾年 TSLA 的大事記 (財報、股東會、發布會)
# 你可以自己隨時擴充這個列表
default_events = """
2024-10-10, Robotaxi Event (We, Robot)
2024-07-23, Q2 財報
2024-06-13, 2024 股東大會
2024-04-23, Q1 財報
2024-01-24, Q4 2023 財報
2023-11-30, Cybertruck 交車發布會
2023-10-18, Q3 財報
2023-07-19, Q2 財報
2023-05-16, 2023 股東大會
2023-04-19, Q1 財報
2023-03-01, Investor Day 2023
"""

st.sidebar.header("⚙️ 參數設定")
ticker = st.sidebar.text_input("股票代碼", "TSLA")
event_input = st.sidebar.text_area("輸入事件列表 (格式: YYYY-MM-DD, 事件名稱)", default_events, height=250)

# 設定觀察天數
pre_days = st.sidebar.slider("觀察前 N 天 (醞釀期)", 1, 20, 10)
post_days = st.sidebar.slider("觀察後 N 天 (出盡期)", 1, 20, 5)

# --- 核心分析函數 ---
def analyze_events(ticker, events_text, pre_window, post_window):
    # 1. 抓取股價
    df = yf.download(ticker, period="5y", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # 處理輸入的文字轉成列表
    event_list = []
    for line in events_text.strip().split('\n'):
        if ',' in line:
            parts = line.split(',')
            date_str = parts[0].strip()
            name = parts[1].strip()
            event_list.append({'Date': pd.to_datetime(date_str), 'Event': name})
    
    results = []
    
    for e in event_list:
        event_date = e['Date']
        
        # 找最接近的交易日 (因為事件日可能是假日)
        if event_date not in df.index:
            # 往後找最近的交易日
            temp_df = df[df.index > event_date]
            if temp_df.empty: continue # 資料不足
            target_date = temp_df.index[0]
        else:
            target_date = event_date
            
        try:
            # 取得該日期的位置索引 (Integer Location)
            idx = df.index.get_loc(target_date)
            
            # 確保前後有足夠的資料
            if idx < pre_window or idx + post_window >= len(df):
                continue
                
            # 計算前 N 天漲跌幅 (Pre-Run)
            price_event = df['Close'].iloc[idx]
            price_pre = df['Close'].iloc[idx - pre_window]
            pre_return = ((price_event - price_pre) / price_pre) * 100
            
            # 計算後 N 天漲跌幅 (Post-Drop) -> 這就是你要驗證的「利多出盡」
            price_post = df['Close'].iloc[idx + post_window]
            post_return = ((price_post - price_event) / price_event) * 100
            
            results.append({
                "日期": target_date.strftime('%Y-%m-%d'),
                "事件名稱": e['Event'],
                f"前{pre_window}天漲幅(%)": round(pre_return, 2),
                f"後{post_window}天漲幅(%)": round(post_return, 2),
                "利多出盡?": "✅ 是" if post_return < 0 else "❌ 否"
            })
            
        except Exception as ex:
            continue
            
    return pd.DataFrame(results)

# --- 執行分析 ---
if st.button("🚀 開始分析"):
    res_df = analyze_events(ticker, event_input, pre_days, post_days)
    
    if not res_df.empty:
        # 1. 總體統計
        avg_pre = res_df[f"前{pre_days}天漲幅(%)"].mean()
        avg_post = res_df[f"後{post_days}天漲幅(%)"].mean()
        win_rate = (res_df["利多出盡?"] == "✅ 是").mean() * 100
        
        c1, c2, c3 = st.columns(3)
        c1.metric(f"事件前 {pre_days} 天平均漲幅", f"{avg_pre:.2f}%")
        c2.metric(f"事件後 {post_days} 天平均漲幅", f"{avg_post:.2f}%")
        c3.metric("利多出盡發生率 (後續下跌機率)", f"{win_rate:.1f}%")
        
        # 2. 詳細數據表格
        st.subheader("📋 個別事件詳細數據")
        st.dataframe(res_df.style.applymap(lambda x: 'color: red' if '是' in str(x) else 'color: green', subset=['利多出盡?']), use_container_width=True)
        
        # 3. 視覺化
        st.subheader("📊 事件前後漲跌幅對比")
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=res_df['日期'] + " (" + res_df['事件名稱'] + ")",
            y=res_df[f"前{pre_days}天漲幅(%)"],
            name=f"前 {pre_days} 天 (預期)",
            marker_color='green'
        ))
        
        fig.add_trace(go.Bar(
            x=res_df['日期'] + " (" + res_df['事件名稱'] + ")",
            y=res_df[f"後{post_days}天漲幅(%)"],
            name=f"後 {post_days} 天 (現實)",
            marker_color='red'
        ))
        
        fig.update_layout(title="Buy the Rumor (綠), Sell the News (紅)", barmode='group')
        st.plotly_chart(fig, use_container_width=True)
        
        st.info("""
        **如何利用這個結果？**
        1. **避開下跌段：** 如果數據顯示「利多出盡率」很高 (例如 > 70%)，那麼在未來重大事件發布前一天，**先獲利了結 (Sell Call / Sell Stock)** 是期望值最高的策略。
        2. **反向操作：** 激進者可以在事件當天收盤前 **買入 Put** 或 **做空**，博取那一段高機率的修正。
        """)
        
    else:
        st.warning("無數據，請檢查事件日期格式。")
