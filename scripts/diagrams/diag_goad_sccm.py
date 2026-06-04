"""goad-sccm — SCCM attack lab on sccm.lab (DC + SCCM + SQL + client),
fronted by the AWS-hosted Dashboard Server. Operator -> Dashboard hub ->
peered GOAD VPC. The GOAD jumpbox is the Ansible AD-lab provisioning host
(not a bastion); the dashboard is the SSH jump."""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.network import InternetGateway, NATGateway

from _common import rt_diagram, operator, dashboard_hub, OPERATOR_EDGE, PEERING_EDGE

with rt_diagram("GOAD-SCCM — Dashboard-fronted AD lab", "goad-sccm-architecture"):
    op = operator()

    with dashboard_hub() as dash:
        op >> OPERATOR_EDGE >> dash

    with Cluster("GOAD VPC  192.168.56.0/24"):
        with Cluster("Public subnet  .64/26"):
            igw = InternetGateway("IGW")
            nat = NATGateway("NAT GW\n(outbound for private)")
            jump = EC2("Jumpbox\n.100 · GOAD Ansible provisioning")

        with Cluster("Private subnet  .0/26"):
            ts = EC2("CS Team Server\n.40 · :50050")
            ab = EC2("Attack Box\n.50 · Win2022 · CS Client")
            with Cluster("GOAD AD targets — sccm.lab"):
                dc01 = EC2("DC01\n.10 · DC · sccm.lab")
                srv01 = EC2("SRV01\n.11 · SCCM site server")
                srv02 = EC2("SRV02\n.12 · MSSQL (site DB)")
                ws01 = EC2("WS01\n.13 · domain client")

        # Dashboard server is the jump into every GOAD instance (VPC peering).
        dash >> PEERING_EDGE >> jump
        dash >> Edge(label="SSH · CS 50050", color="#8a96a8", style="dashed") >> ts
        dash >> Edge(color="#8a96a8", style="dashed") >> ab
        dash >> Edge(label="RDP/WinRM", color="#8a96a8", style="dashed") >> dc01

        # SCCM site relationships.
        srv01 >> Edge(label="site DB", color="#8a96a8", style="dotted") >> srv02
        srv01 >> Edge(color="#8a96a8", style="dotted") >> dc01
        ws01 >> Edge(label="MP/client", color="#8a96a8", style="dotted") >> srv01

        # CS client-to-server + attack path within the lab.
        ab >> Edge(label="CS 50050", color="#5a6472") >> ts
        ab >> Edge(label="attack", color="#b4564f") >> srv01
