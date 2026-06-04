# CCRTS Lab Module - ELK Telemetry Host
# =============================================================================
# Single-node ELK 8.19.0 stack (Elasticsearch + Kibana + Logstash) on Ubuntu
# 22.04. Bootstrap via docker-compose, no auth (lab posture). Matches the
# Phase E curriculum (commit 7927dd8) — single-node deployment, ILM with
# 7-day retention, all components on one host.
# =============================================================================

resource "aws_instance" "elk" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = "t3.large"
  key_name      = local.effective_key_pair_name
  subnet_id     = aws_subnet.private.id
  private_ip    = "${local.ip_range}.50"

  vpc_security_group_ids = [
    aws_security_group.lab_fabric.id,
    aws_security_group.elk.id,
  ]

  iam_instance_profile = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null

  user_data = templatefile("${path.module}/scripts/elk_init.sh", {
    hostname = "elk"
  })

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 60 # ELK indices + 7-day retention
    encrypted             = true
    delete_on_termination = true

    tags = merge(local.base_tags, {
      Name     = "${local.name_prefix}-elk-root"
      Hostname = "elk"
    })
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  tags = merge(local.base_tags, {
    Name     = "${local.name_prefix}-elk"
    Hostname = "elk"
    Role     = "telemetry"
    OS       = "Ubuntu2204"
  })
}
