FROM python:3.11-slim

WORKDIR /app

# ক্যাশ মেমোরি ক্লিয়ার ও প্রয়োজনীয় ডিপেন্ডেন্সি
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# PEP 668 এরর বাইপাস নিশ্চিত করতে ফ্ল্যাগসহ ইন্সটলেশন
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
