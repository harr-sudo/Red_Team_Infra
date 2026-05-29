"""c2-purple — 2 team servers (redundancy) + 2 redirectors + attack box,
fronted by the AWS-hosted Dashboard Server.

Same topology as the c2-adhoc reference but with TWO team servers
(10.0.10.10 + 10.0.10.11) for redundancy / multi-operator high availability.
The Dashboard Server (own VPC, AWS-hosted prod control plane) is the hub all
deployments branch from; the per-deployment bastion is LEGACY/fallback only.
"""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.network import InternetGateway, NATGateway
from diagrams.onprem.client import Users

from _common import rt_diagram, operator, dashboard_hub, OPERATOR_EDGE, PEERING_EDGE

with rt_diagram("C2 Purple — Dashboard-fronted, 2 team servers (eu-central-1)", "c2-purple-architecture"):
    target = Users("Target estate\n(beacon callbacks)")
    op = operator()

    with dashboard_hub() as dash:
        op >> OPERATOR_EDGE >> dash

    with Cluster("C2 VPC  10.0.0.0/16"):
        with Cluster("Public / DMZ subnets"):
            igw = InternetGateway("IGW")
            r1 = EC2("Redirector 1\nHTTPS 443 · EIP")
            r2 = EC2("Redirector 2\nHTTPS 443 · EIP")
        with Cluster("Management 10.0.0.0/24"):
            bastion = EC2("Bastion\n10.0.0.10 · LEGACY/fallback")
        with Cluster("Private 10.0.10.0/24"):
            nat = NATGateway("NAT GW")
            ts1 = EC2("CS Team Server 1\n10.0.10.10")
            ts2 = EC2("CS Team Server 2\n10.0.10.11 · redundant")
            ab = EC2("Attack Box\n10.0.10.50 · Win+WSL2")

        # Dashboard server is the jump into every private instance.
        dash >> PEERING_EDGE >> ts1
        dash >> Edge(color="#8a96a8", style="dashed") >> ts2
        dash >> Edge(color="#8a96a8", style="dashed") >> ab
        # Beacon traffic: target -> redirectors -> team servers (HA pair).
        target >> Edge(label="HTTPS 443", color="#b4564f") >> r1
        target >> Edge(color="#b4564f") >> r2
        r1 >> Edge(label="reverse proxy", color="#5a6472") >> ts1
        r2 >> Edge(color="#5a6472") >> ts2
