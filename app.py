import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# --- 1. 合言葉チェック ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "your-password-123": # ←必要に応じて変更
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.text_input("パスワードを入力してください", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("パスワードを入力してください", type="password", on_change=password_entered, key="password")
        st.error("パスワードが違います")
        return False
    else:
        return True

if not check_password():
    st.stop()

# --- 2. 基本設定 ---
st.set_page_config(page_title="バギーツアー共有管理", layout="wide")
st.title("🚜 バギーツアー車両管理 (リアルタイム同期)")

# スプレッドシート接続の設定
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 3. データ読み込み関数 ---
def load_data():
    # スプレッドシートから全データを読み込む
    return conn.read(ttl="0s") # ttl="0s"で常に最新を取得

# --- 4. 計算・並べ替え関数 ---
def calculate_details(df):
    df = df.copy()
    required_cols = ['開始時間', '顧客', '大人人数', '小人人数', '総販売金額', 'ステータス']
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    df['大人人数'] = pd.to_numeric(df['大人人数'], errors='coerce').fillna(0)
    df['小人人数'] = pd.to_numeric(df['小人人数'], errors='coerce').fillna(0)
    df['総販売金額'] = pd.to_numeric(df['総販売金額'], errors='coerce').fillna(0)
    
    if '開始時間' in df.columns:
        df['temp_time'] = pd.to_datetime(df['開始時間'], errors='coerce')
        df = df.sort_values(by='temp_time', na_position='last').drop(columns=['temp_time'])

    total_count = df['大人人数'] + df['小人人数']
    df['運転手'] = ((df['総販売金額'] - (500 * total_count)) / 4000).apply(lambda x: int(x) if x > 0 else 0)
    df['同乗者'] = (total_count - df['運転手']).apply(lambda x: int(x) if x > 0 else 0)
    df['2人乗り割当'] = df['同乗者']
    df['1人乗り割当'] = (df['運転手'] - df['同乗者']).clip(lower=0)
    
    df['判定'] = "✅ OK"
    mask_error = (df['運転手'] < df['同乗者']) & (total_count > 0)
    df.loc[mask_error, '判定'] = "⚠️ 運転手不足！"
    
    return df

# --- 5. メイン処理 ---
# サイドバー在庫設定
st.sidebar.header("本日の車両在庫")
stock_2s = st.sidebar.number_input("2人乗り在庫", value=3)
stock_1s = st.sidebar.number_input("1人乗り在庫", value=3)

# データの読み込み
df = load_data()

st.subheader("📋 予約リストの編集")
st.caption("編集後は必ず下の「変更を保存して全員に共有」ボタンを押してください。")

# 編集用エディタ
edited_df = st.data_editor(
    df,
    num_rows="dynamic",
    use_container_width=True,
    key="editor"
)

# 保存ボタン
if st.button("💾 変更を保存して全員に共有"):
    # スプレッドシートを更新
    conn.update(data=edited_df)
    st.success("スプレッドシートに保存しました！他のデバイスにも反映されます。")
    st.rerun()

# --- 6. 稼働状況表示 ---
if not edited_df.empty:
    res_df = calculate_details(edited_df)
    active_df = res_df[res_df['ステータス'] != 'キャンセル']

    st.divider()
    st.subheader("📊 時間帯別の稼働状況")
    
    summary = active_df.groupby("開始時間").agg({"2人乗り割当": "sum", "1人乗り割当": "sum"})
    
    if not summary.empty:
        cols = st.columns(3)
        for i, time in enumerate(summary.index):
            if str(time).strip() == "": continue
            s2, s1 = summary.loc[time, '2人乗り割当'], summary.loc[time, '1人乗り割当']
            with cols[i % 3]:
                st.write(f"🕒 **{time}**")
                st.metric("2人乗り", f"{int(s2)} / {stock_2s}", delta=int(stock_2s - s2))
                st.metric("1人乗り", f"{int(s1)} / {stock_1s}", delta=int(stock_1s - s1))

    st.subheader("🔍 割り当て詳細")
    st.dataframe(res_df, use_container_width=True)
