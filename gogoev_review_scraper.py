"""
GOGOEV 口コミ投稿一覧スクレイピングスクリプト
東京都の口コミ投稿一覧から情報を抽出してCSVに保存
"""
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import sys
import os
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
REVIEW_BASE_URL = "https://ev.gogo.gs/review/13"  # 東京都の口コミ投稿一覧
# CSV保存先: プロジェクト直下の DB フォルダ
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "DB")
PAGE_DELAY_SEC = 1  # ページ間の待機秒数（サーバー負荷軽減）
MAX_PAGES = None  # 取得する最大ページ数（None=全ページ。確認用は 10 などに変更）

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
            # エンコーディングを明示的に設定
            response.encoding = response.apparent_encoding
            return response
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                print(f"リトライ中... ({attempt + 1}/{max_retries})")
                time.sleep(2)
            else:
                print(f"エラー: {url} の取得に失敗しました: {e}")
                return None
    return None

def extract_reviews(soup):
    """口コミ投稿一覧ページから情報を抽出"""
    reviews = []
    
    # HTML構造から直接抽出（より正確）
    # 各口コミは特定の構造を持っている
    # 充電器名と住所を含む要素を探す
    review_blocks = soup.find_all('div', class_=lambda x: x and 'bg-white' in str(x) and 'border' in str(x))
    
    for block in review_blocks:
        review_data = extract_review_from_block(block)
        if review_data:
            reviews.append(review_data)
    
    # HTML構造から抽出できなかった場合、テキストベースの抽出を試す
    if not reviews:
        reviews = extract_reviews_from_text(soup)
    
    # 重複を除去
    seen = set()
    unique_reviews = []
    for review in reviews:
        # 重複チェック用のキーを作成
        key = (review['充電器名'], review['充電器住所'], review['口コミ内容'][:50] if review['口コミ内容'] else '')
        if key not in seen:
            seen.add(key)
            unique_reviews.append(review)
    
    return unique_reviews

def extract_review_from_block(block):
    """HTMLブロックから口コミ情報を抽出"""
    try:
        charger_name = ""
        address = ""
        review_content = ""
        post_date = ""
        post_author = ""
        
        # 充電器名を探す（h2, h3, h4, h5タグまたは太字のリンク）
        name_elem = block.find(['h2', 'h3', 'h4', 'h5']) or block.find('a', class_=lambda x: x and 'font-bold' in str(x))
        if name_elem:
            name_text = name_elem.get_text(strip=True)
            if '/' in name_text:
                charger_name = name_text.split('/')[0].strip()
            else:
                charger_name = name_text
        
        # 住所を探す（pタグでtext-smクラスを持つ要素）
        address_elem = block.find('p', class_=lambda x: x and 'text-sm' in str(x))
        if address_elem:
            address = address_elem.get_text(strip=True)
            # 都道府県を含むことを確認
            if not ('都' in address or '県' in address or '府' in address):
                address = ""
        
        # 口コミ内容を探す（区切り線の後のテキスト）
        # 区切り線（---）の後のテキストを取得
        hr = block.find('hr')
        if hr:
            content_elem = hr.find_next_sibling()
            if content_elem:
                review_content = content_elem.get_text(separator='\n', strip=True)
        else:
            # 区切り線がない場合、住所の後のテキストを取得
            if address_elem:
                next_elem = address_elem.find_next_sibling()
                if next_elem:
                    review_content = next_elem.get_text(separator='\n', strip=True)
        
        # 投稿日時を探す（<span class="mr-4">投稿日時</span>の後のテキスト）
        date_span = block.find('span', string=re.compile('投稿日時'))
        if date_span:
            date_parent = date_span.find_parent('p')
            if date_parent:
                date_text = date_parent.get_text(strip=True)
                # "投稿日時"の後の部分を取得
                post_date = re.sub(r'投稿日時\s*', '', date_text).strip()
        
        # 投稿者を探す（<a class="u-id">タグの中のテキスト）
        author_link = block.find('a', class_=lambda x: x and 'u-id' in str(x))
        if author_link:
            post_author = author_link.get_text(strip=True)
        
        # データが揃っているか確認
        if charger_name or address or review_content:
            return {
                '充電器名': charger_name,
                '充電器住所': address,
                '口コミ内容': review_content,
                '投稿日時': post_date,
                '投稿者': post_author
            }
    
    except Exception as e:
        print(f"ブロックからの抽出エラー: {e}")
    
    return None

