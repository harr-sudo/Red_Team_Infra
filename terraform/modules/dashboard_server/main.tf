terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# =============================================================================
# DATA SOURCES
# =============================================================================

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

data "aws_caller_identity" "current" {}

# =============================================================================
# VPC
# =============================================================================

resource "aws_vpc" "dashboard" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, {
    Name = "${var.project_name}-vpc"
  })
}

resource "aws_subnet" "dashboard" {
  vpc_id                  = aws_vpc.dashboard.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 1)
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name = "${var.project_name}-public-subnet"
  })
}

resource "aws_internet_gateway" "dashboard" {
  vpc_id = aws_vpc.dashboard.id

  tags = merge(var.tags, {
    Name = "${var.project_name}-igw"
  })
}

resource "aws_route_table" "dashboard" {
  vpc_id = aws_vpc.dashboard.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.dashboard.id
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-rt"
  })
}

resource "aws_route_table_association" "dashboard" {
  subnet_id      = aws_subnet.dashboard.id
  route_table_id = aws_route_table.dashboard.id
}

# =============================================================================
# SECURITY GROUP
# =============================================================================

resource "aws_security_group" "dashboard" {
  name_prefix = "${var.project_name}-sg-"
  vpc_id      = aws_vpc.dashboard.id
  description = "Dashboard server - SSH from operator IPs only"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.dashboard_allowed_ips
    description = "SSH from operator IPs"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound"
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# =============================================================================
# IAM ROLE (scoped policy - NOT AdministratorAccess)
# =============================================================================

resource "aws_iam_role" "dashboard" {
  name = "${var.project_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })

  tags = merge(var.tags, { Name = "${var.project_name}-role" })
}

resource "aws_iam_policy" "dashboard" {
  name = "${var.project_name}-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EC2Scoped"
        Effect = "Allow"
        Action = [
          "ec2:Describe*",
          "ec2:RunInstances", "ec2:TerminateInstances", "ec2:StartInstances", "ec2:StopInstances",
          "ec2:CreateSecurityGroup", "ec2:DeleteSecurityGroup",
          "ec2:AuthorizeSecurityGroupIngress", "ec2:AuthorizeSecurityGroupEgress",
          "ec2:RevokeSecurityGroupIngress", "ec2:RevokeSecurityGroupEgress",
          "ec2:UpdateSecurityGroupRuleDescriptionsIngress", "ec2:UpdateSecurityGroupRuleDescriptionsEgress",
          "ec2:CreateVpc", "ec2:DeleteVpc", "ec2:ModifyVpcAttribute",
          "ec2:CreateSubnet", "ec2:DeleteSubnet",
          "ec2:CreateRouteTable", "ec2:DeleteRouteTable", "ec2:CreateRoute", "ec2:DeleteRoute",
          "ec2:AssociateRouteTable", "ec2:DisassociateRouteTable",
          "ec2:CreateInternetGateway", "ec2:DeleteInternetGateway",
          "ec2:AttachInternetGateway", "ec2:DetachInternetGateway",
          "ec2:CreateNatGateway", "ec2:DeleteNatGateway",
          "ec2:AllocateAddress", "ec2:ReleaseAddress", "ec2:AssociateAddress", "ec2:DisassociateAddress",
          "ec2:CreateTags", "ec2:DeleteTags",
          "ec2:CreateKeyPair", "ec2:DeleteKeyPair", "ec2:ImportKeyPair",
          "ec2:ModifyInstanceAttribute",
          "ec2:CreateNetworkInterface", "ec2:DeleteNetworkInterface", "ec2:AttachNetworkInterface", "ec2:DetachNetworkInterface",
          "ec2:CreateVpcPeeringConnection", "ec2:AcceptVpcPeeringConnection", "ec2:DeleteVpcPeeringConnection",
          "ec2:CreateManagedPrefixList", "ec2:DeleteManagedPrefixList", "ec2:ModifyManagedPrefixList", "ec2:GetManagedPrefixListEntries",
          "ec2:GetPasswordData",
          "ec2:CreateNetworkAcl", "ec2:DeleteNetworkAcl", "ec2:CreateNetworkAclEntry", "ec2:DeleteNetworkAclEntry", "ec2:ReplaceNetworkAclAssociation",
          "ec2:CreateVpcEndpoint", "ec2:DeleteVpcEndpoints", "ec2:ModifyVpcEndpoint",
        ]
        Resource = "*"
        Condition = { StringEquals = { "aws:RequestedRegion" = [var.aws_region, "us-east-1"] } }
      },
      {
        Sid    = "NetworkingAndCDN"
        Effect = "Allow"
        Action = [
          "elasticloadbalancing:*",
          "cloudfront:CreateDistribution", "cloudfront:GetDistribution", "cloudfront:UpdateDistribution",
          "cloudfront:DeleteDistribution", "cloudfront:TagResource", "cloudfront:UntagResource",
          "cloudfront:ListDistributions", "cloudfront:ListTagsForResource",
        ]
        Resource = "*"
      },
      {
        Sid    = "S3Scoped"
        Effect = "Allow"
        Action = ["s3:*"]
        Resource = [
          "arn:aws:s3:::${var.project_name}-*",
          "arn:aws:s3:::${var.project_name}-*/*",
          aws_s3_bucket.tfstate.arn,
          "${aws_s3_bucket.tfstate.arn}/*"
        ]
      },
      {
        Sid    = "Route53"
        Effect = "Allow"
        Action = ["route53:*", "route53domains:*"]
        Resource = "*"
      },
      {
        Sid    = "ACM"
        Effect = "Allow"
        Action = ["acm:*"]
        Resource = "*"
      },
      {
        Sid    = "IAMScoped"
        Effect = "Allow"
        Action = [
          "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:PassRole",
          "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:PutRolePolicy",
          "iam:DeleteRolePolicy", "iam:GetRolePolicy", "iam:ListRolePolicies",
          "iam:ListAttachedRolePolicies", "iam:TagRole", "iam:UntagRole",
          "iam:CreateInstanceProfile", "iam:DeleteInstanceProfile",
          "iam:AddRoleToInstanceProfile", "iam:RemoveRoleFromInstanceProfile",
          "iam:GetInstanceProfile", "iam:ListInstanceProfiles",
          "iam:ListInstanceProfilesForRole", "iam:CreatePolicy", "iam:DeletePolicy",
          "iam:GetPolicy", "iam:GetPolicyVersion", "iam:ListPolicyVersions"
        ]
        Resource = "*"
      },
      {
        Sid    = "SecretsManagerScoped"
        Effect = "Allow"
        Action = [
          "secretsmanager:CreateSecret", "secretsmanager:DeleteSecret",
          "secretsmanager:GetSecretValue", "secretsmanager:PutSecretValue",
          "secretsmanager:UpdateSecret", "secretsmanager:DescribeSecret",
          "secretsmanager:TagResource", "secretsmanager:UntagResource",
          "secretsmanager:GetResourcePolicy", "secretsmanager:PutResourcePolicy",
          "secretsmanager:DeleteResourcePolicy",
        ]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:*"
      },
      {
        Sid      = "SecretsManagerList"
        Effect   = "Allow"
        Action   = ["secretsmanager:ListSecrets"]
        Resource = "*"
      },
      {
        Sid    = "Monitoring"
        Effect = "Allow"
        Action = ["logs:*", "cloudwatch:*", "ce:GetCostAndUsage", "ce:GetCostForecast"]
        Resource = "*"
      },
      {
        Sid    = "SSMScoped"
        Effect = "Allow"
        Action = [
          "ssm:SendCommand", "ssm:GetCommandInvocation", "ssm:ListCommandInvocations",
          "ssm:StartSession", "ssm:TerminateSession", "ssm:ResumeSession", "ssm:DescribeSessions",
          "ssm:DescribeInstanceInformation",
          "ssm:GetParameter", "ssm:GetParameters", "ssm:PutParameter", "ssm:DeleteParameter",
          "ssm:DescribeParameters", "ssm:GetParametersByPath",
          "ssm:ListDocuments", "ssm:DescribeDocument", "ssm:GetDocument",
        ]
        Resource = "*"
      },
      {
        Sid    = "DynamoDB"
        Effect = "Allow"
        Action = ["dynamodb:*"]
        Resource = "arn:aws:dynamodb:${var.aws_region}:*:table/${var.project_name}-*"
      },
      {
        Sid    = "STS"
        Effect = "Allow"
        Action = ["sts:GetCallerIdentity"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "dashboard" {
  role       = aws_iam_role.dashboard.name
  policy_arn = aws_iam_policy.dashboard.arn
}

resource "aws_iam_instance_profile" "dashboard" {
  name = "${var.project_name}-profile"
  role = aws_iam_role.dashboard.name
}

# =============================================================================
# S3 STATE BACKEND (created by this module, used by server)
# =============================================================================

resource "aws_s3_bucket" "tfstate" {
  bucket_prefix = "${var.project_name}-tfstate-"
  force_destroy = false

  tags = merge(var.tags, { Name = "${var.project_name}-tfstate" })
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyUnencryptedTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.tfstate.arn, "${aws_s3_bucket.tfstate.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
      {
        Sid       = "DenyOtherAccounts"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.tfstate.arn, "${aws_s3_bucket.tfstate.arn}/*"]
        Condition = { StringNotEquals = { "aws:PrincipalAccount" = data.aws_caller_identity.current.account_id } }
      }
    ]
  })
  depends_on = [aws_s3_bucket_public_access_block.tfstate]
}

resource "aws_dynamodb_table" "tflock" {
  name         = "${var.project_name}-tflock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = merge(var.tags, { Name = "${var.project_name}-tflock" })
}

# =============================================================================
# EC2 INSTANCE
# =============================================================================

resource "aws_instance" "dashboard" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.dashboard.id
  vpc_security_group_ids = [aws_security_group.dashboard.id]
  iam_instance_profile   = aws_iam_instance_profile.dashboard.name

  root_block_device {
    volume_size = var.ebs_volume_size
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = templatefile("${path.module}/user_data.sh", {
    operator_keys  = var.operator_ssh_public_keys
    s3_bucket      = aws_s3_bucket.tfstate.id
    dynamodb_table = aws_dynamodb_table.tflock.name
    aws_region     = var.aws_region
  })

  tags = merge(var.tags, { Name = "${var.project_name}-server" })
}

resource "aws_eip" "dashboard" {
  instance = aws_instance.dashboard.id
  domain   = "vpc"

  tags = merge(var.tags, { Name = "${var.project_name}-eip" })
}
