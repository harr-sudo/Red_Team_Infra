"""SSL/TLS options comparison — 3 side-by-side clusters, NOT a topology.

  1. Let's Encrypt  — redirector certs, DNS-01 via Route53, auto-renew (default).
  2. ACM            — public cert for CloudFront domain-fronting (us-east-1,
                      DNS-validated, no Let's Encrypt needed).
  3. Self-signed    — immediate fallback, browser warnings, RSA 2048 / 365d.

Landscape with three option columns so the operator can compare at a glance.
"""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.security import ACM
from diagrams.aws.network import CloudFront, Route53
from diagrams.onprem.network import Internet

from _common import rt_diagram

with rt_diagram("SSL / TLS Options — Let's Encrypt vs ACM vs Self-Signed", "ssl-options-comparison"):

    # Option 1: Let's Encrypt (recommended for redirectors).
    with Cluster("1. Let's Encrypt  (recommended · auto-renew)"):
        le_ca = Internet("Let's Encrypt CA\nDNS-01 challenge")
        le_r53 = Route53("Route53\n_acme-challenge TXT")
        le_redir = EC2("Redirector\ncertbot --dns-route53\nrenew via systemd timer")
        le_ca >> Edge(label="validate TXT", color="#5a6472") >> le_r53
        le_r53 >> Edge(label="issue · 90d auto-renew", color="#2c7a4b") >> le_redir

    # Option 2: ACM (for CloudFront domain fronting).
    with Cluster("2. ACM  (CloudFront domain fronting)"):
        acm = ACM("ACM cert (us-east-1)\nDNS-validated · auto-managed")
        cf = CloudFront("CloudFront\nfront domain edge")
        acm >> Edge(label="attach (no LE needed)", color="#2c7a4b") >> cf

    # Option 3: Self-signed (immediate fallback).
    with Cluster("3. Self-signed  (fallback · no deps)"):
        ss = EC2("Redirector\nopenssl RSA 2048 · 365d\nimmediate · browser warnings")
        ss_note = Internet("No CA / no DNS\n(testing / OPSEC-weak)")
        ss_note >> Edge(label="self-issued", color="#b4564f", style="dashed") >> ss
