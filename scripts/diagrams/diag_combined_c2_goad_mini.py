"""combined-adhoc-mini — c2-adhoc + goad-mini, 3-way VPC peering.

The AWS-hosted Dashboard Server (own VPC, prod control plane + jump) is the
hub all deployments branch from. In COMBINED mode there are TWO deployment
VPCs:
  * C2 VPC  10.0.0.0/16        — c2-adhoc (1 team server + 2 redirectors + AB)
  * GOAD VPC 192.168.56.0/24   — goad-mini (1 DC + jumpbox + TS + AB)

Three peering connections form the mesh:
  1. Dashboard VPC  <-> C2 VPC        (dashboard jumps into C2)
  2. Dashboard VPC  <-> GOAD VPC      (dashboard jumps into GOAD)
  3. C2 VPC         <-> GOAD VPC      (beacons reach the AD targets)
"""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.network import InternetGateway, NATGateway
from diagrams.onprem.client import Users

from _common import rt_diagram, operator, dashboard_hub, OPERATOR_EDGE, PEERING_EDGE

with rt_diagram("Combined — C2 Ad-Hoc + GOAD Mini (3-way VPC peering)", "combined-c2-goad-mini"):
    target = Users("Target estate\n(beacon callbacks)")
    op = operator()

    with dashboard_hub() as dash:
        op >> OPERATOR_EDGE >> dash

    # ── C2 VPC (c2-adhoc) ────────────────────────────────────────────────
    with Cluster("C2 VPC  10.0.0.0/16  (c2-adhoc)"):
        with Cluster("Public / DMZ subnets"):
            igw_c2 = InternetGateway("IGW")
            r1 = EC2("Redirector 1\nHTTPS 443 · EIP")
            r2 = EC2("Redirector 2\nHTTPS 443 · EIP")
        with Cluster("Private 10.0.10.0/24"):
            nat_c2 = NATGateway("NAT GW")
            ts = EC2("CS Team Server\n10.0.10.10")
            ab_c2 = EC2("Attack Box\n10.0.10.50 · Win+WSL2")

    # ── GOAD VPC (goad-mini) ─────────────────────────────────────────────
    with Cluster("GOAD VPC  192.168.56.0/24  (goad-mini)"):
        with Cluster("Public 192.168.56.64/26"):
            igw_goad = InternetGateway("IGW")
            nat_goad = NATGateway("NAT GW")
            jump = EC2("Jumpbox\n.100 · GOAD Ansible provisioning")
        with Cluster("Private 192.168.56.0/26"):
            dc01 = EC2("DC01 kingslanding\n.10 · sevenkingdoms.local")
            ts_goad = EC2("CS Team Server\n.40")
            ab_goad = EC2("Attack Box\n.50 · Win+WSL2")

    # Dashboard server jumps into every private instance in BOTH VPCs.
    dash >> PEERING_EDGE >> ts
    dash >> Edge(color="#8a96a8", style="dashed") >> ab_c2
    dash >> PEERING_EDGE >> dc01
    dash >> Edge(color="#8a96a8", style="dashed") >> ts_goad
    dash >> Edge(color="#8a96a8", style="dashed") >> ab_goad

    # C2 <-> GOAD peering: beacons from the C2 team server reach the AD lab.
    ts >> Edge(label="C2 ↔ GOAD peering\n(beacon → AD targets)", color="#8a96a8", style="dashed") >> dc01

    # Beacon traffic: target -> redirectors -> team server.
    target >> Edge(label="HTTPS 443", color="#b4564f") >> r1
    target >> Edge(color="#b4564f") >> r2
    r1 >> Edge(label="reverse proxy", color="#5a6472") >> ts
    r2 >> Edge(color="#5a6472") >> ts
