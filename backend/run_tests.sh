#!/bin/bash

echo "=========================================="
echo "  高融石英管多通道液位检测系统 - 测试脚本"
echo "=========================================="

cd "$(dirname "$0")"

echo ""
echo "1. 运行单元测试..."
python3 -m pytest tests/test_unit.py -v --tb=short 2>/dev/null || python3 -m unittest tests.test_unit -v

echo ""
echo "=========================================="
echo "2. 运行 API 测试..."
echo "   (需要后端服务运行在 http://localhost:8000)"
echo "=========================================="

python3 tests/test_api.py

echo ""
echo "测试完成!"
