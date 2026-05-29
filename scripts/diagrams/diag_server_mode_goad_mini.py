"""server-mode-goad-mini — dashboard-as-control-plane view of a goad-mini lab.

Emphasises the AWS-hosted Dashboard Server as the production control plane +
SSH jump. The operator reaches everything through ONE tunnel to the dashboard
(`ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>`); the Dashboard VPC is
peered with the GOAD VPC so the dashboard has direct routable access to every
lab instance. The GOAD jumpbox is the Ansible AD-lab provisioning host (not a
bastion); the dashboard is the SSH jump.
"""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.network import InternetGateway, NATGateway

from _common import rt_diagram, operator

# Operator one-liner shown as the labeled access edge into the dashboard.
OP_TUNNEL = Edge(
    label="ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>\nSSH key · IP allow-list",
    color="#2c7a4b",
    style="bold",
)

with rt_diagram("Server Mode — GOAD Mini (dashboard control plane)", "server-mode-goad-mini"):
    op = operator()

    # ── Dashboard VPC (control plane — shown in detail) ──────────────────
    with Cluster("Dashboard VPC (AWS · prod control plane)  10.100.0.0/16"):
        with Cluster("Subnet 10.100.1.0/24"):
            igw_dash = InternetGateway("IGW")
            dash = EC2("Dashboard Server\n10.100.1.10 · EIP\nFlask UI :5000 loopback")

    op >> OP_TUNNEL >> dash

    # ── GOAD VPC (goad-mini) ─────────────────────────────────────────────
    with Cluster("GOAD VPC  192.168.56.0/24  (goad-mini)"):
        with Cluster("Public 192.168.56.64/26"):
            igw_goad = InternetGateway("IGW")
            nat_goad = NATGateway("NAT GW")
            jump = EC2("Jumpbox\n.100 · GOAD Ansible provisioning")
        with Cluster("Private 192.168.56.0/26"):
            dc01 = EC2("DC01 kingslanding\n.10 · sevenkingdoms.local")
            ts_goad = EC2("CS Team Server\n.40 · :50050")
            ab_goad = EC2("Attack Box\n.50 · Win+WSL2")

    # Dashboard VPC <-> GOAD VPC peering: direct SSH/RDP/WinRM to every instance.
    dash >> Edge(label="Dashboard ↔ GOAD VPC peering\n10.100.0.0/16 ↔ 192.168.56.0/24", color="#8a96a8", style="dashed") >> dc01
    dash >> Edge(color="#8a96a8", style="dashed") >> ts_goad
    dash >> Edge(color="#8a96a8", style="dashed") >> ab_goad
    dash >> Edge(color="#8a96a8", style="dashed") >> jump

    # CS client to server (internal VPC routing) + lab beacon path.
    ts_goad >> Edge(label="CS 50050", color="#5a6472") >> ab_goad
    ab_goad >> Edge(label="beacon → AD", color="#b4564f") >> dc01
