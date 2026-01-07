# Web Application File Upload for Cobalt Strike

## Overview

Since the web application is **local-only**, files uploaded through it stay on your local machine initially. This document explains how to handle Cobalt Strike file uploads and get them to AWS for deployment.

## The Challenge

**Local Web App → AWS EC2 Instances:**
- Web app runs locally (files uploaded stay local)
- EC2 instances need files from AWS (S3)
- Need a bridge: Local → AWS S3 → EC2 instances

## Solution Options

### Option 1: Web App Uploads to S3 (Recommended)

**Flow:**
```
User → Web App (Local) → Upload to S3 → EC2 Instances Download from S3
```

**How it works:**
1. User uploads Cobalt Strike files through web app
2. Web app temporarily stores locally
3. Web app uploads to encrypted S3 bucket
4. Ansible playbook downloads from S3 to EC2 instances

**Pros:**
- ✅ Files never stored permanently on local machine
- ✅ Secure (encrypted S3)
- ✅ Works with existing Ansible automation
- ✅ Files available for all instances

**Cons:**
- ⚠️ Requires AWS credentials with S3 write access
- ⚠️ Files pass through local machine (temporarily)

### Option 2: Direct S3 Upload (Alternative)

**Flow:**
```
User → AWS Console / AWS CLI → S3 → EC2 Instances Download
```

**How it works:**
1. User uploads directly to S3 (bypass web app)
2. Ansible playbook downloads from S3

**Pros:**
- ✅ No local storage needed
- ✅ Direct to AWS

**Cons:**
- ⚠️ Bypasses web app
- ⚠️ Less user-friendly

### Option 3: Web App → Temporary Storage → S3

**Flow:**
```
User → Web App → Temp Storage → Background Upload to S3 → EC2 Download
```

**How it works:**
1. User uploads through web app
2. Files stored temporarily in web app directory
3. Background job uploads to S3
4. Files deleted from local after upload
5. Ansible downloads from S3

**Pros:**
- ✅ User-friendly (web app interface)
- ✅ Files cleaned up after upload
- ✅ Progress tracking possible

**Cons:**
- ⚠️ Temporary local storage needed
- ⚠️ More complex implementation

## Recommended Implementation

### Web App File Upload Feature

**Backend API Endpoint:**
```python
# webapp/backend/routes/deploy.py

@bp.route('/upload-cobalt-strike', methods=['POST'])
def upload_cobalt_strike():
    """Upload Cobalt Strike files to S3"""
    try:
        # Get uploaded file
        file = request.files['cobalt_strike_archive']
        
        # Validate file
        if not file or file.filename == '':
            return jsonify({"error": "No file provided"}), 400
        
        # Generate unique filename
        filename = f"cobalt-strike-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"
        temp_path = f"/tmp/{filename}"
        
        # Save temporarily
        file.save(temp_path)
        
        # Upload to S3
        s3_client = boto3.client('s3')
        s3_client.upload_file(
            temp_path,
            'red-team-artifacts',
            f'cobalt-strike/{filename}',
            ExtraArgs={
                'ServerSideEncryption': 'aws:kms',
                'SSEKMSKeyId': 'alias/red-team-kms-key'  # Or use default
            }
        )
        
        # Clean up temp file
        os.remove(temp_path)
        
        return jsonify({
            "success": True,
            "s3_key": f"cobalt-strike/{filename}",
            "message": "File uploaded to S3 successfully"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

**Frontend Upload Form:**
```html
<!-- Upload section in web app -->
<div class="upload-section">
    <h3>Upload Cobalt Strike</h3>
    <form id="upload-cs-form" enctype="multipart/form-data">
        <input type="file" id="cs-file" accept=".tar.gz,.zip" required>
        <button type="submit">Upload to S3</button>
    </form>
    <div id="upload-status"></div>
