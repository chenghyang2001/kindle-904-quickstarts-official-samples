#!/bin/bash
# 初始化與驗收腳本：顯示 Python 版本並執行全部測試
set -e
echo 檢查 Python 版本
python --version
echo 執行 tests 目錄下的全部驗收測試
python -m unittest discover -s tests
echo 全部測試完成