def extract_review_info(element):
    """要素から口コミ情報を抽出"""
    try:
        text = element.get_text(separator='\n')
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        charger_name = ""
        address = ""
        review_content = ""
        post_date = ""
        post_author = ""
        
        # 充電器名と住所を抽出
        # パターン: "充電器名 / 運営会社名" の後に住所が続く
        for i, line in enumerate(lines):
            # 充電器名のパターン（「/」を含む行）
            if '/' in line and not charger_name:
                parts = line.split('/')
                if len(parts) >= 2:
                    charger_name = parts[0].strip()
            
            # 住所のパターン（都道府県を含む）
            if ('都' in line or '県' in line or '府' in line) and not address:
                # 数字と「-」を含む可能性（例: "東京都江東区有明2-1-8"）
                if re.search(r'\d+-\d+', line) or '区' in line or '市' in line:
                    address = line.strip()
            
            # 投稿日時のパターン
            if '投稿日時' in line:
                date_match = re.search(r'投稿日時(.+?)(投稿者|$)', line)
                if date_match:
                    post_date = date_match.group(1).strip()
                else:
                    # 次の行に日時がある可能性
                    if i + 1 < len(lines):
                        post_date = lines[i + 1].strip()
            
            # 投稿者のパターン
            if '投稿者' in line:
                author_match = re.search(r'投稿者(.+)', line)
                if author_match:
                    post_author = author_match.group(1).strip()
        
        # 口コミ内容を抽出（住所の後から投稿日時の前まで）
        content_start = False
        content_lines = []
        for i, line in enumerate(lines):
            if address and line == address:
                content_start = True
                continue
            if content_start:
                if '投稿日時' in line or '投稿者' in line:
                    break
                if line and line != address and line != charger_name:
                    content_lines.append(line)
        
        review_content = '\n'.join(content_lines).strip()
        
        # データが揃っているか確認
        if charger_name or address or review_content:
            return {
                '充電器名': charger_name,
                '充電器住所': address,
                '口コミ内容': review_content,
                '投稿日時': post_date,
                '投稿者': post_author
            }
    
    except Exception as e:
        print(f"要素からの抽出エラー: {e}")
    
    return None

def extract_reviews_from_text(soup):
    """テキストから直接口コミ情報を抽出（メインの抽出方法）"""
    reviews = []
    text = soup.get_text(separator='\n')
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # 充電器名のパターン（「/」を含む行、URLでない）
        if '/' in line and len(line) > 5 and not line.startswith('http') and not line.startswith('www'):
            charger_name = line.split('/')[0].strip()
            address = ""
            review_content = ""
            post_date = ""
            post_author = ""
            
            # 次の行から情報を抽出
            j = i + 1
            content_lines = []
            found_address = False
            
            while j < len(lines) and j < i + 30:
                next_line = lines[j].strip()
                
                # 空行をスキップ
                if not next_line:
                    j += 1
                    continue
                
                # 住所のパターン（都道府県を含み、数字を含む）
                if not found_address and ('都' in next_line or '県' in next_line or '府' in next_line):
                    if re.search(r'\d+', next_line) and ('区' in next_line or '市' in next_line or '町' in next_line or '郡' in next_line):
                        address = next_line
                        found_address = True
                        j += 1
                        continue
                
                # 投稿日時のパターン
                if '投稿日時' in next_line:
                    # パターン: "投稿日時2026年2月7日（土） 18時"
                    date_match = re.search(r'投稿日時\s*(\d{4}年\d{1,2}月\d{1,2}日[^投稿者]*)', next_line)
                    if date_match:
                        post_date = date_match.group(1).strip()
                    else:
                        # 投稿日時の後の部分を取得
                        post_date = re.sub(r'投稿日時\s*', '', next_line).strip()
                    j += 1
                    continue
                
                # 投稿者のパターン
                if '投稿者' in next_line:
                    # パターン: "投稿者EVuser"
                    author_match = re.search(r'投稿者\s*(.+)', next_line)
                    if author_match:
                        post_author = author_match.group(1).strip()
                    else:
                        post_author = re.sub(r'投稿者\s*', '', next_line).strip()
                    j += 1
                    # この口コミの終わり
                    break
                
                # 口コミ内容（住所が見つかった後、投稿日時の前まで）
                if found_address and next_line:
                    # 充電器名や住所と同じ行でないことを確認
                    if next_line != charger_name and next_line != address:
                        # 投稿日時や投稿者を含まないことを確認
                        if '投稿日時' not in next_line and '投稿者' not in next_line:
                            # ページネーションやその他の不要な行を除外
                            if (not re.match(r'^\d+\s*$', next_line) and 
                                '件' not in next_line and 
                                'ページ' not in next_line and
                                '都道府県' not in next_line and
                                'クチコミ' not in next_line and
                                '充電スタンド' not in next_line):
                                content_lines.append(next_line)
                
                j += 1
            
            review_content = '\n'.join(content_lines).strip()
            
            # データが揃っているか確認
            if charger_name or address or review_content:
                reviews.append({
                    '充電器名': charger_name,
                    '充電器住所': address,
                    '口コミ内容': review_content,
                    '投稿日時': post_date,
                    '投稿者': post_author
                })
            
            i = j
        else:
            i += 1
    
    return reviews

