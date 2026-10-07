FROM python:3.11-alpine

WORKDIR /app

# Alpine me packages turant bina wait kiye install ho jate hain
RUN apk add --no-cache gcc musl-dev libffi-dev

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
