#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知識ベースの配置確認スクリプト
"""

import os
import json

print("="*60)
print("知識ベース配置確認")
print("="*60)

# 現在の作業ディレクトリ
cwd = os.getcwd()
print(f"\n1. 現在の作業ディレクトリ: {cwd}")

# app.pyの場所を基準に確認
if os.path.exists("app.py"):
    BASE_DIR = os.path.dirname(os.path.abspath("app.py"))
    if not BASE_DIR:
        BASE_DIR = os.getcwd()
    print(f"2. app.pyのベースディレクトリ: {BASE_DIR}")
else:
    print("2. ⚠️ app.pyが見つかりません")
    BASE_DIR = os.getcwd()

# knowledge_baseディレクトリの確認
kb_dir = os.path.join(BASE_DIR, "knowledge_base")
print(f"\n3. 期待される knowledge_base パス:")
print(f"   {kb_dir}")
print(f"   存在: {'✅ Yes' if os.path.exists(kb_dir) else '❌ No'}")

# qa_knowledge_base_all.jsonの確認
kb_file = os.path.join(kb_dir, "qa_knowledge_base_all.json")
print(f"\n4. 期待される qa_knowledge_base_all.json パス:")
print(f"   {kb_file}")
print(f"   存在: {'✅ Yes' if os.path.exists(kb_file) else '❌ No'}")

if os.path.exists(kb_file):
    try:
        with open(kb_file, 'r', encoding='utf-8') as f:
            kb = json.load(f)
            qa_count = len(kb.get("qa_pairs", []))
            print(f"\n5. 知識ベースの内容:")
            print(f"   Q&A件数: {qa_count}件")
            print(f"   ✅ 正常に読み込めます!")
    except Exception as e:
        print(f"\n5. ❌ エラー: {e}")
else:
    print(f"\n5. ❌ ファイルが存在しないため読み込めません")

# カレントディレクトリの内容表示
print(f"\n6. カレントディレクトリの内容:")
for item in os.listdir(BASE_DIR):
    item_path = os.path.join(BASE_DIR, item)
    if os.path.isdir(item_path):
        print(f"   📁 {item}/")
    else:
        print(f"   📄 {item}")

print("\n" + "="*60)
print("確認完了")
print("="*60)

print("\n📝 次のアクション:")
if not os.path.exists(kb_dir):
    print("1. knowledge_base ディレクトリを作成してください:")
    print(f"   mkdir -p {kb_dir}")
if not os.path.exists(kb_file):
    print("2. qa_knowledge_base_all.json を配置してください:")
    print(f"   cp qa_knowledge_base_all.json {kb_file}")
if os.path.exists(kb_file):
    print("✅ 設定は正しいです！")
