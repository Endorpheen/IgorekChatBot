FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir fastapi uvicorn playwright
RUN playwright install

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
