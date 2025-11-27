#!/bin/bash
# 快速测试脚本 - 检查代码质量和运行测试

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║        Astrbot Self-Learning Plugin - 测试工具                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# 检查是否安装了测试工具
check_tool() {
    if ! command -v $1 &> /dev/null; then
        echo "⚠️  $1 未安装，跳过..."
        return 1
    fi
    return 0
}

# 1. Python 语法检查
echo "🔍 [1/6] Python 语法检查..."
python -m py_compile *.py 2>/dev/null && echo "✅ 语法检查通过" || echo "❌ 语法错误"
echo ""

# 2. 代码风格检查
echo "🎨 [2/6] 代码风格检查 (flake8)..."
if check_tool flake8; then
    flake8 --max-line-length=120 --exclude=venv,__pycache__,.git,web_res --count --statistics . || true
else
    echo "💡 安装: pip install flake8"
fi
echo ""

# 3. 代码复杂度分析
echo "📊 [3/6] 代码复杂度分析 (radon)..."
if check_tool radon; then
    echo "圈复杂度 (推荐 < 10):"
    radon cc . -a -s --exclude="venv,__pycache__,web_res" | head -20
    echo ""
    echo "可维护性指数 (推荐 > 20):"
    radon mi . -s --exclude="venv,__pycache__,web_res" | head -10
else
    echo "💡 安装: pip install radon"
fi
echo ""

# 4. 安全检查
echo "🔒 [4/6] 安全漏洞扫描 (bandit)..."
if check_tool bandit; then
    bandit -r . -ll -f json -o bandit_report.json 2>/dev/null && \
        echo "✅ 安全检查完成，报告: bandit_report.json" || \
        echo "⚠️  发现潜在安全问题，查看: bandit_report.json"
else
    echo "💡 安装: pip install bandit"
fi
echo ""

# 5. 运行现有测试
echo "🧪 [5/6] 运行 API 测试..."
if [ -f "test_api_simple.py" ]; then
    echo "运行简化测试..."
    timeout 10 python test_api_simple.py 2>&1 | head -20 || echo "⚠️  测试需要 WebUI 运行"
else
    echo "ℹ️  未找到测试文件"
fi
echo ""

# 6. 文件统计
echo "📈 [6/6] 项目统计..."
echo "Python 文件数:"
find . -name "*.py" -not -path "./venv/*" -not -path "./__pycache__/*" | wc -l
echo "总代码行数:"
find . -name "*.py" -not -path "./venv/*" -not -path "./__pycache__/*" -exec wc -l {} + | tail -1
echo ""

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                        测试完成                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "💡 建议的下一步:"
echo "  1. 查看 bandit_report.json 处理安全问题"
echo "  2. 运行 'flake8 .' 修复代码风格问题"
echo "  3. 创建单元测试 (参考 docs/TESTING_GUIDE.md)"
echo ""
