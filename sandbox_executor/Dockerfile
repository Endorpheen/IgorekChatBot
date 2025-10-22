FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir fastapi uvicorn pymupdf python-docx python-multipart

RUN useradd --create-home --shell /bin/bash app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
