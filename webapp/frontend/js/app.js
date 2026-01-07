// Red Team Infrastructure Manager - Frontend JavaScript
// Complete redesign with robust tab system

const API_BASE = '/api';

// ============================================================================
// APPLICATION CORE - Tab Management System
// ============================================================================

const APP = {
    currentPage: 'dashboard',
    pages: ['dashboard', 'configuration', 'deployment', 'deployments', 'aws-check', 'settings'],
    
    /**
     * Initialize the application
     */
    init() {
        console.log('🚀 Initializing Red Team Infrastructure Manager...');
        
        // Setup tab navigation
        this.setupNavigation();
        
        // Load initial page
        this.navigateTo('dashboard');
        
        // Setup event handlers
        this.setupEventHandlers();
        
        console.log('✅ Application initialized successfully');
    },
    
    /**
     * Setup navigation click handlers
     */
    setupNavigation() {
        const navButtons = document.querySelectorAll('.tab-btn');
        navButtons.forEach(btn => {
            const target = btn.getAttribute('data-target');
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                console.log(`Navigation clicked: ${target}`);
                this.navigateTo(target);
            });
        });
    },
    
    /**
     * Navigate to a specific page
     * @param {string} pageName - The page to navigate to
     */
    navigateTo(pageName) {
        console.log(`📄 Navigating to: ${pageName}`);
        
        // Validate page exists
        if (!this.pages.includes(pageName)) {
            console.error(`❌ Page "${pageName}" does not exist!`);
            return;
        }
        
        // Hide all pages
        const allPages = document.querySelectorAll('.tab-page');
        allPages.forEach(page => {
            page.classList.remove('active');
            page.style.display = 'none';
        });
        
        // Remove active class from all nav buttons
        const allButtons = document.querySelectorAll('.tab-btn');
        allButtons.forEach(btn => {
            btn.classList.remove('active');
        });
        
        // Show target page
        const targetPage = document.querySelector(`.tab-page[data-page="${pageName}"]`);
        if (targetPage) {
            targetPage.classList.add('active');
            targetPage.style.display = 'block';
            console.log(`✅ Page "${pageName}" displayed`);
        } else {
            console.error(`❌ Page element for "${pageName}" not found!`);
            return;
        }
        
        // Activate corresponding nav button
        const targetButton = document.querySelector(`.tab-btn[data-target="${pageName}"]`);
        if (targetButton) {
            targetButton.classList.add('active');
        }
        
        // Update current page
        this.currentPage = pageName;
        
        // Load page-specific content
        this.loadPageContent(pageName);
    },
    
    /**
     * Load page-specific content and initialize page
     * @param {string} pageName - The page to load content for
     */
    loadPageContent(pageName) {
        console.log(`📦 Loading content for: ${pageName}`);
        
        try {
            switch(pageName) {
                case 'dashboard':
                    loadDashboard();
                    break;
                case 'configuration':
                    loadConfig();
                    break;
                case 'deployment':
                    checkDeploymentStatus();
                    checkDomainConfig();
                    checkCobaltStrikeFile();
                    break;
                case 'deployments':
                    loadDeploymentsPage();
                    break;
                case 'aws-check':
                    // AWS page is interactive, no auto-load
                    console.log('AWS Check page ready');
                    break;
                case 'settings':
                    // Settings page is static for now
                    console.log('Settings page ready');
                    break;
                default:
                    console.log(`No specific loader for: ${pageName}`);
            }
        } catch (error) {
            console.error(`Error loading content for ${pageName}:`, error);
        }
    },
    
    /**
     * Setup event handlers for forms and buttons
     */
    setupEventHandlers() {
        // File upload form
        const uploadForm = document.getElementById('upload-cs-form');
        if (uploadForm) {
            uploadForm.addEventListener('submit', handleFileUpload);
        }
        
        // Delete file button
        const deleteBtn = document.getElementById('delete-file-btn');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', handleFileDelete);
        }
    }
};

// ============================================================================
// PAGE LOADERS
// ============================================================================

/**
 * Load Dashboard content
 */
async function loadDashboard() {
    console.log('Loading Dashboard...');
    const statusDiv = document.getElementById('dashboard-status');
    if (!statusDiv) return;
    
    statusDiv.innerHTML = '<div class="spinner"></div>Loading dashboard...';
    
    try {
        statusDiv.innerHTML = `
            <div class="status-display info">
                <p><strong>Welcome to Red Team Infrastructure Manager</strong></p>
                <p>Use the Configuration tab to set up your infrastructure, then deploy from the Deploy tab.</p>
                <p style="margin-top: 10px;"><strong>Quick Start:</strong></p>
                <ul style="margin-left: 20px;">
                    <li>Verify AWS credentials and permissions in Pre Reqs tab</li>
                    <li>Set up your infrastructure parameters in Configuration</li>
                    <li>Upload Cobalt Strike and deploy from the Deploy tab</li>
                </ul>
            </div>
        `;
    } catch (error) {
        statusDiv.innerHTML = '<p>Error loading dashboard: ' + error.message + '</p>';
    }
}

/**
 * Load Configuration
 */
async function loadConfig() {
    console.log('Loading Configuration...');
    try {
        const response = await fetch(`${API_BASE}/config/`);
        const data = await response.json();
        
        if (data.success) {
            const config = data.config;
            
            // Convert CIDR array to comma-separated string for display
            let cidrDisplay = '';
            if (Array.isArray(config.management_cidr_blocks)) {
                cidrDisplay = config.management_cidr_blocks.join(', ');
            }
            
            // Convert backup domains array to comma-separated string
            let backupDomainsDisplay = '';
            if (Array.isArray(config.backup_domains)) {
                backupDomainsDisplay = config.backup_domains
                    .map(d => typeof d === 'object' ? d.domain_name : d)
                    .filter(d => d)
                    .join(', ');
            }
            
            // Populate form fields
            const fields = {
                'engagement-type': config.engagement_type || '',
                'project-name': config.project_name || '',
                'environment': config.environment || 'dev',
                'aws-region': config.aws_region || 'us-east-1',
                'key-pair-name': config.key_pair_name || '',
                'management-cidr': cidrDisplay,
                'primary-domain': config.primary_domain_name || '',
                'backup-domains': backupDomainsDisplay,
                'c2-subdomain': config.c2_subdomain || 'c2',
                'www-subdomain': config.www_subdomain || 'www',
                'cdn-subdomain': config.cdn_subdomain || 'cdn',
                'c2-server-count': config.c2_server_count || 2,
                'c2-instance-type': config.c2_server_instance_type || 't3.medium'
            };
            
            Object.entries(fields).forEach(([id, value]) => {
                const element = document.getElementById(id);
                if (element) element.value = value;
            });
            
            // Update the deployment overview based on loaded engagement type
            updateEngagementType();
            
            showMessage('Configuration loaded', 'success');
        }
    } catch (error) {
        console.error('Error loading configuration:', error);
        showMessage('Error loading configuration: ' + error.message, 'error');
    }
}

