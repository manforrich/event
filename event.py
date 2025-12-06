import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="事件驅動分析 Pro", layout="wide")
st.title("📅 事件驅動量化分析 (Auto-Fetch 版)")

# --- 💡 內建特斯拉大事件資料庫 (手動維護這些特殊日最準) ---
# 包含：股東會(AGM), Battery Day, AI Day, Investor Day
TSLA_SPECIAL_EVENTS = [
    "2025-11-06, 2025 年度股東大會",
    "2024-06-13, 2024 年度股東大會",
    "2023-05-16, 2023 年度股東大會",
    "2023-03-01, Investor Day 2023 (宏圖計畫3)",
    "2022-09-30, AI Day 2022 (Optimus)",
    "2022-08-04, 2022 年度股東大會",
    "2022-04-07, Giga Texas 開幕 (Cyber Rodeo)",
    "2021-10-07, 2021 年度股東大會",
    "2021-08-19, AI Day 2021",
    "2020-09-22, Battery Day & 股東會"
]

# --- 核心功能：自動抓取 ---
def get_auto_events(ticker):
    events_list = []
    status_log = []
    
    try:
        stock = yf.Ticker(ticker)
        
        # 1. 自動抓取財報日 (Earnings)
        # yfinance 的 get_earnings_dates() 通常能抓到近幾年的
        try:
            earnings = stock.get_earnings_dates(limit=20) # 抓最近 20 次
            if earnings is not None and not earnings.empty:
                for date in earnings.index:
                    # 格式化日期 YYYY-MM-DD
                    date_str = date.strftime('%Y-%m-%d')
                    # 判斷是過去還是未來
                    if date.tz_localize(None) < datetime.now():
                         events_list.append(f"{date_str}, {ticker} 財報發布")
                status_log.append(f"✅ 成功抓取 {len(earnings)} 筆財報日期")
            else:
                status_log.append("⚠️ 無法透過 API 取得財報日期 (可能來源中斷)")
        except Exception as e:
            status_log.append(f"⚠️ 財報抓取錯誤: {str(e)}")

        # 2. 如果是 TSLA，自動合併特殊事件
        if ticker.upper() == "TSLA":
            events_list.extend(TSLA_SPECIAL_EVENTS)
            status_log.append(f"✅ 已合併 {len(TSLA_SPECIAL_EVENTS)} 筆特斯拉特殊事件 (股東會/AI Day)")
            
    except Exception as e:
        status_log.append(f"❌ 發生錯誤: {str(e)}")
        
    # 排序並轉成字串
    events_list.sort(reverse=True)
    return "\n".join(events_list), status_log

# --- 側邊欄 ---
st.sidebar.header("⚙️ 參數設定")
ticker = st.sidebar.text_input("股票代碼", "TSLA")

# 自動抓取按鈕
if st.sidebar.button("🔄 一鍵自動抓取事件"):
    with st.spinner("正在連線 Yahoo Finance 資料庫..."):
        auto_text, logs = get_auto_events(ticker)
        st.session_state['event_input'] = auto_text
        for log in logs:
            if "✅" in log: st.sidebar.success(log)
            else: st.sidebar.warning(log)

# 初始化 session state
if 'event_input' not in st.session_state:
    st.session_state['event_input'] = "2024-06-13, 2024 股東大會\n2024-04-23, Q1 財報"

event_input = st.sidebar.text_area("事件列表 (可手動修改)", key='event_input', height=300)

pre_days = st.sidebar.slider("觀察前 N 天", 1, 20, 10)
post_days = st.sidebar.slider("觀察後 N 天", 1, 20, 5)

# --- 分析邏輯 (維持原樣) ---
def analyze_events(ticker, events_text, pre_window, post_window):
    df = yf.download(ticker, period="5y", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    event_list = []
    for line in events_text.strip().split('\n'):
        if ',' in line:
            parts = line.split(',')
            event_list.append({'Date': pd.to_datetime(parts[0].strip()), 'Event': parts[1].strip()})
    
    results = []
    for e in event_list:
        event_date = e['Date']
        if event_date not in df.index:
            # 尋找最近交易日
            temp = df[df.index > event_date]
            if temp.empty: continue
            target_date = temp.index[0]
        else:
            target_date = event_date
            
        try:
            idx = df.index.get_loc(target_date)
            if idx < pre_window or idx + post_window >= len(df): continue
            
            price_event = df['Close'].iloc[idx]
            price_pre = df['Close'].iloc[idx - pre_window]
            pre_ret = ((price_event - price_pre) / price_pre) * 100
            
            price_post = df['Close'].iloc[idx + post_window]
            post_ret = ((price_post - price_event) / price_event) * 100
            
            results.append({
                "日期": target_date.strftime('%Y-%m-%d'),
                "事件名稱": e['Event'],
                f"前{pre_window}天漲幅": pre_ret,
                f"後{post_window}天漲幅": post_ret,
                "利多出盡?": "✅ 是" if post_ret < 0 else "❌ 否"
            })
        except: continue
    return pd.DataFrame(results)

if st.button("🚀 開始回測"):
    res_df = analyze_events(ticker, event_input, pre_days, post_days)
    if not res_df.empty:
        avg_post = res_df[f"後{post_days}天漲幅"].mean()
        win_rate = (res_df["利多出盡?"] == "✅ 是").mean() * 100
        
        c1, c2 = st.columns(2)
        c1.metric("事件後平均漲幅", f"{avg_post:.2f}%", help="負數代表平均下跌")
        c2.metric("利多出盡機率", f"{win_rate:.1f}%", help="事件後股價下跌的機率")
        
        st.dataframe(res_df.style.applymap(lambda x: 'color: red' if '是' in str(x) else 'color: green', subset=['利多出盡?']), use_container_width=True)
        
        # 繪圖
        fig = go.Figure()
        fig.add_trace(go.Bar(x=res_df['日期'], y=res_df[f"前{pre_days}天漲幅"], name="前 (預期)", marker_color='green'))
        fig.add_trace(go.Bar(x=res_df['日期'], y=res_df[f"後{post_days}天漲幅"], name="後 (現實)", marker_color='red'))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("無數據")
