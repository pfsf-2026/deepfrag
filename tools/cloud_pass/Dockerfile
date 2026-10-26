# Demo-pass image for the Cloud Run jobs `demo-pass` (sharded) and `demo-nightly`.
# Build context: tools/ (see build.sh). qw-analyze is cross-compiled by build.sh from the local
# mvd_analyzer checkout, the same source the mvd-api image is built from.
FROM python:3.12-slim
RUN pip install --no-cache-dir google-cloud-storage==2.18.2 requests==2.32.3
WORKDIR /app
COPY cloud_pass/qw-analyze /app/qw-analyze
COPY cloud_pass/passes.py cloud_pass/run_shard.py /app/
COPY mvd_features/*.py mvd_features/*.json /app/mvd_features/
ENTRYPOINT ["python3", "/app/run_shard.py"]
