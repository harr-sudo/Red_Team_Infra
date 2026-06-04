# CCRTS Lab Module - Kali Attacker Host
# =============================================================================
# CREST RTS Kali Candidate Image (CREST AMI), copied from eu-west-2 by the
# aws_ami_copy in main.tf. Sits in the private subnet at <ip_range>.20 and is
# reached operationally via the dashboard SSH jump.
# =============================================================================

resource "aws_instance" "kali" {
  ami           = local.kali_ami_id
  instance_type = "t3.medium"
  key_name      = local.effective_key_pair_name
  subnet_id     = aws_subnet.private.id
  private_ip    = "${local.ip_range}.20"

  vpc_security_group_ids = [
    aws_security_group.lab_fabric.id,
    aws_security_group.kali.id,
  ]

  iam_instance_profile = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null

  user_data = templatefile("${path.module}/scripts/kali_init.sh", {
    hostname = "kali"
  })

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 60
    encrypted             = true
    delete_on_termination = true

    tags = merge(local.base_tags, {
      Name     = "${local.name_prefix}-kali-root"
      Hostname = "kali"
    })
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  tags = merge(local.base_tags, {
    Name     = "${local.name_prefix}-kali"
    Hostname = "kali"
    Role     = "attacker"
    OS       = "Kali"
  })
}
