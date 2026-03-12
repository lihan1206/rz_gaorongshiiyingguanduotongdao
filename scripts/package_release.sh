#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_DIR="$ROOT_DIR/release"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
PACKAGE_NAME="gaorongshiiyingguanduotongdao_release_${TIMESTAMP}.tar.gz"
PACKAGE_PATH="$RELEASE_DIR/$PACKAGE_NAME"

mkdir -p "$RELEASE_DIR"

# 轻量打包：不执行任何自动测试，仅保留业务运行所需文件。
tar -czf "$PACKAGE_PATH" \
  --exclude='./.git' \
  --exclude='./release' \
  --exclude='./frontend/node_modules' \
  --exclude='./frontend/dist' \
  --exclude='./**/__pycache__' \
  --exclude='./**/.pytest_cache' \
  --exclude='./**/.venv' \
  --exclude='./**/venv' \
  --exclude='./**/target' \
  --exclude='./**/__tests__' \
  --exclude='./**/tests' \
  --exclude='./**/*_test.py' \
  --exclude='./**/test_*.py' \
  --exclude='./**/*.test.*' \
  --exclude='./**/*.spec.*' \
  --exclude='./**/qa_*.sh' \
  --exclude='./**/*qa*.sh' \
  --exclude='./.DS_Store' \
  --exclude='./Prompt.md' \
  --exclude='./user_rule.md' \
  --exclude='./mb.docx' \
  --exclude='./高融石英管多通道液位同步检测系统_软著材料说明书.docx' \
  --exclude='./高融石英管多通道液位同步检测系统_软著材料说明书.txt' \
  --exclude='./高融石英管多通道液位同步检测系统_软著材料说明书.html' \
  -C "$ROOT_DIR" .

echo "打包完成: $PACKAGE_PATH"
ls -lh "$PACKAGE_PATH"
