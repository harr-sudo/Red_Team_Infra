// Red Team Infrastructure Manager - Frontend JavaScript

const API_BASE = '/api';

// Tab Management
document.querySelectorAll('.tab-button').forEach(button => {
    button.addEventListener('click', () => {
        const tabName = button.getAttribute('data-tab');
        switchTab(tabName);
    });
});

function switchTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Remove active class from all buttons
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Show selected tab
    document.getElementById(tabName).classList.add('active');
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    
    // Load tab-specific data
    if (tabName === 'dashboard') {
        loadDashboard();
    } else if (tabName === 'status') {
        refreshStatus();
    }
}

function loadConfigTab() {
    switchTab('config');
    loadConfig();
}

function loadDeployTab() {
    switchTab('deploy');
    checkDeploymentStatus();
}

// Configuration Management
async function loadConfig() {
    try {
        const response = await fetch(`${API_BASE}/config/`);
        const data = await response.json();
        
        if (data.success) {
            const config = data.config;
            
            // Populate form fields
            document.getElementById('engagement-type').value = config.engagement_type || '';
            document.getElementById('project-name').value = config.project_name || '';
            document.getElementById('environment').value = config.environment || 'dev';
            document.getElementById('aws-region').value = config.aws_region || 'us-east-1';
            document.getElementById('key-pair-name').value = config.key_pair_name || '';
            document.getElementById('management-cidr').value = Array.isArray(config.management_cidr_blocks) 
                ? JSON.stringify(config.management_cidr_blocks) 
                : '["0.0.0.0/0"]';
            document.getElementById('c2-server-count').value = config.c2_server_count || 2;
            document.getElementById('c2-instance-type').value = config.c2_server_instance_type || 't3.medium';
            
            showMessage('Configuration loaded', 'success');
        }
    } catch (error) {
        showMessage('Error loading configuration: ' + error.message, 'error');
    }
}

function updateEngagementType() {
    const engagementType = document.getElementById('engagement-type').value;
    
    // Auto-configure based on engagement type
    if (engagementType === 'adhoc') {
        document.getElementById('c2-server-count').value = 1;
    } else if (engagementType === 'purple-team') {
        document.getElementById('c2-server-count').value = 2;
    } else if (engagementType === 'full-red-team') {
        document.getElementById('c2-server-count').value = 2; // Will be overridden by phases
    }
}

async function saveConfig() {
    try {
        // Build config object from form
        const config = {
            engagement_type: document.getElementById('engagement-type').value,
            project_name: document.getElementById('project-name').value,
            environment: document.getElementById('environment').value,
            aws_region: document.getElementById('aws-region').value,
            key_pair_name: document.getElementById('key-pair-name').value,
            management_cidr_blocks: JSON.parse(document.getElementById('management-cidr').value),
            c2_server_count: parseInt(document.getElementById('c2-server-count').value),
            c2_server_instance_type: document.getElementById('c2-instance-type').value
        };
        
        const response = await fetch(`${API_BASE}/config/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ config })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showMessage('Configuration saved successfully!', 'success');
        } else {
            showMessage('Error: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        showMessage('Error saving configuration: ' + error.message, 'error');
    }
}

async function validateConfig() {
    try {
        const config = {
            engagement_type: document.getElementById('engagement-type').value,
            project_name: document.getElementById('project-name').value,
            environment: document.getElementById('environment').value,
            aws_region: document.getElementById('aws-region').value,
            key_pair_name: document.getElementById('key-pair-name').value,
            management_cidr_blocks: JSON.parse(document.getElementById('management-cidr').value),
            c2_server_count: parseInt(document.getElementById('c2-server-count').value),
            c2_server_instance_type: document.getElementById('c2-instance-type').value
        };
        
        const response = await fetch(`${API_BASE}/config/validate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ config })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showMessage('Configuration is valid!', 'success');
        } else {
            const errors = data.errors || [data.error || 'Validation failed'];
            showMessage('Validation errors: ' + errors.join(', '), 'error');
        }
    } catch (error) {
        showMessage('Error validating configuration: ' + error.message, 'error');
    }
}

