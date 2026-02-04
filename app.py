import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from streamlit_autorefresh import st_autorefresh

# --- 1. 合言葉チェック (セッション保持版) ---
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
        if "password_correct" in st.session_state and not st.session_state["password_correct"]:
            st.error("合言葉が違います")
        return False
    return True

if "password_correct" not in st.session_state:
    st.session_state["password_correct"] = False

if not check_password():
    st.stop()

# --- 2. 基本設定 & 自動更新 (3分) ---
st.set_page_config(page_title="バギーツアー管理", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

# スプレッドシート接続
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 3. データの読み込み関数 ---
def load_all_data():
    # 予約データの読み込み (一番左のシート)
    try:
        df = conn.read(ttl=0)
    except Exception as e:
        st.error("予約データの読み込みに失敗しました。")
        st.stop()

    if 'チェックイン' not in df.columns:
        df['チェックイン'] = False
    df['チェックイン'] = df['チェックイン'].fillna(False).astype(bool)
    
    # チェックイン列を左端へ移動
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
        # 読み込めない場合はサイドバーに警告を出す
        st
