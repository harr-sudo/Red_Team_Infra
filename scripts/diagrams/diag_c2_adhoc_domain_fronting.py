"""c2-adhoc + domain fronting — the single-team-server ad-hoc topology with a
CloudFront distribution in front of the redirectors.

Operator -> Dashboard hub -> C2 VPC for management. Beacon path: target ->
CloudFront edge (front domain, Host header -> back domain) -> redirector
origins -> CS team server. ACM provides the public-facing cert (auto,
DNS-validated, no Let's Encrypt needed). The Dashboard Server (own VPC,
AWS-hosted prod control plane) is the hub all deployments branch from; the
per-deployment bastion has been removed — the dashboard is the only jump.
"""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.network import InternetGateway, NATGateway, CloudFront
from diagrams.aws.security import ACM
from diagrams.onprem.client import Users

from _common import rt_diagram, operator, dashboard_hub, OPERATOR_EDGE, PEERING_EDGE

with rt_diagram("C2 Ad-Hoc + Domain Fronting — Dashboard-fronted (eu-central-1)", "c2-adhoc-domain-fronting"):
    target = Users("Target estate\n(beacon callbacks)")
    op = operator()

    with dashboard_hub() as dash:
        op >> OPERATOR_EDGE >> dash

    # Domain fronting layer in front of the C2 VPC.
    with Cluster("Domain fronting (us-east-1 ACM)"):
        cf = CloudFront("CloudFront\nfront domain · Host -> back domain")
        acm = ACM("ACM cert\n(auto · DNS-validated)")
        acm >> Edge(style="dotted", color="#5a6472") >> cf

    with Cluster("C2 VPC  10.0.0.0/16"):
        with Cluster("Public / DMZ subnets"):
            igw = InternetGateway("IGW")
            r1 = EC2("Redirector 1\nHTTPS 443 · CloudFront origin")
            r2 = EC2("Redirector 2\nHTTPS 443 · CloudFront origin")
        with Cluster("Private 10.0.10.0/24"):
            nat = NATGateway("NAT GW")
            ts = EC2("CS Team Server\n10.0.10.10")
            ab = EC2("Attack Box\n10.0.10.50 · Win+WSL2")

        # Dashboard server is the jump into every private instance.
        dash >> PEERING_EDGE >> ts
        dash >> Edge(color="#8a96a8", style="dashed") >> ab
        # Beacon traffic: target -> CloudFront edge -> redirector origins -> team server.
        target >> Edge(label="HTTPS · front domain", color="#b4564f") >> cf
        cf >> Edge(label="origin (EIP) · SG locked to CloudFront IPs", color="#b4564f") >> r1
        cf >> Edge(color="#b4564f") >> r2
        r1 >> Edge(label="reverse proxy", color="#5a6472") >> ts
        r2 >> Edge(color="#5a6472") >> ts
