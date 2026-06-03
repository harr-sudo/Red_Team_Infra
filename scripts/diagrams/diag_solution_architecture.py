"""solution-architecture — the comprehensive, portfolio-grade overview of the
Red Team Infra platform: what it provisions, the AWS services it orchestrates,
and the deployment estates that branch off the control plane.

This is the "do the solution justice" diagram for the README. Unlike
server-mode-full-overview (deliberately high-level VPC boxes), this one conveys
the BREADTH of the platform while staying organised into readable clusters so
it never overcrowds:

    Operator                                                 (left)
      └─ SSH key + IP allow-list ─┐
                                  ▼
    CONTROL PLANE — Dashboard Server VPC (10.100.0.0/16)
      • Dashboard Server EC2 (Flask control plane + Terraform/Ansible engine, EIP)
      • IAM instance role (no static keys) + S3 remote-state backend
      • the AWS services it orchestrates: EC2 · VPC · S3 · Route 53 · ACM ·
        IAM · Secrets Manager · CloudWatch · SSM · CloudFront
                                  │ VPC peering (per estate)
        ┌─────────────────┬──────┴───────────┐
        ▼                 ▼                  ▼          (right)
    C2 VPC            GOAD VPC           CCRTS VPC
    10.0.0.0/16       192.168.56.0/24    192.168.57.0/24

Beacon callback path (C2 side): target estate -> redirectors -> team server.
The Dashboard Server is the SOLE SSH jump — there is no per-deployment bastion.

LAYOUT NOTE: the 10 orchestrated-service icons are arranged as a compact 5x2
grid (chained with invisible edges per row, rows linked invisibly) so the
cluster reads as a tidy block instead of one tall column that would stretch the
whole canvas. Same trick keeps the CCRTS hosts in a row.

Engine: the `diagrams` PyPI lib (+ graphviz). House style via _common.rt_diagram
(landscape LR, white bg, AWS icon set). Run from the repo root:

    PYTHONPATH=scripts/diagrams ./venv/bin/python scripts/diagrams/diag_solution_architecture.py
"""
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.network import (
    VPC,
    Route53,
    CloudFront,
    InternetGateway,
    NATGateway,
)
from diagrams.aws.storage import S3
from diagrams.aws.security import IAMRole, SecretsManager, ACM
from diagrams.aws.management import Cloudwatch, SystemsManager
from diagrams.onprem.client import User, Users

from _common import GRAPH_ATTR, NODE_ATTR, EDGE_ATTR, OUTPUT_DIR

# ── Per-diagram layout override ────────────────────────────────────────────
# This poster is content-dense (control plane + 10 AWS services + three peered
# estates). The house default (ratio=0.52 ≈ 1.9:1) stretches the canvas WIDE,
# which leaves a large dead zone in the centre where the hub-and-spoke VPC-
# peering edges fan out to far-apart estate clusters. We keep the full house
# style (white bg, LR, AWS icons, fonts) but tighten the packing for THIS
# diagram only: smaller rank/node separation and a less extreme aspect ratio
# (~1.5:1) so the clusters pull together into a cohesive block.
SOLUTION_GRAPH_ATTR = {
    **GRAPH_ATTR,
    "nodesep": "0.18",   # tighter within-rank (vertical, in LR) gap
    "ranksep": "0.45",   # tighter left→right step — shortens the long peering edges
    "ratio": "0.64",     # ≈ 1.5:1 (was 0.52 ≈ 1.9:1) — landscape but far denser
    "pad": "0.4",
}

# ── Edge styles (consistent with the house set in _common) ────────────────
OPERATOR_EDGE = Edge(label="SSH key · IP allow-list", color="#2c7a4b", style="bold")
PEER = Edge(label="VPC peering", color="#8a96a8", style="dashed")
PEER_PLAIN = Edge(color="#8a96a8", style="dashed")
ORCH = Edge(label="provisions / orchestrates", color="#5a6472", style="dotted")
WIRE = Edge(color="#5a6472")
# Beacon edges originate from the Target node. They are drawn (content
# preserved) but marked constraint="false" so they do NOT pull the C2 estate
# to the far-left rank — without this, the Target source node yanks the whole
# C2 VPC away from the other estates, opening a big dead zone in the centre.
BEACON = Edge(label="HTTPS 443 · beacon", color="#b4564f", constraint="false")
BEACON_PLAIN = Edge(color="#b4564f", constraint="false")
# Invisible layout edge — forces grid placement without drawing a line.
HIDE = Edge(style="invis")


