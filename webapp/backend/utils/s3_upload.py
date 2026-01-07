"""
S3 Upload Utility
=================
Handles uploading Cobalt Strike archives to S3 for EC2 deployment.
"""

import os
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


class S3UploadError(Exception):
    """Custom exception for S3 upload errors"""
    pass


def get_s3_client(region: str = 'us-east-1', profile: Optional[str] = None):
    """
    Get boto3 S3 client.
    
    Args:
        region: AWS region
        profile: AWS profile name (optional)
    
    Returns:
        boto3 S3 client
    """
    session_kwargs = {}
    if profile:
        session_kwargs['profile_name'] = profile
    
    session = boto3.Session(**session_kwargs)
    return session.client('s3', region_name=region)


def find_cs_bucket(project_name: str, region: str = 'us-east-1', profile: Optional[str] = None) -> Optional[str]:
    """
    Find the CS files S3 bucket created by Terraform.
    
    Args:
        project_name: Project name used in Terraform
        region: AWS region
        profile: AWS profile name (optional)
    
    Returns:
        Bucket name if found, None otherwise
    """
    try:
        s3 = get_s3_client(region, profile)
        response = s3.list_buckets()
        
        # Look for bucket with our naming pattern
        prefix = f"{project_name.lower()}-cs-files-"
        for bucket in response.get('Buckets', []):
            if bucket['Name'].startswith(prefix):
                return bucket['Name']
        
        return None
    except (ClientError, NoCredentialsError) as e:
        raise S3UploadError(f"Failed to list S3 buckets: {e}")


