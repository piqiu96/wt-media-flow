#!/bin/bash

# 矩阵视频自动发布系统 - 打包脚本

ENV=${1:-dev}  # 默认 dev 环境

# 清理旧包
echo "清理旧包..."
rm -rf output

# 创建输出目录
echo "创建输出目录..."
mkdir -p output/{src,data/videos,log,conf}

# 复制源代码
echo "复制源代码..."
cp -r src/* output/src/

# 复制主程序文件
echo "复制主程序文件..."
cp main.py settings.py requirements.txt README.md output/

# 根据环境复制配置
if [ "$ENV" == "online" ]; then
    echo "使用生产环境配置 (conf_online)..."
    cp conf_online/* output/conf/
else
    echo "使用开发环境配置 (conf)..."
    cp conf/* output/conf/
fi

# 创建 .gitignore
cat > output/.gitignore << 'EOF'
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
*.db
*.log
conf/.env
EOF

echo ""
echo "========================================="
echo "打包完成!"
echo "输出目录: output/"
echo "环境: $ENV"
echo "========================================="
