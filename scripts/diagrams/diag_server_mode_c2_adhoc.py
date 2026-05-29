"""server-mode-c2-adhoc — dashboard-as-control-plane view of a c2-adhoc
deployment.

Emphasises the AWS-hosted Dashboard Server as the production control plane +
SSH jump. The operator reaches everything through ONE tunnel to the dashboard
(`ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>`); the Dashboard VPC is
peered with the C2 VPC so the dashboard has direct routable access to every
instance. The per-deployment bastion is LEGACY/fallback only.
"""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.network import InternetGateway, NATGateway
from diagrams.onprem.client import Users

from _common import rt_diagram, operator, PEERING_EDGE

# Operator one-liner shown as the labeled access edge into the dashboard.
OP_TUNNEL = Edge(
    label="ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>\nSSH key · IP allow-list",
    color="#2c7a4b",
    style="bold",
)

with rt_diagram("Server Mode — C2 Ad-Hoc (dashboard control plane)", "server-mode-c2-adhoc"):
    target = Users("Target estate\n(beacon callbacks)")
    op = operator()

    # ── Dashboard VPC (control plane — shown in detail) ──────────────────
    with Cluster("Dashboard VPC (AWS · prod control plane)  10.100.0.0/16"):
        with Cluster("Subnet 10.100.1.0/24"):
            igw_dash = InternetGateway("IGW")
            dash = EC2("Dashboard Server\n10.100.1.10 · EIP\nFlask UI :5000 loopback")

    op >> OP_TUNNEL >> dash

    # ── C2 VPC (c2-adhoc) ────────────────────────────────────────────────
    with Cluster("C2 VPC  10.0.0.0/16  (c2-adhoc)"):
        with Cluster("Public / DMZ subnets"):
            igw_c2 = InternetGateway("IGW")
            r1 = EC2("Redirector 1\nHTTPS 443 · EIP")
            r2 = EC2("Redirector 2\nHTTPS 443 · EIP")
        with Cluster("Management 10.0.0.0/24"):
            bastion = EC2("Bastion\n10.0.0.10 · LEGACY/fallback")
        with Cluster("Private 10.0.10.0/24"):
            nat_c2 = NATGateway("NAT GW")
            ts = EC2("CS Team Server\n10.0.10.10\n:50050 CS · :50443 REST")
            ab = EC2("Attack Box\n10.0.10.50 · Win+WSL2")

    # Dashboard VPC <-> C2 VPC peering: direct SSH/REST to every instance.
    dash >> Edge(label="Dashboard ↔ C2 VPC peering\n10.100.0.0/16 ↔ 10.0.0.0/16", color="#8a96a8", style="dashed") >> ts
    dash >> Edge(color="#8a96a8", style="dashed") >> ab
    dash >> Edge(color="#8a96a8", style="dashed") >> r1
    dash >> Edge(color="#8a96a8", style="dashed") >> r2

    # Beacon traffic: target -> redirectors -> team server.
    target >> Edge(label="HTTPS 443", color="#b4564f") >> r1
    target >> Edge(color="#b4564f") >> r2
    r1 >> Edge(label="reverse proxy", color="#5a6472") >> ts
    r2 >> Edge(color="#5a6472") >> ts