// ============================================================================
// CONFIGURATION FUNCTIONS
// ============================================================================

/**
 * Parse CIDR input - supports comma-separated values
 * @param {string} input - User input (comma-separated CIDR blocks)
 * @returns {string[]} Array of CIDR blocks
 */
function parseCidrInput(input) {
    if (!input || !input.trim()) {
        return [];
    }
    
    // Split by comma, trim whitespace, filter empty strings
    return input
        .split(',')
        .map(cidr => cidr.trim())
        .filter(cidr => cidr.length > 0);
}

function updateEngagementType() {
    const engagementType = document.getElementById('engagement-type').value;
    const serverCountInput = document.getElementById('c2-server-count');
    const serverCountGroup = document.getElementById('c2-server-count-group');
    const instanceTypeGroup = document.getElementById('c2-instance-type-group');
    const overviewDiv = document.getElementById('deployment-overview');
    const overviewTitle = document.getElementById('overview-title');
    const overviewContent = document.getElementById('overview-content');
    const overviewDetails = document.getElementById('overview-details');
    
    // Engagement type configurations
    const engagementConfigs = {
        'adhoc': {
            title: 'Adhoc Deployment',
            color: 'linear-gradient(135deg, #0d7377 0%, #14a085 100%)',
            serverCount: 1,
            serverCountEditable: false,
            instanceTypeEditable: true,
            mode: 'Single',
            components: [
                { icon: '🎯', label: 'C2 Server', value: '1' },
                { icon: '🔀', label: 'Redirectors', value: '2' },
                { icon: '🖥️', label: 'Bastion', value: '1' },
                { icon: '💰', label: 'Est. Cost', value: '~$105/mo' }
            ],
            details: 'Quick, minimal setup for one-off tests and proof-of-concepts. Single C2 server with standard proxy infrastructure.',
            bestFor: 'Quick security tests, POCs, training exercises',
            costBreakdown: '1× C2 (t3.medium ~$30) + 2× Redirector (t3.small ~$30) + 1× Bastion Windows (~$45)'
        },
        'purple-team': {
            title: 'Purple Team Deployment',
            color: 'linear-gradient(135deg, #4a4e8c 0%, #6b5b95 100%)',
            serverCount: 2,
            serverCountEditable: true,
            instanceTypeEditable: true,
            mode: 'Redundancy',
            components: [
                { icon: '🎯', label: 'C2 Servers', value: '2+' },
                { icon: '🔀', label: 'Redirectors', value: '2' },
                { icon: '🖥️', label: 'Bastion', value: '1' },
                { icon: '💰', label: 'Est. Cost', value: '~$135/mo' }
            ],
            details: 'Redundant C2 infrastructure for collaborative purple team exercises. High availability with multiple C2 servers.',
            bestFor: 'Purple team exercises, collaborative testing, controlled scenarios',
            costBreakdown: '2× C2 (t3.medium ~$60) + 2× Redirector (t3.small ~$30) + 1× Bastion Windows (~$45)'
        },
        'full-red-team': {
            title: 'Full Red Team Deployment',
            color: 'linear-gradient(135deg, #b91c1c 0%, #991b1b 100%)',
            serverCount: 3,
            serverCountEditable: false,
            instanceTypeEditable: false,
            mode: 'Phases',
            components: [
                { icon: '🎯', label: 'C2 Servers', value: '3' },
                { icon: '🔀', label: 'Redirectors', value: '2' },
                { icon: '🖥️', label: 'Bastion', value: '1' },
                { icon: '💰', label: 'Est. Cost', value: '~$165/mo' }
            ],
            details: 'Phase-based distributed C2 infrastructure: Staging → Post-Exploitation → Long-Haul. Each phase has dedicated infrastructure.',
            phases: ['🚀 Staging Server', '⚡ Post-Ex Server', '🔒 Long-Haul Server'],
            bestFor: 'Full red team engagements, distributed operations, long-term campaigns',
            costBreakdown: '3× C2 (t3.medium ~$90) + 2× Redirector (t3.small ~$30) + 1× Bastion Windows (~$45)'
        }
    };
    
    const config = engagementConfigs[engagementType];
    
    if (config) {
        // Update server count
        serverCountInput.value = config.serverCount;
        
        // Enable/disable server count based on engagement type
        serverCountInput.disabled = !config.serverCountEditable;
        if (serverCountGroup) {
            serverCountGroup.style.opacity = config.serverCountEditable ? '1' : '0.6';
        }
        
        // Enable/disable instance type based on engagement type
        const instanceTypeSelect = document.getElementById('c2-instance-type');
        if (instanceTypeSelect) {
            instanceTypeSelect.disabled = !config.instanceTypeEditable;
        }
        if (instanceTypeGroup) {
            instanceTypeGroup.style.opacity = config.instanceTypeEditable ? '1' : '0.6';
        }
        
        // Show and populate overview
        overviewDiv.style.display = 'block';
        overviewDiv.style.background = config.color;
        overviewTitle.textContent = config.title;
        
        // Build components grid
        overviewContent.innerHTML = config.components.map(comp => `
            <div style="background: rgba(255,255,255,0.15); padding: 12px; border-radius: 6px; text-align: center;">
                <div style="font-size: 1.5em;">${comp.icon}</div>
                <div style="font-size: 1.3em; font-weight: bold; margin: 5px 0;">${comp.value}</div>
                <div style="font-size: 0.85em; opacity: 0.9;">${comp.label}</div>
            </div>
        `).join('');
        
        // Build details section
        let detailsHtml = `
            <div style="margin-bottom: 10px;">
                <strong>Mode:</strong> ${config.mode} &nbsp;|&nbsp; <strong>Best for:</strong> ${config.bestFor}
            </div>
            <div style="opacity: 0.9;">${config.details}</div>
            ${config.costBreakdown ? `
            <div style="margin-top: 10px; font-size: 0.85em; opacity: 0.8;">
                <strong>💵 Cost breakdown (24/7 on-demand):</strong> ${config.costBreakdown}
            </div>
            ` : ''}
        `;
        
        // Add phases for full-red-team
        if (config.phases) {
            detailsHtml += `
                <div style="margin-top: 12px; display: flex; gap: 10px; flex-wrap: wrap;">
                    ${config.phases.map(phase => `
                        <span style="background: rgba(255,255,255,0.2); padding: 5px 12px; border-radius: 15px; font-size: 0.85em;">
                            ${phase}
                        </span>
                    `).join('')}
                </div>
            `;
        }
        
        overviewDetails.innerHTML = detailsHtml;
        
    } else {
        // No engagement type selected - hide overview and enable all fields
        overviewDiv.style.display = 'none';
        
        // Re-enable fields
        serverCountInput.disabled = false;
        if (serverCountGroup) serverCountGroup.style.opacity = '1';
        
        const instanceTypeSelect = document.getElementById('c2-instance-type');
        if (instanceTypeSelect) instanceTypeSelect.disabled = false;
        if (instanceTypeGroup) instanceTypeGroup.style.opacity = '1';
    }
}