</div>
```

**JavaScript:**
```javascript
document.getElementById('upload-cs-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = new FormData();
    formData.append('cobalt_strike_archive', document.getElementById('cs-file').files[0]);
    
    const statusDiv = document.getElementById('upload-status');
    statusDiv.innerHTML = 'Uploading...';
    
    try {
        const response = await fetch('/api/deploy/upload-cobalt-strike', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        if (data.success) {
            statusDiv.innerHTML = `✅ Uploaded to S3: ${data.s3_key}`;
        } else {
            statusDiv.innerHTML = `❌ Error: ${data.error}`;
        }
    } catch (error) {
        statusDiv.innerHTML = `❌ Upload failed: ${error.message}`;
    }
});
```

## Complete Workflow

### Step-by-Step Process

1. **User uploads through web app:**
   - Navigate to "Deploy" tab
   - Click "Upload Cobalt Strike"
   - Select file (tar.gz archive)
   - Click "Upload"

2. **Web app processes:**
   - Validates file
   - Temporarily saves to `/tmp/`
   - Uploads to S3 (encrypted)
   - Deletes temp file
   - Returns S3 key

3. **Deployment:**
   - User clicks "Deploy Infrastructure"
   - Infrastructure deploys
   - Ansible playbook runs
   - Downloads from S3
   - Installs on EC2 instances

## Security Considerations

### File Handling

**Temporary Storage:**
- ✅ Files stored in `/tmp/` (temporary)
- ✅ Deleted immediately after S3 upload
- ✅ No permanent local storage
- ✅ File size limits (check before upload)

**S3 Upload:**
- ✅ Encrypted with KMS
- ✅ Access controlled (IAM)
- ✅ Versioned (optional)
- ✅ Lifecycle policies (auto-delete old versions)

**Access Control:**
- ✅ Web app uses AWS credentials (from `~/.aws/credentials`)
- ✅ S3 bucket policy restricts access
- ✅ CloudTrail logs all access

### Best Practices

1. **Validate files:**
   - Check file type
   - Check file size
   - Verify archive integrity

2. **Secure upload:**
   - Use HTTPS (even locally)
   - Encrypt in transit
   - Encrypt at rest (S3 KMS)

3. **Clean up:**
   - Delete temp files immediately
   - Set S3 lifecycle policies
   - Rotate S3 keys regularly

## Implementation Details

### S3 Bucket Setup

**Create bucket:**
```bash
aws s3 mb s3://red-team-artifacts --region us-east-1

# Enable encryption
aws s3api put-bucket-encryption \
    --bucket red-team-artifacts \
    --server-side-encryption-configuration '{
        "Rules": [{
            "ApplyServerSideEncryptionByDefault": {
                "SSEAlgorithm": "aws:kms",
                "KMSMasterKeyID": "alias/red-team-kms-key"
            }
        }]
    }'

# Set bucket policy (restrict access)
aws s3api put-bucket-policy --bucket red-team-artifacts --policy '{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"AWS": "arn:aws:iam::ACCOUNT:user/red-team-user"},
        "Action": ["s3:PutObject", "s3:GetObject"],
        "Resource": "arn:aws:s3:::red-team-artifacts/*"
    }]
}'
```

### Web App Dependencies

**Add to requirements.txt:**
```
boto3>=1.28.0
```

**Backend configuration:**
```python
# webapp/backend/config.py
import boto3
import os

S3_BUCKET = os.getenv('S3_ARTIFACTS_BUCKET', 'red-team-artifacts')
S3_REGION = os.getenv('AWS_REGION', 'us-east-1')

# Initialize S3 client (uses AWS credentials from environment)
s3_client = boto3.client('s3', region_name=S3_REGION)
```

## Alternative: Pre-upload to S3

### Manual Upload First

**If user prefers manual upload:**

1. **User uploads to S3 manually:**
   ```bash
   aws s3 cp cobalt-strike.tar.gz s3://red-team-artifacts/cobalt-strike/ \
       --sse aws:kms
   ```

2. **Web app references existing file:**
   - Web app lists available files in S3
   - User selects which version to deploy
   - Ansible uses selected file

**Web app feature:**
```python
@bp.route('/list-cobalt-strike', methods=['GET'])
def list_cobalt_strike():
    """List available Cobalt Strike files in S3"""
    try:
        s3_client = boto3.client('s3')
        response = s3_client.list_objects_v2(
            Bucket='red-team-artifacts',
            Prefix='cobalt-strike/'
        )
        
        files = [obj['Key'] for obj in response.get('Contents', [])]
        return jsonify({"files": files})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

