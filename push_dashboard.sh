#!/bin/bash

echo "------------------------------------------"
echo "🔍 STARTING SECURITY PRE-FLIGHT CHECK..."
echo "------------------------------------------"

# 1. Check if .env is ignored
if git check-ignore -q .env; then
    echo "✅ .env is safely ignored."
else
    echo "❌ ERROR: .env is NOT ignored! Stopping push."
    exit 1
fi

# 2. Check if .streamlit/ is ignored
if git check-ignore -q .streamlit/; then
    echo "✅ .streamlit/ is safely ignored."
else
    echo "❌ ERROR: .streamlit/ is NOT ignored! Stopping push."
    exit 1
fi

# 3. Check for tracked __pycache__ (the bug we found earlier)
if git ls-files | grep -q "__pycache__"; then
    echo "⚠️  WARNING: __pycache__ files are being tracked by git."
    echo "Cleaning up cache tracking..."
    git rm -r --cached __pycache__ > /dev/null 2>&1
    echo "✅ Cache tracking removed."
fi

echo "------------------------------------------"
echo "🚀 ALL CHECKS PASSED."
echo "------------------------------------------"

# 4. Prompt for Commit & Push
read -p "Enter commit message (or press enter for 'update dashboard'): " msg
if [ -z "$msg" ]; then
    msg="update dashboard"
fi

read -p "Ready to push to GitHub? (y/n): " confirm
if [[ $confirm == [yY] || $confirm == [yY][eE][sS] ]]; then
    git add .
    git commit -m "$msg"
    git push origin main
    echo "🎉 Push complete!"
else
    echo "❌ Push cancelled."
fi