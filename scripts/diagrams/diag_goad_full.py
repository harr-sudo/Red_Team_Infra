"""goad-full — 3 DC + 2 member servers across two forests
(sevenkingdoms.local + essos.local, with parent-child + forest trusts),
fronted by the AWS-hosted Dashboard Server. Operator -> Dashboard hub ->
peered GOAD VPC. The GOAD jumpbox is the Ansible AD-lab provisioning host
(not a bastion); the dashboard is the SSH jump."""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.network import InternetGateway, NATGateway

from _common import rt_diagram, operator, dashboard_hub, OPERATOR_EDGE, PEERING_EDGE

with rt_diagram("GOAD-Full — Dashboard-fronted AD lab", "goad-full-architecture"):
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
            with Cluster("GOAD AD targets — sevenkingdoms.local + essos.local"):
                dc01 = EC2("DC01 kingslanding\n.10 · root DC · sevenkingdoms.local")
                dc02 = EC2("DC02 winterfell\n.11 · child DC · north.sevenkingdoms.local")
                dc03 = EC2("DC03 meereen\n.12 · forest DC · essos.local")
                srv02 = EC2("SRV02 castelblack\n.22 · member · north.sevenkingdoms.local")
                srv03 = EC2("SRV03 braavos\n.23 · member · essos.local")

        # Dashboard server is the jump into every GOAD instance (VPC peering).
        dash >> PEERING_EDGE >> jump
        dash >> Edge(label="SSH · CS 50050", color="#8a96a8", style="dashed") >> ts
        dash >> Edge(color="#8a96a8", style="dashed") >> ab
        dash >> Edge(label="RDP/WinRM", color="#8a96a8", style="dashed") >> dc01

        # Trusts: parent-child within sevenkingdoms, forest trust to essos.
        dc02 >> Edge(label="parent-child trust", color="#5a6472", style="dotted") >> dc01
        dc03 >> Edge(label="forest trust", color="#5a6472", style="dotted") >> dc01
        srv02 >> Edge(color="#8a96a8", style="dotted") >> dc02
        srv03 >> Edge(color="#8a96a8", style="dotted") >> dc03

        # CS client-to-server + attack path within the lab.
        ab >> Edge(label="CS 50050", color="#5a6472") >> ts
        ab >> Edge(label="attack", color="#b4564f") >> dc01
