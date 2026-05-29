"""Shared style + helpers for the Red Team Infra architecture diagrams.

2026-05-29 — Diagrams are now generated from committed scripts (this dir)
instead of ad-hoc AWS-diagram-MCP sessions, so every regen is reproducible.
Engine: the `diagrams` PyPI library (the same one awslabs.aws-diagram-mcp-server
wraps) + graphviz. Run all scripts with the repo venv:

    for f in scripts/diagrams/diag_*.py; do ./venv/bin/python "$f"; done

House style (matches the prior April-2026 set the operator approved):
  * LANDSCAPE — direction="LR" (left-to-right), wide aspect for readability.
  * White background, generous padding, readable label fontsize.
  * AWS service icons via the `diagrams.aws.*` icon set.

THE ARCHITECTURE MODEL (post-2026-05-29):
  * The DASHBOARD SERVER is a dedicated EC2 instance hosted IN AWS, in its
    own VPC (10.100.0.0/16). It is the production control plane + the SSH
    jump host. The operator's laptop only runs a *dev* instance.
  * The operator connects laptop -> Dashboard Server (SSH key + IP allow-list;
    UI via `ssh -L 5000:localhost:5000`).
  * ALL deployments branch OUT from the Dashboard Server: its VPC is peered
    with every deployment VPC (C2 / GOAD / CCRTS), and it reaches every
    instance directly. Per-deployment bastions are LEGACY/fallback only.
"""
from contextlib import contextmanager

from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.onprem.client import User

OUTPUT_DIR = "generated-diagrams"

# ── House style ──────────────────────────────────────────────────────────
GRAPH_ATTR = {
    "bgcolor": "white",
    "pad": "0.6",
    "splines": "spline",
    "nodesep": "0.55",
    "ranksep": "0.85",
    "fontname": "Helvetica",
    "fontsize": "11",
}
NODE_ATTR = {"fontname": "Helvetica", "fontsize": "11"}
EDGE_ATTR = {"fontname": "Helvetica", "fontsize": "10", "color": "#5a6472"}

# Edge styles
OPERATOR_EDGE = Edge(label="SSH key · IP allow-list", color="#2c7a4b", style="bold")
PEERING_EDGE = Edge(label="VPC peering", color="#8a96a8", style="dashed")
JUMP_EDGE = Edge(label="jump", color="#8a96a8")


@contextmanager
def rt_diagram(title: str, filename: str, direction: str = "LR"):
    """Landscape diagram in the house style, written to generated-diagrams/."""
    with Diagram(
        title,
        filename=f"{OUTPUT_DIR}/{filename}",
        direction=direction,
        show=False,
        graph_attr=GRAPH_ATTR,
        node_attr=NODE_ATTR,
        edge_attr=EDGE_ATTR,
        outformat="png",
    ):
        yield


def operator(label: str = "Operator\n(laptop · dev instance)") -> User:
    """The operator node — always the left-most element."""
    return User(label)


@contextmanager
def dashboard_hub(cidr: str = "10.100.0.0/16"):
    """The Dashboard Server VPC cluster — the AWS-hosted control plane + jump.
    Yields the EC2 node so callers can wire peering edges out to deployments."""
    with Cluster(f"Dashboard VPC (AWS · prod control plane)\n{cidr}"):
        node = EC2("Dashboard Server\nEIP · :5000 loopback")
        yield node