def upload_cs_file(
    file_path: str,
    project_name: str,
    region: str = 'us-east-1',
    profile: Optional[str] = None,
    bucket_name: Optional[str] = None
) -> Tuple[str, str]:
    """
    Upload Cobalt Strike archive to S3.
    
    Args:
        file_path: Local path to the Cobalt Strike archive
        project_name: Project name (used to find bucket)
        region: AWS region
        profile: AWS profile name (optional)
        bucket_name: Override bucket name (optional)
    
    Returns:
        Tuple of (S3 URI, bucket name)
    
    Raises:
        S3UploadError: If upload fails
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise S3UploadError(f"File not found: {file_path}")
    
    if not file_path.is_file():
        raise S3UploadError(f"Not a file: {file_path}")
    
    # Find or use bucket
    if not bucket_name:
        bucket_name = find_cs_bucket(project_name, region, profile)
        if not bucket_name:
            raise S3UploadError(
                f"CS files S3 bucket not found for project '{project_name}'. "
                "Ensure Terraform has created it (run terraform apply first)."
            )
    
    try:
        s3 = get_s3_client(region, profile)
        
        # Generate unique key with timestamp
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        key = f"cobaltstrike-{timestamp}.tar.gz"
        
        # Upload file
        s3.upload_file(str(file_path), bucket_name, key)
        
        s3_uri = f"s3://{bucket_name}/{key}"
        return s3_uri, bucket_name
        
    except ClientError as e:
        raise S3UploadError(f"Failed to upload file to S3: {e}")
    except NoCredentialsError:
        raise S3UploadError("AWS credentials not found. Configure AWS CLI or set environment variables.")


def check_bucket_exists(bucket_name: str, region: str = 'us-east-1', profile: Optional[str] = None) -> bool:
    """
    Check if an S3 bucket exists and is accessible.
    
    Args:
        bucket_name: Name of the bucket
        region: AWS region
        profile: AWS profile name (optional)
    
    Returns:
        True if bucket exists and is accessible
    """
    try:
        s3 = get_s3_client(region, profile)
        s3.head_bucket(Bucket=bucket_name)
        return True
    except ClientError:
        return False


def list_cs_files(
    project_name: str,
    region: str = 'us-east-1',
    profile: Optional[str] = None,
    bucket_name: Optional[str] = None
) -> list:
    """
    List Cobalt Strike files in S3 bucket.
    
    Args:
        project_name: Project name (used to find bucket)
        region: AWS region
        profile: AWS profile name (optional)
        bucket_name: Override bucket name (optional)
    
    Returns:
        List of file info dicts
    """
    if not bucket_name:
        bucket_name = find_cs_bucket(project_name, region, profile)
        if not bucket_name:
            return []
    
    try:
        s3 = get_s3_client(region, profile)
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix='cobaltstrike-')
        
        files = []
        for obj in response.get('Contents', []):
            files.append({
                'key': obj['Key'],
                'size': obj['Size'],
                'size_mb': round(obj['Size'] / (1024 * 1024), 2),
                'last_modified': obj['LastModified'].isoformat(),
                's3_uri': f"s3://{bucket_name}/{obj['Key']}"
            })
        
        # Sort by last modified (newest first)
        files.sort(key=lambda x: x['last_modified'], reverse=True)
        return files
        
    except ClientError as e:
        raise S3UploadError(f"Failed to list S3 files: {e}")


def delete_cs_file(
    key: str,
    project_name: str,
    region: str = 'us-east-1',
    profile: Optional[str] = None,
    bucket_name: Optional[str] = None
) -> bool:
    """
    Delete a Cobalt Strike file from S3.
    
    Args:
        key: S3 object key
        project_name: Project name (used to find bucket)
        region: AWS region
        profile: AWS profile name (optional)
        bucket_name: Override bucket name (optional)
    
    Returns:
        True if deleted successfully
    """
    if not bucket_name:
        bucket_name = find_cs_bucket(project_name, region, profile)
        if not bucket_name:
            raise S3UploadError(f"CS files S3 bucket not found for project '{project_name}'")
    
    try:
        s3 = get_s3_client(region, profile)
        s3.delete_object(Bucket=bucket_name, Key=key)
        return True
    except ClientError as e:
        raise S3UploadError(f"Failed to delete S3 file: {e}")


def get_upload_command(bucket_name: str) -> str:
    """Get AWS CLI command to upload CS file."""
    return f"aws s3 cp cobaltstrike.tar.gz s3://{bucket_name}/"


# =============================================================================
# CLI Interface (for testing)
# =============================================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='S3 Upload Utility for Cobalt Strike')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Upload command
    upload_parser = subparsers.add_parser('upload', help='Upload file to S3')
    upload_parser.add_argument('file', help='File to upload')
    upload_parser.add_argument('--project', required=True, help='Project name')
    upload_parser.add_argument('--region', default='us-east-1', help='AWS region')
    upload_parser.add_argument('--profile', help='AWS profile')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List files in S3')
    list_parser.add_argument('--project', required=True, help='Project name')
    list_parser.add_argument('--region', default='us-east-1', help='AWS region')
    list_parser.add_argument('--profile', help='AWS profile')
    
    # Find bucket command
    find_parser = subparsers.add_parser('find-bucket', help='Find CS bucket')
    find_parser.add_argument('--project', required=True, help='Project name')
    find_parser.add_argument('--region', default='us-east-1', help='AWS region')
    find_parser.add_argument('--profile', help='AWS profile')
    
    args = parser.parse_args()
    
    try:
        if args.command == 'upload':
            s3_uri, bucket = upload_cs_file(
                args.file, args.project, args.region, args.profile
            )
            print(f"Uploaded to: {s3_uri}")
            print(f"Bucket: {bucket}")
            
        elif args.command == 'list':
            files = list_cs_files(args.project, args.region, args.profile)
            if files:
                print(f"Found {len(files)} file(s):")
                for f in files:
                    print(f"  - {f['key']} ({f['size_mb']} MB) - {f['last_modified']}")
            else:
                print("No files found")
                
        elif args.command == 'find-bucket':
            bucket = find_cs_bucket(args.project, args.region, args.profile)
            if bucket:
                print(f"Found bucket: {bucket}")
            else:
                print("Bucket not found")
        else:
            parser.print_help()
            
    except S3UploadError as e:
        print(f"Error: {e}")
        exit(1)

