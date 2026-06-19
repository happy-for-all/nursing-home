import os
import json
import sys
import zipfile
import io
import re
import pandas as pd
import unicodedata
import math
import shutil

# ==========================================
# 👑 まごころ介護施設ナビ: 自動ビルドエンジン (Ver 1.0 全国版)
# 開発者: ちゃろ ＆ AIバディ
# 理念: HFA (Happy for All)
# ==========================================

COORD_OVERRIDES = {
    # 例: "テスト事業所名": {"lat": 34.0, "lon": 135.0},
}

SERVICE_DEFINITIONS = [
    {
        "csv_file": "jigyosho_510.csv",
        "service_name": "介護老人福祉施設（特養）",
        "output_key": "tokuyo",
    },
    {
        "csv_file": "jigyosho_520.csv",
        "service_name": "介護老人保健施設（老健）",
        "output_key": "roken",
    },
    {
        "csv_file": "jigyosho_331.csv",
        "service_name": "有料老人ホーム",
        "output_key": "yuryo",
    },
    {
        "csv_file": "jigyosho_334.csv",
        "service_name": "サービス付き高齢者向け住宅",
        "output_key": "sakoju",
    },
]

# 👑 全国47都道府県庁の緯度経度フェイルセーフ辞書
PREFECTURE_FAILSAFE = {
    "北海道": {"lat": 43.0642, "lon": 141.3469},
    "青森県": {"lat": 40.8244, "lon": 140.7400},
    "岩手県": {"lat": 39.7036, "lon": 141.1527},
    "宮城県": {"lat": 38.2688, "lon": 140.8721},
    "秋田県": {"lat": 39.7186, "lon": 140.1024},
    "山形県": {"lat": 38.2404, "lon": 140.3633},
    "福島県": {"lat": 37.7503, "lon": 140.4676},
    "茨城県": {"lat": 36.3418, "lon": 140.4468},
    "栃木県": {"lat": 36.5657, "lon": 139.8836},
    "群馬県": {"lat": 36.3911, "lon": 139.0608},
    "埼玉県": {"lat": 35.8569, "lon": 139.6489},
    "千葉県": {"lat": 35.6047, "lon": 140.1232},
    "東京都": {"lat": 35.6895, "lon": 139.6917},
    "神奈川県": {"lat": 35.4478, "lon": 139.6425},
    "新潟県": {"lat": 37.9026, "lon": 139.0233},
    "富山県": {"lat": 36.6953, "lon": 137.2113},
    "石川県": {"lat": 36.5947, "lon": 136.6256},
    "福井県": {"lat": 36.0652, "lon": 136.2216},
    "山梨県": {"lat": 35.6642, "lon": 138.5685},
    "長野県": {"lat": 36.6513, "lon": 138.1810},
    "岐阜県": {"lat": 35.3912, "lon": 136.7223},
    "静岡県": {"lat": 34.9769, "lon": 138.3831},
    "愛知県": {"lat": 35.1802, "lon": 136.9066},
    "三重県": {"lat": 34.7303, "lon": 136.5086},
    "滋賀県": {"lat": 35.0045, "lon": 135.8686},
    "京都府": {"lat": 35.0210, "lon": 135.7556},
    "大阪府": {"lat": 34.6862, "lon": 135.5201},
    "兵庫県": {"lat": 34.6913, "lon": 135.1830},
    "奈良県": {"lat": 34.6853, "lon": 135.8327},
    "和歌山県": {"lat": 34.2260, "lon": 135.1675},
    "鳥取県": {"lat": 35.5036, "lon": 134.2383},
    "島根県": {"lat": 35.4723, "lon": 133.0505},
    "岡山県": {"lat": 34.6618, "lon": 133.9344},
    "広島県": {"lat": 34.3966, "lon": 132.4596},
    "山口県": {"lat": 34.1859, "lon": 131.4706},
    "徳島県": {"lat": 34.0658, "lon": 134.5593},
    "香川県": {"lat": 34.3401, "lon": 134.0434},
    "愛媛県": {"lat": 33.8417, "lon": 132.7657},
    "高知県": {"lat": 33.5597, "lon": 133.5311},
    "福岡県": {"lat": 33.6064, "lon": 130.4181},
    "佐賀県": {"lat": 33.2494, "lon": 130.2989},
    "長崎県": {"lat": 32.7448, "lon": 129.8737},
    "熊本県": {"lat": 32.7898, "lon": 130.7417},
    "大分県": {"lat": 33.2382, "lon": 131.6126},
    "宮崎県": {"lat": 31.9111, "lon": 131.4239},
    "鹿児島県": {"lat": 31.5602, "lon": 130.5581},
    "沖縄県": {"lat": 26.2125, "lon": 127.6809},
}


