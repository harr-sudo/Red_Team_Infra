"""c2-full — 3 phase-based team servers + 2-3 redirectors fronted by a
CloudFront distribution (domain fronting), plus attack box, all branching
from the AWS-hosted Dashboard Server.

Phase-based team servers (staging / post-ex / long-haul) at
10.0.10.10 / .11 / .12. CloudFront sits in front of the redirectors to hide
their EIPs behind CloudFront edge IPs. The Dashboard Server (own VPC,
AWS-hosted prod control plane) is the hub all deployments branch from; the
per-deployment bastion has been removed — the dashboard is the only jump.
"""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.network import InternetGateway, NATGateway, CloudFront
from diagrams.aws.security import ACM
from diagrams.onprem.client import Users

from _common import rt_diagram, operator, dashboard_hub, OPERATOR_EDGE, PEERING_EDGE

with rt_diagram("C2 Full — Dashboard-fronted, 3 phase team servers + CloudFront (eu-central-1)", "c2-full-architecture"):
    target = Users("Target estate\n(beacon callbacks)")
    op = operator()

    with dashboard_hub() as dash:
        op >> OPERATOR_EDGE >> dash

    # Domain fronting layer in front of the C2 VPC.
    with Cluster("Domain fronting (us-east-1 ACM)"):
        cf = CloudFront("CloudFront\nfront domain · caching off")
        acm = ACM("ACM cert\n(auto · DNS-validated)")
        acm >> Edge(style="dotted", color="#5a6472") >> cf

    with Cluster("C2 VPC  10.0.0.0/16"):
        with Cluster("Public / DMZ subnets"):
            igw = InternetGateway("IGW")
            r1 = EC2("Redirector 1\nHTTPS 443 · EIP")
            r2 = EC2("Redirector 2\nHTTPS 443 · EIP")
            r3 = EC2("Redirector 3\nHTTPS 443 · EIP")
        with Cluster("Private 10.0.10.0/24"):
            nat = NATGateway("NAT GW")
            ts_stage = EC2("Team Server — Staging\n10.0.10.10")
            ts_postex = EC2("Team Server — Post-Ex\n10.0.10.11")
            ts_long = EC2("Team Server — Long-Haul\n10.0.10.12")
            ab = EC2("Attack Box\n10.0.10.50 · Win+WSL2")

        # Dashboard server is the jump into every private instance.
        dash >> PEERING_EDGE >> ts_stage
        dash >> Edge(color="#8a96a8", style="dashed") >> ts_postex
        dash >> Edge(color="#8a96a8", style="dashed") >> ts_long
        dash >> Edge(color="#8a96a8", style="dashed") >> ab

        # Beacon traffic: target -> CloudFront edge -> redirectors -> team servers.
        target >> Edge(label="HTTPS · front domain", color="#b4564f") >> cf
        cf >> Edge(label="origin (EIP)", color="#b4564f") >> r1
        cf >> Edge(color="#b4564f") >> r2
        cf >> Edge(color="#b4564f") >> r3
        r1 >> Edge(label="reverse proxy", color="#5a6472") >> ts_stage
        r2 >> Edge(color="#5a6472") >> ts_postex
        r3 >> Edge(color="#5a6472") >> ts_long
