FROM python:3.13-alpine@sha256:79e7a9b9ff1cbceff819f856fb374477792a5967759d94df266de7b7b4120e6f
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
RUN addgroup -g 10001 -S app && adduser -u 10001 -S -G app -H -D app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app app/ ./app/
USER app
EXPOSE 8080
CMD ["python", "-m", "app.server"]
