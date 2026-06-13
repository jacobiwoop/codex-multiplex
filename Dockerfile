FROM python:3.13-slim

# Install codex-relay + pyyaml
RUN pip install --no-cache-dir codex-relay pyyaml

# Copy app
COPY server.py /app/server.py
COPY providers.yaml /app/providers.yaml

EXPOSE 4444

CMD ["python3", "/app/server.py"]
