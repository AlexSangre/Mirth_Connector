FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY devices.py exporter.py ./

CMD ["python", "exporter.py"]
