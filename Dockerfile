FROM python:3.9-slim


ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY page_modules/ ./page_modules/
COPY app.py splash_page.py database.py timezone_utils.py ./
COPY crawler.py scraper_worker.py run_scraper_loop.py sentiment_service.py ./
COPY indonesian-normalisasi-slangword-complete.txt indonesian-stopwords-complete.txt ./
COPY nrt_activation.json ./
COPY model_naive_bayes.pkl tfidf_vectorizer.pkl ./

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
