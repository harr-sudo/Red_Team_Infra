"""S3 deployment storage — one per-deployment bucket guarded by 3-layer
confused-deputy protection, reached only over VPC endpoints. The AWS-hosted
Dashboard Server reaches the same bucket via ITS OWN VPC endpoint.

3 layers:
  L1 IAM trust policy   — aws:SourceAccount on sts:AssumeRole.
  L2 IAM permission     — aws:SourceVpc + aws:SecureTransport on S3 actions.
  L3 S3 bucket policy   — deny non-authorized VPC / non-account / non-HTTPS.
Prefixes: archives/ + scripts/ (persist), keys/ + status/ (7-day expiry).
"""
from diagrams import Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.storage import S3
from diagrams.aws.security import IAMRole
from diagrams.aws.network import VPCElasticNetworkInterface

from _common import rt_diagram, operator, dashboard_hub, OPERATOR_EDGE

with rt_diagram("S3 Deployment Storage — 3-layer confused-deputy + VPC endpoints", "s3-storage-security-architecture"):
    op = operator()

    with dashboard_hub() as dash:
        op >> OPERATOR_EDGE >> dash
        dash_vpce = VPCElasticNetworkInterface("Dashboard VPC endpoint\n(S3 gateway)")
        dash >> Edge(color="#5a6472") >> dash_vpce

    with Cluster("C2 VPC  10.0.0.0/16"):
        role_c2 = IAMRole("cs_download_c2\nL1 SourceAccount · L2 SourceVpc=C2")
        ec2_c2 = EC2("C2 instances")
        vpce_c2 = VPCElasticNetworkInterface("VPC endpoint (S3)")
        role_c2 >> Edge(color="#5a6472") >> ec2_c2
        ec2_c2 >> Edge(color="#5a6472") >> vpce_c2

    with Cluster("GOAD VPC  192.168.56.0/24"):
        role_goad = IAMRole("cs_download_goad\nL1 SourceAccount · L2 SourceVpc=GOAD")
        ec2_goad = EC2("GOAD instances")
        vpce_goad = VPCElasticNetworkInterface("VPC endpoint (S3)")
        role_goad >> Edge(color="#5a6472") >> ec2_goad
        ec2_goad >> Edge(color="#5a6472") >> vpce_goad

    with Cluster("S3 deployment bucket  {project}-deploy-files-{hex}"):
        bucket = S3("L3 bucket policy: deny non-VPC / non-account / non-HTTPS\n"
                    "SSE-S3 · versioned · public access blocked")
        with Cluster("Prefixes"):
            persist = S3("archives/ · scripts/\n(no expiry)")
            ephem = S3("keys/ · status/\n(7-day expiry)")
        bucket >> Edge(style="dotted", color="#8a96a8") >> persist
        bucket >> Edge(style="dotted", color="#8a96a8") >> ephem

    # Every path into the bucket goes through a VPC endpoint (HTTPS-only).
    dash_vpce >> Edge(label="GetObject (HTTPS)", color="#2c7a4b") >> bucket
    vpce_c2 >> Edge(label="L2/L3: SourceVpc + HTTPS", color="#2c7a4b") >> bucket
    vpce_goad >> Edge(label="L2/L3: SourceVpc + HTTPS", color="#2c7a4b") >> bucket
