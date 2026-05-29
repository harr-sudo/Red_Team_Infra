"""goad-mini — single-DC AD lab (sevenkingdoms.local), fronted by the
AWS-hosted Dashboard Server. Operator -> Dashboard hub -> peered GOAD VPC.
The GOAD jumpbox is legacy/fallback; the dashboard is the real jump."""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.network import InternetGateway, NATGateway

from _common import rt_diagram, operator, dashboard_hub, OPERATOR_EDGE, PEERING_EDGE

with rt_diagram("GOAD-Mini — Dashboard-fronted AD lab", "goad-mini-architecture"):
    op = operator()

    with dashboard_hub() as dash:
        op >> OPERATOR_EDGE >> dash

    with Cluster("GOAD VPC  192.168.56.0/24"):
        with Cluster("Public subnet  .64/26"):
            igw = InternetGateway("IGW")
            nat = NATGateway("NAT GW\n(outbound for private)")
            jump = EC2("Jumpbox\n.100 · EIP · LEGACY/fallback")

        with Cluster("Private subnet  .0/26"):
            ts = EC2("CS Team Server\n.40 · :50050")
            ab = EC2("Attack Box\n.50 · Win2022 · CS Client")
            with Cluster("GOAD AD targets — sevenkingdoms.local"):
                dc01 = EC2("DC01 kingslanding\n.10 · DC · sevenkingdoms.local")

        # Dashboard server is the jump into every GOAD instance (VPC peering).
        dash >> PEERING_EDGE >> jump
        dash >> Edge(label="SSH · CS 50050", color="#8a96a8", style="dashed") >> ts
        dash >> Edge(color="#8a96a8", style="dashed") >> ab
        dash >> Edge(label="RDP/WinRM", color="#8a96a8", style="dashed") >> dc01

        # CS client-to-server + attack path within the lab.
        ab >> Edge(label="CS 50050", color="#5a6472") >> ts
        ab >> Edge(label="attack", color="#b4564f") >> dc01
