FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY frontend ./frontend
COPY scenarios ./scenarios
RUN pip install --no-cache-dir .

ENV INSIGHTIQ_AGENT_MODE=deterministic
EXPOSE 8000
CMD ["uvicorn", "insightiq.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