async function saveConfig() {
    console.log('Saving configuration...');
    try {
        const cidrInput = document.getElementById('management-cidr').value;
        const cidrBlocks = parseCidrInput(cidrInput);
        
        if (cidrBlocks.length === 0) {
            showMessage('Error: Please enter at least one Management CIDR block', 'error');
            return;
        }
        
        // Parse backup domains
        const backupDomainsInput = document.getElementById('backup-domains').value;
        const backupDomains = backupDomainsInput
            .split(',')
            .map(d => d.trim())
            .filter(d => d.length > 0)
            .map(d => ({ domain_name: d, hosted_zone_id: '' }));
        
        const config = {
            engagement_type: document.getElementById('engagement-type').value,
            project_name: document.getElementById('project-name').value,
            environment: document.getElementById('environment').value,
            aws_region: document.getElementById('aws-region').value,
            key_pair_name: document.getElementById('key-pair-name').value,
            management_cidr_blocks: cidrBlocks,
            primary_domain_name: document.getElementById('primary-domain').value.trim(),
            backup_domains: backupDomains,
            c2_subdomain: document.getElementById('c2-subdomain').value.trim() || 'c2',
            www_subdomain: document.getElementById('www-subdomain').value.trim() || 'www',
            cdn_subdomain: document.getElementById('cdn-subdomain').value.trim() || 'cdn',
            c2_server_count: parseInt(document.getElementById('c2-server-count').value),
            c2_server_instance_type: document.getElementById('c2-instance-type').value
        };
        
        const response = await fetch(`${API_BASE}/config/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
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
    console.log('Validating configuration...');
    try {
        const cidrInput = document.getElementById('management-cidr').value;
        const cidrBlocks = parseCidrInput(cidrInput);
        
        if (cidrBlocks.length === 0) {
            showMessage('Validation error: Please enter at least one Management CIDR block', 'error');
            return;
        }
        
        // Parse backup domains
        const backupDomainsInput = document.getElementById('backup-domains').value;
        const backupDomains = backupDomainsInput
            .split(',')
            .map(d => d.trim())
            .filter(d => d.length > 0)
            .map(d => ({ domain_name: d, hosted_zone_id: '' }));
        
        const config = {
            engagement_type: document.getElementById('engagement-type').value,
            project_name: document.getElementById('project-name').value,
            environment: document.getElementById('environment').value,
            aws_region: document.getElementById('aws-region').value,
            key_pair_name: document.getElementById('key-pair-name').value,
            management_cidr_blocks: cidrBlocks,
            primary_domain_name: document.getElementById('primary-domain').value.trim(),
            backup_domains: backupDomains,
            c2_subdomain: document.getElementById('c2-subdomain').value.trim() || 'c2',
            www_subdomain: document.getElementById('www-subdomain').value.trim() || 'www',
            cdn_subdomain: document.getElementById('cdn-subdomain').value.trim() || 'cdn',
            c2_server_count: parseInt(document.getElementById('c2-server-count').value),
            c2_server_instance_type: document.getElementById('c2-instance-type').value
        };
        
        const response = await fetch(`${API_BASE}/config/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
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

// ============================================================================
// DEPLOYMENT FUNCTIONS
// ============================================================================

let deploymentPollInterval = null;

async function checkDeploymentStatus() {
    pollDeploymentStatus();
}

function pollDeploymentStatus() {
    const statusDiv = document.getElementById('deployment-status');
    const outputDiv = document.getElementById('deployment-output');
    
    if (!statusDiv) return;
    
    // Clear existing interval
    if (deploymentPollInterval) {
        clearInterval(deploymentPollInterval);
        deploymentPollInterval = null;
    }
    
    deploymentPollInterval = setInterval(async () => {
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
                    clearInterval(deploymentPollInterval);
                    deploymentPollInterval = null;
                    if (status.output && outputDiv) {
                        outputDiv.textContent = JSON.stringify(status.output, null, 2);
                    }
                } else if (status.status === 'error') {
                    statusDiv.className = 'status-display error';
                    statusDiv.innerHTML += '<p>Error: ' + (status.error || 'Unknown error') + '</p>';
                    clearInterval(deploymentPollInterval);
                    deploymentPollInterval = null;
                }
            }
        } catch (error) {
            console.error('Error checking status:', error);
        }
    }, 2000);
}

async function checkDomainConfig() {
    const statusDiv = document.getElementById('domain-status');
    const domainInfoDiv = document.getElementById('domain-info');
    const domainDetails = document.getElementById('domain-details');
    const deployBtn = document.getElementById('deploy-btn');
    const warningDiv = document.getElementById('deployment-prereq-warning');
    
    if (!statusDiv) return;
    
    try {
        const response = await fetch(`${API_BASE}/health/domain-config`);
        const data = await response.json();
        
        if (data.success) {
            if (data.configured) {
                const domain = data.domain_info;
                statusDiv.innerHTML = `
                    <div class="status-display success">
                        <p><strong>✅ Domain Configured:</strong> ${domain.primary_domain}</p>
                    </div>
                `;
                if (domainInfoDiv) domainInfoDiv.style.display = 'block';
                if (domainDetails) {
                    domainDetails.innerHTML = `
                        <strong>Primary Domain:</strong> ${domain.primary_domain}<br>
                        <strong>C2 Subdomain:</strong> ${domain.c2_subdomain}.${domain.primary_domain}<br>
                        <strong>WWW Subdomain:</strong> ${domain.www_subdomain}.${domain.primary_domain}<br>
                        <strong>CDN Subdomain:</strong> ${domain.cdn_subdomain}.${domain.primary_domain}<br>
                        <strong>Backup Domains:</strong> ${domain.backup_domains && domain.backup_domains.length > 0 ? domain.backup_domains.length : '0'} configured
                    `;
                }
            } else {
                statusDiv.innerHTML = `
                    <div class="status-display warning">
                        <p><strong>⚠️ Domain Not Configured</strong></p>
                        <p>Please configure primary_domain_name in the Configuration tab before deployment.</p>
                    </div>
                `;
                if (domainInfoDiv) domainInfoDiv.style.display = 'none';
                if (deployBtn) {
                    deployBtn.disabled = true;
                    deployBtn.style.opacity = '0.5';
                }
            }
        }
    } catch (error) {
        statusDiv.innerHTML = `<p>Error checking domain config: ${error.message}</p>`;
    }
}

