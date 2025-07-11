FROM python:3.10-slim

WORKDIR /app

# 安装依赖
COPY ../requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 只复制主代码目录，其它数据和配置文件由挂载提供
COPY ../app/ ./app/

# 默认启动命令（可被compose覆盖）
CMD ["python", "-m", "app.core.monitor"] 