#!/bin/bash
# 封裝檢查腳本

echo "🔍 檢查假封裝..."
echo ""

echo "1️⃣ 檢查：私有屬性被暴露為 property"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep -n "@property" doro_app/*.py | grep -A 3 "def.*_" | head -20
echo ""

echo "2️⃣ 檢查：方法鏈（Law of Demeter 違反）"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep -n '\.\w\+\.\w\+(' doro_app/*.py | grep -v "^\s*#" | head -20
echo ""

echo "3️⃣ 檢查：直接存取 gif_repo"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep -n 'gif_repo\.' doro_app/*.py
echo ""

echo "4️⃣ 檢查：getter/setter 數量"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
for file in doro_app/*.py; do
    count=$(grep -c "def get_\|def set_" "$file" 2>/dev/null || echo "0")
    if [ "$count" -gt 0 ]; then
        echo "$file: $count getter/setter"
    fi
done
echo ""

echo "✅ 檢查完成"
