# CCRTS Lab Module - Active Directory (ccrts-full only)
# =============================================================================
# Deploys dc01 (DC for ccrts.local) and ad_ws01 (domain-joined member) when
# lab_size = "ccrts-full". Both use the public Windows Server 2022 AMI —
# the DC role is established at first boot via dc_init.ps1; the workstation
# domain-joins via ad_ws_init.ps1.
#
# The local.ad_vms map is populated in main.tf and gated on lab_size.
# =============================================================================

resource "aws_instance" "ad" {
  for_each = local.ad_vms

  ami           = each.value.ami
  instance_type = each.value.instance_type
  key_name      = local.effective_key_pair_name
  subnet_id     = aws_subnet.private.id
  private_ip    = each.value.private_ip

  vpc_security_group_ids = [
    aws_security_group.lab_fabric.id,
    each.key == "dc01" ? aws_security_group.ad_dc[0].id : aws_security_group.ad_ws[0].id,
  ]

  iam_instance_profile = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null
  user_data            = each.value.user_data

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 60
    encrypted             = true
    delete_on_termination = true

    tags = merge(local.base_tags, {
      Name     = "${local.name_prefix}-${each.value.hostname}-root"
      Hostname = each.value.hostname
    })
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  tags = merge(local.base_tags, {
    Name     = "${local.name_prefix}-${each.value.hostname}"
    Hostname = each.value.hostname
    Role     = each.value.role
    Domain   = "ccrts.local"
    OS       = "WindowsServer2022"
  })

  # The AD-joined workstation must wait for the DC to come up first.
  depends_on = [aws_instance.kali]
}
