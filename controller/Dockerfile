FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir requests redis pyyaml docker

COPY controller.py .

CMD ["python", "-u", "controller.py"]
