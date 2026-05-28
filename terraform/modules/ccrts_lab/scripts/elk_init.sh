#!/bin/bash
# =============================================================================
# CCRTS Lab — ELK Telemetry Host First-Boot
# =============================================================================
# Installs Docker + docker-compose and runs a single-node Elasticsearch +
# Kibana + Logstash 8.19.0 stack with no auth (lab posture). 7-day ILM
# retention matches the Phase E curriculum (commit 7927dd8).
# =============================================================================
set -euxo pipefail

LOG=/var/log/ccrts-elk-init.log
exec > >(tee -a "$LOG") 2>&1
echo "=== CCRTS ELK ${hostname} first-boot $(date -u +%FT%TZ) ==="

# -----------------------------------------------------------------------------
# Hostname
# -----------------------------------------------------------------------------
hostnamectl set-hostname "${hostname}"
if ! grep -q "${hostname}" /etc/hosts; then
    echo "127.0.1.1 ${hostname}" >> /etc/hosts
fi

# -----------------------------------------------------------------------------
# Wait for NAT egress to come up
# -----------------------------------------------------------------------------
for i in $(seq 1 30); do
    if curl -sS --connect-timeout 3 http://archive.ubuntu.com >/dev/null 2>&1; then
        echo "Network ready after $i attempts"
        break
    fi
    echo "Waiting for NAT egress ($i/30)..."
    sleep 10
done

# -----------------------------------------------------------------------------
# Docker + docker-compose
# -----------------------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg lsb-release

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

DOCKER_ARCH=$(dpkg --print-architecture)
DOCKER_CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
echo "deb [arch=$DOCKER_ARCH signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $DOCKER_CODENAME stable" \
    > /etc/apt/sources.list.d/docker.list

apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker

# -----------------------------------------------------------------------------
# vm.max_map_count — required for Elasticsearch
# -----------------------------------------------------------------------------
sysctl -w vm.max_map_count=262144
echo "vm.max_map_count=262144" > /etc/sysctl.d/99-elasticsearch.conf

# -----------------------------------------------------------------------------
# docker-compose stack — single-node ELK 8.19.0, no auth (lab posture).
# Source: Phase E curriculum (commit 7927dd8).
# -----------------------------------------------------------------------------
mkdir -p /opt/ccrts-elk
cat > /opt/ccrts-elk/docker-compose.yml <<'YAML'
version: "3.8"
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.19.0
    container_name: ccrts-es
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - xpack.security.http.ssl.enabled=false
      - xpack.security.transport.ssl.enabled=false
      - ES_JAVA_OPTS=-Xms1g -Xmx1g
      - bootstrap.memory_lock=true
    ulimits:
      memlock:
        soft: -1
        hard: -1
    ports:
      - "9200:9200"
    volumes:
      - es-data:/usr/share/elasticsearch/data
    restart: unless-stopped

  kibana:
    image: docker.elastic.co/kibana/kibana:8.19.0
    container_name: ccrts-kibana
    depends_on:
      - elasticsearch
    environment:
      - ELASTICSEARCH_HOSTS=http://elasticsearch:9200
      - SERVER_HOST=0.0.0.0
      - SERVER_PUBLICBASEURL=http://0.0.0.0:5601
    ports:
      - "5601:5601"
    restart: unless-stopped

  logstash:
    image: docker.elastic.co/logstash/logstash:8.19.0
    container_name: ccrts-logstash
    depends_on:
      - elasticsearch
    environment:
      - LS_JAVA_OPTS=-Xms512m -Xmx512m
    ports:
      - "5044:5044"      # Beats
      - "5514:5514/udp"  # Syslog (UDP)
      - "5514:5514/tcp"  # Syslog (TCP)
    volumes:
      - ./logstash/pipeline:/usr/share/logstash/pipeline:ro
    restart: unless-stopped

volumes:
  es-data:
YAML

# Minimal Logstash pipeline: accept beats + syslog, ship to ES with ILM-managed
# index pattern matching the curriculum.
mkdir -p /opt/ccrts-elk/logstash/pipeline
cat > /opt/ccrts-elk/logstash/pipeline/ccrts.conf <<'CONF'
input {
  beats { port => 5044 }
  syslog { port => 5514 }
}

output {
  elasticsearch {
    hosts => ["http://elasticsearch:9200"]
    index => "ccrts-%%{+YYYY.MM.dd}"
  }
}
CONF

# -----------------------------------------------------------------------------
# Start the stack
# -----------------------------------------------------------------------------
cd /opt/ccrts-elk
docker compose pull
docker compose up -d

# -----------------------------------------------------------------------------
# 7-day ILM policy — wait for ES to be reachable, then PUT the policy and a
# matching index template. This mirrors the Phase E curriculum retention spec.
# -----------------------------------------------------------------------------
for i in $(seq 1 60); do
    if curl -sS --connect-timeout 3 http://localhost:9200/_cluster/health >/dev/null 2>&1; then
        echo "Elasticsearch reachable after $i attempts"
        break
    fi
    sleep 5
done

curl -sS -XPUT http://localhost:9200/_ilm/policy/ccrts-7d \
    -H 'Content-Type: application/json' \
    -d '{
      "policy": {
        "phases": {
          "hot":    { "actions": {} },
          "delete": { "min_age": "7d", "actions": { "delete": {} } }
        }
      }
    }' || true

curl -sS -XPUT http://localhost:9200/_index_template/ccrts \
    -H 'Content-Type: application/json' \
    -d '{
      "index_patterns": ["ccrts-*"],
      "template": {
        "settings": { "index.lifecycle.name": "ccrts-7d" }
      }
    }' || true

# -----------------------------------------------------------------------------
# Marker
# -----------------------------------------------------------------------------
mkdir -p /var/lib/ccrts
echo "ccrts-elk-init: ok $(date -u +%FT%TZ)" > /var/lib/ccrts/init.status

echo "=== CCRTS ELK first-boot complete $(date -u +%FT%TZ) ==="
