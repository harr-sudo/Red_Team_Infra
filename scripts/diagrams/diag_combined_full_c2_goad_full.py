"""combined-full-full — c2-full + goad-full, 3-way VPC peering.

The AWS-hosted Dashboard Server (own VPC, prod control plane + jump) is the
hub all deployments branch from. In COMBINED mode there are TWO deployment
VPCs:
  * C2 VPC  10.0.0.0/16        — c2-full (3 phase team servers + CloudFront)
  * GOAD VPC 192.168.56.0/24   — goad-full (3 DCs + 2 srv, 2 forests)

GOAD-full = two forests:
  * sevenkingdoms.local : DC01 kingslanding (.10)
      └─ north.sevenkingdoms.local : DC02 winterfell (.11), SRV02 castelblack (.22)
  * essos.local         : DC03 meereen (.12), SRV03 braavos (.23)

Three peering connections form the mesh:
  1. Dashboard VPC  <-> C2 VPC
  2. Dashboard VPC  <-> GOAD VPC
  3. C2 VPC         <-> GOAD VPC   (beacons reach the AD forests)
"""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.network import InternetGateway, NATGateway, CloudFront
from diagrams.aws.security import ACM
from diagrams.onprem.client import Users

from _common import rt_diagram, operator, dashboard_hub, OPERATOR_EDGE, PEERING_EDGE

with rt_diagram("Combined — C2 Full + GOAD Full (3-way VPC peering)", "combined-full-c2-goad-full"):
    target = Users("Target estate\n(beacon callbacks)")
    op = operator()

    with dashboard_hub() as dash:
        op >> OPERATOR_EDGE >> dash

    # Domain fronting layer in front of the C2 VPC.
    with Cluster("Domain fronting (us-east-1 ACM)"):
        cf = CloudFront("CloudFront\nfront domain · caching off")
        acm = ACM("ACM cert\n(auto · DNS-validated)")
        acm >> Edge(style="dotted", color="#5a6472") >> cf

    # ── C2 VPC (c2-full) ─────────────────────────────────────────────────
    with Cluster("C2 VPC  10.0.0.0/16  (c2-full)"):
        with Cluster("Public / DMZ subnets"):
            igw_c2 = InternetGateway("IGW")
            r1 = EC2("Redirector 1\nHTTPS 443 · EIP")
            r2 = EC2("Redirector 2\nHTTPS 443 · EIP")
            r3 = EC2("Redirector 3\nHTTPS 443 · EIP")
        with Cluster("Management 10.0.0.0/24"):
            bastion = EC2("Bastion\n10.0.0.10 · LEGACY/fallback")
        with Cluster("Private 10.0.10.0/24"):
            nat_c2 = NATGateway("NAT GW")
            ts_stage = EC2("Team Server — Staging\n10.0.10.10")
            ts_postex = EC2("Team Server — Post-Ex\n10.0.10.11")
            ts_long = EC2("Team Server — Long-Haul\n10.0.10.12")
            ab_c2 = EC2("Attack Box\n10.0.10.50 · Win+WSL2")

    # ── GOAD VPC (goad-full, 2 forests) ──────────────────────────────────
    with Cluster("GOAD VPC  192.168.56.0/24  (goad-full · 2 forests)"):
        with Cluster("Public 192.168.56.64/26"):
            igw_goad = InternetGateway("IGW")
            nat_goad = NATGateway("NAT GW")
            jump = EC2("Jumpbox\n.100 · EIP · LEGACY/fallback")
        with Cluster("Private 192.168.56.0/26"):
            with Cluster("Forest: sevenkingdoms.local"):
                dc01 = EC2("DC01 kingslanding\n.10 · sevenkingdoms.local")
                dc02 = EC2("DC02 winterfell\n.11 · north.sevenkingdoms")
                srv02 = EC2("SRV02 castelblack\n.22 · north.sevenkingdoms")
            with Cluster("Forest: essos.local"):
                dc03 = EC2("DC03 meereen\n.12 · essos.local")
                srv03 = EC2("SRV03 braavos\n.23 · essos.local")
            ts_goad = EC2("CS Team Server\n.40")
            ab_goad = EC2("Attack Box\n.50 · Win+WSL2")

    # Dashboard server jumps into every private instance in BOTH VPCs.
    dash >> PEERING_EDGE >> ts_stage
    dash >> Edge(color="#8a96a8", style="dashed") >> ab_c2
    dash >> PEERING_EDGE >> dc01
    dash >> Edge(color="#8a96a8", style="dashed") >> ts_goad

    # C2 <-> GOAD peering: beacons from the C2 team servers reach the AD forests.
    ts_long >> Edge(label="C2 ↔ GOAD peering\n(beacon → AD forests)", color="#8a96a8", style="dashed") >> dc01

    # Beacon traffic: target -> CloudFront -> redirectors -> team servers.
    target >> Edge(label="HTTPS · front domain", color="#b4564f") >> cf
    cf >> Edge(label="origin (EIP)", color="#b4564f") >> r1
    cf >> Edge(color="#b4564f") >> r2
    cf >> Edge(color="#b4564f") >> r3
    r1 >> Edge(label="reverse proxy", color="#5a6472") >> ts_stage
    r2 >> Edge(color="#5a6472") >> ts_postex
    r3 >> Edge(color="#5a6472") >> ts_long