def safe_get(row, possible_keys):
    for key in possible_keys:
        if key in row:
            if pd.isna(row[key]):
                continue
            value = str(row[key]).strip()
            if value.lower() == "nan" or value == "":
                continue
            return value
    return ""


def extract_clean_url(raw_text):
    if not raw_text or pd.isna(raw_text):
        return ""
    text = unicodedata.normalize('NFKC', str(raw_text)).replace('\n', '').replace('\r', '').strip()
    url_pattern = re.compile(r'(?:https?://|www\.)[a-zA-Z0-9\.\-\_]+[\w/\:\%\#\$\&\?\(\)\~\.\=\+\-]*')
    match = url_pattern.search(text)
    if match:
        extracted = match.group(0)
        if extracted.startswith("www."):
            extracted = "https://" + extracted
        extracted = extracted.rstrip('\'"）)]}>')
        if len(extracted) <= 8 and extracted.endswith("://"):
            return ""
        return extracted
    return ""


def extract_map_address(address):
    if not address:
        return address
    s = unicodedata.normalize('NFKC', address)
    s = re.sub(r'[\u2010-\u2015\u2212\uFF0D]', '-', s)

    chome = r'(?:[0-9]+条[西東南北]?)?[0-9]+丁目'
    ban = r'[0-9]+番地?'
    gou = r'[0-9]+号'
    blocknum = r'[0-9]+(?:-[0-9]+)?'

    pattern = re.compile(
        rf'(?:{chome})?(?:{ban})?{gou}'
        rf'|(?:{chome})?{ban}'
        rf'|{chome}{blocknum}'
        rf'|{chome}'
        rf'|[0-9]+-[0-9]+-[0-9]+'
        rf'|[0-9]+-[0-9]+'
    )
    m = pattern.search(s)
    return s[:m.end()].strip() if m else s


