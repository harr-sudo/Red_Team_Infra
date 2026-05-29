"""ccrts — single, self-contained CREST exam-mirror lab.

ONE deployment type (no size tiers, no C2 integration, no combined modes),
matching upstream spark42/ccrts-lab. The lab is fully isolated in its own VPC
(192.168.57.0/24) with NO VPC peering to a C2 deployment. Cobalt Strike runs
on the Kali host directly, so there is no shared C2 tooling / bolt-ons here.

Connection model: the AWS-hosted Dashboard Server is the sole SSH jump (no
bastion inside the CCRTS VPC). The operator tunnels through the dashboard EIP
and the dashboard VPC is peered with the CCRTS VPC to reach the lab hosts.

CREST AMI mechanism (kept): the Kali + Windows candidate images are CREST
Community AMIs (owner 126620636130) copied eu-west-2 -> eu-central-1 via
aws_ami_copy. Only metadata reads + snapshot copies happen in the source
region — no compute is provisioned there.
"""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.network import NATGateway

from _common import rt_diagram, operator, dashboard_hub, OPERATOR_EDGE, PEERING_EDGE

with rt_diagram("CCRTS — Self-contained CREST exam-mirror lab", "ccrts-architecture"):
    op = operator()

    with dashboard_hub() as dash:
        op >> OPERATOR_EDGE >> dash

    # ── CCRTS VPC — fully isolated, NO C2 peering ────────────────────────────
    with Cluster("CCRTS VPC  192.168.57.0/24  (self-contained · no C2)"):
        with Cluster("Private subnet  192.168.57.0/26"):
            kali = EC2("ccrts-kali\n.20 · CREST Kali AMI")
            winws = EC2("ccrts-win-ws\n.30 · CREST Win AMI")
            dc01 = EC2("ccrts-dc01\n.40 · DC · ccrts.local")
            adws = EC2("ccrts-ad-ws01\n.41 · domain-joined")
            elk = EC2("ccrts-elk\n.50 · ELK")

        with Cluster("Public subnet  192.168.57.64/26"):
            nat = NATGateway("NAT GW\n(egress only — no lab hosts)")

        # Dashboard server is the sole SSH jump into the lab (VPC peering).
        # No bastion lives inside the CCRTS VPC.
        dash >> PEERING_EDGE >> kali
        dash >> Edge(label="SSH/RDP jump", color="#8a96a8", style="dashed") >> winws
        dash >> Edge(color="#8a96a8", style="dashed") >> dc01
        dash >> Edge(color="#8a96a8", style="dashed") >> adws
        dash >> Edge(label="Kibana 5601", color="#8a96a8", style="dashed") >> elk

        # Intra-lab: domain membership + CS runs on the Kali host directly.
        adws >> Edge(label="domain", color="#5a6472") >> dc01
        kali >> Edge(label="attack (CS on Kali)", color="#b4564f") >> winws
        kali >> Edge(color="#b4564f") >> dc01