## File Size Considerations

### Limits

**Web app limits:**
- Flask default: 16MB (configurable)
- Browser upload: Depends on browser
- Network timeout: Large files may timeout

**Solutions:**
1. **Increase Flask limit:**
   ```python
   app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB
   ```

2. **Chunked upload:**
   - Split large files into chunks
   - Upload chunks separately
   - Reassemble in S3

3. **Direct S3 upload (presigned URLs):**
   - Web app generates presigned URL
   - Browser uploads directly to S3
   - No web app in middle

### Presigned URL Approach (Best for Large Files)

**How it works:**
1. Web app generates presigned S3 URL
2. Browser uploads directly to S3
3. No file passes through web app
4. Web app just triggers deployment

**Backend:**
```python
@bp.route('/get-upload-url', methods=['POST'])
def get_upload_url():
    """Generate presigned URL for direct S3 upload"""
    s3_client = boto3.client('s3')
    
    filename = request.json.get('filename', 'cobalt-strike.tar.gz')
    s3_key = f"cobalt-strike/{filename}"
    
    url = s3_client.generate_presigned_url(
        'put_object',
        Params={
            'Bucket': 'red-team-artifacts',
            'Key': s3_key,
            'ServerSideEncryption': 'aws:kms'
        },
        ExpiresIn=3600  # 1 hour
    )
    
    return jsonify({
        "upload_url": url,
        "s3_key": s3_key
    })
```

**Frontend:**
```javascript
// Upload directly to S3 (no web app in middle)
async function uploadToS3(file) {
    // Get presigned URL
    const response = await fetch('/api/deploy/get-upload-url', {
        method: 'POST',
        body: JSON.stringify({ filename: file.name })
    });
    
    const { upload_url, s3_key } = await response.json();
    
    // Upload directly to S3
    await fetch(upload_url, {
        method: 'PUT',
        body: file,
        headers: {
            'Content-Type': 'application/gzip'
        }
    });
    
    return s3_key;
}
```

## Deployment Integration

### After Upload

**Web app deployment flow:**
1. User uploads Cobalt Strike (via web app)
2. File stored in S3
3. User clicks "Deploy Infrastructure"
4. Infrastructure deploys
5. Ansible playbook runs automatically
6. Downloads from S3
7. Installs on EC2 instances

**Or manual trigger:**
```bash
# After upload through web app
ansible-playbook -i inventory/hosts.yml \
    playbooks/deploy-cobalt-strike.yml \
    -e "cs_s3_key=cobalt-strike/cobalt-strike-20240101.tar.gz"
```

## Summary

### Answer to Your Question

**Does the binary need to sit in AWS first?**

**Short answer:** Yes, but the web app can upload it for you!

**Flow:**
1. ✅ User uploads through **local web app** (stays local temporarily)
2. ✅ Web app **uploads to S3** (encrypted)
3. ✅ Temp file **deleted from local**
4. ✅ Ansible **downloads from S3** to EC2 instances

**Key points:**
- ✅ Files **don't stay on local machine** (deleted after S3 upload)
- ✅ Web app acts as **uploader to S3** (not permanent storage)
- ✅ All files **end up in AWS S3** (encrypted)
- ✅ EC2 instances **download from S3** (not from local)

**Best approach:**
- **Presigned URL upload** - Browser uploads directly to S3
- **No file passes through web app** (better for large files)
- **Web app just coordinates** the process

The web app makes it user-friendly, but files ultimately need to be in AWS S3 for the EC2 instances to access them!

