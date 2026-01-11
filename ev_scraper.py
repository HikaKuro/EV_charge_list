"""
GOGOEV 故障・メンテナンス情報自動収集スクリプト
"""
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import json
import os
import sys
from urllib.parse import urljoin

# Windows環境での標準出力のエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    try:
        # 標準出力のエンコーディングをUTF-8に設定
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        # エンコーディング設定に失敗した場合は無視
        pass

# 設定
BASE_URL = "https://ev.gogo.gs"
ACCIDENT_URL = "https://ev.gogo.gs/accident"
MAINTENANCE_URL = "https://ev.gogo.gs/maintenance"

# User-Agent設定（403エラー回避）
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_page(url, max_retries=3):
    """ページを取得する（リトライ機能付き）"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                print(f"リトライ中... ({attempt + 1}/{max_retries})")
                time.sleep(2)
            else:
                print(f"エラー: {url} の取得に失敗しました: {e}")
                return None
    return None

def extract_list_items(soup, status_type):
    """一覧ページから施設情報を抽出"""
    items = []
    
    # 各施設のカードを取得（bg-white p-2 md:p-3 border mt-3 クラスを持つdiv）
    cards = soup.find_all('div', class_=lambda x: x and 'bg-white' in x and 'border' in x and 'mt-3' in x)
    
    for card in cards:
        try:
            # 施設名と詳細URL
            facility_link = card.find('a', class_='font-bold')
            if not facility_link:
                continue
                
            facility_name = facility_link.get_text(strip=True)
            detail_path = facility_link.get('href', '')
            if detail_path:
                detail_url = urljoin(BASE_URL, detail_path)
            else:
                continue
            
            # 住所
            address_elem = card.find('p', class_=lambda x: x and 'text-sm' in x and 'mt-1' in x)
            address = address_elem.get_text(strip=True) if address_elem else ""
            
            # 都道府県を抽出（住所から）
            prefecture = ""
            prefecture_match = re.search(r'^([^都道府県]*[都道府県])', address)
            if prefecture_match:
                prefecture = prefecture_match.group(1)
            
            # 故障/メンテナンスの詳細内容
            detail_content = ""
            h5 = card.find('h5', class_='font-bold')
            if h5:
                # h5の次のpタグを取得
                next_p = h5.find_next_sibling('p')
                if next_p:
                    detail_content = next_p.get_text(strip=True)
            
            # 確認時間（更新日）
            update_date = ""
            info_section = card.find('div', class_=lambda x: x and 'bg-base_color' in x and 'border' in x)
            if info_section:
                grid = info_section.find('div', class_=lambda x: x and 'grid' in x)
                if grid:
                    cols = grid.find_all('div', recursive=False)
                    if len(cols) >= 2:
                        # 確認時間は右側の列の最初のpタグ
                        right_col = cols[1]
                        time_p = right_col.find('p')
                        if time_p:
                            update_date = time_p.get_text(strip=True)
            
            items.append({
                'facility_name': facility_name,
                'prefecture': prefecture,
                'address': address,
                'status_type': status_type,
                'detail_content': detail_content,
                'update_date': update_date,
                'detail_url': detail_url
            })
            
        except Exception as e:
            print(f"一覧項目の抽出エラー: {e}")
            continue
    
    return items

def extract_detail_info(detail_url):
    """詳細ページから追加情報を抽出"""
    detail_info = {
        'address': '',
        'charge_type': '',
        'output': '',
        'charger_count': '',
        'maker': ''
    }
    
    try:
        response = get_page(detail_url)
        if not response:
            return detail_info
        
        soup = BeautifulSoup(response.content, 'html.parser')
        page_text = soup.get_text()
        
        # 住所を再取得（詳細ページの方が正確な場合がある）
        # 複数のパターンを試す
        address_patterns = [
            soup.find('p', class_=lambda x: x and 'text-sm' in x),
            soup.find('div', string=re.compile('住所|所在地')),
        ]
        
        for pattern in address_patterns:
            if pattern:
                if hasattr(pattern, 'get_text'):
                    address_text = pattern.get_text(strip=True)
                else:
                    # 次の要素を取得
                    next_elem = pattern.find_next_sibling()
                    if next_elem:
                        address_text = next_elem.get_text(strip=True)
                    else:
                        continue
                
                if address_text and len(address_text) > 5:  # 短すぎる場合は無視
                    detail_info['address'] = address_text
                    break
        
        # テーブルから情報を抽出
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                th = row.find('th')
                td = row.find('td')
                if th and td:
                    label = th.get_text(strip=True)
                    value = td.get_text(strip=True)
                    
                    if ('住所' in label or '所在地' in label) and not detail_info['address']:
                        detail_info['address'] = value
                    elif ('出力' in label or 'kW' in label) and not detail_info['output']:
                        detail_info['output'] = value
                    elif '充電器' in label and ('数' in label or '口' in label) and not detail_info['charger_count']:
                        detail_info['charger_count'] = value
                    elif ('メーカー' in label or '製造' in label) and not detail_info['maker']:
                        detail_info['maker'] = value
                    elif '充電' in label and 'タイプ' in label and not detail_info['charge_type']:
                        detail_info['charge_type'] = value
        
        # 定義リスト（dl）から情報を抽出
        dl_list = soup.find_all('dl')
        for dl in dl_list:
            dts = dl.find_all('dt')
            dds = dl.find_all('dd')
            for dt, dd in zip(dts, dds):
                label = dt.get_text(strip=True)
                value = dd.get_text(strip=True)
                
                if ('住所' in label or '所在地' in label) and not detail_info['address']:
                    detail_info['address'] = value
                elif ('出力' in label or 'kW' in label) and not detail_info['output']:
                    detail_info['output'] = value
                elif '充電器' in label and ('数' in label or '口' in label) and not detail_info['charger_count']:
                    detail_info['charger_count'] = value
                elif ('メーカー' in label or '製造' in label) and not detail_info['maker']:
                    detail_info['maker'] = value
                elif '充電' in label and 'タイプ' in label and not detail_info['charge_type']:
                    detail_info['charge_type'] = value
        
        # div構造から情報を抽出（より柔軟な検索）
        # 充電タイプの検出（CHAdeMO、テスラ、普通充電など）
        if not detail_info['charge_type']:
            charge_types = []
            if 'CHAdeMO' in page_text or 'チャデモ' in page_text:
                charge_types.append('CHAdeMO')
            if 'テスラ' in page_text or 'Tesla' in page_text:
                charge_types.append('テスラ')
            if '普通充電' in page_text or '200V' in page_text:
                charge_types.append('普通充電')
            if '急速充電' in page_text:
                charge_types.append('急速充電')
            if 'CCS' in page_text or 'ccs' in page_text:
                charge_types.append('CCS')
            if 'NACS' in page_text or 'nacs' in page_text:
                charge_types.append('NACS')
            if charge_types:
                detail_info['charge_type'] = '、'.join(charge_types)
        
        # 出力の検出（数値 + kWのパターン）
        if not detail_info['output']:
            output_matches = re.findall(r'(\d+(?:\.\d+)?)\s*kW', page_text, re.IGNORECASE)
            if output_matches:
                # 最大値を取得（複数の出力がある場合）
                outputs = [float(m) for m in output_matches]
                max_output = max(outputs)
                detail_info['output'] = f"{max_output}kW"
        
        # 充電器数の検出（○口、○台などのパターン）
        if not detail_info['charger_count']:
            charger_matches = re.findall(r'(\d+)\s*[口台]', page_text)
            if charger_matches:
                # 最大値を取得
                counts = [int(m) for m in charger_matches]
                detail_info['charger_count'] = str(max(counts))
        
        # メーカーの検出（一般的なメーカー名のパターン）
        if not detail_info['maker']:
            maker_keywords = ['日産', '三菱', 'パナソニック', '東芝', 'ABB', 'シーメンス', 'テスラ', 'Tesla']
            for keyword in maker_keywords:
                if keyword in page_text:
                    detail_info['maker'] = keyword
                    break
        
    except Exception as e:
        print(f"詳細ページの抽出エラー ({detail_url}): {e}")
    
    return detail_info

def geocode_address(address):
    """住所を緯度・経度に変換する関数"""
    if not address or len(address) < 3:
        return None, None
    
    try:
        # OpenStreetMap Nominatim APIを使用（無料）
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": address,
            "format": "json",
            "limit": 1,
            "countrycodes": "jp"  # 日本に限定
        }
        headers = {
            "User-Agent": "EV-Charger-Scraper/1.0"
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if data and len(data) > 0:
            result = data[0]
            return float(result["lat"]), float(result["lon"])
        else:
            return None, None
    except Exception as e:
        print(f"ジオコーディングエラー ({address}): {e}")
        return None, None

def get_all_pages(url, status_type):
    """全ページを取得してリストを結合"""
    all_items = []
    page = 1
    max_pages = 100  # 無限ループ防止
    
    while page <= max_pages:
        # Livewireを使用している場合、ページパラメータの形式が異なる可能性がある
        # まず通常の形式を試す
        if page == 1:
            page_url = url
        else:
            page_url = f"{url}?page={page}"
        
        print(f"{status_type}情報 - ページ {page} を取得中...")
        
        response = get_page(page_url)
        if not response:
            break
        
        soup = BeautifulSoup(response.content, 'html.parser')
        items = extract_list_items(soup, status_type)
        
        if not items:
            print(f"ページ {page} にデータがありません。終了します。")
            break
        
        all_items.extend(items)
        print(f"ページ {page}: {len(items)}件の施設を取得")
        
        # 次のページがあるか確認
        # ページネーションのボタンを確認
        pagination = soup.find('nav', {'aria-label': 'Pagination Navigation'})
        if pagination:
            # 現在のページが最後のページか確認
            current_page_span = pagination.find('span', {'aria-current': 'page'})
            if current_page_span:
                current_page_num = current_page_span.get_text(strip=True)
                try:
                    if int(current_page_num) == page:
                        # 次のページボタンを確認
                        next_buttons = pagination.find_all('button', {'aria-label': lambda x: x and 'Next' in x})
                        if not next_buttons:
                            # 最後のページ番号を取得
                            page_buttons = pagination.find_all('button', {'aria-label': lambda x: x and 'Go to page' in x})
                            if page_buttons:
                                page_numbers = []
                                for btn in page_buttons:
                                    text = btn.get_text(strip=True)
                                    if text.isdigit():
                                        page_numbers.append(int(text))
                                if page_numbers and page >= max(page_numbers):
                                    break
                            else:
                                # ページ番号が表示されていない場合、次のページがないと判断
                                break
                except ValueError:
                    pass
        
        page += 1
        time.sleep(1)  # リクエスト間の待機
    
    return all_items

def main():
    """メイン処理"""
    try:
        print("=" * 60)
        print("GOGOEV 故障・メンテナンス情報収集スクリプト")
        print("=" * 60)
        
        all_data = []
        
        # 故障情報を取得
        print("\n【故障情報の取得を開始】")
        accident_items = get_all_pages(ACCIDENT_URL, "故障")
        print(f"故障情報: {len(accident_items)}件取得")
        
        # メンテナンス情報を取得
        print("\n【メンテナンス情報の取得を開始】")
        maintenance_items = get_all_pages(MAINTENANCE_URL, "メンテナンス")
        print(f"メンテナンス情報: {len(maintenance_items)}件取得")
        
        # 全データを結合
        all_items = accident_items + maintenance_items
        print(f"\n合計: {len(all_items)}件の施設情報を取得しました")
        
        # 詳細ページから追加情報を取得
        print("\n【詳細ページからの追加情報取得を開始】")
        detailed_data = []
        
        for idx, item in enumerate(all_items, 1):
            print(f"[{idx}/{len(all_items)}] {item['facility_name']} の詳細情報を取得中...")
            
            detail_info = extract_detail_info(item['detail_url'])
            
            # 詳細ページの住所が取得できた場合は上書き
            if detail_info['address']:
                item['address'] = detail_info['address']
            
            # 詳細情報を追加
            row = {
                '更新日': item['update_date'],
                '施設名': item['facility_name'],
                '都道府県': item['prefecture'],
                '住所': item['address'],
                '種別': item['status_type'],
                '詳細内容': item['detail_content'],
                '充電タイプ': detail_info['charge_type'],
                '出力': detail_info['output'],
                '充電器数': detail_info['charger_count'],
                'メーカー': detail_info['maker'],
                '詳細URL': item['detail_url']
            }
            
            detailed_data.append(row)
            
            # リクエスト間の待機
            time.sleep(1.5)
        
        # ジオコーディングを実行
        print("\n【住所から位置情報（緯度・経度）を取得中】")
        geocoded_count = 0
        for idx, row in enumerate(detailed_data, 1):
            address = row['住所'] or row['都道府県'] or row['施設名']
            if address and len(address) > 3:
                print(f"[{idx}/{len(detailed_data)}] {address} の位置情報を取得中...")
                lat, lon = geocode_address(address)
                if lat and lon:
                    row['緯度'] = lat
                    row['経度'] = lon
                    geocoded_count += 1
                else:
                    row['緯度'] = ''
                    row['経度'] = ''
                
                # レート制限を考慮して1秒待機
                time.sleep(1)
            else:
                row['緯度'] = ''
                row['経度'] = ''
        
        print(f"位置情報取得完了: {geocoded_count}/{len(detailed_data)}件の施設の位置情報を取得しました。")
        
        # CSVに出力
        print("\n【CSVファイルに出力中】")
        df = pd.DataFrame(detailed_data)
        output_file = 'ev_status_list.csv'
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"CSV: {output_file} に {len(detailed_data)}件のデータを保存しました。")
        
        # JSONに出力（React用）
        print("\n【JSONファイルに出力中】")
        # Reactアプリのpublicフォルダのパスを取得
        script_dir = os.path.dirname(os.path.abspath(__file__))
        public_dir = os.path.join(script_dir, 'ev-charger-dashboard', 'public')
        if not os.path.exists(public_dir):
            os.makedirs(public_dir)
            print(f"{public_dir} フォルダを作成しました。")
        
        json_file = os.path.join(public_dir, 'data.json')
        # orient='records'で配列形式のJSONに変換
        json_data = df.to_dict(orient='records')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        print(f"JSON: {json_file} に {len(detailed_data)}件のデータを保存しました。")
        
        print(f"\n完了！合計 {len(detailed_data)}件のデータを保存しました。")
        print("=" * 60)
        
        return detailed_data
    except Exception as e:
        import traceback
        error_msg = f"エラーが発生しました: {str(e)}\n{traceback.format_exc()}"
        print(error_msg, file=sys.stderr)
        raise  # エラーを再発生させて、APIサーバーがキャッチできるようにする

if __name__ == "__main__":
    main()
