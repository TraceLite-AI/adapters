FROM python:3.12-slim

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        bash ca-certificates curl git jq procps socat \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY workspace/ /workspace/
COPY entrypoint_sim.sh /opt/tracetrial/entrypoint_sim.sh
RUN chmod +x /opt/tracetrial/entrypoint_sim.sh
