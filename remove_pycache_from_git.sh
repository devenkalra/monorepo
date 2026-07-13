#!/bin/bash
# remove_pycache_from_git.sh
# Removes __pycache__ files from git tracking

set -e

cd "$(dirname "$0")"

echo "================================================"
echo "Remove __pycache__ from Git Tracking"
echo "================================================"
echo ""

echo "Step 1: Removing __pycache__ directories from git index..."
git rm -r --cached **/__pycache__/ 2>/dev/null || true
git rm -r --cached **/*.pyc 2>/dev/null || true
git rm -r --cached **/*.pyo 2>/dev/null || true
git rm -r --cached **/*.pyd 2>/dev/null || true

echo "✓ Removed from git index"
echo ""

echo "Step 2: Updating .gitignore..."

# Check if .gitignore exists
if [ ! -f .gitignore ]; then
    echo "Creating .gitignore..."
    touch .gitignore
fi

# Add Python cache entries if not already present
if ! grep -q "__pycache__" .gitignore; then
    echo "" >> .gitignore
    echo "# Python cache files" >> .gitignore
    echo "__pycache__/" >> .gitignore
    echo "*.py[cod]" >> .gitignore
    echo "*\$py.class" >> .gitignore
    echo "*.so" >> .gitignore
    echo ".Python" >> .gitignore
    echo "*.egg" >> .gitignore
    echo "*.egg-info/" >> .gitignore
    echo "dist/" >> .gitignore
    echo "build/" >> .gitignore
    echo ".eggs/" >> .gitignore
    echo "✓ Added Python cache entries to .gitignore"
else
    echo "✓ Python cache entries already in .gitignore"
fi

echo ""
echo "Step 3: Checking status..."
PYCACHE_COUNT=$(git status --short | grep -c "__pycache__\|\.pyc" || true)

if [ "$PYCACHE_COUNT" -gt 0 ]; then
    echo "⚠️  Found $PYCACHE_COUNT __pycache__ files still staged"
    echo ""
    echo "These files are staged for deletion. To complete:"
    echo "  git commit -m 'Remove __pycache__ from tracking'"
else
    echo "✓ No __pycache__ files in git tracking"
fi

echo ""
echo "Step 4: Cleaning up existing __pycache__ directories..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
find . -type f -name "*.pyd" -delete 2>/dev/null || true

echo "✓ Cleaned up local __pycache__ directories"
echo ""
echo "================================================"
echo "✓ Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "  1. Review changes: git status"
echo "  2. Commit the removal: git commit -m 'Remove __pycache__ from tracking and update .gitignore'"
echo "  3. Push changes: git push"
echo ""
echo "Note: __pycache__ directories will be recreated when you run Python,"
echo "but they will now be ignored by git."