async function checkCobaltStrikeFile() {
    const statusDiv = document.getElementById('cs-file-status');
    const fileInfoDiv = document.getElementById('cs-file-info');
    const fileDetails = document.getElementById('file-details');
    const deployBtn = document.getElementById('deploy-btn');
    const warningDiv = document.getElementById('deployment-prereq-warning');
    
    if (!statusDiv) return;
    
    try {
        const response = await fetch(`${API_BASE}/deploy/cobalt-strike-file`);
        const data = await response.json();
        
        if (data.success) {
            if (data.has_file && data.latest_file) {
                const file = data.latest_file;
                statusDiv.innerHTML = `
                    <div class="status-display success">
                        <p><strong>✅ File Uploaded:</strong> ${file.filename}</p>
                        <p><strong>Size:</strong> ${file.size_mb} MB</p>
                    </div>
                `;
                if (fileInfoDiv) {
                    fileInfoDiv.style.display = 'block';
                    if (fileDetails) {
                        fileDetails.innerHTML = `
                            <strong>Filename:</strong> ${file.filename}<br>
                            <strong>Size:</strong> ${file.size_mb} MB<br>
                            <strong>Path:</strong> ${file.path}
                        `;
                    }
                }
            } else {
                statusDiv.innerHTML = `
                    <div class="status-display warning">
                        <p><strong>⚠️ No file uploaded</strong></p>
                        <p>Please upload Cobalt Strike archive before deployment.</p>
                    </div>
                `;
                if (fileInfoDiv) fileInfoDiv.style.display = 'none';
            }
            
            // Check both prerequisites
            const domainCheck = await fetch(`${API_BASE}/health/domain-config`);
            const domainData = await domainCheck.json();
            const hasDomain = domainData.success && domainData.configured;
            
            if (deployBtn) {
                if (data.has_file && hasDomain) {
                    deployBtn.disabled = false;
                    deployBtn.style.opacity = '1';
                } else {
                    deployBtn.disabled = true;
                    deployBtn.style.opacity = '0.5';
                }
            }
            
            if (warningDiv) {
                const missing = [];
                if (!data.has_file) missing.push('Cobalt Strike file');
                if (!hasDomain) missing.push('Domain configuration');
                
                if (missing.length > 0) {
                    warningDiv.style.display = 'block';
                    warningDiv.innerHTML = `<p><strong>⚠️ Prerequisites Missing:</strong> ${missing.join(' and ')} required before deployment.</p>`;
                } else {
                    warningDiv.style.display = 'none';
                }
            }
        }
    } catch (error) {
        statusDiv.innerHTML = `<p>Error checking file: ${error.message}</p>`;
    }
}

async function handleFileUpload(e) {
    e.preventDefault();
    
    const fileInput = document.getElementById('cs-file-input');
    const uploadBtn = document.getElementById('upload-btn');
    const progressDiv = document.getElementById('upload-progress');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');
    const statusDiv = document.getElementById('cs-file-status');
    
    if (!fileInput.files[0]) {
        alert('Please select a file');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    
    uploadBtn.disabled = true;
    progressDiv.style.display = 'block';
    progressFill.style.width = '0%';
    progressText.textContent = 'Uploading...';
    
    try {
        const xhr = new XMLHttpRequest();
        
        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percentComplete = (e.loaded / e.total) * 100;
                progressFill.style.width = percentComplete + '%';
                progressText.textContent = `Uploading... ${Math.round(percentComplete)}%`;
            }
        });
        
        xhr.addEventListener('load', () => {
            if (xhr.status === 200) {
                const data = JSON.parse(xhr.responseText);
                if (data.success) {
                    progressFill.style.width = '100%';
                    progressText.textContent = 'Upload complete!';
                    setTimeout(() => {
                        progressDiv.style.display = 'none';
                        checkCobaltStrikeFile();
                    }, 1000);
                } else {
                    statusDiv.innerHTML = `<p>Error: ${data.error || 'Upload failed'}</p>`;
                    progressDiv.style.display = 'none';
                }
            } else {
                statusDiv.innerHTML = `<p>Error: Upload failed (${xhr.status})</p>`;
                progressDiv.style.display = 'none';
            }
            uploadBtn.disabled = false;
        });
        
        xhr.addEventListener('error', () => {
            statusDiv.innerHTML = '<p>Error: Upload failed</p>';
            progressDiv.style.display = 'none';
            uploadBtn.disabled = false;
        });
        
        xhr.open('POST', `${API_BASE}/deploy/upload-cobalt-strike`);
        xhr.send(formData);
        
    } catch (error) {
        statusDiv.innerHTML = `<p>Error: ${error.message}</p>`;
        progressDiv.style.display = 'none';
        uploadBtn.disabled = false;
    }
}

