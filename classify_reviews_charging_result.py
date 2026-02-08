# -*- coding: utf-8 -*-
"""
口コミCSVに「充電結果」列を追加し、以下の4分類で仕分けする。
- 充電できた
- 他の車が使用中のため断念
- その他（確認のみ等）
- 充電できなかった
"""
import pandas as pd
import re
import sys
import os

if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 分類ラベル
LABEL_SUCCESS = '充電できた'
LABEL_GAVE_UP_IN_USE = '他の車が使用中のため断念'
LABEL_OTHER = 'その他（確認のみ等)'
LABEL_FAILED = '充電できなかった'


def classify_charging_result(text: str) -> str:
    """口コミ内容から充電結果を判定する。"""
    if not text or not isinstance(text, str):
        return LABEL_OTHER
    t = text.strip()
    if not t:
        return LABEL_OTHER

    # 1) 他の車が使用中のため断念（使用中・満車・断念など）
    give_up_patterns = [
        r'使用中で\s*充電できず',
        r'使用中で\s*利用できな',
        r'全て\s*使用中',
        r'すべて\s*使用中',
        r'EV枠は?\s*全て\s*使用中',
        r'全ての充電器が使用中',
        r'使用中でした[。、]',  # 「普通充電器は2台とも使用中でした。」
        r'使用中で空き無',
        r'一般車のおかげで充電できなかった',
        r'一般車で埋ま',
        r'他の車が使用中',
        r'他車が使用中',
        r'空きがなく',
        r'空き無し',
        r'空き無でした',
        r'満車で\s*充電できず',
        r'満車だった',
        r'EV充電2基とも使用中で充電できず',
        r'使用中に加えて',
        r'使用中止に加えて',  # 混在する場合は「使えなく」の方が強そうだが、文脈で使用中
    ]
    for pat in give_up_patterns:
        if re.search(pat, t):
            return LABEL_GAVE_UP_IN_USE

    if '断念' in t and ('使用中' in t or '満車' in t or '空き' in t or '他の車' in t or '一般車' in t):
        return LABEL_GAVE_UP_IN_USE

    # 「〇〇できない可能性」のみの注意書きはその他
    if re.search(r'(利用|充電)\s*できな(い|ず)\s*可能性', t):
        if not re.search(r'充電できなかった|利用できなかった|故障|使えな|調整中|使用中止|利用できない状況|利用できないとのこと|利用できないようです', t):
            return LABEL_OTHER

    # 2) 充電できた（失敗より先に判定し、成功の言及がある口コミを優先）
    success_patterns = [
        r'充電ができました', r'充電できました', r'充電ができた', r'充電できた[ので]', r'充電できた[のは]',
        r'充電完了', r'充電した[。、]', r'充電しました', r'充電を開始', r'利用できた', r'利用できました',
        r'利用できるようになっておりました', r'充電ができる[ので]', r'充電できる[ので]', r'充電がお得です',
        r'使わせてもらっています', r'充電スタート', r'左側の充電口で充電しました',
    ]
    for pat in success_patterns:
        if re.search(pat, t):
            return LABEL_SUCCESS

    # 3) 充電できなかった（故障・調整中・利用不可・明確な失敗）
    failed_patterns = [
        r'充電できなかった',
        r'充電できませんでした',
        r'充電できません[。、]',  # 貼り紙等「充電できません」
        r'充電できなくて',
        r'充電できなくなって',
        r'利用できなかった',
        r'利用できませんでした',
        r'利用できない\s*状況',
        r'一般の方は?\s*利用できな',
        r'使えなかった',
        r'使えなくなり',
        r'使用中止',
        # 注: 「カードからは使用できず」は支払い手段の話なので 使えません/使えず は失敗に含めない
        r'機器調整中のため充電できません',
        r'調整中のため',
        r'故障',
        r'壊れ',
        r'利用できないようです',
        r'利用できないとのこと',
    ]
    for pat in failed_patterns:
        if re.search(pat, t):
            return LABEL_FAILED

    # 「充電できず」は使用中以外の理由でも使うので、ここで判定（使用中は上で済み）
    if re.search(r'充電できず', t):
        return LABEL_FAILED

    # 4) その他
    return LABEL_OTHER


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(base_dir, 'DB', 'gogoev_reviews_20260208_114046.csv')
    output_path = os.path.join(base_dir, 'DB', 'gogoev_reviews_20260208_114046_with_charging_result.csv')
    # 元ファイルに上書きする場合: output_path = input_path

    print('読み込み中:', input_path)
    df = pd.read_csv(input_path, encoding='utf-8-sig')
    if '口コミ内容' not in df.columns:
        print('エラー: 列「口コミ内容」が見つかりません。')
        return
    total = len(df)

    df['充電結果'] = df['口コミ内容'].astype(str).map(classify_charging_result)
    df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print('保存しました:', output_path)

    # 集計
    print()
    print('=== 充電結果 集計 ===')
    vc = df['充電結果'].value_counts()
    for label in [LABEL_SUCCESS, LABEL_GAVE_UP_IN_USE, LABEL_OTHER, LABEL_FAILED]:
        n = int(vc.get(label, 0))
        print(f'  {label}: {n} 件')
    print(f'  合計: {total} 件')

    # 充電できなかった のみ抽出して別CSVと一覧表示
    failed_df = df[df['充電結果'] == LABEL_FAILED].copy()
    failed_count = len(failed_df)
    failed_path = os.path.join(base_dir, 'DB', 'gogoev_reviews_充電できなかった.csv')
    failed_df.to_csv(failed_path, index=False, encoding='utf-8-sig')
    print()
    print('=== 充電できなかった 抽出結果 ===')
    print(f'件数: {failed_count} 件')
    print(f'保存先: {failed_path}')
    if failed_count > 0:
        print()
        print('--- 充電できなかった 口コミ（先頭20件の抜粋）---')
        for i, row in failed_df.head(20).iterrows():
            content = (row.get('口コミ内容', '') or '')[:120]
            content = content.replace('\n', ' ')
            print(f'  [{row.get("充電器名", "")}] {content}...' if len(str(row.get('口コミ内容', ''))) > 120 else f'  [{row.get("充電器名", "")}] {content}')


if __name__ == '__main__':
    main()
