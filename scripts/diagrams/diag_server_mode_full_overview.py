"""server-mode-full-overview — the canonical "everything branches from the
AWS dashboard" hub-and-spoke diagram.

The BIG picture, deliberately high-level (VPC boxes, not every host) so the
hub-and-spoke reads clearly and strongly landscape:

    operator --ssh--> Dashboard VPC (AWS, control plane + jump)
                         ├── VPC peering ──> C2 VPC      (10.0.0.0/16)
                         ├── VPC peering ──> GOAD VPC    (192.168.56.0/24)
                         └── VPC peering ──> CCRTS VPC   (optional)

Every deployment VPC is peered back to the Dashboard VPC; the C2 and GOAD VPCs
are additionally peered to EACH OTHER in combined mode so beacons reach the AD
targets. The dashboard is the single hub all deployments branch from.
"""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.network import VPC, VPCPeering, InternetGateway
from diagrams.onprem.client import User

from _common import rt_diagram

# Operator one-liner shown as the labeled access edge into the dashboard.
OP_TUNNEL = Edge(
    label="ssh -L 5000:localhost:5000\nubuntu@<dashboard-eip>",
    color="#2c7a4b",
    style="bold",
)
PEER = Edge(label="VPC peering", color="#8a96a8", style="dashed")

with rt_diagram("Server Mode — Full Overview (AWS dashboard hub-and-spoke)", "server-mode-full-overview"):
    op = User("Operator\n(laptop · dev instance)")

    # ── Hub: Dashboard VPC (center-left) ─────────────────────────────────
    with Cluster("Dashboard VPC (AWS · prod control plane + jump)  10.100.0.0/16"):
        igw = InternetGateway("IGW")
        dash = EC2("Dashboard Server\n10.100.1.10 · EIP · :5000")

    op >> OP_TUNNEL >> dash

    # ── Spokes: one VPC box per deployment, fanning to the right ──────────
    with Cluster("C2 VPC  10.0.0.0/16"):
        c2 = VPC("Cobalt Strike\nteam servers · redirectors\nattack box")

    with Cluster("GOAD VPC  192.168.56.0/24"):
        goad = VPC("Vulnerable AD lab\nDCs · member servers\nTS · attack box")

    with Cluster("CCRTS VPC  (optional)"):
        ccrts = VPC("CCRTS range\nadd-on deployment")

    # Hub-and-spoke: every deployment VPC peers back to the dashboard hub.
    dash >> PEER >> c2
    dash >> PEER >> goad
    dash >> PEER >> ccrts

    # Combined mode: C2 and GOAD VPCs peer to each other (beacons -> AD).
    c2 >> Edge(label="C2 ↔ GOAD peering\n(beacon → AD targets)", color="#8a96a8", style="dashed") >> goad
