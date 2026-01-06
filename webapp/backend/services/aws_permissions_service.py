"""
AWS Permissions Service
Check if AWS account has required permissions for deployment
"""

import subprocess
import json
from typing import Dict, List, Tuple
from pathlib import Path

class AWSPermissionsService:
    """Service for checking AWS permissions"""
    
    # Required permissions for infrastructure deployment
    REQUIRED_PERMISSIONS = {
        "EC2": [
            "ec2:CreateVpc",
            "ec2:CreateSubnet",
            "ec2:CreateInternetGateway",
            "ec2:CreateRouteTable",
            "ec2:CreateRoute",
            "ec2:CreateSecurityGroup",
            "ec2:RunInstances",
            "ec2:AllocateAddress",
            "ec2:AssociateAddress",
            "ec2:DescribeVpcs",
            "ec2:DescribeSubnets",
            "ec2:DescribeInternetGateways",
            "ec2:DescribeRouteTables",
            "ec2:DescribeSecurityGroups",
            "ec2:DescribeInstances",
            "ec2:DescribeAddresses",
            "ec2:DescribeImages",
            "ec2:DescribeAvailabilityZones",
            "ec2:DescribeKeyPairs",
            "ec2:AuthorizeSecurityGroupIngress",
            "ec2:AuthorizeSecurityGroupEgress",
            "ec2:AttachInternetGateway",
            "ec2:CreateTags",
        ],
        "IAM": [
            "iam:GetRole",
            "iam:GetInstanceProfile",
            "iam:PassRole",  # If using instance profiles
        ],
        "S3": [
            "s3:CreateBucket",
            "s3:PutObject",
            "s3:GetObject",
            "s3:ListBucket",
            "s3:GetBucketLocation",
        ],
        "CloudWatch": [
            "cloudwatch:PutMetricData",
            "logs:CreateLogGroup",
            "logs:PutLogEvents",
        ],
    }
    
    @staticmethod
    def _run_aws_command(command: List[str], timeout: int = 10) -> Tuple[int, str, str]:
        """Run AWS CLI command"""
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)
    
    @staticmethod
    def check_permission(action: str, resource: str = "*") -> Tuple[bool, str]:
        """
        Check if a specific permission is allowed
        Uses IAM simulate-principal-policy if available, otherwise tries actual action
        """
        # This method is kept for compatibility but not used in current implementation
        return None, "Use check_permissions_batch or check_using_policy_simulation instead"
    
    @staticmethod
    def check_permissions_batch() -> Dict:
        """
        Check all required permissions
        Returns a dictionary with permission status
        """
        results = {
            "overall": "unknown",
            "categories": {},
            "missing_permissions": [],
            "available_permissions": [],
            "warnings": []
        }
        
        # Check each category
        all_missing = []
        all_available = []
        
        for category, permissions in AWSPermissionsService.REQUIRED_PERMISSIONS.items():
            category_results = {
                "status": "unknown",
                "permissions": {},
                "missing": [],
                "available": []
            }
            
            for permission in permissions:
                # For now, we'll do a simplified check
                # In production, you'd want to use IAM policy simulation
                has_permission, reason = AWSPermissionsService._check_permission_simple(permission)
                
                category_results["permissions"][permission] = {
                    "allowed": has_permission,
                    "reason": reason
                }
                
                if has_permission:
                    all_available.append(permission)
                    category_results["available"].append(permission)
                else:
                    all_missing.append(permission)
                    category_results["missing"].append(permission)
            
            # Determine category status
            if len(category_results["missing"]) == 0:
                category_results["status"] = "complete"
            elif len(category_results["available"]) == 0:
                category_results["status"] = "missing"
            else:
                category_results["status"] = "partial"
            
            results["categories"][category] = category_results
        
        # Overall status
        if len(all_missing) == 0:
            results["overall"] = "complete"
        elif len(all_available) == 0:
            results["overall"] = "missing"
        else:
            results["overall"] = "partial"
        
        results["missing_permissions"] = all_missing
        results["available_permissions"] = all_available
        
        return results
    
    @staticmethod
    def _check_permission_simple(permission: str) -> Tuple[bool, str]:
        """
        Simplified permission check using safe read operations
        This is a best-effort approach
        """
        # Map permissions to safe test operations
        test_operations = {
            "ec2:DescribeVpcs": ["aws", "ec2", "describe-vpcs", "--max-items", "1"],
            "ec2:DescribeSubnets": ["aws", "ec2", "describe-subnets", "--max-items", "1"],
            "ec2:DescribeInstances": ["aws", "ec2", "describe-instances", "--max-items", "1"],
            "ec2:DescribeSecurityGroups": ["aws", "ec2", "describe-security-groups", "--max-items", "1"],
            "ec2:DescribeImages": ["aws", "ec2", "describe-images", "--owners", "amazon", "--max-items", "1"],
            "ec2:DescribeAvailabilityZones": ["aws", "ec2", "describe-availability-zones"],
            "ec2:DescribeKeyPairs": ["aws", "ec2", "describe-key-pairs", "--max-items", "1"],
            "s3:ListBucket": ["aws", "s3", "ls", "--max-items", "1"],
            "iam:GetRole": ["aws", "iam", "list-roles", "--max-items", "1"],
        }
        
        # Check if we can test this permission
        if permission in test_operations:
            exit_code, stdout, stderr = AWSPermissionsService._run_aws_command(
                test_operations[permission]
            )
            if exit_code == 0:
                return True, "Test operation succeeded"
            else:
                # Check if it's a permission error
                if "AccessDenied" in stderr or "UnauthorizedOperation" in stderr:
                    return False, "Access denied"
                else:
                    return None, "Cannot determine (may need other permissions)"
        
        # For write operations, we can't safely test without actually doing them
        # So we'll mark them as unknown but note they're required
        if permission.startswith(("ec2:Create", "ec2:Allocate", "ec2:Associate", "ec2:Authorize", "ec2:Attach")):
            return None, "Write permission - cannot safely test"
        
        return None, "Cannot test this permission"
    
    @staticmethod
    def check_using_policy_simulation() -> Dict:
        """
        Use IAM policy simulation to check permissions (more accurate)
        Requires iam:SimulatePrincipalPolicy permission
        """
        # Get caller identity
        exit_code, stdout, stderr = AWSPermissionsService._run_aws_command([
            "aws", "sts", "get-caller-identity"
        ])
        
        if exit_code != 0:
            return {
                "success": False,
                "error": "Cannot get caller identity: " + stderr
            }
        
        try:
            identity = json.loads(stdout)
            arn = identity.get("Arn", "")
        except:
            return {
                "success": False,
                "error": "Cannot parse caller identity"
            }
        
        # Collect all permissions
        all_permissions = []
        for permissions in AWSPermissionsService.REQUIRED_PERMISSIONS.values():
            all_permissions.extend(permissions)
        
        # Simulate policy for all permissions
        exit_code, stdout, stderr = AWSPermissionsService._run_aws_command([
            "aws", "iam", "simulate-principal-policy",
            "--policy-source-arn", arn,
            "--action-names"
        ] + all_permissions + [
            "--resource-arns", "*"
        ])
        
        if exit_code != 0:
            # Policy simulation may not be available
            return {
                "success": False,
                "error": "Policy simulation not available (may need iam:SimulatePrincipalPolicy permission)",
                "fallback": AWSPermissionsService.check_permissions_batch()
            }
        
        try:
            result = json.loads(stdout)
            evaluation_results = result.get("EvaluationResults", [])
            
            permissions_status = {}
            missing = []
            available = []
            
            for eval_result in evaluation_results:
                action = eval_result.get("EvalActionName", "")
                decision = eval_result.get("EvalDecision", "deny")
                is_allowed = decision == "allowed"
                
                permissions_status[action] = {
                    "allowed": is_allowed,
                    "decision": decision
                }
                
                if is_allowed:
                    available.append(action)
                else:
                    missing.append(action)
            
            return {
                "success": True,
                "permissions": permissions_status,
                "missing_permissions": missing,
                "available_permissions": available,
                "overall": "complete" if len(missing) == 0 else "partial"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Cannot parse simulation results: {str(e)}",
                "fallback": AWSPermissionsService.check_permissions_batch()
            }

