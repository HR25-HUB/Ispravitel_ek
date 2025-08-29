FROM mcr.microsoft.com/devcontainers/python:3.11

RUN pip install --no-cache-dir uv ruff
WORKDIR /workspace

COPY requirements.txt .
RUN uv pip install -r requirements.txt

CMD [ "python", "main.py" ]
