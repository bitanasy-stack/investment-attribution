FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV APP_DATA_DIR=/app-data
RUN useradd -m appuser && mkdir -p /app-data && chown appuser:appuser /app-data
USER appuser
EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health',timeout=5)"
CMD ["python","-m","streamlit","run","app.py","--server.address=0.0.0.0","--server.port=8501","--server.headless=true"]
