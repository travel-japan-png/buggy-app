import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from streamlit_autorefresh import st_autorefresh

# --- 1. 基本設定 & 自動更新 ---
st.set_page_config(page_title="バギーツアー管理", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

conn = st.connection("gsheets", type=GSheetsConnection)

def load_and_calculate():
    try:
        raw_df = conn.read(ttl=0)
    except Exception as e:
        st.error(f"メインシートの読み込みに失敗: {e}")
        st.stop()

    # 在庫設定の読み込み
    default_stock = {
        "9:00": [3, 3], "9:30": [3, 3], "10:00": [3, 3], "10:30": [3, 3],
        "14:00": [3, 3], "14:30": [3, 3], "15:00": [3, 3]
    }
    time_stocks = default_stock.copy()
    try:
        stock_df = conn.read(worksheet="在庫設定", ttl=0)
        if not stock_df.empty:
            for _, row in stock_df.iterrows():
                t_str = str(row['開始時間']).strip()
                time_stocks[t_str] = [int(row['2人乗り']), int(row['1人乗り'])]
    except:
        pass

    df = raw_df.copy()
    
    # 状況列の処理（チェックイン列がある場合は移行）
    if '状況' not in df.columns:
        if 'チェックイン' in df.columns:
            df['状況'] = df['チェックイン'].apply(lambda x: "✅受付済" if x == True else "未受付")
        else:
            df['状況'] = "未受付"
    
    df['状況'] = df['状況'].fillna("未受付")

    # 必須列の型変換
    num_cols = ['大人人数', '小人人数', '総販売金額']
    for col in num_cols:
        if col not in df.columns: df[col] = 0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    
    if '開始時間' not in df.columns: df['開始時間'] = ""
    if 'ステータス' not in df.columns: df['ステータス'] = "予約確定"

    # 車両計算ロジック
    def calc_logic(row):
        try:
            t = int(row['大人人数']) + int(row['小人人数'])
            r = int(row['総販売金額'])
            if t <= 0: return 0, 0
            d = max(0, int(round((r - (500 * t)) / 4000)))
            p = max(0, t - d)
            return d, p
        except: return 0, 0

    calc_results = df.apply(calc_logic, axis=1)
    df['_s2_req'] = [x[1] for x in calc_results]
    df['_s1_req'] = [max(0, x[0] - x[1]) for x in calc_results]
    
    df['使用車両'] = df.apply(lambda row: 
        (f"【2人】{int(row['_s2_req'])}台 " if row['_s2_req'] > 0 else "") + \
        (f"【1人】{int(row['_s1_req'])}台" if row['_s1_req'] > 0 else ""), axis=1)
    
    df['人数'] = df['大人人数'].astype(str) + "大 " + df['小人人数'].astype(str) + "小"
    
    if '開始時間' in df.columns:
        df['temp_time'] = pd.to_datetime(df['開始時間'], errors='coerce')
        df = df.sort_values(by='temp_time', na_position='last').drop(columns=['temp_time'])
        
    return df, time_stocks

full_df, time_stocks = load_and_calculate()

# --- 2. メイン表示 ---
st.title("🚜 バギーツアー受付・車両管理")

if st.button("🔄 最新の情報に更新"):
    st.cache_data.clear()
    st.rerun()

# --- 3. 予約編集
