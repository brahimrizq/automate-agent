FROM ubuntu:25.10@sha256:7cc5e35f6567ee8c66d2abb4aab0fd866669e6207c237c3a8f0947a5c7f17092 AS base

# Digest pins the distribution; scheduled rebuilds take security package updates.
# hadolint ignore=DL3008
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ca-certificates python3 tini \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /usr/local/ltechagent /run/wrapper /backup
COPY wrapper/ /opt/wrapper/
COPY LICENSE /usr/share/doc/automate-wrapper/LICENSE
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /usr/local/ltechagent
ENTRYPOINT ["/usr/bin/tini", "-s", "--", "python3", "/opt/wrapper/entrypoint.py"]
CMD ["run"]
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python3", "/opt/wrapper/healthcheck.py"]
LABEL org.opencontainers.image.source="https://github.com/brahimrizq/automate-agent" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.description="Experimental unofficial wrapper; contains no ConnectWise agent"

# Explicit test-only target: original synthetic fixture, never a release target.
FROM base AS mock-build
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
COPY tests/fixtures/ /fixtures/
RUN gcc -Wall -Wextra -Werror -O2 /fixtures/mock.c -o /fixtures/ltechagent \
    && python3 /fixtures/make_archive.py
FROM base AS mock
COPY --from=mock-build /fixtures/installer.zip /fixtures/installer.zip
COPY --from=mock-build /fixtures/config /fixtures/config
ENV INSTALLER_FILE=/fixtures/installer.zip AGENT_CONFIG_FILE=/fixtures/config

# The default build is always the public dependency-only image.
FROM base AS runtime
