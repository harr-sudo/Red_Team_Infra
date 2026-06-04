# CCRTS Lab Module - Windows Workstation
# =============================================================================
# CREST RTS Windows AMI, copied from eu-west-2. Sits in the private subnet at
# <ip_range>.30. user_data enables PSRemoting + sets the local Administrator
# password from the tfvar.
# =============================================================================

resource "aws_instance" "windows_workstation" {
  ami           = local.windows_ami_id
  instance_type = "t3.large"
  key_name      = local.effective_key_pair_name
  subnet_id     = aws_subnet.private.id
  private_ip    = "${local.ip_range}.30"

  vpc_security_group_ids = [
    aws_security_group.lab_fabric.id,
    aws_security_group.win_ws.id,
  ]

  iam_instance_profile = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null

  user_data = templatefile("${path.module}/scripts/windows_workstation_init.ps1", {
    hostname       = "windows-ws"
    admin_password = var.windows_admin_password
  })

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 80
    encrypted             = true
    delete_on_termination = true

    tags = merge(local.base_tags, {
      Name     = "${local.name_prefix}-windows-ws-root"
      Hostname = "windows-ws"
    })
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  tags = merge(local.base_tags, {
    Name     = "${local.name_prefix}-windows-ws"
    Hostname = "windows-ws"
    Role     = "workstation"
    OS       = "Windows"
  })
}
