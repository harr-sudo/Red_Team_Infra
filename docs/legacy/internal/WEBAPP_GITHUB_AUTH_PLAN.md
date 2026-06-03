# Web App GitHub Authentication Check - Implementation Plan

## Overview

Add a GitHub authentication check to the web application that acts as a **helpful nudge** (not a prerequisite) to verify users can access the tools repository. This helps users discover if they need to set up GitHub authentication before deployment.

## Goals

1. **Non-Blocking Check**: Does not prevent deployment if GitHub auth fails
2. **Helpful Nudge**: Encourages users to set up GitHub for tools repository access
3. **Clear Guidance**: Provides specific instructions if authentication fails
4. **User-Friendly**: Clear visual indicators (success/warning, not error)

## Implementation Approach

### 1. Backend API Endpoint

**New Route**: `/api/health/github`

**Location**: `webapp/backend/routes/health.py`

**Functionality**:
- Check if GitHub CLI (`gh`) is installed
- Check if user is authenticated with GitHub CLI
- If authenticated, verify access to tools repository
- Return status with helpful messages

**Response Format**:
```json
{
  "success": true,
  "authenticated": true/false,
  "gh_installed": true/false,
  "repo_accessible": true/false,
  "repo_url": "https://github.com/harr-sudo/red-team-tools",
  "message": "Status message",
  "setup_instructions": "Instructions if not authenticated"
}
```

### 2. Frontend UI Component

**Location**: `webapp/frontend/index.html` - Health Tab

**Placement**: 
- Add new section after AWS Permissions check
- Use warning/info styling (not error)
- Include "Check GitHub Auth" button
- Display status with helpful messages

**Visual Design**:
- ✅ Green: Authenticated and can access repo
- ⚠️ Yellow: Not authenticated (nudge to set up)
- ℹ️ Blue: GitHub CLI not installed (informational)

### 3. JavaScript Function

**Location**: `webapp/frontend/js/app.js`

**Function**: `checkGitHubAuth()`

