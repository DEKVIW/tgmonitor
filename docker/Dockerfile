FROM python:3.10-slim

WORKDIR /app

# 安装依赖
COPY ../requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 复制主代码和数据目录
COPY ../app/ ./app/
COPY ../data/ ./data/
COPY ../users.json ./
COPY ../.env ./

# 默认启动命令（可被compose覆盖）
CMD ["python", "-m", "app.core.monitor"] 