async function handleFileDelete() {
    if (!confirm('Are you sure you want to delete the uploaded file?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/deploy/cobalt-strike-file`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: 'latest' })
        });
        
        const data = await response.json();
        if (data.success) {
            checkCobaltStrikeFile();
        } else {
            alert('Error deleting file: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

async function startDeployment() {
    const fileCheck = await fetch(`${API_BASE}/health/cobalt-strike-file`);
    const fileData = await fileCheck.json();
    
    const domainCheck = await fetch(`${API_BASE}/health/domain-config`);
    const domainData = await domainCheck.json();
    
    const missing = [];
    if (!fileData.success || !fileData.has_file) {
        missing.push('Cobalt Strike file');
    }
    if (!domainData.success || !domainData.configured) {
        missing.push('Domain configuration');
    }
    
    if (missing.length > 0) {
        alert(`⚠️ Prerequisites missing!\n\nPlease complete:\n- ${missing.join('\n- ')}`);
        return;
    }
    
    if (!confirm('Are you sure you want to deploy the infrastructure?')) {
        return;
    }
    
    const statusDiv = document.getElementById('deployment-status');
    statusDiv.innerHTML = '<div class="spinner"></div>Starting deployment...';
    statusDiv.className = 'status-display info';
    
    try {
        const response = await fetch(`${API_BASE}/deploy/deploy`, { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            statusDiv.innerHTML = '<p>Deployment started. Checking status...</p>';
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
            if (outputDiv) outputDiv.textContent = data.stdout || 'No changes detected';
        } else {
            statusDiv.innerHTML = '<p>Plan failed</p>';
            statusDiv.className = 'status-display error';
            if (outputDiv) outputDiv.textContent = data.stderr || data.error || 'Unknown error';
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
            headers: { 'Content-Type': 'application/json' },
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

// ============================================================================
// AWS CHECK FUNCTIONS
// ============================================================================

async function checkAWSCredentials() {
    const statusDiv = document.getElementById('aws-credentials-status');
    if (!statusDiv) return;
    
    statusDiv.innerHTML = '<div class="spinner"></div>Checking AWS credentials...';
    statusDiv.className = 'status-display info';
    
    try {
        const response = await fetch(`${API_BASE}/aws/credentials`);
        const data = await response.json();
        
        if (data.success && data.authenticated) {
            let html = `
                <div class="status-display success">
                    <p><strong>✅ ${data.message || 'AWS credentials are valid'}</strong></p>
                    <div style="margin-top: 15px; padding: 15px; background: white; border-radius: 5px;">
                        <p><strong>Account ID:</strong> <code style="background: #f5f5f5; padding: 3px 6px; border-radius: 3px;">${data.account || 'N/A'}</code></p>
                        <p><strong>User ARN:</strong> <code style="background: #f5f5f5; padding: 3px 6px; border-radius: 3px; font-size: 0.9em; word-break: break-all;">${data.user || 'N/A'}</code></p>
                        ${data.user_id ? `<p><strong>User ID:</strong> <code style="background: #f5f5f5; padding: 3px 6px; border-radius: 3px;">${data.user_id}</code></p>` : ''}
                    </div>
                </div>
            `;
            statusDiv.innerHTML = html;
        } else {
            let html = `
                <div class="status-display error">
                    <p><strong>❌ ${data.message || 'AWS credentials are not configured or invalid'}</strong></p>
                    ${data.error ? `<p><strong>Error:</strong> ${data.error}</p>` : ''}
                    <div style="margin-top: 15px; padding: 15px; background: #fff3cd; border-radius: 5px; border-left: 4px solid #ffc107;">
                        <p><strong>How to fix:</strong></p>
                        <p>Run: <code style="background: #f5f5f5; padding: 5px;">aws configure</code></p>
                    </div>
                </div>
            `;
            statusDiv.innerHTML = html;
        }
    } catch (error) {
        statusDiv.innerHTML = `<div class="status-display error"><p><strong>Error:</strong> ${error.message}</p></div>`;
    }
}

async function checkGitHubCLI() {
    const statusDiv = document.getElementById('github-cli-status');
    if (!statusDiv) return;
    
    statusDiv.innerHTML = '<div class="spinner"></div>Checking GitHub CLI authentication and repo access...';
    statusDiv.className = 'status-display info';
    
    try {
        const response = await fetch(`${API_BASE}/aws/github-cli`);
        const data = await response.json();
        
        if (data.success && data.authenticated) {
            if (data.has_repo_access) {
                // Fully authenticated with repo access
                let html = `
                    <div class="status-display success">
                        <p><strong>✅ ${data.message || 'GitHub CLI authenticated with repo access'}</strong></p>
                        <div style="margin-top: 15px; padding: 15px; background: white; border-radius: 5px;">
                            ${data.username ? `<p><strong>Logged in as:</strong> <code style="background: #f5f5f5; padding: 3px 6px; border-radius: 3px;">@${data.username}</code></p>` : ''}
                            ${data.account_type ? `<p><strong>Auth Type:</strong> <code style="background: #f5f5f5; padding: 3px 6px; border-radius: 3px;">${data.account_type}</code></p>` : ''}
                            <p style="margin-top: 10px;"><strong>✅ Tools Repository Access:</strong> <span style="color: #4CAF50;">Confirmed</span></p>
                            ${data.repo_visibility ? `<p><strong>Repo Visibility:</strong> <code style="background: #f5f5f5; padding: 3px 6px; border-radius: 3px;">${data.repo_visibility}</code></p>` : ''}
                            <p style="margin-top: 10px;"><a href="${data.tools_repo}" target="_blank" style="color: #9c27b0;">${data.tools_repo}</a></p>
                        </div>
                    </div>
                `;
                statusDiv.innerHTML = html;
            } else {
                // Authenticated but no repo access
                const accessInfo = data.access_request_info || {};
                let html = `
                    <div class="status-display warning">
                        <p><strong>⚠️ GitHub CLI authenticated but NO access to tools repository</strong></p>
                        <div style="margin-top: 15px; padding: 15px; background: white; border-radius: 5px;">
                            ${data.username ? `<p><strong>Logged in as:</strong> <code style="background: #f5f5f5; padding: 3px 6px; border-radius: 3px;">@${data.username}</code></p>` : ''}
                            <p style="margin-top: 10px;"><strong>❌ Tools Repository Access:</strong> <span style="color: #f44336;">Denied</span></p>
                        </div>
                        <div style="margin-top: 15px; padding: 15px; background: #fff3cd; border-radius: 5px; border-left: 4px solid #ffc107;">
                            <p><strong>🔐 Access Required</strong></p>
                            <p style="margin-top: 10px;">The tools repository is private. To get access:</p>
                            <ol style="margin-left: 20px; margin-top: 10px;">
                                <li><strong>Contact Harris</strong> and request access to the repository</li>
                                <li>Provide your GitHub username: <code style="background: #f5f5f5; padding: 3px 6px; border-radius: 3px;">@${data.username || 'your-username'}</code></li>
                                <li>Once granted, click "Check GitHub CLI" again to verify</li>
                            </ol>
                            <p style="margin-top: 15px;"><strong>Repository:</strong> <a href="${data.tools_repo}" target="_blank" style="color: #9c27b0;">${data.tools_repo}</a></p>
                        </div>
                    </div>
                `;
                statusDiv.innerHTML = html;
            }
        } else {
            // Not authenticated at all
            let html = `
                <div class="status-display error">
                    <p><strong>❌ ${data.message || 'GitHub CLI is not authenticated'}</strong></p>
                    ${data.error ? `<p><strong>Error:</strong> ${data.error}</p>` : ''}
                    <div style="margin-top: 15px; padding: 15px; background: #fff3cd; border-radius: 5px; border-left: 4px solid #ffc107;">
                        <p><strong>How to fix:</strong></p>
                        <p>1. Install GitHub CLI: <a href="https://cli.github.com/" target="_blank">https://cli.github.com/</a></p>
                        <p>2. Run: <code style="background: #f5f5f5; padding: 5px;">gh auth login</code></p>
                        <p style="margin-top: 10px;"><strong>Required for:</strong> Accessing the private tools repository at <a href="${data.tools_repo || 'https://github.com/harr-sudo/red-team-tools'}" target="_blank" style="color: #9c27b0;">${data.tools_repo || 'https://github.com/harr-sudo/red-team-tools'}</a></p>
                    </div>
                </div>
            `;
            statusDiv.innerHTML = html;
        }
    } catch (error) {
        statusDiv.innerHTML = `<div class="status-display error"><p><strong>Error:</strong> ${error.message}</p></div>`;
    }
}

async function checkAWSPermissions() {
    const statusDiv = document.getElementById('aws-permissions-status');
    if (!statusDiv) return;
    
    statusDiv.innerHTML = '<div class="spinner"></div>Checking AWS permissions...';
    statusDiv.className = 'status-display info';
    
    try {
        const response = await fetch(`${API_BASE}/aws/permissions`);
        const data = await response.json();
        
        if (data.success) {
            const status = data.status || 'unknown';
            const statusClass = status === 'sufficient' ? 'success' : (status === 'insufficient' ? 'error' : 'warning');
            
            let html = `
                <div class="status-display ${statusClass}">
                    <p><strong>${data.status_icon || '📊'} ${data.status_text || 'Checking permissions...'}</strong></p>
                    <p><strong>Method:</strong> ${data.method === 'policy_simulation' ? 'Policy Simulation (Accurate)' : 'Simple Check (Best Effort)'}</p>
                    
                    <div style="margin-top: 15px; padding: 15px; background: white; border-radius: 5px;">
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 15px;">
                            <div style="text-align: center; padding: 10px; background: #f5f5f5; border-radius: 5px;">
                                <div style="font-size: 1.5em; font-weight: bold; color: #2196F3;">${data.total_required || 0}</div>
                                <div style="color: #666; font-size: 0.9em;">Total Required</div>
                            </div>
                            <div style="text-align: center; padding: 10px; background: #e8f5e9; border-radius: 5px;">
                                <div style="font-size: 1.5em; font-weight: bold; color: #4CAF50;">${data.total_available || 0}</div>
                                <div style="color: #666; font-size: 0.9em;">Available</div>
                            </div>
                            <div style="text-align: center; padding: 10px; background: #ffebee; border-radius: 5px;">
                                <div style="font-size: 1.5em; font-weight: bold; color: #f44336;">${data.total_missing || 0}</div>
                                <div style="color: #666; font-size: 0.9em;">Missing</div>
                            </div>
                        </div>
            `;
            
            if (data.missing_permissions && data.missing_permissions.length > 0) {
                html += '<h4 style="margin-top: 20px; margin-bottom: 10px;">Missing Permissions:</h4><ul style="list-style: none; padding: 0; max-height: 300px; overflow-y: auto;">';
                data.missing_permissions.slice(0, 30).forEach(perm => {
                    html += `<li style="padding: 5px; margin-bottom: 5px; background: #fff3cd; border-radius: 3px;"><code style="background: #f5f5f5; padding: 2px 6px; border-radius: 3px;">${perm}</code></li>`;
                });
                if (data.missing_permissions.length > 30) {
                    html += `<li style="padding: 5px; color: #666; font-style: italic;">... and ${data.missing_permissions.length - 30} more</li>`;
                }
                html += '</ul>';
            }
            
            html += '</div></div>';
            statusDiv.innerHTML = html;
        } else {
            statusDiv.innerHTML = `<div class="status-display error"><p><strong>Error:</strong> ${data.message || data.error || 'Unknown error'}</p></div>`;
        }
    } catch (error) {
        statusDiv.innerHTML = `<div class="status-display error"><p><strong>Error:</strong> ${error.message}</p></div>`;
    }
}

// ============================================================================
// DEPLOYMENTS PAGE FUNCTIONS
// ============================================================================

/**
 * Load and display the deployments page
 */
async function loadDeploymentsPage() {
    console.log('Loading Deployments page...');
    await refreshDeployments();
}

/**
 * Refresh deployment information from backend
 */
async function refreshDeployments() {
    const overviewDiv = document.getElementById('deployments-overview');
    const lastUpdatedSpan = document.getElementById('deployments-last-updated');
    const noDeploymentDiv = document.getElementById('no-deployment-message');
    
    // Show loading state
    if (overviewDiv) {
        overviewDiv.innerHTML = `
            <div class="status-display info">
                <div class="spinner"></div>
                <p>Loading infrastructure information...</p>
            </div>
        `;
    }
    
    try {
        const response = await fetch(`${API_BASE}/deploy/infrastructure`);
        const data = await response.json();
        
        // Update last updated time
        if (lastUpdatedSpan) {
            lastUpdatedSpan.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
        }
        
        if (!data.success) {
            overviewDiv.innerHTML = `
                <div class="status-display error">
                    <p><strong>Error:</strong> ${data.error || 'Failed to load infrastructure'}</p>
                </div>
            `;
            return;
        }
        
        if (!data.has_deployment) {
            // No deployment - show empty state
            hideAllInfrastructureSections();
            if (noDeploymentDiv) noDeploymentDiv.style.display = 'block';
            if (overviewDiv) overviewDiv.innerHTML = '';
            document.getElementById('connection-info-section').style.display = 'none';
            document.getElementById('destroy-section').style.display = 'none';
            return;
        }
        
        // Has deployment - show infrastructure
        if (noDeploymentDiv) noDeploymentDiv.style.display = 'none';
        
        // Show overview summary
        const summary = data.summary || {};
        overviewDiv.innerHTML = `
            <div class="status-display success">
                <p><strong>✅ Infrastructure Active</strong></p>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 15px; margin-top: 15px;">
                    <div style="text-align: center; padding: 15px; background: white; border-radius: 8px;">
                        <div style="font-size: 2em; font-weight: bold; color: #f44336;">${summary.c2_server_count || 0}</div>
                        <div style="color: #666; font-size: 0.9em;">C2 Servers</div>
                    </div>
                    <div style="text-align: center; padding: 15px; background: white; border-radius: 8px;">
                        <div style="font-size: 2em; font-weight: bold; color: #4CAF50;">${summary.redirector_count || 0}</div>
                        <div style="color: #666; font-size: 0.9em;">Redirectors</div>
                    </div>
                    <div style="text-align: center; padding: 15px; background: white; border-radius: 8px;">
                        <div style="font-size: 2em; font-weight: bold; color: #2196F3;">${summary.has_bastion ? '1' : '0'}</div>
                        <div style="color: #666; font-size: 0.9em;">Bastion Host</div>
                    </div>
                    <div style="text-align: center; padding: 15px; background: white; border-radius: 8px;">
                        <div style="font-size: 2em; font-weight: bold; color: #9c27b0;">${summary.subnet_count || 0}</div>
                        <div style="color: #666; font-size: 0.9em;">Subnets</div>
                    </div>
                </div>
                <p style="margin-top: 15px; color: #666;"><strong>Deployment Mode:</strong> ${data.deployment_mode || 'N/A'}</p>
            </div>
        `;
        
        // Populate Bastion section
        populateBastionSection(data.bastion);
        
        // Populate C2 Servers section
        populateC2ServersSection(data.c2_servers, data.deployment_mode);
        
        // Populate Redirectors section
        populateRedirectorsSection(data.redirectors);
        
        // Populate Network section
        populateNetworkSection(data.network, data.security_groups);
        
        // Populate Connection Info
        populateConnectionInfo(data);
        
        // Show destroy section when there's an active deployment
        const destroySection = document.getElementById('destroy-section');
        if (destroySection) {
            destroySection.style.display = data.has_deployment ? 'block' : 'none';
        }
        
    } catch (error) {
        console.error('Error loading deployments:', error);
        if (overviewDiv) {
            overviewDiv.innerHTML = `
                <div class="status-display error">
                    <p><strong>Error:</strong> ${error.message}</p>
                </div>
            `;
        }
    }
}

/**
 * Hide all infrastructure sections
 */
function hideAllInfrastructureSections() {
    const sections = ['bastion-section', 'c2-servers-section', 'redirectors-section', 'network-section'];
    sections.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
}

/**
 * Populate Bastion Host section
 */
function populateBastionSection(bastion) {
    const section = document.getElementById('bastion-section');
    const details = document.getElementById('bastion-details');
    
    if (!bastion || !bastion.enabled) {
        if (section) section.style.display = 'none';
        return;
    }
    
    section.style.display = 'block';
    details.innerHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
            <div style="background: white; padding: 15px; border-radius: 5px;">
                <strong>Public IP:</strong><br>
                <code style="background: #f5f5f5; padding: 5px 10px; border-radius: 3px; display: inline-block; margin-top: 5px;">${bastion.public_ip || 'N/A'}</code>
            </div>
            <div style="background: white; padding: 15px; border-radius: 5px;">
                <strong>Private IP:</strong><br>
                <code style="background: #f5f5f5; padding: 5px 10px; border-radius: 3px; display: inline-block; margin-top: 5px;">${bastion.private_ip || 'N/A'}</code>
            </div>
        </div>
        ${bastion.rdp_connection ? `
        <div style="margin-top: 15px; background: white; padding: 15px; border-radius: 5px;">
            <strong>RDP Connection:</strong><br>
            <code style="background: #1e1e1e; color: #4ec9b0; padding: 10px; border-radius: 3px; display: block; margin-top: 5px; overflow-x: auto;">${bastion.rdp_connection}</code>
        </div>
        ` : ''}
        ${bastion.wsl2_info ? `
        <div style="margin-top: 15px; background: #fff3cd; padding: 15px; border-radius: 5px; border-left: 4px solid #ffc107;">
            <strong>WSL2 Info:</strong><br>
            <p style="margin-top: 5px; color: #666;">${bastion.wsl2_info}</p>
        </div>
        ` : ''}
    `;
}

/**
 * Populate C2 Servers section
 */
function populateC2ServersSection(c2Servers, deploymentMode) {
    const section = document.getElementById('c2-servers-section');
    const details = document.getElementById('c2-servers-details');
    
    const servers = c2Servers.servers || {};
    const instanceIds = c2Servers.instance_ids || [];
    const privateIps = c2Servers.private_ips || [];
    
    // Check if we have any servers
    const hasServers = Object.keys(servers).length > 0 || instanceIds.length > 0;
    
    if (!hasServers) {
        if (section) section.style.display = 'none';
        return;
    }
    
    section.style.display = 'block';
    
    let html = '<div style="display: grid; gap: 15px;">';
    
    if (Object.keys(servers).length > 0) {
        // Phase-based or named servers
        for (const [name, server] of Object.entries(servers)) {
            html += `
                <div style="background: white; padding: 15px; border-radius: 5px; border-left: 4px solid #f44336;">
                    <h4 style="margin: 0 0 10px 0; color: #c62828;">${name}</h4>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px;">
                        <div>
                            <strong>Instance ID:</strong><br>
                            <code style="font-size: 0.85em;">${server.instance_id || 'N/A'}</code>
                        </div>
                        <div>
                            <strong>Private IP:</strong><br>
                            <code style="background: #f5f5f5; padding: 3px 8px; border-radius: 3px;">${server.private_ip || 'N/A'}</code>
                        </div>
                        ${server.phase ? `
                        <div>
                            <strong>Phase:</strong><br>
                            <span style="background: #ffebee; padding: 3px 8px; border-radius: 3px;">${server.phase}</span>
                        </div>
                        ` : ''}
                    </div>
                </div>
            `;
        }
    } else {
        // Simple list of servers
        instanceIds.forEach((id, idx) => {
            html += `
                <div style="background: white; padding: 15px; border-radius: 5px; border-left: 4px solid #f44336;">
                    <h4 style="margin: 0 0 10px 0; color: #c62828;">C2 Server ${idx + 1}</h4>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px;">
                        <div>
                            <strong>Instance ID:</strong><br>
                            <code style="font-size: 0.85em;">${id}</code>
                        </div>
                        <div>
                            <strong>Private IP:</strong><br>
                            <code style="background: #f5f5f5; padding: 3px 8px; border-radius: 3px;">${privateIps[idx] || 'N/A'}</code>
                        </div>
                    </div>
                </div>
            `;
        });
    }
    
    html += '</div>';
    details.innerHTML = html;
}

/**
 * Populate Redirectors section
 */
function populateRedirectorsSection(redirectors) {
    const section = document.getElementById('redirectors-section');
    const details = document.getElementById('redirectors-details');
    
    const instanceIds = redirectors.instance_ids || [];
    const publicIps = redirectors.public_ips || [];
    const privateIps = redirectors.private_ips || [];
    
    if (instanceIds.length === 0) {
        if (section) section.style.display = 'none';
        return;
    }
    
    section.style.display = 'block';
    
    let html = '<div style="display: grid; gap: 15px;">';
    
    instanceIds.forEach((id, idx) => {
        html += `
            <div style="background: white; padding: 15px; border-radius: 5px; border-left: 4px solid #4CAF50;">
                <h4 style="margin: 0 0 10px 0; color: #2e7d32;">Redirector ${idx + 1}</h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px;">
                    <div>
                        <strong>Instance ID:</strong><br>
                        <code style="font-size: 0.85em;">${id}</code>
                    </div>
                    <div>
                        <strong>Public IP:</strong><br>
                        <code style="background: #e8f5e9; padding: 3px 8px; border-radius: 3px; color: #2e7d32;">${publicIps[idx] || 'N/A'}</code>
                    </div>
                    <div>
                        <strong>Private IP:</strong><br>
                        <code style="background: #f5f5f5; padding: 3px 8px; border-radius: 3px;">${privateIps[idx] || 'N/A'}</code>
                    </div>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    details.innerHTML = html;
}

/**
 * Populate Network section
 */
function populateNetworkSection(network, securityGroups) {
    const section = document.getElementById('network-section');
    const details = document.getElementById('network-details');
    
    if (!network || !network.vpc_id) {
        if (section) section.style.display = 'none';
        return;
    }
    
    section.style.display = 'block';
    
    details.innerHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px;">
            <div style="background: white; padding: 15px; border-radius: 5px;">
                <strong>VPC ID:</strong><br>
                <code style="font-size: 0.85em;">${network.vpc_id}</code>
            </div>
            <div style="background: white; padding: 15px; border-radius: 5px;">
                <strong>VPC CIDR:</strong><br>
                <code style="background: #f5f5f5; padding: 3px 8px; border-radius: 3px;">${network.vpc_cidr || 'N/A'}</code>
            </div>
        </div>
        
        <div style="margin-top: 15px; display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px;">
            <div style="background: white; padding: 15px; border-radius: 5px;">
                <strong>Public Subnets (${(network.public_subnets || []).length}):</strong>
                <ul style="margin: 10px 0 0 20px; padding: 0;">
                    ${(network.public_subnets || []).map(s => `<li><code style="font-size: 0.85em;">${s}</code></li>`).join('') || '<li>None</li>'}
                </ul>
            </div>
            <div style="background: white; padding: 15px; border-radius: 5px;">
                <strong>Private Subnets (${(network.private_subnets || []).length}):</strong>
                <ul style="margin: 10px 0 0 20px; padding: 0;">
                    ${(network.private_subnets || []).map(s => `<li><code style="font-size: 0.85em;">${s}</code></li>`).join('') || '<li>None</li>'}
                </ul>
            </div>
        </div>
        
        ${securityGroups ? `
        <div style="margin-top: 15px; background: white; padding: 15px; border-radius: 5px;">
            <strong>Security Groups:</strong>
            <div style="margin-top: 10px; display: grid; gap: 5px;">
                ${securityGroups.c2_server_sg ? `<div>C2 Server SG: <code style="font-size: 0.85em;">${securityGroups.c2_server_sg}</code></div>` : ''}
                ${securityGroups.redirector_sg ? `<div>Redirector SG: <code style="font-size: 0.85em;">${securityGroups.redirector_sg}</code></div>` : ''}
            </div>
        </div>
        ` : ''}
    `;
}

/**
 * Populate connection info section
 */
function populateConnectionInfo(data) {
    const section = document.getElementById('connection-info-section');
    const commands = document.getElementById('connection-commands');
    
    if (!data.has_deployment) {
        section.style.display = 'none';
        return;
    }
    
    section.style.display = 'block';
    
    let html = '';
    
    // Bastion RDP command
    if (data.bastion && data.bastion.public_ip) {
        html += `
            <div style="margin-bottom: 20px;">
                <h4 style="margin: 0 0 10px 0;">🖥️ Connect to Bastion (RDP)</h4>
                <code style="background: #1e1e1e; color: #4ec9b0; padding: 10px 15px; border-radius: 5px; display: block; overflow-x: auto;">
                    mstsc /v:${data.bastion.public_ip}
                </code>
            </div>
        `;
    }
    
    // SSH to C2 servers via bastion
    const c2Ips = data.c2_servers?.private_ips || [];
    if (c2Ips.length > 0 && data.bastion?.public_ip) {
        html += `
            <div style="margin-bottom: 20px;">
                <h4 style="margin: 0 0 10px 0;">🎯 SSH to C2 Servers (via Bastion WSL2)</h4>
                ${c2Ips.map((ip, idx) => `
                    <div style="margin-bottom: 10px;">
                        <span style="color: #666;">C2 Server ${idx + 1}:</span>
                        <code style="background: #1e1e1e; color: #4ec9b0; padding: 10px 15px; border-radius: 5px; display: block; margin-top: 5px; overflow-x: auto;">
                            ssh -J wsl@${data.bastion.public_ip} ec2-user@${ip}
                        </code>
                    </div>
                `).join('')}
            </div>
        `;
    }
    
    // Direct SSH to redirectors
    const redirectorIps = data.redirectors?.public_ips || [];
    if (redirectorIps.length > 0) {
        html += `
            <div style="margin-bottom: 20px;">
                <h4 style="margin: 0 0 10px 0;">🔀 SSH to Redirectors</h4>
                ${redirectorIps.map((ip, idx) => `
                    <div style="margin-bottom: 10px;">
                        <span style="color: #666;">Redirector ${idx + 1}:</span>
                        <code style="background: #1e1e1e; color: #4ec9b0; padding: 10px 15px; border-radius: 5px; display: block; margin-top: 5px; overflow-x: auto;">
                            ssh ec2-user@${ip}
                        </code>
                    </div>
                `).join('')}
            </div>
        `;
    }
    
    if (!html) {
        html = '<p style="color: #888;">No connection information available.</p>';
    }
    
    commands.innerHTML = html;
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function showMessage(message, type) {
    const messageDiv = document.getElementById('config-message');
    if (!messageDiv) return;
    
    messageDiv.textContent = message;
    messageDiv.className = `message ${type} show`;
    
    setTimeout(() => {
        messageDiv.classList.remove('show');
    }, 5000);
}

// ============================================================================
// APPLICATION INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    APP.init();
});
