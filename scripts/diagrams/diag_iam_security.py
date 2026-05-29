"""IAM security — least-privilege roles PER VPC + 3-layer confused-deputy
protection. The AWS-hosted Dashboard Server has its own IAM role and assumes/
scopes per-VPC when it drives Terraform + reaches deployments.

Roles:
  * Dashboard Server role — control plane (Terraform, SSM, scoped per VPC).
  * cs_download_c2  — C2 VPC instances (SourceVpc = C2 VPC).
  * cs_download_goad — GOAD VPC instances (SourceVpc = GOAD VPC).
Confused-deputy: trust policy aws:SourceAccount; permission policy
aws:SourceVpc + aws:SecureTransport. Cross-VPC / cross-account = denied.
"""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.storage import S3
from diagrams.aws.security import IAMRole, SecretsManager
from diagrams.aws.management import SystemsManager

from _common import rt_diagram, operator, dashboard_hub, OPERATOR_EDGE, PEERING_EDGE

with rt_diagram("IAM Security — least-privilege roles per VPC + confused-deputy guard", "iam-security-architecture"):
    op = operator()

    with dashboard_hub() as dash:
        op >> OPERATOR_EDGE >> dash
        dash_role = IAMRole("Dashboard role\nTerraform + SSM\nassumes/scopes per-VPC")
        dash >> Edge(color="#5a6472") >> dash_role

    ssm = SystemsManager("SSM")

    with Cluster("C2 VPC  10.0.0.0/16"):
        role_c2 = IAMRole("cs_download_c2\nSourceAccount + SourceVpc=C2\nSecureTransport=true")
        ec2_c2 = EC2("Team Server · Attack Box\n(C2 instance profile)")
        role_c2 >> Edge(label="instance profile", color="#5a6472") >> ec2_c2

    with Cluster("GOAD VPC  192.168.56.0/24"):
        role_goad = IAMRole("cs_download_goad\nSourceAccount + SourceVpc=GOAD\nSecureTransport=true")
        ec2_goad = EC2("Jumpbox · Team Server · Attack Box\n(GOAD instance profile)")
        role_goad >> Edge(label="instance profile", color="#5a6472") >> ec2_goad

    with Cluster("Shared resources  (3-layer confused-deputy)"):
        bucket = S3("S3 deploy bucket\nL3 bucket policy:\ndeny non-VPC / non-account / non-HTTPS")
        secret = SecretsManager("Secrets Manager\nGitHub PAT (ARN-scoped)")

    # Dashboard role scopes into each VPC; SSM is the management path.
    dash_role >> Edge(label="assume / scope", color="#8a96a8", style="dashed") >> role_c2
    dash_role >> Edge(label="assume / scope", color="#8a96a8", style="dashed") >> role_goad
    dash >> Edge(color="#5a6472") >> ssm
    ssm >> Edge(color="#5a6472") >> ec2_c2
    ssm >> Edge(color="#5a6472") >> ec2_goad

    # Per-VPC least-privilege access to shared resources (VPC-conditioned).
    ec2_c2 >> Edge(label="L2: SourceVpc + HTTPS", color="#2c7a4b") >> bucket
    ec2_goad >> Edge(label="L2: SourceVpc + HTTPS", color="#2c7a4b") >> bucket
    ec2_c2 >> Edge(label="GetSecretValue", color="#8a96a8", style="dotted") >> secret
    ec2_goad >> Edge(color="#8a96a8", style="dotted") >> secret
