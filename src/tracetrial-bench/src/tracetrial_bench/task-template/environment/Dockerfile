FROM python:3.12.7-slim-bookworm

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        bash ca-certificates curl git jq procps socat \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 -s /bin/bash agent

WORKDIR /workspace
COPY --chown=agent:agent workspace/ /workspace/
COPY entrypoint_sim.sh /opt/tracetrial/entrypoint_sim.sh
RUN chmod +x /opt/tracetrial/entrypoint_sim.sh \
    && chown -R agent:agent /workspace

USER agent
