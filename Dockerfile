FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && groupadd -g 10001 ivory && useradd -u 10001 -g 10001 -m ivory
COPY app.py seo.py start.py ./
USER 10001:10001
ENV DATA_DIR=/data CLIENT_FILES_DIR=/clients PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "/app/start.py"]