def get_has_next_page(soup):
    """ページネーションから「次のページ」があるか判定"""
    # 次へ / Go to page N のボタンがあるか
    next_btn = soup.find('button', {'aria-label': re.compile(r'Go to page|次の', re.I)})
    if next_btn:
        return True
    # ページ番号のリンク（2以上）があるか
    nav = soup.find('nav', {'aria-label': 'Pagination Navigation'})
    if nav:
        buttons = nav.find_all('button')
        for b in buttons:
            txt = b.get_text(strip=True)
            if txt.isdigit() and int(txt) > 1:
                return True
    return False


def scrape_reviews_page(url):
    """口コミ投稿一覧ページを1ページ分スクレイピング"""
    print(f"ページを取得中: {url}")
    response = get_page(url)
    
    if not response:
        print("ページの取得に失敗しました")
        return [], False
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # 口コミ情報を抽出
    reviews = extract_reviews(soup)
    
    # 抽出結果が少ない場合、別の方法を試す
    if len(reviews) < 5:
        reviews = extract_reviews_alternative(soup)
    
    has_next = get_has_next_page(soup)
    return reviews, has_next

def extract_reviews_alternative(soup):
    """代替の抽出方法 - より正確なパターンマッチング"""
    reviews = []
    
    # すべてのテキストを含む要素を探す
    main_content = soup.find('main') or soup.find('div', class_=lambda x: x and 'container' in str(x).lower()) or soup.body
    
    if main_content:
        # 区切り線や特定のパターンで分割
        text = main_content.get_text(separator='\n')
        
        # より正確なパターンマッチング
        # 充電器名のパターン: 行の最初に充電器名、その後に住所
        lines = text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # 充電器名の可能性（「/」を含む）
            if '/' in line and len(line) > 5 and not line.startswith('http'):
                charger_name = line.split('/')[0].strip()
                address = ""
                review_content = ""
                post_date = ""
                post_author = ""
                
                # 次の数行を確認
                j = i + 1
                content_lines = []
                found_address = False
                
                while j < len(lines) and j < i + 30:  # 最大30行まで確認
                    next_line = lines[j].strip()
                    
                    # 空行や区切り線をスキップ
                    if not next_line or next_line == '---':
                        j += 1
                        continue
                    
                    # 住所のパターン（都道府県を含み、数字を含む）
                    if not found_address and ('都' in next_line or '県' in next_line or '府' in next_line):
                        if re.search(r'\d+', next_line) and ('区' in next_line or '市' in next_line or '町' in next_line):
                            address = next_line
                            found_address = True
                            j += 1
                            continue
                    
                    # 投稿日時のパターン（より正確に）
                    if '投稿日時' in next_line:
                        # パターン: "投稿日時2026年2月7日（土） 18時" または "投稿日時 2026年2月7日（土） 18時"
                        date_pattern = r'投稿日時\s*(\d{4}年\d{1,2}月\d{1,2}日[^投稿者]*)'
                        match = re.search(date_pattern, next_line)
                        if match:
                            post_date = match.group(1).strip()
                        else:
                            # 投稿日時の後の部分を取得
                            post_date = re.sub(r'投稿日時\s*', '', next_line).strip()
                        j += 1
                        continue
                    
                    # 投稿者のパターン（より正確に）
                    if '投稿者' in next_line:
                        # パターン: "投稿者EVuser" または "投稿者 EVuser"
                        author_match = re.search(r'投稿者\s*(.+)', next_line)
                        if author_match:
                            post_author = author_match.group(1).strip()
                        else:
                            post_author = re.sub(r'投稿者\s*', '', next_line).strip()
                        j += 1
                        # この口コミの終わり
                        break
                    
                    # 口コミ内容（住所が見つかった後、投稿日時の前まで）
                    if found_address and next_line:
                        # 充電器名や住所と同じ行でないことを確認
                        if next_line != charger_name and next_line != address:
                            # 投稿日時や投稿者を含まないことを確認
                            if '投稿日時' not in next_line and '投稿者' not in next_line:
                                # ページネーションやその他の不要な行を除外
                                if not re.match(r'^\d+\s*$', next_line) and '件' not in next_line:
                                    content_lines.append(next_line)
                    
                    j += 1
                
                review_content = '\n'.join(content_lines).strip()
                
                # 重複を避けるため、既に同じ内容が追加されていないか確認
                if charger_name or address or review_content:
                    # 重複チェック
                    is_duplicate = False
                    for existing_review in reviews:
                        if (existing_review['充電器名'] == charger_name and 
                            existing_review['充電器住所'] == address and
                            existing_review['口コミ内容'] == review_content):
                            is_duplicate = True
                            break
                    
                    if not is_duplicate:
                        reviews.append({
                            '充電器名': charger_name,
                            '充電器住所': address,
                            '口コミ内容': review_content,
                            '投稿日時': post_date,
                            '投稿者': post_author
                        })
                
                i = j
            else:
                i += 1
    
    return reviews

