"""test-lab — the bolt-on vulnerable lab (enable_test_lab = true on a c2-*).

The test lab is NOT a new VPC. It is a new PRIVATE SUBNET (default
10.0.20.0/24) created INSIDE the existing C2 VPC (10.0.0.0/16). The subnet is
associated with the C2 VPC's existing private route table, so it reuses the
C2 NAT Gateway for outbound — no new VPC, no new NAT, no new IGW, no peering.

4 hosts (mini, the only Phase-1 size), all on the test-lab subnet:
  * tldc01    .10 — Windows Server 2022, Domain Controller (testlab.local)
  * tlms01    .11 — Windows Server 2022, member server
  * tlws01    .12 — Windows 11 Pro, workstation
  * tllinux01 .13 — Ubuntu 22.04, Linux member

Ingress to the lab hosts comes from the Dashboard Server SG (RDP to the
Windows hosts, SSH to the Linux host). The Dashboard Server is the SSH jump;
it reaches the lab subnet over the existing dashboard<->C2 VPC peering.
Source: terraform/modules/test_lab/{main.tf,variables.tf,user_data/*.tpl}.
"""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.network import InternetGateway, NATGateway

from _common import rt_diagram, operator, dashboard_hub, OPERATOR_EDGE, PEERING_EDGE

with rt_diagram("Test Lab — bolt-on subnet inside the C2 VPC", "test-lab-architecture"):
    op = operator()

    with dashboard_hub() as dash:
        op >> OPERATOR_EDGE >> dash

    # ── Existing C2 VPC — the test lab is a NEW SUBNET inside it ──────────────
    with Cluster("C2 VPC  10.0.0.0/16"):
        with Cluster("Existing C2 subnets (context)"):
            igw = InternetGateway("IGW")
            nat = NATGateway("NAT GW\n(shared — reused by test lab)")
            c2 = EC2("C2: team server /\nredirectors / attack box")

        # New private subnet inside the SAME VPC. No new VPC/NAT/IGW/peering.
        with Cluster("Test Lab subnet  10.0.20.0/24  (enable_test_lab)"):
            tldc = EC2("tldc01\n.10 · Win2022 DC · testlab.local")
            tlms = EC2("tlms01\n.11 · Win2022 member srv")
            tlws = EC2("tlws01\n.12 · Win11 Pro ws")
            tllinux = EC2("tllinux01\n.13 · Ubuntu 22.04")

        # Test-lab subnet reuses the C2 private route table -> C2 NAT GW egress.
        tldc >> Edge(label="reuses C2 private RT -> NAT", color="#5a6472", style="dashed") >> nat

        # Dashboard server jumps into the lab hosts (RDP to Windows, SSH to Linux)
        # via the existing dashboard <-> C2 VPC peering. Ingress is from the
        # Dashboard Server SG only.
        dash >> PEERING_EDGE >> tldc
        dash >> Edge(label="RDP (from dashboard SG)", color="#8a96a8", style="dashed") >> tlms
        dash >> Edge(color="#8a96a8", style="dashed") >> tlws
        dash >> Edge(label="SSH", color="#8a96a8", style="dashed") >> tllinux

        # Intra-lab AD fabric: members + workstation join the DC.
        tlms >> Edge(label="domain", color="#5a6472") >> tldc
        tlws >> Edge(color="#5a6472") >> tldc
        tllinux >> Edge(label="DNS -> DC", color="#5a6472") >> tldc
