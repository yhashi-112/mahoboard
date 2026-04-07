#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
簡易知識ベース確認スクリプト - app.pyと同じディレクトリで実行してください
"""

import os
import json
import sys

print("="*70)
print("知識ベース配置確認")
print("="*70)

# 1. 現在のディレクトリ
print(f"\n現在のディレクトリ: {os.getcwd()}")

# 2. app.pyの存在確認
if os.path.exists("app.py"):
    print("✅ app.py が見つかりました")
else:
    print("❌ app.py が見つかりません")
    print("   → このスクリプトをapp.pyと同じディレクトリで実行してください")
    sys.exit(1)

# 3. knowledge_baseディレクトリの確認
if os.path.exists("knowledge_base"):
    print("✅ knowledge_base/ ディレクトリが存在します")
else:
    print("❌ knowledge_base/ ディレクトリが存在しません")
    print("\n【解決方法】")
    print("mkdir knowledge_base")
    sys.exit(1)

# 4. qa_knowledge_base_all.jsonの確認
json_path = "knowledge_base/qa_knowledge_base_all.json"
if os.path.exists(json_path):
    print(f"✅ {json_path} が存在します")
    
    # ファイルサイズ確認
    size = os.path.getsize(json_path)
    print(f"   ファイルサイズ: {size:,} bytes ({size/1024:.1f} KB)")
    
    # 内容確認
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            kb = json.load(f)
            qa_count = len(kb.get("qa_pairs", []))
            print(f"   Q&A件数: {qa_count}件")
            print("\n✅ すべて正常です！")
            print("\nstreamlit run app.py で起動してください")
    except json.JSONDecodeError as e:
        print(f"❌ JSONファイルの読み込みエラー: {e}")
        print("   → ファイルが壊れている可能性があります")
        sys.exit(1)
    except Exception as e:
        print(f"❌ エラー: {e}")
        sys.exit(1)
else:
    print(f"❌ {json_path} が存在しません")
    print("\n【解決方法】")
    print(f"cp qa_knowledge_base_all.json {json_path}")
    sys.exit(1)

print("="*70)
