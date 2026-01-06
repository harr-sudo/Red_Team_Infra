# Where Do AWS Credentials Come From?

## Quick Answer

Your AWS credentials are coming from **`~/.aws/credentials`** - a file that was created when you (or someone) previously ran `aws configure` on this machine.

## How It Works

The web application (and all AWS tools) use the **AWS Credential Chain** to find credentials automatically. They check in this order:

1. ✅ **Environment Variables** (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) - Not set in your case
2. ✅ **`~/.aws/credentials` file** - **This is where yours are!** ✅
3. IAM Roles (if running on EC2)
4. AWS SSO (if configured)

## Your Current Setup

Based on the check, your credentials are stored in:

**File:** `~/.aws/credentials`  
**Last Modified:** May 16, 2025  
**Account:** 434060576903  
**User:** pen-test

These credentials were likely configured previously with:
```bash
aws configure
```

## How the Web App Found Them

When you clicked "Check AWS" in the web application:

1. The web app runs: `aws sts get-caller-identity`
2. AWS CLI automatically reads `~/.aws/credentials`
3. Uses those credentials to authenticate
4. Returns your account and user information

**No credentials were entered in the web app** - it uses whatever AWS CLI finds!

## Viewing Your Credentials (Safely)

You can see which profile is configured (without showing secrets):

```bash
# See which profiles exist
cat ~/.aws/config

# See profile names (without secrets)
grep "^\[" ~/.aws/credentials
```

## Security Note

⚠️ **Important**: The `~/.aws/credentials` file contains your access keys. It's protected (permissions: `600`), but:

- ✅ **Don't share this file**
- ✅ **Don't commit it to Git**
- ✅ **Rotate keys regularly**
- ✅ **Use different keys for different projects if needed**

## Using Different Credentials

If you want to use different credentials:

### Option 1: Update Existing Credentials
```bash
aws configure
# Enter new access key, secret key, region
```

### Option 2: Create a New Profile
```bash
aws configure --profile red-team
# Enter credentials for red team project
```

Then in `terraform.tfvars`:
```hcl
aws_profile = "red-team"
```

### Option 3: Use Environment Variables
```bash
export AWS_ACCESS_KEY_ID="new-key"
export AWS_SECRET_ACCESS_KEY="new-secret"
```

## Verifying Which Credentials Are Active

```bash
# See current credentials
aws sts get-caller-identity

# See which profile is default
cat ~/.aws/config | grep "\[default\]" -A 2
```

## Summary

- ✅ Your credentials are in `~/.aws/credentials` (created previously)
- ✅ The web app uses AWS CLI, which reads that file automatically
- ✅ No credentials entered in web app - it uses existing AWS CLI config
- ✅ This is the standard, secure way AWS tools work

**Your credentials are working correctly!** The web app is just showing you what AWS CLI already knows.

