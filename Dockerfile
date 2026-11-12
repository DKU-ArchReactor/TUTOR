FROM python:3.12-slim
WORKDIR /tutor
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home tutor
COPY service ./service
COPY tutor_contract ./tutor_contract
RUN chmod -R a+rX /tutor
ARG TUTOR_VERSION=development
ENV TUTOR_VERSION=$TUTOR_VERSION
USER 10001
EXPOSE 50051
HEALTHCHECK --interval=15s --timeout=3s --start-period=15s CMD ["python", "-m", "service.healthcheck"]
CMD ["python", "-m", "service.server"]
