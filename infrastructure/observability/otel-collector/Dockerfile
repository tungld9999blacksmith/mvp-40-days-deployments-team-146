# OpenTelemetry Collector (contrib) with the EV Care config baked in.
# Railway cannot mount config files, so the config ships inside the image.
# Build context = this directory (railway up ... --path-as-root, docker compose).
# Pinned version: bump deliberately and re-run the config validation.
ARG OTELCOL_VERSION=0.161.0
FROM otel/opentelemetry-collector-contrib:${OTELCOL_VERSION}

# The image's default command already reads this path.
COPY config.yaml /etc/otelcol-contrib/config.yaml

# Soft Go heap limit (~80% of OTEL_MEMORY_LIMIT_MIB) so GC kicks in before
# memory_limiter starts refusing data.
ENV GOMEMLIMIT=160MiB

# 4317 OTLP gRPC, 4318 OTLP HTTP, 13133 health check
EXPOSE 4317 4318 13133
