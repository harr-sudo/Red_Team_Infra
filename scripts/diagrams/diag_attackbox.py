"""attack box — Windows Server 2022 + WSL2 red team workstation, reached
THROUGH the AWS-hosted Dashboard Server (jump), not a per-deployment bastion.

Access path: operator -> Dashboard Server (SSH key + IP allow-list) -> VPC
peering into the deployment -> RDP tunnel to the attack box in the private
subnet. The one-liner
    ssh -L 13389:<attackbox-ip>:3389 ubuntu@<dashboard-eip>
forwards RDP 3389 over the dashboard jump; the operator then mstsc to
localhost:13389. The per-deployment bastion remains LEGACY/fallback only.
S3 + Secrets Manager feed the bootstrap (init script, CS archive, GitHub PAT).
"""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.network import NATGateway
from diagrams.aws.storage import S3
from diagrams.aws.security import SecretsManager

from _common import rt_diagram, operator, dashboard_hub, OPERATOR_EDGE, PEERING_EDGE

with rt_diagram("Attack Box — Dashboard-jumped RDP (Win Server 2022 + WSL2)", "attackbox-architecture"):
    op = operator()

    with dashboard_hub() as dash:
        op >> OPERATOR_EDGE >> dash

    with Cluster("Deployment VPC  (C2 10.0.0.0/16  ·  GOAD 192.168.56.0/24)"):
        with Cluster("Management subnet"):
            bastion = EC2("Bastion / Jumpbox\nLEGACY / fallback")
        with Cluster("Private subnet  (10.0.10.0/24 · 192.168.56.0/26)"):
            nat = NATGateway("NAT GW")
            ab = EC2("Attack Box\n10.0.10.50 · Win Server 2022\nWSL2 · RDP 3389 / SSH 22 / WinRM")
            ts = EC2("CS Team Server\n10.0.10.10 (.40 GOAD)")

        # Bootstrap supply chain (S3 init script + CS archive, Secrets Manager PAT).
        with Cluster("Bootstrap sources"):
            bucket = S3("S3 deploy bucket\nattack_box_init.ps1 · CS archive")
            secret = SecretsManager("Secrets Manager\nGitHub PAT (runtime)")

        # Dashboard server is the jump into the attack box (RDP over the tunnel).
        dash >> PEERING_EDGE >> ab
        dash >> Edge(
            label="ssh -L 13389:<attackbox-ip>:3389 ubuntu@<dashboard-eip>  (RDP via jump)",
            color="#2c7a4b", style="bold",
        ) >> ab

        # Attack box -> team server (direct CS client, no tunnel needed).
        ab >> Edge(label="SSH 22 / CS 50050", color="#5a6472") >> ts
        # Bootstrap pulls.
        bucket >> Edge(label="S3 GetObject (VPC endpoint)", color="#8a96a8", style="dotted") >> ab
        secret >> Edge(label="GetSecretValue", color="#8a96a8", style="dotted") >> ab
