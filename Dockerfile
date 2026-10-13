FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55 AS runtime

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
FROM runtime AS mock-build
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
COPY tests/fixtures/ /fixtures/
RUN gcc -Wall -Wextra -Werror -O2 /fixtures/mock.c -o /fixtures/ltechagent \
    && python3 /fixtures/make_archive.py
FROM runtime AS mock
COPY --from=mock-build /fixtures/installer.zip /fixtures/installer.zip
COPY --from=mock-build /fixtures/config /fixtures/config
ENV INSTALLER_FILE=/fixtures/installer.zip AGENT_CONFIG_FILE=/fixtures/config
