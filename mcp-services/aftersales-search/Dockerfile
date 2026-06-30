FROM python:3.12-slim
WORKDIR /app

# 先装依赖（含本项目，pyproject + src 即可 pip install）
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# 再放运行期辅助文件
COPY service.yaml register.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

# 监听地址/端口固定为容器内 0.0.0.0:8000；FQC 报告落地到挂卷目录
ENV MCP_HOST=0.0.0.0 \
    MCP_PORT=8000 \
    FQC_REPORT_DIR=/data/fqc_reports

EXPOSE 8000
CMD ["./entrypoint.sh"]