**Features**:
- Calls `/api/health/github` endpoint
- Updates UI with status
- Shows setup instructions if needed
- Non-blocking (doesn't prevent other actions)

## Detailed Implementation

### Backend Implementation

**File**: `webapp/backend/routes/health.py`

**New Route**:
```python
@bp.route('/github', methods=['GET'])
def check_github():
    """Check GitHub authentication status (non-blocking check)"""
    try:
        # Check if GitHub CLI is installed
        gh_installed = False
        try:
            result = subprocess.run(
                ["gh", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            gh_installed = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            gh_installed = False
        
        if not gh_installed:
            return jsonify({
                "success": True,
                "authenticated": False,
                "gh_installed": False,
                "repo_accessible": False,
                "repo_url": "https://github.com/harr-sudo/red-team-tools",
                "message": "GitHub CLI not installed",
                "setup_instructions": "Install GitHub CLI: brew install gh (macOS) or see https://cli.github.com"
            })
        
        # Check if authenticated
        authenticated = False
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=5
            )
            authenticated = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            authenticated = False
        
        if not authenticated:
            return jsonify({
                "success": True,
                "authenticated": False,
                "gh_installed": True,
                "repo_accessible": False,
                "repo_url": "https://github.com/harr-sudo/red-team-tools",
                "message": "Not authenticated with GitHub",
                "setup_instructions": "Run 'gh auth login' in your terminal to authenticate"
            })
        
        # Check if can access tools repository
        repo_accessible = False
        repo_url = "https://github.com/harr-sudo/red-team-tools"
        try:
            result = subprocess.run(
                ["gh", "repo", "view", "harr-sudo/red-team-tools"],
                capture_output=True,
                text=True,
                timeout=10
            )
            repo_accessible = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            repo_accessible = False
        
        if repo_accessible:
            return jsonify({
                "success": True,
                "authenticated": True,
                "gh_installed": True,
                "repo_accessible": True,
                "repo_url": repo_url,
                "message": "GitHub authenticated and tools repository accessible",
                "setup_instructions": None
            })
        else:
            return jsonify({
                "success": True,
                "authenticated": True,
                "gh_installed": True,
                "repo_accessible": False,
                "repo_url": repo_url,
                "message": "Authenticated but cannot access tools repository",
                "setup_instructions": "You may need to be added as a collaborator. Contact repository owner."
            })
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
```

### Frontend Implementation

**File**: `webapp/frontend/index.html`

**New Section in Health Tab**:
```html
<!-- GitHub Authentication Check (Non-Blocking) -->
<div class="card" style="margin-top: 20px;">
    <h3>🔐 GitHub Authentication (Optional)</h3>
    <p style="color: #666; margin-bottom: 15px;">
        Check if you can access the tools repository. This is optional but recommended for easy tool access.
    </p>
    
    <button class="btn btn-info" onclick="checkGitHubAuth()">Check GitHub Auth</button>
    
    <div id="github-status" class="status-display" style="margin-top: 15px;">
        <p>Click button to check GitHub authentication status</p>
    </div>
</div>
```

**File**: `webapp/frontend/js/app.js`

**New Function**:
```javascript
async function checkGitHubAuth() {
    const statusDiv = document.getElementById('github-status');
    statusDiv.innerHTML = '<div class="spinner"></div>Checking GitHub authentication...';
    statusDiv.className = 'status-display info';
    
    try {
        const response = await fetch(`${API_BASE}/health/github`);
        const data = await response.json();
        
        if (data.success) {
            const authenticated = data.authenticated;
            const ghInstalled = data.gh_installed;
            const repoAccessible = data.repo_accessible;
            const repoUrl = data.repo_url;
            const message = data.message;
            const instructions = data.setup_instructions;
            
            let statusClass = 'info';
            let statusIcon = 'ℹ️';
            
            if (authenticated && repoAccessible) {
                statusClass = 'success';
                statusIcon = '✅';
            } else if (authenticated && !repoAccessible) {
                statusClass = 'warning';
                statusIcon = '⚠️';
            } else if (!authenticated && ghInstalled) {
                statusClass = 'warning';
                statusIcon = '⚠️';
            } else {
                statusClass = 'info';
                statusIcon = 'ℹ️';
            }
            
            let html = `
                <div class="status-display ${statusClass}">
                    <p><strong>${statusIcon} Status:</strong> ${message}</p>
                    <p><strong>GitHub CLI Installed:</strong> ${ghInstalled ? 'Yes ✅' : 'No ❌'}</p>
                    <p><strong>Authenticated:</strong> ${authenticated ? 'Yes ✅' : 'No ❌'}</p>
                    <p><strong>Repository Accessible:</strong> ${repoAccessible ? 'Yes ✅' : 'No ❌'}</p>
                    <p><strong>Repository:</strong> <a href="${repoUrl}" target="_blank">${repoUrl}</a></p>
            `;
            
            if (instructions) {
                html += `
                    <div style="margin-top: 15px; padding: 10px; background-color: #fff3cd; border-radius: 4px;">
                        <p><strong>Setup Instructions:</strong></p>
                        <p>${instructions}</p>
                        <p style="margin-top: 10px;">
                            <strong>Quick Setup:</strong><br>
                            <code style="background: #f5f5f5; padding: 5px; border-radius: 3px; display: block; margin-top: 5px;">
                                gh auth login
                            </code>
                        </p>
                    </div>
                `;
            }
            
            html += '</div>';
            statusDiv.innerHTML = html;
        } else {
            statusDiv.innerHTML = `
                <div class="status-display error">
                    <p><strong>Error:</strong> ${data.error || 'Unknown error'}</p>
                </div>
            `;
        }
    } catch (error) {
        statusDiv.innerHTML = `
            <div class="status-display error">
                <p><strong>Error:</strong> ${error.message}</p>
            </div>
        `;
    }
}
```

## User Experience Flow

### Scenario 1: GitHub CLI Not Installed
1. User clicks "Check GitHub Auth"
2. Status shows: ⚠️ GitHub CLI not installed
3. Instructions: "Install GitHub CLI: brew install gh (macOS)"
4. **Action**: User can still deploy (not blocked)

### Scenario 2: GitHub CLI Installed but Not Authenticated
1. User clicks "Check GitHub Auth"
2. Status shows: ⚠️ Not authenticated with GitHub
3. Instructions: "Run 'gh auth login' in your terminal"
4. **Action**: User can still deploy (not blocked)

### Scenario 3: Authenticated but No Repository Access
1. User clicks "Check GitHub Auth"
2. Status shows: ⚠️ Authenticated but cannot access repository
3. Instructions: "You may need to be added as a collaborator"
4. **Action**: User can still deploy (not blocked)

### Scenario 4: Fully Configured
1. User clicks "Check GitHub Auth"
2. Status shows: ✅ GitHub authenticated and tools repository accessible
3. No instructions needed
4. **Action**: User knows they're ready for tools repository access

## Design Considerations

### Visual Hierarchy
- **Success (Green)**: Everything working
- **Warning (Yellow)**: Needs setup but not blocking
- **Info (Blue)**: Informational only
- **Never Red/Error**: This is a nudge, not a blocker

### Messaging
- Use friendly, helpful language
- Emphasize "optional" and "recommended"
- Provide clear next steps
- Link to repository URL

### Placement
- In Health Tab (not Deploy Tab)
- After AWS Permissions check
- Clearly labeled as "Optional"

## Implementation Steps

1. **Add Backend Route**
   - Create `/api/health/github` endpoint
   - Implement GitHub CLI checks
   - Return helpful status messages

2. **Add Frontend UI**
   - Add section to Health tab
   - Create check button
   - Add status display area

3. **Add JavaScript Function**
   - Implement `checkGitHubAuth()` function
   - Handle all status scenarios
   - Display helpful messages

4. **Test Scenarios**
   - Test with GitHub CLI installed and authenticated
   - Test with GitHub CLI installed but not authenticated
   - Test with GitHub CLI not installed
   - Test with no repository access

5. **Update Documentation**
   - Add to web app README
   - Update Health tab documentation

## Benefits

1. **Proactive Discovery**: Users discover GitHub setup needs early
2. **Non-Intrusive**: Doesn't block deployment
3. **Helpful Guidance**: Clear instructions for setup
4. **Better UX**: Users know their status before deployment
5. **Encourages Best Practices**: Nudges users to set up tools repository access

## Future Enhancements

1. **Auto-Check on Tab Load**: Automatically check when Health tab opens
2. **Repository Access Test**: Test actual clone/pull operation
3. **Token Validation**: Check if PAT is valid (if using tokens)
4. **Multi-Repository Support**: Check access to multiple repos
5. **Setup Wizard**: Guided setup flow for GitHub authentication

## Security Considerations

1. **No Credential Storage**: Only checks authentication status
2. **Read-Only Checks**: Only verifies access, doesn't modify anything
3. **Local Only**: All checks run locally via GitHub CLI
4. **No Sensitive Data**: Doesn't expose tokens or keys

## Summary

This feature adds a helpful, non-blocking GitHub authentication check that:
- ✅ Verifies GitHub CLI installation
- ✅ Checks authentication status
- ✅ Tests repository access
- ✅ Provides clear setup instructions
- ✅ Does NOT block deployment
- ✅ Encourages best practices

The check acts as a **nudge** to help users discover if they need to set up GitHub authentication for tools repository access, without preventing them from deploying infrastructure.