// Deployment Management
async function startDeployment() {
    if (!confirm('Are you sure you want to deploy the infrastructure?')) {
        return;
    }
    
    const statusDiv = document.getElementById('deployment-status');
    statusDiv.innerHTML = '<div class="spinner"></div>Starting deployment...';
    statusDiv.className = 'status-display info';
    
    try {
        const response = await fetch(`${API_BASE}/deploy/deploy`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            statusDiv.innerHTML = '<p>Deployment started. Checking status...</p>';
            // Poll for status
            pollDeploymentStatus();
        } else {
            statusDiv.innerHTML = '<p>Error: ' + (data.error || 'Unknown error') + '</p>';
            statusDiv.className = 'status-display error';
        }
    } catch (error) {
        statusDiv.innerHTML = '<p>Error: ' + error.message + '</p>';
        statusDiv.className = 'status-display error';
    }
}

async function checkDeploymentStatus() {
    pollDeploymentStatus();
}

function pollDeploymentStatus() {
    const statusDiv = document.getElementById('deployment-status');
    const outputDiv = document.getElementById('deployment-output');
    
    const interval = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE}/deploy/status`);
            const data = await response.json();
            
            if (data.success && data.status) {
                const status = data.status;
                
                statusDiv.innerHTML = `
                    <p><strong>Status:</strong> ${status.status}</p>
                    <p><strong>Step:</strong> ${status.step || 'N/A'}</p>
                `;
                
                if (status.status === 'running') {
                    statusDiv.className = 'status-display info';
                } else if (status.status === 'success') {
                    statusDiv.className = 'status-display success';
                    clearInterval(interval);
                    if (status.output) {
                        outputDiv.textContent = JSON.stringify(status.output, null, 2);
                    }
                } else if (status.status === 'error') {
                    statusDiv.className = 'status-display error';
                    statusDiv.innerHTML += '<p>Error: ' + (status.error || 'Unknown error') + '</p>';
                    clearInterval(interval);
                }
            }
        } catch (error) {
            console.error('Error checking status:', error);
        }
    }, 2000); // Poll every 2 seconds
}

async function runPlan() {
    const statusDiv = document.getElementById('deployment-status');
    statusDiv.innerHTML = '<div class="spinner"></div>Running Terraform plan...';
    statusDiv.className = 'status-display info';
    
    try {
        const response = await fetch(`${API_BASE}/deploy/plan`);
        const data = await response.json();
        
        const outputDiv = document.getElementById('deployment-output');
        if (data.success) {
            statusDiv.innerHTML = '<p>Plan completed successfully</p>';
            statusDiv.className = 'status-display success';
            outputDiv.textContent = data.stdout || 'No changes detected';
        } else {
            statusDiv.innerHTML = '<p>Plan failed</p>';
            statusDiv.className = 'status-display error';
            outputDiv.textContent = data.stderr || data.error || 'Unknown error';
        }
    } catch (error) {
        statusDiv.innerHTML = '<p>Error: ' + error.message + '</p>';
        statusDiv.className = 'status-display error';
    }
}

async function destroyInfrastructure() {
    const confirmText = prompt('Type "DESTROY" to confirm infrastructure destruction:');
    if (confirmText !== 'DESTROY') {
        return;
    }
    
    const statusDiv = document.getElementById('deployment-status');
    statusDiv.innerHTML = '<div class="spinner"></div>Destroying infrastructure...';
    statusDiv.className = 'status-display warning';
    
    try {
        const response = await fetch(`${API_BASE}/deploy/destroy`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ confirm: 'DESTROY' })
        });
        
        const data = await response.json();
        
        if (data.success) {
            statusDiv.innerHTML = '<p>Destruction started. Checking status...</p>';
            pollDeploymentStatus();
        } else {
            statusDiv.innerHTML = '<p>Error: ' + (data.error || 'Unknown error') + '</p>';
            statusDiv.className = 'status-display error';
        }
    } catch (error) {
        statusDiv.innerHTML = '<p>Error: ' + error.message + '</p>';
        statusDiv.className = 'status-display error';
    }
}

// Status Management
async function refreshStatus() {
    const statusDiv = document.getElementById('status-info');
    statusDiv.innerHTML = '<div class="spinner"></div>Loading status...';
    
    try {
        const response = await fetch(`${API_BASE}/status/`);
        const data = await response.json();
        
        if (data.success) {
            const status = data.status;
            let statusClass = 'info';
            let statusText = status;
            
            if (status === 'deployed') {
                statusClass = 'success';
                statusText = '✅ Infrastructure is deployed';
            } else if (status === 'configured') {
                statusClass = 'warning';
                statusText = '⚠️ Configuration exists but not deployed';
            } else {
                statusText = 'ℹ️ ' + statusText;
            }
            
            statusDiv.innerHTML = `
                <div class="status-display ${statusClass}">
                    <p><strong>Status:</strong> ${statusText}</p>
                    <p><strong>Config Exists:</strong> ${data.config_exists ? 'Yes' : 'No'}</p>
                    <p><strong>Terraform Initialized:</strong> ${data.terraform_initialized ? 'Yes' : 'No'}</p>
                    <p><strong>Infrastructure Deployed:</strong> ${data.infrastructure_deployed ? 'Yes' : 'No'}</p>
                </div>
            `;
            
            // Load outputs and resources
            loadOutputs();
            loadResources();
        }
    } catch (error) {
        statusDiv.innerHTML = '<p>Error: ' + error.message + '</p>';
    }
}

async function loadOutputs() {
    try {
        const response = await fetch(`${API_BASE}/status/outputs`);
        const data = await response.json();
        
        const outputsDiv = document.getElementById('status-outputs');
        if (data.success && data.outputs) {
            outputsDiv.textContent = JSON.stringify(data.outputs, null, 2);
        } else {
            outputsDiv.textContent = 'No outputs available';
        }
    } catch (error) {
        document.getElementById('status-outputs').textContent = 'Error loading outputs: ' + error.message;
    }
}

async function loadResources() {
    try {
        const response = await fetch(`${API_BASE}/status/resources`);
        const data = await response.json();
        
        const resourcesDiv = document.getElementById('status-resources');
        if (data.success && data.resources && data.resources.length > 0) {
            resourcesDiv.textContent = JSON.stringify(data.resources, null, 2);
        } else {
            resourcesDiv.textContent = 'No resources found';
        }
    } catch (error) {
        document.getElementById('status-resources').textContent = 'Error loading resources: ' + error.message;
    }
}

// Health Checks
async function checkPrerequisites() {
    const statusDiv = document.getElementById('prerequisites-status');
    statusDiv.innerHTML = '<div class="spinner"></div>Checking prerequisites...';
    
    try {
        const response = await fetch(`${API_BASE}/health/prerequisites`);
        const data = await response.json();
        
        if (data.success) {
            let html = '<div class="status-display ' + (data.all_installed ? 'success' : 'warning') + '">';
            html += '<p><strong>All Installed:</strong> ' + (data.all_installed ? 'Yes ✅' : 'No ❌') + '</p>';
            html += '<ul>';
            
            for (const [tool, info] of Object.entries(data.prerequisites)) {
                html += `<li><strong>${tool}:</strong> ${info.installed ? '✅ ' + info.version : '❌ Not installed'}</li>`;
            }
            
            html += '</ul></div>';
            statusDiv.innerHTML = html;
        }
    } catch (error) {
        statusDiv.innerHTML = '<p>Error: ' + error.message + '</p>';
    }
}

async function checkAWS() {
    const statusDiv = document.getElementById('aws-status');
    statusDiv.innerHTML = '<div class="spinner"></div>Checking AWS connectivity...';
    
    try {
        const response = await fetch(`${API_BASE}/health/aws`);
        const data = await response.json();
        
        if (data.success && data.authenticated) {
            statusDiv.innerHTML = `
                <div class="status-display success">
                    <p><strong>Status:</strong> ✅ Authenticated</p>
                    <p><strong>Account:</strong> ${data.account || 'N/A'}</p>
                    <p><strong>User:</strong> ${data.user || 'N/A'}</p>
                </div>
            `;
        } else {
            statusDiv.innerHTML = `
                <div class="status-display error">
                    <p><strong>Status:</strong> ❌ Not authenticated</p>
                    <p><strong>Error:</strong> ${data.error || 'Unknown error'}</p>
                </div>
            `;
        }
    } catch (error) {
        statusDiv.innerHTML = '<p>Error: ' + error.message + '</p>';
    }
}

async function runHealthCheck() {
    const statusDiv = document.getElementById('health-status');
    statusDiv.innerHTML = '<div class="spinner"></div>Running health check...';
    
    try {
        const response = await fetch(`${API_BASE}/health/check`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            statusDiv.innerHTML = `
                <div class="status-display success">
                    <p><strong>Health Check:</strong> ✅ Passed</p>
                    <pre>${data.stdout || ''}</pre>
                </div>
            `;
        } else {
            statusDiv.innerHTML = `
                <div class="status-display error">
                    <p><strong>Health Check:</strong> ❌ Failed</p>
                    <pre>${data.stderr || data.error || 'Unknown error'}</pre>
                </div>
            `;
        }
    } catch (error) {
        statusDiv.innerHTML = '<p>Error: ' + error.message + '</p>';
    }
}

// Dashboard
async function loadDashboard() {
    const statusDiv = document.getElementById('dashboard-status');
    statusDiv.innerHTML = '<div class="spinner"></div>Loading dashboard...';
    
    try {
        const response = await fetch(`${API_BASE}/status/`);
        const data = await response.json();
        
        if (data.success) {
            const status = data.status;
            let statusClass = 'info';
            let statusText = status;
            let actionText = 'Configure Infrastructure';
            
            if (status === 'deployed') {
                statusClass = 'success';
                statusText = '✅ Infrastructure is deployed and running';
                actionText = 'View Status';
            } else if (status === 'configured') {
                statusClass = 'warning';
                statusText = '⚠️ Configuration ready, not yet deployed';
                actionText = 'Deploy Infrastructure';
            } else {
                statusText = 'ℹ️ Infrastructure not configured';
            }
            
            statusDiv.innerHTML = `
                <div class="status-display ${statusClass}">
                    <p><strong>${statusText}</strong></p>
                    <p><strong>Configuration:</strong> ${data.config_exists ? '✅ Exists' : '❌ Missing'}</p>
                    <p><strong>Terraform:</strong> ${data.terraform_initialized ? '✅ Initialized' : '❌ Not initialized'}</p>
                    <p><strong>Deployed:</strong> ${data.infrastructure_deployed ? '✅ Yes' : '❌ No'}</p>
                </div>
            `;
        }
    } catch (error) {
        statusDiv.innerHTML = '<p>Error loading dashboard: ' + error.message + '</p>';
    }
}

// Utility Functions
function showMessage(message, type) {
    const messageDiv = document.getElementById('config-message');
    messageDiv.textContent = message;
    messageDiv.className = `message ${type} show`;
    
    setTimeout(() => {
        messageDiv.classList.remove('show');
    }, 5000);
}

// Permission Checking
async function checkPermissions() {
    const statusDiv = document.getElementById('permissions-status');
    statusDiv.innerHTML = '<div class="spinner"></div>Checking AWS permissions...';
    statusDiv.className = 'status-display info';
    
    try {
        const response = await fetch(`${API_BASE}/health/permissions`);
        const data = await response.json();
        
        if (data.success) {
            const overallStatus = data.overall_status || 'unknown';
            const missing = data.missing_permissions || [];
            const available = data.available_permissions || [];
            const categories = data.categories || {};
            const method = data.method || 'unknown';
            
            let statusClass = 'info';
            let statusIcon = 'ℹ️';
            let statusText = 'Checking permissions...';
            
            if (overallStatus === 'complete') {
                statusClass = 'success';
                statusIcon = '✅';
                statusText = 'All required permissions are available';
            } else if (overallStatus === 'missing') {
                statusClass = 'error';
                statusIcon = '❌';
                statusText = 'Missing required permissions';
            } else if (overallStatus === 'partial') {
                statusClass = 'warning';
                statusIcon = '⚠️';
                statusText = 'Some permissions may be missing';
            }
            
            let html = `
                <div class="status-display ${statusClass}">
                    <p><strong>${statusIcon} Overall Status:</strong> ${statusText}</p>
                    <p><strong>Method:</strong> ${method === 'policy_simulation' ? 'Policy Simulation (Accurate)' : 'Simple Check (Best Effort)'}</p>
                    <p><strong>Available Permissions:</strong> ${available.length}</p>
                    <p><strong>Missing Permissions:</strong> ${missing.length}</p>
            `;
            
            if (data.warning) {
                html += `<p><strong>Note:</strong> ${data.warning}</p>`;
            }
            
            // Show categories
            html += '<h4>Permission Categories:</h4><ul>';
            for (const [category, info] of Object.entries(categories)) {
                const catStatus = info.status || (info.required ? 'complete' : 'missing');
                const catIcon = catStatus === 'complete' ? '✅' : (catStatus === 'partial' ? '⚠️' : '❌');
                html += `<li>${catIcon} <strong>${category}:</strong> ${catStatus}</li>`;
            }
            html += '</ul>';
            
            // Show missing permissions if any
            if (missing.length > 0) {
                html += '<h4>Missing Permissions:</h4><ul>';
                missing.slice(0, 20).forEach(perm => {
                    html += `<li><code>${perm}</code></li>`;
                });
                if (missing.length > 20) {
                    html += `<li><em>... and ${missing.length - 20} more</em></li>`;
                }
                html += '</ul>';
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

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
    checkPrerequisites();
});

