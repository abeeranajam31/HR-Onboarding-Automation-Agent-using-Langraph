FROM python:3.11-slim@sha256:6d85378d88a19cd4d76079817532d62232be95757cb45945a99fec8e8084b9c2

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
RUN mkdir -p /app/persistence/checkpoints

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
