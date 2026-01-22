# S3 Security Analysis - Confused Deputy Attack Protection

## Current Security Status: ⚠️ **PARTIALLY PROTECTED**

Your S3 bucket has **good IAM-level security** but is **missing bucket-level Confused Deputy protection**.

---

## What is a Confused Deputy Attack?

A **Confused Deputy attack** occurs when an attacker tricks AWS into accessing your resources by:
1. Obtaining temporary credentials for an EC2 instance role
2. Using those credentials from a **different account or VPC**
3. AWS (the "deputy") grants access because it's "confused" about the request origin

### Example Attack Scenario:
```
┌─────────────────────────────────────────────────────────────┐
│  Attacker's AWS Account                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Attacker's EC2 Instance                             │   │
│  │  • Assumes YOUR IAM role (if trust policy too broad) │   │
│  │  • Uses credentials to access YOUR S3 bucket         │   │
│  │  • Downloads your Cobalt Strike archives & scripts   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                         ↓
              ❌ Access YOUR S3 bucket
                         ↓
┌─────────────────────────────────────────────────────────────┐
│  Your AWS Account                                           │
│  s3://your-cs-files-bucket/                                 │
│    • Cobalt Strike archives                                 │
│    • Attack box init scripts                                │
│    • SSH keys                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Current Protection: IAM Roles ✅ (Good!)

### What You Have:

**IAM Role Trust Policy** (lines 218-243):
```hcl
condition {
  test     = "StringEquals"
  variable = "aws:SourceAccount"
  values   = [data.aws_caller_identity.current.account_id]
}

condition {
  test     = "StringEquals"
  variable = "aws:SourceVpc"
  values   = [var.goad_vpc_id]  # or var.c2_vpc_id
}
```

**IAM Permission Policy** (lines 474-502):
```hcl
condition {
  test     = "StringEquals"
  variable = "aws:SourceVpc"
  values   = [var.goad_vpc_id]
}

condition {
  test     = "Bool"
  variable = "aws:SecureTransport"
  values   = ["true"]
}
```

### What This Protects:
✅ Prevents role assumption from other AWS accounts  
✅ Prevents role assumption from other VPCs  
✅ Requires HTTPS for all S3 operations  
✅ Separate roles per VPC (defense in depth)

---

## Missing Protection: S3 Bucket Policy ⚠️ (Gap!)

### What's Missing:

You have **NO S3 bucket policy** defined. This means:
- ⚠️ Bucket relies entirely on IAM policies
- ⚠️ No defense-in-depth at the bucket level
- ⚠️ If IAM role trust policy is misconfigured, bucket is exposed
- ⚠️ No additional validation of request origin at bucket level

### The Problem:

**Defense in depth principle:** Security should be enforced at **multiple layers**:
1. ✅ **IAM Role Trust Policy** - Who can assume the role?
2. ✅ **IAM Permission Policy** - What can the role do?
3. ❌ **S3 Bucket Policy** - What requests does the bucket accept? ← **MISSING**

---

## Attack Scenarios

### Scenario 1: IAM Trust Policy Bypass (Current Risk)
If an attacker can:
- Compromise an EC2 instance in your VPC
- OR find a way to bypass VPC restrictions
- They can access your S3 bucket (only IAM enforcement)

**Risk Level:** 🟡 Medium (requires VPC access)

### Scenario 2: If You Add an S3 Bucket Policy (Improved)
Even if IAM is compromised, the bucket policy provides a second layer:
- Bucket policy validates `aws:SourceVpc`
- Bucket policy validates `aws:SourceAccount`
- Bucket policy enforces `aws:SecureTransport`

**Risk Level:** 🟢 Low (defense in depth)

---

## Recommendations

### 🔴 Critical: Add S3 Bucket Policy

Add a bucket policy that mirrors and reinforces your IAM conditions:

```hcl
resource "aws_s3_bucket_policy" "cs_files" {
  bucket = aws_s3_bucket.cs_files.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DenyNonVPCAccess"
        Effect = "Deny"
        Principal = "*"
        Action = "s3:*"
        Resource = [
          aws_s3_bucket.cs_files.arn,
          "\${aws_s3_bucket.cs_files.arn}/*"
        ]
        Condition = {
          StringNotEquals = {
            "aws:SourceVpc" = [var.c2_vpc_id, var.goad_vpc_id]
          }
          StringNotEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      },
      {
        Sid    = "DenyUnencryptedTransport"
        Effect = "Deny"
        Principal = "*"
        Action = "s3:*"
        Resource = [
          aws_s3_bucket.cs_files.arn,
          "\${aws_s3_bucket.cs_files.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}
```

**Benefits:**
- ✅ Blocks all access from outside your VPCs (even if IAM is bypassed)
- ✅ Blocks all access from other AWS accounts
- ✅ Enforces HTTPS at bucket level
- ✅ Defense in depth - two layers of security

---

## Current Security Score

| Security Layer | Status | Score |
|---------------|--------|-------|
| Public Access Block | ✅ Enabled | 10/10 |
| Encryption at Rest | ✅ AES256 | 10/10 |
| Versioning | ✅ Enabled | 10/10 |
| IAM Role Trust Policy | ✅ SourceAccount + SourceVpc | 10/10 |
| IAM Permission Policy | ✅ SourceVpc + SecureTransport | 10/10 |
| **S3 Bucket Policy** | ❌ **Missing** | **0/10** |
| Lifecycle Policies | ✅ Auto-delete | 10/10 |
| **Overall Score** | | **60/70** |

---

## Attack Box Script Security

### Scripts Path: `{deployment_id}/scripts/attackbox_init.ps1`

**Current Protection:**
- ✅ Scripts stored in S3 (not in user_data)
- ✅ IAM role can read from S3
- ✅ HTTPS required for download (IAM policy)
- ⚠️ No bucket-level enforcement

**With Bucket Policy:**
- ✅ Scripts only accessible from GOAD VPC
- ✅ Second layer of Confused Deputy protection
- ✅ Defense in depth

---

## Comparison: With vs Without Bucket Policy

### Without Bucket Policy (Current):
```
Attacker → Compromised IAM Role → S3 Bucket ✓ (Access Granted)
          (Bypasses IAM trust)
```

### With Bucket Policy (Recommended):
```
Attacker → Compromised IAM Role → S3 Bucket Policy ✗ (Access Denied)
          (Bypasses IAM trust)   (Enforces SourceVpc/SourceAccount)
```

---

## Conclusion

### Current Status:
- ✅ **Good IAM security** with VPC and account restrictions
- ⚠️ **Missing defense in depth** at the bucket level
- 🟡 **Medium risk** - vulnerable if IAM trust policy is bypassed

### Recommended:
- 🔴 **Add S3 bucket policy** for Confused Deputy protection
- 🟢 **Achieve defense in depth** with multiple security layers
- 🟢 **Reduce risk to Low** with comprehensive protection

### Priority: **HIGH**
The S3 bucket policy should be added to achieve proper Confused Deputy protection and follow AWS security best practices.
