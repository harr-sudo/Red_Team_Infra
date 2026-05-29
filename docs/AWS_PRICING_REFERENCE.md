# AWS Pricing Reference — eu-central-1 (Frankfurt)

Last verified: March 2026
Source: [Vantage EC2 Instances](https://instances.vantage.sh), [CostGoat NAT Gateway](https://costgoat.com/pricing/aws-nat-gateway)

## EC2 On-Demand Hourly Pricing (eu-central-1)

| Instance Type | vCPU | RAM | Linux $/hr | Linux $/mo (×730) | Windows $/hr | Windows $/mo | Used By |
|---|---|---|---|---|---|---|---|
| t3.small | 2 | 2 GB | $0.0272 | $19.86 | — | — | Redirectors |
| t3.medium | 2 | 4 GB | $0.0432 | $31.54 | — | — | C2 Team Server, Dashboard Server |
| t3.large | 2 | 8 GB | $0.0885 | $64.61 | — | — | C2 (optional upgrade) |
| t3.xlarge | 4 | 16 GB | $0.1792 | $130.82 | — | — | C2 (optional upgrade) |
| t2.small | 2 | 2 GB | $0.0205 | $14.97 | — | — | GOAD Jumpbox |
| t2.medium | 2 | 4 GB | $0.0411 | $30.00 | $0.1087 | $79.35 | GOAD AD VMs, GOAD Team Server |
| t2.large | 2 | 8 GB | $0.0945 | $68.99 | $0.1621 | $118.33 | Attack Box (Win), GOAD SCCM srv01 |

## Other AWS Services (eu-central-1)

| Service | Cost | Notes |
|---|---|---|
| NAT Gateway (hourly) | $0.048/hr | $35.04/mo (730 hrs) |
| NAT Gateway (data) | $0.048/GB | Outbound data processing |
| EBS gp3 | ~$0.0952/GB/mo | Default volume type, encrypted |
| Elastic IP (attached) | Free | No charge when associated |
| Route 53 Hosted Zone | $0.50/mo | Per hosted zone |
| S3 Standard | ~$0.024/GB/mo | Minimal usage for CS storage |

## Root Volume Sizes (Terraform defaults)

| Component | Volume (GB) | EBS Cost/mo |
|---|---|---|
| C2 Team Server | 20 | $1.90 |
| Proxy Redirector | 8 | $0.76 |
| Dashboard Server (Linux) | 20 | $1.90 |
| Attack Box (Windows) | 40 | $3.81 |
| GOAD Jumpbox | 20 | $1.90 |
| GOAD Team Server | 20 | $1.90 |
| GOAD Windows VMs | 50 | $4.76 |

## Deployment Cost Estimates

Rounded to nearest $5. Includes: EC2, NAT Gateway, EBS, Route 53, S3.
Does NOT include: data transfer, CloudFront (if domain fronting enabled), ACM.

### C2-Only Deployments

| Deployment | Components | Monthly Est. |
|---|---|---|
| **c2-adhoc** | 1× C2 (t3.med) + 2× Redir (t3.sm) + Attack Box (t2.lg Win) + NAT | ~$235 |
| **c2-purple** | 2× C2 (t3.med) + 2× Redir (t3.sm) + Attack Box (t2.lg Win) + NAT | ~$270 |
| **c2-full** | 3× C2 (t3.med) + 2× Redir (t3.sm) + Attack Box (t2.lg Win) + NAT | ~$300 |

### GOAD-Only Deployments

| Deployment | Components | Monthly Est. |
|---|---|---|
| **goad-mini** | 1× AD VM (t2.med Win) + Jumpbox (t2.sm) + Attack Box (t2.lg Win) + NAT | ~$260 |
| **goad-light** | 3× AD VMs (t2.med Win) + Jumpbox (t2.sm) + Attack Box (t2.lg Win) + NAT | ~$425 |
| **goad-sccm** | 3× AD VMs (t2.med Win) + 1× SCCM (t2.lg Win) + Jumpbox (t2.sm) + Attack Box (t2.lg Win) + NAT | ~$550 |
| **goad-full** | 5× AD VMs (t2.med Win) + Jumpbox (t2.sm) + Attack Box (t2.lg Win) + NAT | ~$595 |
| **goad-nha** | 5× AD VMs (t2.med Win) + Jumpbox (t2.sm) + Attack Box (t2.lg Win) + NAT | ~$595 |

### Combined Deployments (2 VPCs + VPC Peering)

| Deployment | Components | Monthly Est. |
|---|---|---|
| **combined-adhoc-mini** | c2-adhoc infra + 1× AD VM (t2.med Win) + Jumpbox + 2× NAT | ~$370 |
| **combined-adhoc-light** | c2-adhoc infra + 3× AD VMs (t2.med Win) + Jumpbox + 2× NAT | ~$535 |
| **combined-full-full** | c2-full infra + 5× AD VMs (t2.med Win) + Jumpbox + 2× NAT | ~$770 |

## Cost Drivers (ranked by impact)

1. **Windows Server licenses** — $49/mo surcharge per instance (t2.medium: $30 Linux → $79 Windows)
2. **NAT Gateway** — $35/mo fixed per VPC (combined deployments have 2)
3. **Attack Box (Windows t2.large)** — $118/mo single largest instance
4. **GOAD AD VMs** — $79/mo each (Windows t2.medium)
5. **EBS storage** — Minor (~$5-25/mo total depending on VM count)

## Notes

- Prices are On-Demand. Reserved Instances or Savings Plans can reduce costs 30-60%.
- Data transfer costs are not included (typically minimal for lab/test usage).
- CloudFront domain fronting adds ~$0.085/GB for data transfer if enabled.
- These are eu-central-1 (Frankfurt) prices. US regions are ~5-10% cheaper.