with Diagram(
    "Red Team Infra — Solution Architecture (control plane · AWS services · deployment estates)",
    filename=f"{OUTPUT_DIR}/solution-architecture",
    direction="LR",
    show=False,
    graph_attr=SOLUTION_GRAPH_ATTR,
    node_attr=NODE_ATTR,
    edge_attr=EDGE_ATTR,
    outformat="png",
):
    # ── 1. Operator (left-most) ───────────────────────────────────────────
    op = User("Operator\n(laptop)")

    # ── 2. Control plane: Dashboard Server VPC + the AWS it orchestrates ───
    with Cluster("Control plane — Dashboard Server VPC  10.100.0.0/16  (AWS-hosted)"):
        dash = EC2("Dashboard Server\nFlask UI + Terraform/Ansible engine\nEIP · :5000 loopback")
        dash_role = IAMRole("IAM instance role\n(no static keys)")
        state = S3("S3 remote state\n(Terraform backend)")
        dash >> WIRE >> dash_role
        dash >> WIRE >> state

        # The managed AWS services the control plane provisions/drives, laid
        # out as a compact 5x2 grid so the cluster stays a tidy block.
        with Cluster("AWS services orchestrated"):
            # Row 1
            svc_ec2 = EC2("EC2")
            svc_vpc = VPC("VPC")
            svc_s3 = S3("S3")
            svc_r53 = Route53("Route 53")
            svc_acm = ACM("ACM")
            # Row 2
            svc_iam = IAMRole("IAM")
            svc_sm = SecretsManager("Secrets Mgr")
            svc_cw = Cloudwatch("CloudWatch")
            svc_ssm = SystemsManager("SSM")
            svc_cf = CloudFront("CloudFront")

            # Chain each row horizontally, then link the rows (all invisible)
            # so graphviz places them as two neat rows rather than one column.
            svc_ec2 >> HIDE >> svc_vpc >> HIDE >> svc_s3 >> HIDE >> svc_r53 >> HIDE >> svc_acm
            svc_iam >> HIDE >> svc_sm >> HIDE >> svc_cw >> HIDE >> svc_ssm >> HIDE >> svc_cf
            svc_ec2 >> HIDE >> svc_iam

        # One representative orchestration edge keeps the cluster legible; the
        # rest are implied by membership in the "AWS services orchestrated" box.
        dash >> ORCH >> svc_ec2

    op >> OPERATOR_EDGE >> dash

    # ── 3. Deployment estates — each its own VPC, peered to the dashboard ──
    # 3a. C2 estate (with optional CloudFront domain fronting).
    with Cluster("C2 VPC  10.0.0.0/16"):
        with Cluster("Domain fronting (optional · us-east-1 ACM)"):
            cf = CloudFront("CloudFront\nfront domain")
            acm_front = ACM("ACM cert\n(DNS-validated)")
            acm_front >> Edge(style="dotted", color="#5a6472") >> cf

        with Cluster("Public / DMZ subnets"):
            igw_c2 = InternetGateway("IGW")
            r1 = EC2("Redirector 1\nHTTPS 443 · EIP")
            r2 = EC2("Redirector 2\nHTTPS 443 · EIP")

        with Cluster("Private subnets  10.0.10.0/24"):
            nat_c2 = NATGateway("NAT GW")
            ts = EC2("CS Team Server\n10.0.10.10 · :50050")
            ab = EC2("Attack Box\n10.0.10.50 · Win+WSL2")

        # Dashboard is the jump into the private C2 instances (VPC peering).
        dash >> PEER >> ts
        dash >> PEER_PLAIN >> ab

    # 3b. GOAD estate — vulnerable AD lab + Ansible provisioning jumpbox.
    with Cluster("GOAD VPC  192.168.56.0/24"):
        with Cluster("Public subnet  .64/26"):
            igw_goad = InternetGateway("IGW")
            nat_goad = NATGateway("NAT GW")
            jump = EC2("GOAD Jumpbox\n.100 · Ansible provisioning")
        with Cluster("Private subnet  .0/26"):
            goad_ad = EC2("Vulnerable AD lab\nDCs + member servers\n(sevenkingdoms / essos)")
        dash >> PEER_PLAIN >> jump
        dash >> Edge(label="RDP / WinRM", color="#8a96a8", style="dashed") >> goad_ad

    # ── Layout-only tie (invisible) ───────────────────────────────────────
    # Link the tail of the AWS-services grid to the GOAD estate. Without this,
    # the wide services grid floats alone in the top-right while the estates
    # hang in a vertical fan off the dashboard, leaving a large dead zone in
    # the centre/bottom-right. This invisible edge pulls the grid and the
    # estates into one cohesive block — collapsing that dead space — without
    # drawing any line or changing the semantics.
    svc_cf >> HIDE >> goad_ad

    # 3c. CCRTS estate — self-contained CREST exam-mirror lab (hosts in a row).
    with Cluster("CCRTS VPC  192.168.57.0/24  (self-contained)"):
        ccrts_kali = EC2("Kali\n.20 · CS on host")
        ccrts_win = EC2("Windows ws\n.30")
        ccrts_dc = EC2("AD DC\n.40 · ccrts.local")
        ccrts_elk = EC2("ELK\n.50")
        ccrts_kali >> HIDE >> ccrts_win >> HIDE >> ccrts_dc >> HIDE >> ccrts_elk
        dash >> PEER_PLAIN >> ccrts_kali
        dash >> Edge(label="SSH/RDP jump", color="#8a96a8", style="dashed") >> ccrts_elk

    # ── 4. Beacon callback path on the C2 side (target -> redirectors -> TS) ─
    target = Users("Target estate\n(beacon callbacks)")
    target >> BEACON >> cf
    target >> BEACON_PLAIN >> r1
    target >> BEACON_PLAIN >> r2
    cf >> Edge(label="origin · SG locked to CloudFront", color="#b4564f") >> r1
    cf >> BEACON_PLAIN >> r2
    r1 >> Edge(label="reverse proxy", color="#5a6472") >> ts
    r2 >> WIRE >> ts