def main():
    """メイン処理（1ページ目から次のページへ順に取得し、DBフォルダにCSV保存）"""
    try:
        print("=" * 60)
        print("GOGOEV 口コミ投稿一覧スクレイピング")
        print("=" * 60)
        
        # 保存先ディレクトリを作成
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        print(f"保存先: {OUTPUT_DIR}")
        max_pages = MAX_PAGES
        if max_pages is not None:
            print(f"取得ページ数: 1 ～ {max_pages} ページまで（確認用）")
        
        all_reviews = []
        seen_keys = set()
        page = 1
        page_counts = []  # ページごとの取得件数（確認用）
        
        while True:
            if page == 1:
                url = REVIEW_BASE_URL
            else:
                url = f"{REVIEW_BASE_URL}?page={page}"
            
            reviews, has_next = scrape_reviews_page(url)
            page_counts.append((page, len(reviews)))
            
            # 重複を除いて追加
            for r in reviews:
                key = (r['充電器名'], r['充電器住所'], (r['口コミ内容'] or '')[:80])
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_reviews.append(r)
            
            print(f"  ページ{page}: {len(reviews)}件取得（累計: {len(all_reviews)}件）")
            
            if not reviews:
                print(f"  ページ{page}で0件のため終了します。")
                break
            if max_pages is not None and page >= max_pages:
                print(f"  {max_pages}ページ目まで取得しました（確認用で打ち切り）。")
                break
            if not has_next:
                break
            page += 1
            time.sleep(PAGE_DELAY_SEC)
        
        # 1～10ページの取得結果サマリ（確認用）
        print("\n" + "=" * 50)
        print("【確認】ページ別取得件数（1～10ページ）")
        print("=" * 50)
        for p, cnt in page_counts:
            status = "OK" if cnt > 0 else "要確認(0件)"
            print(f"  ページ{p:3d}: {cnt:3d}件  {status}")
        print("=" * 50)
        print(f"\n取得した口コミ数（重複除く）: {len(all_reviews)}件")
        
        if all_reviews:
            df = pd.DataFrame(all_reviews)
            output_file = os.path.join(OUTPUT_DIR, f"gogoev_reviews_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            df.to_csv(output_file, index=False, encoding='utf-8-sig')
            print(f"\nCSVファイルに保存しました: {output_file}")
            
            print("\n=== 取得したデータのサンプル（先頭3件） ===")
            for idx, review in enumerate(all_reviews[:3], 1):
                print(f"\n【口コミ {idx}】")
                print(f"充電器名: {review['充電器名']}")
                print(f"住所: {review['充電器住所']}")
                content = review['口コミ内容'] or ''
                print(f"口コミ内容: {content[:100]}..." if len(content) > 100 else f"口コミ内容: {content}")
                print(f"投稿日時: {review['投稿日時']}")
                print(f"投稿者: {review['投稿者']}")
        else:
            print("\n口コミデータを取得できませんでした。")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
