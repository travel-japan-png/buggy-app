import streamlit as st

# --- 合言葉チェック ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "your-password-123": # ←ここを好きなパスワードに変える
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
# --- ここまで書き足す ---

import streamlit as st
import pandas as pd

# --- 1. 基本設定 ---
st.set_page_config(page_title="バギーツアー管理くん", layout="wide")
st.title("🚜 バギーツアー車両管理・編集ツール")

# --- 2. サイドバー：在庫管理 ---
st.sidebar.header("本日の車両在庫")
stock_2s = st.sidebar.number_input("2人乗り在庫 (台)", value=3, min_value=0)
stock_1s = st.sidebar.number_input("1人乗り在庫 (台)", value=3, min_value=0)

# --- 3. ロジック関数（計算・並べ替え） ---
def calculate_details(df):
    """表全体のデータに対して計算と並べ替えを行う"""
    # データのコピーを作成
    df = df.copy()
    
    # 列が存在しない場合の補完
    required_cols = ['開始時間', '顧客', '大人人数', '小人人数', '総販売金額', 'ステータス']
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    # 数値変換（エラー回避）
    df['大人人数'] = pd.to_numeric(df['大人人数'], errors='coerce').fillna(0)
    df['小人人数'] = pd.to_numeric(df['小人人数'], errors='coerce').fillna(0)
    df['総販売金額'] = pd.to_numeric(df['総販売金額'], errors='coerce').fillna(0)
    
    # 自動並べ替え（開始時間を基準に早い順）
    if '開始時間' in df.columns:
        # 入力された時間を一時的に時間型に変換してソート、空行は一番下へ
        df['temp_time'] = pd.to_datetime(df['開始時間'], errors='coerce')
        df = df.sort_values(by='temp_time', na_position='last').drop(columns=['temp_time'])

    # 連立方程式で運転手(x)と同乗者(y)を算出
    # 4500x + 500y = Amount / x + y = Count
    total_count = df['大人人数'] + df['小人人数']
    # 0除算や計算ミスを防ぎつつ整数化
    df['運転手'] = ((df['総販売金額'] - (500 * total_count)) / 4000).apply(lambda x: int(x) if x > 0 else 0)
    df['同乗者'] = (total_count - df['運転手']).apply(lambda x: int(x) if x > 0 else 0)
    
    # 車両割当ロジック
    df['2人乗り割当'] = df['同乗者']
    df['1人乗り割当'] = (df['運転手'] - df['同乗者']).clip(lower=0)
    
    # 判定メッセージ
    df['判定'] = "✅ OK"
    # 運転手 < 同乗者 の場合はエラー（ただし人数が入力されている場合のみ）
    mask_error = (df['運転手'] < df['同乗者']) & (total_count > 0)
    df.loc[mask_error, '判定'] = "⚠️ 運転手不足！"
    # 金額未入力のチェック
    mask_no_price = (total_count > 0) & (df['総販売金額'] == 0)
    df.loc[mask_no_price, '判定'] = "❓ 金額未入力"
    # そもそも人数が0の行
    df.loc[total_count == 0, '判定'] = "-"
    
    return df

# --- 4. メイン画面：データの読み込みと編集 ---
uploaded_file = st.file_uploader("Trunk ToolsのCSVをアップロード（または空の表から開始）", type="csv")

# データの土台を作成
if uploaded_file:
    try:
        base_df = pd.read_csv(uploaded_file, encoding='cp932')
    except:
        base_df = pd.read_csv(uploaded_file, encoding='utf-8')
else:
    # ファイルがない場合は空のひな形を作成
    base_df = pd.DataFrame(columns=['開始時間', '顧客', '大人人数', '小人人数', '総販売金額', 'ステータス'])

# 編集・追加ができるデータエディタを表示
st.subheader("📋 予約リストの編集・追加")
