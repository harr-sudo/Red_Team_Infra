"""c2-adhoc — 1 team server + 2 redirectors + attack box, fronted by the
AWS-hosted Dashboard Server. Reference diagram that locks the house style."""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.network import InternetGateway, NATGateway, ELB
from diagrams.aws.security import IAMRole
from diagrams.onprem.client import Users

from _common import rt_diagram, operator, dashboard_hub, OPERATOR_EDGE, PEERING_EDGE

with rt_diagram("C2 Ad-Hoc — Dashboard-fronted (eu-central-1)", "c2-adhoc-architecture"):
    target = Users("Target estate\n(beacon callbacks)")
    op = operator()

    with dashboard_hub() as dash:
        op >> OPERATOR_EDGE >> dash

    with Cluster("C2 VPC  10.0.0.0/16"):
        with Cluster("Public / DMZ subnets"):
            igw = InternetGateway("IGW")
            r1 = EC2("Redirector 1\nHTTPS 443 · EIP")
            r2 = EC2("Redirector 2\nHTTPS 443 · EIP")
        with Cluster("Private 10.0.10.0/24"):
            nat = NATGateway("NAT GW")
            ts = EC2("CS Team Server\n10.0.10.10")
            ab = EC2("Attack Box\n10.0.10.50 · Win+WSL2")

        # Dashboard server is the jump into every private instance.
        dash >> PEERING_EDGE >> ts
        dash >> Edge(color="#8a96a8", style="dashed") >> ab
        # Beacon traffic: target -> redirectors -> team server.
        target >> Edge(label="HTTPS 443", color="#b4564f") >> r1
        target >> Edge(color="#b4564f") >> r2
        r1 >> Edge(label="reverse proxy", color="#5a6472") >> ts
        r2 >> Edge(color="#5a6472") >> ts
