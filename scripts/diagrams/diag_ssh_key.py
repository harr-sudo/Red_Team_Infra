"""SSH key distribution — the operator's key only authorizes to the AWS-hosted
Dashboard Server (IP allow-list). The dashboard server then holds/uses the
INTERNAL keys to reach every deployment instance (Ansible + SSM), so the
operator's key never lands on deployment hosts.

Key categories:
  A. Operator external key  -> Dashboard Server (IP allow-list) ONLY.
  B. Windows RSA key (Terraform-generated) -> decrypts attack box/bastion pw.
  C. Host-generated internal ed25519 keys, exchanged via S3 (GOAD bootstrap).
SSM is the PREFERRED path from the dashboard to instances (no SSH key hop).
"""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.storage import S3
from diagrams.aws.management import SystemsManager
from diagrams.onprem.client import User

from _common import rt_diagram, operator, dashboard_hub, OPERATOR_EDGE, PEERING_EDGE

with rt_diagram("SSH Key Management — operator key stops at the Dashboard jump", "ssh-key-architecture"):
    op = operator("Operator laptop\nKey A: ed25519 private\n(never leaves laptop)")

    with dashboard_hub() as dash:
        # Category A: operator key authorizes ONLY to the dashboard server.
        op >> Edge(label="Key A public · IP allow-list (only authorized host)",
                   color="#2c7a4b", style="bold") >> dash

    # SSM is the preferred control path out of the dashboard.
    ssm = SystemsManager("SSM\n(preferred · no SSH key hop)")

    # S3 brokers the host-generated internal public keys (Category C).
    s3 = S3("S3 keys/{id}/*.pub\ninternal key exchange (7-day expiry)")

    with Cluster("Deployment VPCs  (C2 · GOAD)"):
        with Cluster("Linux instances"):
            jb = EC2("Jumpbox / Team Server / Redirector")
        with Cluster("Windows instances"):
            ab = EC2("Attack Box / Bastion\nKey B: RSA 4096 (pw decrypt)")

    # Dashboard holds the INTERNAL keys + reaches instances over peering / SSM.
    dash >> Edge(label="Key C internal (Ansible over VPC peering)",
                 color="#8a96a8", style="dashed") >> jb
    dash >> Edge(color="#8a96a8", style="dashed") >> ab
    dash >> Edge(label="run commands", color="#5a6472") >> ssm
    ssm >> Edge(color="#5a6472") >> jb
    ssm >> Edge(color="#5a6472") >> ab

    # Category C: ed25519 internal keys generated on hosts, swapped via S3.
    jb >> Edge(label="ed25519 .pub (PutObject)", color="#8a96a8", style="dotted") >> s3
    s3 >> Edge(label="peer .pub (GetObject)", color="#8a96a8", style="dotted") >> ab
