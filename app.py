import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from streamlit_autorefresh import st_autorefresh

# --- 1. 基本設定 & 自動更新 (3分) ---
# パスワードチェックを削除しました
st.set_page_config(page_title="バギーツアー管理", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

# スプレッドシート接続
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. データの読み込み関数 ---
def load_all_data():
    try:
        df = conn.read(ttl=0)
    except Exception:
        st.error("データの読み込みに失敗しました。")
        st.stop()

    if 'チェックイン' not in df.columns:
        df['チェックイン'] = False
    df['チェックイン'] = df['チェックイン'].fillna(False).astype(bool)
    
    # 編集用画面も使いやすく並び替え
    cols = ['チェックイン'] + [c for c in df.columns if c != 'チェックイン']
    df = df[cols]

    # 在庫データの読み込み (「在庫設定」シート)
    s2_stock, s1_stock = 3, 3 
    try:
        stock_df = conn.read(worksheet="在庫設定", ttl=0)
        if not stock_df.empty:
            s2_stock = int(stock_df.iloc[0]['2人乗り'])
            s1_stock = int(stock_df.iloc[0]['1人乗り'])
    except:
        pass
        
    return df, s2_stock, s1_stock

# データの取得
df_raw, stock_2s, stock_1s = load_all_data()

# --- 3. メイン画面表示 ---
col_t1, col_t2 = st.columns([3, 1])
with col_t1:
    st.title("🚜 バギーツアー受付・車両管理")
with col_t2:
    st.write("") 
    if st.button("🔄 最新の情報に更新", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# サイドバー表示
st.sidebar.header("⚙️ 車両在庫")
st.sidebar.metric("2人乗り在庫", f"{stock_2s} 台")
st.sidebar.metric("1人乗り在庫", f"{stock_1s} 台")

# --- 4. 計算ロジック ---
def calculate_details(df):
    df = df.copy()
    for col in ['開始時間', '顧客', '大人人数', '小人人数', '総販売金額', 'ステータス']:
        if col not in df.columns: df[col] = ""
    
    df['大人人数'] = pd.to_numeric(df['大人人数'], errors='coerce').fillna(0).astype(int)
    df['小人人数'] = pd.to_numeric(df['小人人数'], errors='coerce').fillna(0).astype(int)
    
    if '開始時間' in df.columns:
        df['temp_time'] = pd.to_datetime(df['開始時間'], errors='coerce')
        df = df.sort_values(by='temp_time', na_position='last').drop(columns=['temp_time'])
    
    total = df['大人人数'] + df['小人人数']
    revenue = pd.to_numeric(df['総販売金額'], errors='coerce').fillna(0)
    drivers = ((revenue - (500 * total)) / 4000).apply(lambda x: int(round(x)) if x > 0 else 0)
    passengers = (total - drivers).apply(lambda x: int(x) if x > 0 else 0)
    
    df['使用車両'] = passengers.apply(lambda x: f"【2人】{int(x)}台 " if x > 0 else "") + \
                     (drivers - passengers).clip(lower=0).apply(lambda x: f"【1人】{int(x)}台" if x > 0 else "")
    df['_s2'] = passengers
    df['_s1'] = (drivers - passengers).clip(lower=0)
    
    df.insert(0, '状況', "未受付")
    df.loc[df['チェックイン'] == True, '状況'] = "✅受付済"
    return df

# --- 5. 予約入力・編集 ---
st.subheader("📋 予約編集・チェックイン")
edited_df = st.data_editor(
    df_raw, 
    num_rows="dynamic", 
    use_container_width=True,
    column_config={"チェックイン": st.column_config.CheckboxColumn("チェックイン", width="small")},
    key="editor"
)

if st.button("💾 変更を保存して全員に共有", type="primary", use_container_width=True):
    conn.update(data=edited_df)
    st.cache_data.clear()
    st.success("保存完了！")
    st.rerun()

# --- 6. 結果表示 (項目を絞り込み) ---
if not edited_df.empty:
    res_df = calculate_details(edited_df)
    active_df = res_df[res_df['ステータス'] != 'キャンセル'].copy()
    
    st.divider()
    
    # 時間帯別サマリー
    st.subheader("📊 時間帯別の稼働合計")
    target_times = ["9:00", "9:30", "10:00", "10:30", "14:00", "14:30", "15:00"]
    summary = active_df.groupby("開始時間").agg({"_s2": "sum", "_s1": "sum"})
    
    cols = st.columns(len(target_times))
    for i, time in enumerate(target_times):
        s2_req, s1_req = 0, 0
        for idx in summary.index:
            if str(idx) == time:
                s2_req = int(summary.loc[idx, '_s2'])
                s1_req = int(summary.loc[idx, '_s1'])
                break
        
        s1_overflow = max(0, s1_req - stock_1s)
        final_s1, final_s2 = s1_req - s1_overflow, s2_req + s1_overflow
        
        with cols[i]:
            st.write(f"🕒 **{time}**")
            s2_color = "normal" if final_s2 <= stock_2s else "inverse"
            st.metric("2人", f"{final_s2}/{stock_2s}", delta=int(stock_2s - final_s2), delta_color=s2_color)
            st.metric("1人", f"{final_s1}/{stock_1s}")

    # 現場用詳細リスト (項目を「開始時間」「顧客」「人数」「使用車両」に絞り込み)
    st.subheader("🔍 現場用・当日車両割当リスト")
    
    # 表示する列を指定
    display_cols = ['状況', '開始時間', '顧客', '大人人数', '小人人数', '使用車両']
    
    if not active_df.empty:
        # 受付済みの行を青くするスタイル
        def highlight_rows(row):
            return ['background-color: #e6f3ff' if row['状況'] == "✅受付済" else '' for _ in row]
        
        # 不要な「大人人数」「小人人数」を「人数」としてまとめる場合は以下のように加工
        view_df = active_df[display_cols].copy()
        view_df['人数'] = view_df['大人人数'].astype(str) + "大 " + view_df['小人人数'].astype(str) + "小"
        
        # 最終的に表示する4項目(+状況)に絞る
        final_view_cols = ['状況', '開始時間', '顧客', '人数', '使用車両']
        
        st.dataframe(
            view_df[final_view_cols].style.apply(highlight_rows, axis=1),
            use_container_width=True,
            hide_index=True
        )




