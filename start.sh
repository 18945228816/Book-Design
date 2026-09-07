#!/bin/bash

# 切换到项目目录
cd /root/workhome/Book-Design/backend

# 激活 conda 环境
source ~/miniconda3/etc/profile.d/conda.sh
conda activate book_design

# 启动后端
echo "正在启动后端服务..."
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
