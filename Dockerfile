FROM python:3.9-slim

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

# install requirements (without paddle)
RUN pip install --no-cache-dir -r requirements.txt

# 🔥 install paddle separately
RUN pip install --no-cache-dir paddlepaddle==2.5.2 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

RUN pip install --no-cache-dir paddleocr

CMD ["python", "bot.py"]
