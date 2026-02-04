import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from streamlit_autorefresh import st_autorefresh

# --- 1. 合言葉チェック ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True
    def password_entered():
        if st.session_state["password_input"] == "your-password-123":
            st.session_state["password_correct"] = True
            del st.session_state["password_input"]
        else:
            st.session_state["password_correct"] = False
    if not st.session_state.get("password_correct", False):
        st.title("🔒 認証が必要です")
        st.text_input("合言葉を入力してください", type="password", on_change=password_entered, key="password_input")
        return False
    return True

if "password_correct" not in st.session_state:
    st.session_state["password_correct"] = False
if not check_password():
    st.stop()

# --- 2. 基本設定 & 自動更新 ---
st.set_page_config(page_title="バギーツアー管理", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

conn = st.connection("gsheets", type=GSheetsConnection)

def load_all_data():
    try:
        df = conn.read(ttl=0)
    except Exception:
        st.error("データの読み込みに失敗しました。")
        st.stop()
    if 'チェックイン' not in df.columns:
        df['チェックイン'] = False
    df['チェックイン'] = df['チェックイン'].fillna(False).astype(bool)
    cols = ['チェックイン'] + [c for c in df.columns if c != 'チェックイン']
    df = df[cols]
    
    s2_stock, s1_stock = 3, 3 
    try:
        stock_df = conn.read(worksheet="在庫設定", ttl=0)
        if not stock_df.empty:
            s2_stock = int(stock_df.iloc[0]['2人乗り'])
            s1_stock = int(stock_df.iloc[0]['1人乗り'])
    except:
        pass
    return df, s2_stock, s1_stock

df_raw, stock_2s, stock_1s = load_all_data()

# --- 3. メイン画面表示 ---
col_t1, col_t2 = st.columns([3, 1])
with col_t1:
    st.title("🚜 車両割当 & 受付管理")
with col_t2:
    st.write("") 
    if st.button("🔄 最新の情報に更新", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.sidebar.header("⚙️ 車両在庫 (同期中)")
st.sidebar.metric("2人乗り在庫", f"{stock_2s} 台")
st.sidebar.metric("1人乗り在庫", f"{stock_1s} 台")

# --- 4. 計算ロジック ---
def calculate_details(df):
    df = df.copy()
    # 必須列の確保
    for col in ['開始時間', '顧客', '大人人数', '小人人数', '総販売金額', 'ステータス']:
        if col not in df.columns: df[col] = ""
    
    df['大人人数'] = pd.to_numeric(df['大人人数'], errors='coerce').fillna(0).astype(int)
    df['小人人数'] = pd.to_numeric(df['小人人数'], errors='coerce').fillna(0).astype(int)
    
    # 時間順ソート
    if '開始時間' in df.columns:
        df['temp_time'] = pd.to_datetime(df['開始時間'], errors='coerce')
        df = df.sort_values(by='temp_time', na_position='last').drop(columns=['temp_time'])
    
    # 【車両判定ロジック】
    # 総額 = (運転手台数 * 4500) + (同乗者数 * 500)  ※保険料込み単価から逆算
    # ここから、必ず2人乗りが必要な数(s2)と、1人乗りで済む数(s1)を導出
    total_ppl = df['大人人数'] + df['小人人数']
    revenue = pd.to_numeric(df['総販売金額'], errors='coerce').fillna(0)
    
    # 運転が必要な台数 (x)
    # 4000x + 500 * (大人+小人) = 総額  => x = (総額 - 500*(大人+小人)) / 4000
    drivers = ((revenue - (500 * total_ppl)) / 4000).apply(lambda x: int(round(x)) if x > 0 else 0)
    passengers = (total_ppl - drivers).apply(lambda x: int(x) if x > 0 else 0)
    
    # 基本の必要台数
    df['_s2'] = passengers # 同乗者がいる＝必ず2人乗り
    df['_s1'] = (drivers - passengers).clip(lower=0) # 運転手のみ＝1人乗り(または余った2人乗り)
    
    df['使用車両'] = df.apply(lambda row: 
        (f"【2人】{int(row['_s2'])}台 " if row['_s2'] > 0 else "") + 
        (f"【1人】{int(row['_s1'])}台" if row['_s1'] > 0 else ""), axis=1)
    
    df.insert(0, '状況', "未受付")
    df.loc[df['チェックイン'] == True, '状況'] = "✅受付済"
    return df

st.subheader("📋 予約入力・受付編集")
edited_df = st.data_editor(df_raw, num_rows="dynamic", use_container_width=True,
                           column_config={"チェックイン": st.column_config.CheckboxColumn("チェックイン", width="small")},
                           key="editor")

if st.button("💾 変更を保存して全員に共有", type="primary", use_container_width=True):
    conn.update(data=edited_df)
    st.cache_data.clear()
    st.success("保存完了！")
    st.rerun()

# --- 5. 結果表示 & 振替適用 ---
if not edited_df.empty:
    res_df = calculate_details(edited_df)
    active_df = res_df[res_df['ステータス'] != 'キャンセル'].copy()
    
    st.divider()
    st.subheader("📊 時間帯別の稼働合計 (1人乗り不足は2人乗りへ振替)")
    
    summary = active_df.groupby("開始時間").agg({"_s2": "sum", "_s1": "sum"})
    
    if not summary.empty:
        cols = st.columns(4)
        for i, time in enumerate(summary.index):
            if str(time).strip() in ["", "NaT"]: continue
            
            s2_req = int(summary.loc[time, '_s2'])
            s1_req = int(summary.loc[time, '_s1'])
            
            # 【振替ロジック】 1人乗りが足りない分を2人乗りに加算
            s1_overflow = max(0, s1_req - stock_1s)
            final_s1 = s1_req - s1_overflow
            final_s2 = s2_req + s1_overflow
            
            with cols[i % 4]:
                st.write(f"🕒 **{time}**")
                # 2人乗り在庫チェック
                s2_color = "normal" if final_s2 <= stock_2s else "inverse"
                st.metric("2人乗り使用", f"{final_s2} / {stock_2s}", delta=int(stock_2s - final_s2), delta_color=s2_color)
                st.metric("1人乗り使用", f"{final_s1} / {stock_1s}", delta=int(stock_1s - final_s1))
                if s1_overflow > 0:
                    st.caption(f"💡 1人乗り不足分 {s1_overflow}台を2人乗りで対応")

    st.subheader("🔍 現場用・当日車両割当リスト")
    display_cols = ['状況', '開始時間', '顧客', '大人人数', '小人人数', '使用車両']
    if not active_df.empty:
        def highlight_rows(row):
            return ['background-color: #e6f3ff' if row['状況'] == "✅受付済" else '' for _ in row]
        st.dataframe(active_df[display_cols].style.apply(highlight_rows, axis=1), use_container_width=True, hide_index=True)


