"""
GOGOEV 充電記録一覧スクレイピングスクリプト
東京都の充電記録一覧から情報を抽出してCSVに保存
https://ev.gogo.gs/using/13
"""
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import sys
import os
import time
from datetime import datetime

# Windows環境での標準出力のエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 設定
USING_BASE_URL = "https://ev.gogo.gs/using/13"  # 東京都の充電記録一覧
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "DB")
PAGE_DELAY_SEC = 1   # ページ間の待機秒数（サーバー負荷軽減）
MAX_PAGES = None     # 取得する最大ページ数（None=全ページ）

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# CSVカラム（指定の順序）
CSV_COLUMNS = [
    '充電器名',
    '充電器の住所',
    '利用日時',
    '充電タイプ',
    '充電結果',
    '混雑状況',
    '車種',
    '認証',
    '充電量',
    '充電時間',
]


def get_page(url):
    """ページを取得する"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        return response
    except requests.exceptions.RequestException as e:
        print(f"エラー: {url} の取得に失敗しました: {e}")
        return None


def extract_records_from_blocks(soup):
    """充電記録ブロック（bg-white + border のカード）から1件ずつ抽出"""
    records = []
    blocks = soup.find_all('div', class_=lambda x: x and 'bg-white' in str(x) and 'border' in str(x))

    for block in blocks:
        rec = extract_one_record(block)
        if rec:
            records.append(rec)

    return records


def extract_one_record(block):
    """1ブロックから充電器名・住所・表の項目を抽出"""
    try:
        charger_name = ""
        address = ""

        # 充電器名: 詳細ページへのリンクテキスト（「名前 / 運営」形式）
        link = block.find('a', href=re.compile(r'/detail/'))
        if link:
            charger_name = link.get_text(strip=True)

        # 住所: 都道府県を含む p または次のテキスト
        for p in block.find_all('p', class_=lambda x: x and 'text-sm' in str(x)):
            t = p.get_text(strip=True)
            if t and (('都' in t or '県' in t or '府' in t) and re.search(r'\d', t)):
                address = t
                break
        if not address and link:
            next_el = link.find_next_sibling()
            if next_el:
                address = next_el.get_text(strip=True)

        # 表の行からキー・値を取得
        row_map = {}
        table = block.find('table')
        if table:
            for tr in table.find_all('tr'):
                cells = tr.find_all(['th', 'td'])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    row_map[label] = value

        # ラベル名のゆらぎに対応（スペースや全角含む）
        def get_val(*keys):
            for k in keys:
                if k in row_map:
                    return row_map[k]
                # キーに含まれるもの
                for mk, v in row_map.items():
                    if k in mk or mk in k:
                        return v
            return ""

        record = {
            '充電器名': charger_name,
            '充電器の住所': address,
            '利用日時': get_val('利用日時'),
            '充電タイプ': get_val('充電タイプ'),
            '充電結果': get_val('充電結果'),
            '混雑状況': get_val('混雑状況'),
            '車種': get_val('車種'),
            '認証': get_val('認証'),
            '充電量': get_val('充電量'),
            '充電時間': get_val('充電時間'),
        }

        # 充電器名か住所が取れていれば有効レコードとする
        if record['充電器名'] or record['充電器の住所']:
            return record

    except Exception as e:
        print(f"ブロック解析エラー: {e}")

    return None


def extract_records_from_text(soup):
    """HTMLブロックで取れない場合のフォールバック: テキストと表から抽出"""
    records = []
    text = soup.get_text(separator='\n')
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]
        # 充電器名: 「〇〇 / 〇〇」で detail 付近のリンクは別なので、ここでは「/」を含む行で住所の前のブロックとして扱う
        if '/' in line and len(line) > 5 and not line.startswith('http'):
            charger_name = line
            address = ""
            j = i + 1
            while j < len(lines) and j < i + 2:
                if '都' in lines[j] or '県' in lines[j] or '府' in lines[j]:
                    if re.search(r'\d', lines[j]):
                        address = lines[j]
                        break
                j += 1
            # --- の後を探す
            k = i + 1
            row_map = {}
            while k < len(lines) and k < i + 25:
                if lines[k] == '---':
                    k += 1
                    while k < len(lines) and k < i + 25:
                        # 表形式 "ラベル | 値" または "ラベル" の次が値
                        if '|' in lines[k]:
                            parts = [p.strip() for p in lines[k].split('|')]
                            if len(parts) >= 2 and parts[0] and parts[1]:
                                row_map[parts[0]] = parts[1]
                        elif lines[k].startswith('利用日時') or '利用日時' in lines[k]:
                            row_map['利用日時'] = re.sub(r'^利用日時\s*', '', lines[k]).strip() or (lines[k + 1] if k + 1 < len(lines) else "")
                        elif '充電タイプ' in lines[k]:
                            row_map['充電タイプ'] = re.sub(r'^.*充電タイプ\s*', '', lines[k]).strip() or (lines[k + 1] if k + 1 < len(lines) else "")
                        elif '充電結果' in lines[k]:
                            row_map['充電結果'] = re.sub(r'^.*充電結果\s*', '', lines[k]).strip() or (lines[k + 1] if k + 1 < len(lines) else "")
                        elif '混雑状況' in lines[k]:
                            row_map['混雑状況'] = re.sub(r'^.*混雑状況\s*', '', lines[k]).strip() or (lines[k + 1] if k + 1 < len(lines) else "")
                        elif '車種' in lines[k]:
                            row_map['車種'] = re.sub(r'^.*車種\s*', '', lines[k]).strip() or (lines[k + 1] if k + 1 < len(lines) else "")
                        elif '認証' in lines[k] and '認証' not in row_map:
                            row_map['認証'] = re.sub(r'^.*認証\s*', '', lines[k]).strip() or (lines[k + 1] if k + 1 < len(lines) else "")
                        elif '充電量' in lines[k]:
                            row_map['充電量'] = re.sub(r'^.*充電量\s*', '', lines[k]).strip() or (lines[k + 1] if k + 1 < len(lines) else "")
                        elif '充電時間' in lines[k]:
                            row_map['充電時間'] = re.sub(r'^.*充電時間\s*', '', lines[k]).strip() or (lines[k + 1] if k + 1 < len(lines) else "")
                        k += 1
                    break
                k += 1

            def g(k):
                return row_map.get(k, "")

            records.append({
                '充電器名': charger_name,
                '充電器の住所': address,
                '利用日時': g('利用日時'),
                '充電タイプ': g('充電タイプ'),
                '充電結果': g('充電結果'),
                '混雑状況': g('混雑状況'),
                '車種': g('車種'),
                '認証': g('認証'),
                '充電量': g('充電量'),
                '充電時間': g('充電時間'),
            })
            i = k if k > i else i + 1
        else:
            i += 1

    return records


def get_has_next_page(soup):
    """ページネーションから「次のページ」があるか判定"""
    next_btn = soup.find('button', {'aria-label': re.compile(r'Go to page|次の', re.I)})
    if next_btn:
        return True
    nav = soup.find('nav', {'aria-label': 'Pagination Navigation'})
    if nav:
        buttons = nav.find_all('button')
        for b in buttons:
            txt = b.get_text(strip=True)
            if txt.isdigit() and int(txt) > 1:
                return True
    return False


def scrape_using_page(url):
    """充電記録一覧ページを1ページ分スクレイピング。 (records, soup) を返す。"""
    print(f"ページを取得中: {url}")
    response = get_page(url)
    if not response:
        return [], None

    soup = BeautifulSoup(response.content, 'html.parser')
    records = extract_records_from_blocks(soup)

    if not records:
        records = extract_records_from_text(soup)

    return records, soup


def main():
    """最初の MAX_PAGES ページを取得してCSV保存"""
    try:
        print("=" * 60)
        print("GOGOEV 充電記録一覧スクレイピング" + (f"（先頭 {MAX_PAGES} ページ）" if MAX_PAGES else "（全ページ）"))
        print("=" * 60)

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        print(f"保存先: {OUTPUT_DIR}")
        if MAX_PAGES is not None:
            print(f"取得ページ: 1 ～ {MAX_PAGES} ページ\n")
        else:
            print("取得ページ: 全ページ\n")

        all_records = []
        page = 1

        while True:
            if page == 1:
                url = USING_BASE_URL
            else:
                url = f"{USING_BASE_URL}?page={page}"

            records, soup = scrape_using_page(url)
            all_records.extend(records)

            print(f"  ページ{page}: {len(records)}件取得（累計: {len(all_records)}件）")

            if not records:
                print(f"  ページ{page}で0件のため終了します。")
                break
            if soup and not get_has_next_page(soup):
                print("  次のページがありません。")
                break
            if MAX_PAGES is not None and page >= MAX_PAGES:
                print(f"  {MAX_PAGES}ページ目まで取得しました。")
                break

            page += 1
            time.sleep(PAGE_DELAY_SEC)

        print("\n" + "=" * 50)
        print(f"合計取得件数: {len(all_records)} 件")

        if all_records:
            df = pd.DataFrame(all_records, columns=CSV_COLUMNS)
            output_file = os.path.join(OUTPUT_DIR, f"gogoev_using_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            df.to_csv(output_file, index=False, encoding='utf-8-sig')
            print(f"\nCSVに保存しました: {output_file}")

            print("\n=== 取得データのサンプル（先頭3件） ===")
            for idx, rec in enumerate(all_records[:3], 1):
                print(f"\n【{idx}】 {(rec.get('充電器名') or '')[:40]}...")
                print(f"  住所: {rec.get('充電器の住所', '')}")
                print(f"  利用日時: {rec.get('利用日時', '')} | 充電タイプ: {rec.get('充電タイプ', '')} | 充電結果: {rec.get('充電結果', '')}")
                print(f"  混雑: {rec.get('混雑状況', '')} | 車種: {rec.get('車種', '')} | 認証: {rec.get('認証', '')}")
                print(f"  充電量: {rec.get('充電量', '')} | 充電時間: {rec.get('充電時間', '')}")
        else:
            print("データを取得できませんでした。")

    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