def run_build():
    print("==========================================")
    print("🌸 まごころ介護施設ナビ 自動ビルド開始（全国版）")
    print("==========================================")

    # 👑 ビルド前に dist フォルダをクリアして安全な状態を作る
    dist_root = "dist"
    if os.path.exists(dist_root):
        shutil.rmtree(dist_root)

    target_dir = "dist"
    os.makedirs(target_dir, exist_ok=True)

    summary_logs = []

    for srv_def in SERVICE_DEFINITIONS:
        csv_file_path = srv_def["csv_file"]
        service_name = srv_def["service_name"]
        output_key = srv_def["output_key"]

        print(f"\n📡 処理開始: 【{service_name}】 (ファイル: {csv_file_path})")

        # 👑 安全策：ファイルが見つからなければこのサービスだけスキップ
        if not os.path.exists(csv_file_path):
            print(f"⚠️ [警告] 『{csv_file_path}』が見つかりません。スキップします。")
            continue

        df = None
        encodings = ["utf-8-sig", "shift_jis", "cp932", "utf-8"]
        for enc in encodings:
            try:
                df = pd.read_csv(csv_file_path, encoding=enc, dtype=str)
                print(f"🟢 '{enc}' での読み込みに成功しました！")
                break
            except Exception:
                continue

        if df is None:
            print(f"❌ CSV読込失敗 ({service_name})。スキップします。")
            continue

        df.columns = df.columns.str.strip().str.replace('\n', '').str.replace('\r', '')

        if "市区町村名" not in df.columns or "住所" not in df.columns:
            print(f"❌ 想定する住所列（市区町村名・住所）が見つかりません ({service_name})。スキップします。")
            continue

        facilities = []

        for _, row in df.iterrows():
            pref = safe_get(row, ["都道府県名"])
            city = safe_get(row, ["市区町村名"])
            if not pref or not city:
                continue

            name = safe_get(row, ["事業所名"])
            name_kana = safe_get(row, ["事業所名カナ"])
            address = safe_get(row, ["住所"])
            address_sub = safe_get(row, ["方書（ビル名等）"])

            raw_tel = safe_get(row, ["電話番号"])
            tel_clean = re.sub(
                r'[^0-9\-]', '',
                raw_tel.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
            )

            raw_lat = safe_get(row, ["緯度"])
            raw_lon = safe_get(row, ["経度"])

            raw_url_text = safe_get(row, ["URL"])
            clean_url = extract_clean_url(raw_url_text)

            capacity = safe_get(row, ["定員"])
            day_off = safe_get(row, ["利用可能曜日"])
            notes = safe_get(row, ["利用可能曜日特記事項"])

            lat, lon = None, None
            is_approximate = False

            try:
                if raw_lat:
                    lat = float(raw_lat)
                if raw_lon:
                    lon = float(raw_lon)
            except Exception:
                pass

            if lat is not None and math.isnan(lat):
                lat = None
            if lon is not None and math.isnan(lon):
                lon = None

            if lat is None or lon is None:
                is_approximate = True
                # 👑 都道府県名から県庁所在地のフェイルセーフ座標を採用
                if pref in PREFECTURE_FAILSAFE:
                    lat = PREFECTURE_FAILSAFE[pref]["lat"]
                    lon = PREFECTURE_FAILSAFE[pref]["lon"]
                else:
                    # 想定外の都道府県名が来た場合の最終フェイルセーフ（東京都庁）
                    lat = PREFECTURE_FAILSAFE["東京都"]["lat"]
                    lon = PREFECTURE_FAILSAFE["東京都"]["lon"]

            if name in COORD_OVERRIDES:
                lat = COORD_OVERRIDES[name]["lat"]
                lon = COORD_OVERRIDES[name]["lon"]
                is_approximate = False

            facilities.append({
                "name": name,
                "name_kana": name_kana,
                "service_type": service_name,
                "pref": pref,
                "address": address,
                "address_sub": address_sub,
                "map_address": extract_map_address(address),
                "tel": raw_tel,
                "tel_clean": tel_clean,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "url": clean_url,
                "is_approximate": is_approximate,
                "capacity": capacity,
                "day_off": day_off,
                "notes": notes,
            })

        output_path = os.path.join(target_dir, f"data_{output_key}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(facilities, f, ensure_ascii=False, indent=2)

        summary_logs.append(f" - {service_name}: {len(facilities)}件 生成完了")

    if os.path.exists("index.html"):
        shutil.copy2("index.html", os.path.join(target_dir, "index.html"))

    # 👑 安全策：1件もデータが生成されなかった場合のみ、ここで初めてビルドを中断する二段構え
    if not summary_logs:
        print("❌ [致命的エラー] 1件も正常にデータが生成されませんでした。ビルドを中断します。")
        sys.exit(1)

    print("\n==========================================")
    for log in summary_logs:
        print(log)
    print("==========================================")


if __name__ == "__main__":
    try:
        run_build()
    except Exception as e:
        print(f"❌ [未予期エラー] ビルド中に重大なエラーが発生しました: {e}")
        sys.exit(1)
