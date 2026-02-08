# -*- coding: utf-8 -*-
"""充電結果の記入有無と内容別件数を集計"""
import pandas as pd
import sys
import os

if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

p = os.path.join(os.path.dirname(__file__), 'DB', 'gogoev_using_20260208_122138.csv')
df = pd.read_csv(p, encoding='utf-8-sig')
total = len(df)
col = '充電結果'
filled = df[col].notna() & (df[col].astype(str).str.strip() != '')
empty_count = int(total - filled.sum())

print('=== 充電結果の記入状況 ===')
print(f'総件数: {total} 件')
print(f'記入あり: {int(filled.sum())} 件')
print(f'未記入（空欄）: {empty_count} 件')
print()
print('=== 記述内容別 件数 ===')
vc = df[col].fillna('').astype(str).str.strip()
vc = vc.replace('', '（未記入）')
counts = vc.value_counts()
for label, n in counts.items():
    print(f'{label}: {int(n)}件')
