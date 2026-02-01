import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# --- 1. 合言葉チェック ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "your-password-123":
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
st.set_page_config(page_title="バギーツアー車両管理", layout="wide")
st.title("🚜 バギーツアー車両割当・共有システム")

# スプレッドシート接続
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    return conn.read(ttl="0s")

# --- 3. 計算ロジック ---
def calculate_details(df):
    df = df.copy()
    required_cols = ['開始時間', '顧客', '大人人数', '小人人数', '総販売金額', 'ステータス']
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    df['大人人数'] = pd.to_numeric(df['大人人数'], errors='coerce').fillna(0).astype(int)
    df['小人人数'] = pd.to_numeric(df['小人人数'], errors='coerce').fillna(0).astype(int)
    df['総販売金額'] = pd.to_numeric(df['総販売金額'], errors='coerce').fillna(0)
    
    # 時間ソート
    if '開始時間' in df.columns:
        df['temp_time'] = pd.to_datetime(df['開始時間'], errors='coerce')
        df = df.sort_values(by='temp_time', na_position='last').drop(columns=['temp_time'])

    # 計算
    total_count = df['大人人数'] + df['小人人数']
    driver_count = ((df['総販売金額'] - (500 * total_count)) / 4000).apply(lambda x: int(x) if x > 0 else 0)
    passenger_count = (total_count - driver_count).apply(lambda x: int(x) if x > 0 else 0)
    
    s2 = passenger_count
    s1 = (driver_count - passenger_count).clip(lower=0)
    
    df['使用車両'] = s2.apply(lambda x: f"【2人】{int(x)}台 " if x > 0 else "") + \
                     s1.apply(lambda x: f"【1人】{int(x)}台" if x > 0 else "")
    
    df['_s2'] = s2
    df['_s1'] = s1
    
    df.insert(0, '状況', "✅")
    mask_error = (driver_count < passenger_count) & (total_count > 0)
    df.loc[mask_error, '状況'] = "⚠️ 運転手不足"
    df.loc[total_count == 0, '状況'] = "-"
    
    return df

# --- 4. メイン画面 ---
st.sidebar.header("本日の車両在庫")
stock_2s = st.sidebar.number_input("2人乗り在庫", value=3)
stock_1s = st.sidebar.number_input("1人乗り在庫", value=3)

df_raw = load_data()

st.subheader("📋 予約入力・編集 (全データ)")
st.caption("キャンセルに設定した予約は、下のリストには表示されません。")
edited_df = st.data_editor(
    df_raw,
    num_rows="dynamic",
    use_container_width=True,
    key="editor"
)

if st.button("💾 変更を保存して全員に共有"):
    conn.update(data=edited_df)
    st.success("スプレッドシートに保存しました！")
    st.rerun()

# --- 5. 結果表示 ---
if not edited_df.empty:
    res_df = calculate_details(edited_df)
    active_df

