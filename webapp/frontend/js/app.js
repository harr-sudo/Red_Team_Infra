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
        
        // Clear deployment polling when leaving the deployment page
        if (this.currentPage === 'deployment' && pageName !== 'deployment') {
            if (deploymentPollInterval) {
                clearInterval(deploymentPollInterval);
                deploymentPollInterval = null;
                console.log('🛑 Cleared deployment polling interval');
            }
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
                    // Reset plan state when navigating to deployment page
                    isPlanRunning = false;
                    loadConfigSummary();
                    checkDeploymentStatus();
                    checkDomainConfig();
                    checkCobaltStrikeFile();
                    break;
                case 'deployments':
                    loadDeploymentsPage();
                    loadDeploymentDetails();  // Load comprehensive details
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
        
        // Project name input - validate on input with debounce
        const projectNameInput = document.getElementById('project-name');
        if (projectNameInput) {
            projectNameInput.addEventListener('input', debouncedProjectNameCheck);
            projectNameInput.addEventListener('blur', () => validateProjectName(true));
        }
        
        // SSL configuration handlers
        this.setupSSLHandlers();
    },
    
    /**
     * Setup SSL configuration event handlers
     */
    setupSSLHandlers() {
        // Enable SSL checkbox
        const enableSslCheckbox = document.getElementById('enable-ssl');
        if (enableSslCheckbox) {
            enableSslCheckbox.addEventListener('change', function() {
                const sslOptions = document.getElementById('ssl-options');
                if (sslOptions) {
                    sslOptions.style.opacity = this.checked ? '1' : '0.5';
                    sslOptions.style.pointerEvents = this.checked ? 'auto' : 'none';
                }
            });
        }
        
        // SSL provider dropdown
        const sslProviderSelect = document.getElementById('ssl-provider');
        if (sslProviderSelect) {
            sslProviderSelect.addEventListener('change', function() {
                const letsencryptOptions = document.getElementById('letsencrypt-options');
                if (letsencryptOptions) {
                    letsencryptOptions.style.display = this.value === 'letsencrypt' ? 'block' : 'none';
                }
            });
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
                'deployment-type': config.deployment_type || config.engagement_type || '',
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
            
            // Don't auto-load project name if it's the old default - let updateProjectName() generate it
            const savedProjectName = config.project_name || '';
            if (savedProjectName && savedProjectName !== 'red-team-infra') {
                fields['project-name'] = savedProjectName;
            }
            
            Object.entries(fields).forEach(([id, value]) => {
                const element = document.getElementById(id);
                if (element) element.value = value;
            });
            
            // Update the deployment overview based on loaded type (this also updates project name)
            updateDeploymentType();
            
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

/**
 * Fetch user's public IP address and populate the Management CIDR field
 */
async function fetchMyPublicIP() {
    const btn = document.getElementById('fetch-ip-btn');
    const cidrInput = document.getElementById('management-cidr');
    
    if (!btn || !cidrInput) return;
    
    // Show loading state
    const originalText = btn.innerHTML;
    btn.innerHTML = '⏳ Fetching...';
    btn.disabled = true;
    
    try {
        // Try multiple IP services in case one fails
        const ipServices = [
            'https://api.ipify.org?format=json',
            'https://ipinfo.io/json',
            'https://api.ip.sb/geoip'
        ];
        
        let publicIP = null;
        
        for (const service of ipServices) {
            try {
                const response = await fetch(service, { timeout: 5000 });
                if (response.ok) {
                    const data = await response.json();
                    publicIP = data.ip;
                    if (publicIP) break;
                }
            } catch (e) {
                console.log(`IP service ${service} failed, trying next...`);
            }
        }
        
        if (publicIP) {
            // Format as CIDR /32 for single IP
            const cidrValue = `${publicIP}/32`;
            
            // Check if there's already content in the field
            const currentValue = cidrInput.value.trim();
            if (currentValue) {
                // Ask if they want to replace or append
                const existingCidrs = parseCidrInput(currentValue);
                if (!existingCidrs.includes(cidrValue)) {
                    cidrInput.value = currentValue + ', ' + cidrValue;
                    showMessage(`Added your IP (${publicIP}) to existing CIDR blocks`, 'success');
                } else {
                    showMessage(`Your IP (${publicIP}) is already in the list`, 'info');
                }
            } else {
                cidrInput.value = cidrValue;
                showMessage(`Your public IP: ${publicIP}`, 'success');
            }
            
            btn.innerHTML = '✅ Got IP!';
            setTimeout(() => {
                btn.innerHTML = originalText;
            }, 2000);
        } else {
            throw new Error('Could not determine public IP');
        }
    } catch (error) {
        console.error('Error fetching public IP:', error);
        showMessage('Could not fetch public IP. Please enter manually.', 'error');
        btn.innerHTML = '❌ Failed';
        setTimeout(() => {
            btn.innerHTML = originalText;
        }, 2000);
    } finally {
        btn.disabled = false;
    }
}

// Deployment type configurations (combines C2 and GOAD)
const DEPLOYMENT_CONFIGS = {
    // C2 Infrastructure options (Full C2 with redirectors, bastion, etc.)
    'c2-adhoc': {
        title: 'C2: Ad-Hoc Deployment',
        color: 'linear-gradient(135deg, #0d7377 0%, #14a085 100%)',
        type: 'c2',
        c2Mode: 'adhoc',
        goadLab: null,
        serverCount: 1,
        requiresDomain: true,
        requiresCS: true,
        architecture: 'full-c2',
        components: [
            { icon: '🎯', label: 'C2 Server', value: '1' },
            { icon: '🔀', label: 'Redirectors', value: '2' },
            { icon: '🖥️', label: 'Bastion', value: '1' },
            { icon: '💰', label: 'Est. Cost', value: '~$125/mo' }
        ],
        details: 'Quick, minimal setup for one-off tests. Single C2 server with standard proxy infrastructure.',
        bestFor: 'Quick security tests, POCs, training',
        architectureNote: 'Full C2 infrastructure with redirectors for internet-facing operations.'
    },
    'c2-purple': {
        title: 'C2: Purple Team Deployment',
        color: 'linear-gradient(135deg, #4a4e8c 0%, #6b5b95 100%)',
        type: 'c2',
        c2Mode: 'purple-team',
        goadLab: null,
        serverCount: 2,
        serverCountEditable: true,
        requiresDomain: true,
        requiresCS: true,
        architecture: 'full-c2',
        components: [
            { icon: '🎯', label: 'C2 Servers', value: '2+' },
            { icon: '🔀', label: 'Redirectors', value: '2' },
            { icon: '🖥️', label: 'Bastion', value: '1' },
            { icon: '💰', label: 'Est. Cost', value: '~$155/mo' }
        ],
        details: 'Redundant C2 infrastructure for collaborative exercises. High availability.',
        bestFor: 'Purple team exercises, collaborative testing',
        architectureNote: 'Full C2 infrastructure with redirectors for internet-facing operations.'
    },
    'c2-full': {
        title: 'C2: Full Red Team Deployment',
        color: 'linear-gradient(135deg, #b91c1c 0%, #991b1b 100%)',
        type: 'c2',
        c2Mode: 'full-red-team',
        goadLab: null,
        serverCount: 3,
        requiresDomain: true,
        requiresCS: true,
        architecture: 'full-c2',
        components: [
            { icon: '🎯', label: 'C2 Servers', value: '3' },
            { icon: '🔀', label: 'Redirectors', value: '2' },
            { icon: '🖥️', label: 'Bastion', value: '1' },
            { icon: '💰', label: 'Est. Cost', value: '~$185/mo' }
        ],
        details: 'Phase-based C2: Staging → Post-Ex → Long-Haul. Full operational capability.',
        bestFor: 'Full red team engagements, long-term campaigns',
        phases: ['🚀 Staging', '⚡ Post-Ex', '🔒 Long-Haul'],
        architectureNote: 'Full C2 infrastructure with redirectors for internet-facing operations.'
    },
    // GOAD Lab options (Proper architecture: Jumpbox → Team Server + Windows Attack Box)
    'goad-mini': {
        title: 'GOAD Mini + Cobalt Strike',
        color: 'linear-gradient(135deg, #e65100 0%, #ff9800 100%)',
        type: 'goad',
        c2Mode: null,
        goadLab: 'GOAD-Mini',
        requiresDomain: false,
        requiresCS: true,
        architecture: 'goad-only',
        components: [
            { icon: '🏰', label: 'AD VMs', value: '1' },
            { icon: '🚪', label: 'Jumpbox', value: '1' },
            { icon: '🔴', label: 'Team Server', value: '1' },
            { icon: '🖥️', label: 'Attack Box', value: '1 (Win)' },
            { icon: '💰', label: 'Est. Cost', value: '~$195/mo' }
        ],
        details: 'Single DC (sevenkingdoms.local) with Team Server + Windows Attack Box.',
        bestFor: 'Learning AD attacks, quick testing',
        attacks: ['Kerberoasting', 'AS-REP Roasting', 'DCSync', 'Pass-the-Hash'],
        architectureNote: '🔒 Training Lab: Jumpbox (SSH) → Team Server (CS only) + Windows Attack Box (CS Client + PowerSploit)'
    },
    'goad-minilab': {
        title: 'GOAD MiniLab + Cobalt Strike',
        color: 'linear-gradient(135deg, #e65100 0%, #ff9800 100%)',
        type: 'goad',
        c2Mode: null,
        goadLab: 'MINILAB',
        requiresDomain: false,
        requiresCS: true,
        architecture: 'goad-only',
        components: [
            { icon: '🏰', label: 'AD VMs', value: '2' },
            { icon: '🚪', label: 'Jumpbox', value: '1' },
            { icon: '🔴', label: 'Team Server', value: '1' },
            { icon: '🖥️', label: 'Attack Box', value: '1 (Win)' },
            { icon: '💰', label: 'Est. Cost', value: '~$275/mo' }
        ],
        details: 'DC (Win2019) + Workstation (Win10). 1 forest, 1 domain.',
        bestFor: 'Attack chains, lateral movement practice',
        attacks: ['Kerberoasting', 'AS-REP Roasting', 'Lateral Movement', 'Credential Dumping'],
        architectureNote: '🔒 Training Lab: Jumpbox (SSH) → Team Server (CS only) + Windows Attack Box (CS Client + PowerSploit)'
    },
    'goad-light': {
        title: 'GOAD Light + Cobalt Strike',
        color: 'linear-gradient(135deg, #e65100 0%, #ff9800 100%)',
        type: 'goad',
        c2Mode: null,
        goadLab: 'GOAD-Light',
        requiresDomain: false,
        requiresCS: true,
        architecture: 'goad-only',
        components: [
            { icon: '🏰', label: 'AD VMs', value: '3' },
            { icon: '🚪', label: 'Jumpbox', value: '1' },
            { icon: '🔴', label: 'Team Server', value: '1' },
            { icon: '🖥️', label: 'Attack Box', value: '1 (Win)' },
            { icon: '💰', label: 'Est. Cost', value: '~$360/mo' }
        ],
        details: '3 VMs, 1 forest, 2 domains. Smaller version of full GOAD.',
        bestFor: 'Trust attacks, cross-domain techniques',
        attacks: ['Trust Attacks', 'Constrained Delegation', 'Cross-domain attacks', 'Kerberoasting'],
        architectureNote: '🔒 Training Lab: Jumpbox (SSH) → Team Server (CS only) + Windows Attack Box (CS Client + PowerSploit)'
    },
    'goad-sccm': {
        title: 'GOAD SCCM + Cobalt Strike',
        color: 'linear-gradient(135deg, #e65100 0%, #ff9800 100%)',
        type: 'goad',
        c2Mode: null,
        goadLab: 'SCCM',
        requiresDomain: false,
        requiresCS: true,
        architecture: 'goad-only',
        components: [
            { icon: '🏰', label: 'AD VMs', value: '4' },
            { icon: '🚪', label: 'Jumpbox', value: '1' },
            { icon: '🔴', label: 'Team Server', value: '1' },
            { icon: '🖥️', label: 'Attack Box', value: '1 (Win)' },
            { icon: '💰', label: 'Est. Cost', value: '~$815/mo' }
        ],
        details: '4 VMs (t3.xlarge), 1 forest, 1 domain with Microsoft Configuration Manager.',
        bestFor: 'SCCM attacks, enterprise environments',
        attacks: ['NAA Credentials', 'PXE Boot Attacks', 'Task Sequence Attacks', 'SCCM Client Attacks'],
        architectureNote: '🔒 Training Lab: Jumpbox (SSH) → Team Server (CS only) + Windows Attack Box (CS Client + PowerSploit)'
    },
    'goad-full': {
        title: 'GOAD Full + Cobalt Strike',
        color: 'linear-gradient(135deg, #e65100 0%, #ff9800 100%)',
        type: 'goad',
        c2Mode: null,
        goadLab: 'GOAD',
        requiresDomain: false,
        requiresCS: true,
        architecture: 'goad-only',
        components: [
            { icon: '🏰', label: 'AD VMs', value: '5' },
            { icon: '🚪', label: 'Jumpbox', value: '1' },
            { icon: '🔴', label: 'Team Server', value: '1' },
            { icon: '🖥️', label: 'Attack Box', value: '1 (Win)' },
            { icon: '💰', label: 'Est. Cost', value: '~$520/mo' }
        ],
        details: '5 VMs, 2 forests, 3 domains. Complete AD training environment.',
        bestFor: 'Comprehensive AD training, forest attacks',
        attacks: ['Forest Attacks', 'Golden/Silver Tickets', 'DCShadow', 'ACL Abuse', 'Trust Attacks'],
        architectureNote: '🔒 Training Lab: Jumpbox (SSH) → Team Server (CS only) + Windows Attack Box (CS Client + PowerSploit)'
    },
    'goad-nha': {
        title: 'GOAD NHA + Cobalt Strike',
        color: 'linear-gradient(135deg, #e65100 0%, #ff9800 100%)',
        type: 'goad',
        c2Mode: null,
        goadLab: 'NHA',
        requiresDomain: false,
        requiresCS: true,
        architecture: 'goad-only',
        components: [
            { icon: '🏰', label: 'AD VMs', value: '5' },
            { icon: '🚪', label: 'Jumpbox', value: '1' },
            { icon: '🔴', label: 'Team Server', value: '1' },
            { icon: '🖥️', label: 'Attack Box', value: '1 (Win)' },
            { icon: '💰', label: 'Est. Cost', value: '~$520/mo' }
        ],
        details: '5 VMs, 2 domains. Challenge lab - no schema provided!',
        bestFor: 'CTF practice, skill assessment',
        attacks: ['Unknown - Challenge Mode!'],
        architectureNote: '🔒 Training Lab: Jumpbox (SSH) → Team Server (CS only) + Windows Attack Box (CS Client + PowerSploit)'
    },
    // Combined options (Full C2 infrastructure + GOAD lab with VPC peering)
    'combined-adhoc-mini': {
        title: 'Full C2 Ad-Hoc + GOAD Mini',
        color: 'linear-gradient(135deg, #d32f2f 0%, #ff9800 100%)',
        type: 'combined',
        c2Mode: 'adhoc',
        goadLab: 'GOAD-Mini',
        serverCount: 1,
        requiresDomain: true,
        requiresCS: true,
        architecture: 'full-combined',
        components: [
            { icon: '🎯', label: 'C2 Server', value: '1' },
            { icon: '🔀', label: 'Redirectors', value: '2' },
            { icon: '🏰', label: 'GOAD VMs', value: '1' },
            { icon: '💰', label: 'Est. Cost', value: '~$240/mo' }
        ],
        details: 'Full C2 with redirectors + GOAD Mini. VPCs peered for realistic beacon traffic.',
        bestFor: 'Testing C2 tradecraft against AD targets',
        architectureNote: '🔥 Full Infrastructure: Beacons route through redirectors. Realistic C2 operations.'
    },
    'combined-adhoc-light': {
        title: 'Full C2 Ad-Hoc + GOAD Light',
        color: 'linear-gradient(135deg, #d32f2f 0%, #ff9800 100%)',
        type: 'combined',
        c2Mode: 'adhoc',
        goadLab: 'GOAD-Light',
        serverCount: 1,
        requiresDomain: true,
        requiresCS: true,
        architecture: 'full-combined',
        components: [
            { icon: '🎯', label: 'C2 Server', value: '1' },
            { icon: '🔀', label: 'Redirectors', value: '2' },
            { icon: '🏰', label: 'GOAD VMs', value: '3' },
            { icon: '💰', label: 'Est. Cost', value: '~$400/mo' }
        ],
        details: 'Full C2 with redirectors + GOAD Light (multi-domain).',
        bestFor: 'Realistic red team training with trust attacks',
        architectureNote: '🔥 Full Infrastructure: Beacons route through redirectors. Realistic C2 operations.'
    },
    'combined-full-full': {
        title: 'Full C2 Red Team + GOAD Full',
        color: 'linear-gradient(135deg, #d32f2f 0%, #ff9800 100%)',
        type: 'combined',
        c2Mode: 'full-red-team',
        goadLab: 'GOAD',
        serverCount: 3,
        requiresDomain: true,
        requiresCS: true,
        architecture: 'full-combined',
        components: [
            { icon: '🎯', label: 'C2 Servers', value: '3' },
            { icon: '🔀', label: 'Redirectors', value: '2' },
            { icon: '🏰', label: 'GOAD VMs', value: '5' },
            { icon: '💰', label: 'Est. Cost', value: '~$620/mo' }
        ],
        details: 'Complete phased C2 (Staging/Post-Ex/Long-Haul) + Full GOAD lab.',
        bestFor: 'Full-scale red team exercises with realistic AD targets',
        phases: ['🚀 Staging', '⚡ Post-Ex', '🔒 Long-Haul'],
        architectureNote: '🔥 Full Infrastructure: Beacons route through redirectors. Realistic C2 operations.'
    }
};

/**
 * Project name prefixes for each deployment type (without environment)
 */
const PROJECT_NAME_PREFIXES = {
    // C2 Infrastructure
    'c2-adhoc': 'c2_adhoc',
    'c2-purple': 'c2_purple',
    'c2-full': 'c2_redteam',
    // GOAD Labs
    'goad-mini': 'goad_mini',
    'goad-minilab': 'goad_minilab',
    'goad-light': 'goad_light',
    'goad-sccm': 'goad_sccm',
    'goad-full': 'goad_full',
    'goad-nha': 'goad_nha',
    // Combined
    'combined-adhoc-mini': 'c2_goad_mini',
    'combined-adhoc-light': 'c2_goad_light',
    'combined-full-full': 'c2_goad_full'
};

/**
 * Estimated deployment times (in minutes) for each deployment type
 */
const DEPLOYMENT_TIMES = {
    // C2 Infrastructure
    'c2-adhoc': { min: 8, max: 12 },
    'c2-purple': { min: 10, max: 15 },
    'c2-full': { min: 12, max: 18 },
    // GOAD Labs (longer due to Windows + AD setup)
    'goad-mini': { min: 15, max: 20 },
    'goad-minilab': { min: 18, max: 25 },
    'goad-light': { min: 20, max: 30 },
    'goad-sccm': { min: 25, max: 40 },
    'goad-full': { min: 25, max: 35 },
    'goad-nha': { min: 25, max: 35 },
    // Combined (C2 + GOAD)
    'combined-adhoc-mini': { min: 20, max: 30 },
    'combined-adhoc-light': { min: 25, max: 40 },
    'combined-full-full': { min: 30, max: 45 }
};

/**
 * Machine suffix for unique project names (cached)
 */
let machineSuffix = null;

/**
 * Fetch machine suffix from backend
 */
async function fetchMachineSuffix() {
    if (machineSuffix) return machineSuffix;
    
    try {
        const response = await fetch(`${API_BASE}/deploy/machine-info`);
        const data = await response.json();
        if (data.success) {
            machineSuffix = data.machine_suffix;
            console.log(`🖥️ Machine suffix: ${machineSuffix} (from ${data.hostname})`);
            return machineSuffix;
        }
    } catch (error) {
        console.error('Failed to fetch machine suffix:', error);
    }
    
    // Fallback: generate random suffix
    machineSuffix = Math.random().toString(36).substring(2, 8);
    return machineSuffix;
}

/**
 * Update project name based on deployment type and environment
 * Now includes machine-specific suffix for uniqueness across users
 */
async function updateProjectName() {
    const deploymentType = document.getElementById('deployment-type')?.value || '';
    const environment = document.getElementById('environment')?.value || 'dev';
    const projectNameInput = document.getElementById('project-name');
    
    if (!projectNameInput || !deploymentType) return;
    
    const prefix = PROJECT_NAME_PREFIXES[deploymentType] || 'project';
    
    // Get machine suffix for uniqueness
    const suffix = await fetchMachineSuffix();
    const newName = `${prefix}_${environment}_${suffix}`;
    
    // Get current value
    const currentName = projectNameInput.value;
    
    // Check if current name should be replaced:
    // 1. Empty
    // 2. Contains XXX placeholder
    // 3. Is the default "red-team-infra"
    // 4. Matches the auto-generated pattern (starts with known prefix)
    const knownPrefixes = Object.values(PROJECT_NAME_PREFIXES);
    const isAutoGenerated = !currentName || 
                           currentName === 'red-team-infra' ||
                           currentName.includes('XXX') || 
                           knownPrefixes.some(p => currentName.startsWith(p + '_'));
    
    if (isAutoGenerated) {
        projectNameInput.value = newName;
        projectNameInput.placeholder = newName;
        
        // Trigger validation to check availability
        debouncedProjectNameCheck();
    }
}

/**
 * Validate project name format and check availability
 * @param {boolean} checkBackend - Whether to check backend for existing projects
 */
async function validateProjectName(checkBackend = false) {
    const projectNameInput = document.getElementById('project-name');
    const statusSpan = document.getElementById('project-name-status');
    
    if (!projectNameInput) return false;
    
    const name = projectNameInput.value.trim();
    
    // Clear previous status
    if (statusSpan) {
        statusSpan.innerHTML = '';
        statusSpan.style.display = 'none';
    }
    
    // Check if empty
    if (!name) {
        projectNameInput.style.borderColor = '#ccc';
        return false;
    }
    
    // Check if still contains XXX placeholder
    if (name.includes('XXX')) {
        projectNameInput.style.borderColor = '#ff9800';
        if (statusSpan) {
            statusSpan.innerHTML = '<span style="color: #ff9800;">⚠️ Replace XXX with a unique identifier</span>';
            statusSpan.style.display = 'block';
        }
        return false;
    }
    
    // Check for valid characters (letters, numbers, underscores, hyphens, must start with letter)
    if (!/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(name)) {
        projectNameInput.style.borderColor = '#f44336';
        if (statusSpan) {
            statusSpan.innerHTML = '<span style="color: #f44336;">❌ Must start with letter, use only letters/numbers/_/-</span>';
            statusSpan.style.display = 'block';
        }
        return false;
    }
    
    // Basic format is valid
    projectNameInput.style.borderColor = '#4CAF50';
    
    // Optionally check backend for availability
    if (checkBackend) {
        try {
            if (statusSpan) {
                statusSpan.innerHTML = '<span style="color: #666;">🔍 Checking availability...</span>';
                statusSpan.style.display = 'block';
            }
            
            const response = await fetch(`${API_BASE}/deploy/check-project-name?name=${encodeURIComponent(name)}`);
            const data = await response.json();
            
            if (data.success) {
                if (data.available) {
                    projectNameInput.style.borderColor = '#4CAF50';
                    if (statusSpan) {
                        statusSpan.innerHTML = '<span style="color: #4CAF50;">✅ Available</span>';
                        statusSpan.style.display = 'block';
                    }
    return true;
                } else {
                    projectNameInput.style.borderColor = '#f44336';
                    if (statusSpan) {
                        let reason = '';
                        if (data.reason === 'currently_deploying') {
                            reason = '🚀 Currently deploying';
                        } else if (data.reason === 'aws_resources_exist') {
                            // AWS resources found - likely from another user/machine
                            reason = `☁️ Already in AWS: ${data.resource_count} ${data.resource_type}(s)`;
                        } else if (data.reason === 'has_local_resources') {
                            reason = `📁 Local: ${data.resource_count} resources`;
                        } else if (data.reason === 'has_resources') {
                            reason = `⚠️ Exists (${data.resource_count} resources)`;
                        } else {
                            reason = data.message || 'Not available';
                        }
                        statusSpan.innerHTML = `<span style="color: #f44336;">❌ ${reason}</span>`;
                        statusSpan.style.display = 'block';
                    }
                    return false;
                }
            }
        } catch (error) {
            console.error('Error checking project name:', error);
            // On error, allow proceeding (backend will validate again)
        }
    }
    
    return true;
}

// Debounced version for input events
let projectNameCheckTimeout = null;
function debouncedProjectNameCheck() {
    if (projectNameCheckTimeout) {
        clearTimeout(projectNameCheckTimeout);
    }
    projectNameCheckTimeout = setTimeout(() => {
        validateProjectName(true);
    }, 500);
}

/**
 * Update deployment overview when type changes
 */
function updateDeploymentType() {
    const deploymentType = document.getElementById('deployment-type').value;
    const serverCountInput = document.getElementById('c2-server-count');
    const serverCountGroup = document.getElementById('c2-server-count-group');
    const instanceTypeGroup = document.getElementById('c2-instance-type-group');
    const overviewDiv = document.getElementById('deployment-overview');
    const overviewTitle = document.getElementById('overview-title');
    const overviewContent = document.getElementById('overview-content');
    const overviewDetails = document.getElementById('overview-details');
    const estDeployTimeDiv = document.getElementById('est-deploy-time');
    
    // Get domain config section (we'll show/hide based on deployment type)
    const domainConfigSection = document.getElementById('domain-config-section');
    
    // Get key pair field elements
    const keyPairInput = document.getElementById('key-pair-name');
    const keyPairGroup = document.getElementById('key-pair-name-group');
    const keyPairHint = document.getElementById('key-pair-name-hint');
    
    const config = DEPLOYMENT_CONFIGS[deploymentType];
    
    if (config) {
        // Update project name with deployment type + environment
        updateProjectName();
        
        // Update estimated deployment time
        const timeEstimate = DEPLOYMENT_TIMES[deploymentType];
        if (estDeployTimeDiv && timeEstimate) {
            estDeployTimeDiv.textContent = `~${timeEstimate.min}-${timeEstimate.max} minutes`;
        }
        
        // Update server count if applicable
        if (config.serverCount) {
            serverCountInput.value = config.serverCount;
        }
        
        // Enable/disable server count based on type
        const editable = config.serverCountEditable || false;
        serverCountInput.disabled = !editable;
        if (serverCountGroup) {
            serverCountGroup.style.opacity = editable ? '1' : '0.6';
            serverCountGroup.style.display = config.type === 'goad' ? 'none' : 'block';
        }
        
        // Show/hide C2-specific fields based on type
        const instanceTypeSelect = document.getElementById('c2-instance-type');
        if (instanceTypeSelect) {
            instanceTypeSelect.disabled = config.type === 'goad';
        }
        if (instanceTypeGroup) {
            instanceTypeGroup.style.opacity = config.type === 'goad' ? '0.6' : '1';
            instanceTypeGroup.style.display = config.type === 'goad' ? 'none' : 'block';
        }
        
        // Handle key_pair_name field based on deployment type
        // GOAD-only deployments auto-generate their own SSH keys
        const isGoadOnly = config.type === 'goad';
        if (keyPairInput) {
            if (isGoadOnly) {
                keyPairInput.disabled = true;
                keyPairInput.value = '';
                keyPairInput.placeholder = 'Not required - auto-generated';
                keyPairInput.style.backgroundColor = '#f5f5f5';
                keyPairInput.style.cursor = 'not-allowed';
            } else {
                keyPairInput.disabled = false;
                keyPairInput.placeholder = 'red-team-keypair';
                keyPairInput.style.backgroundColor = '';
                keyPairInput.style.cursor = '';
            }
        }
        if (keyPairGroup) {
            keyPairGroup.style.opacity = isGoadOnly ? '0.6' : '1';
        }
        if (keyPairHint) {
            if (isGoadOnly) {
                keyPairHint.innerHTML = '<span style="color: #4CAF50;">✅ GOAD deployments auto-generate SSH keys. Download them after deployment.</span>';
            } else {
                keyPairHint.innerHTML = 'AWS EC2 key pair for SSH access to C2 servers';
            }
        }
        
        // Show/hide domain config based on whether it's required
        if (domainConfigSection) {
            if (config.requiresDomain) {
                domainConfigSection.style.display = 'block';
            } else {
                domainConfigSection.style.display = 'none';
            }
        }
        
        // Show/hide Malleable C2 profile section for C2 deployments
        const malleableSection = document.getElementById('malleable-profile-section');
        if (malleableSection) {
            // Show for any deployment that includes C2 infrastructure
            const hasC2 = config.type === 'c2' || config.type === 'combined';
            malleableSection.style.display = hasC2 ? 'block' : 'none';
        }
        
        // Show/hide SSL config section for C2 deployments
        const sslSection = document.getElementById('ssl-config-section');
        if (sslSection) {
            const hasC2 = config.type === 'c2' || config.type === 'combined';
            sslSection.style.display = hasC2 ? 'block' : 'none';
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
                <strong>Best for:</strong> ${config.bestFor}
            </div>
            <div style="opacity: 0.9;">${config.details}</div>
        `;
        
        // Add architecture note
        if (config.architectureNote) {
            detailsHtml += `
                <div style="margin-top: 12px; padding: 8px 12px; background: rgba(255,255,255,0.2); border-radius: 6px; font-size: 0.85em;">
                    ${config.architectureNote}
                </div>
            `;
        }
        
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
        
        // Add attacks for GOAD labs
        if (config.attacks) {
            detailsHtml += `
                <div style="margin-top: 12px; font-size: 0.85em;">
                    <strong>Available attacks:</strong> ${config.attacks.join(', ')}
                </div>
            `;
        }
        
        overviewDetails.innerHTML = detailsHtml;
        
    } else {
        // No type selected - hide overview
        overviewDiv.style.display = 'none';
        
        // Re-enable all fields
        serverCountInput.disabled = false;
        if (serverCountGroup) {
            serverCountGroup.style.opacity = '1';
            serverCountGroup.style.display = 'block';
        }
        
        const instanceTypeSelect = document.getElementById('c2-instance-type');
        if (instanceTypeSelect) instanceTypeSelect.disabled = false;
        if (instanceTypeGroup) {
            instanceTypeGroup.style.opacity = '1';
            instanceTypeGroup.style.display = 'block';
        }
        
        // Reset key pair field to default state
        if (keyPairInput) {
            keyPairInput.disabled = false;
            keyPairInput.placeholder = 'red-team-keypair';
            keyPairInput.style.backgroundColor = '';
            keyPairInput.style.cursor = '';
        }
        if (keyPairGroup) {
            keyPairGroup.style.opacity = '1';
        }
        if (keyPairHint) {
            keyPairHint.innerHTML = 'AWS EC2 key pair for SSH access to C2 servers';
        }
        
        // Show domain config by default
        if (domainConfigSection) {
            domainConfigSection.style.display = 'block';
        }
    }
}

// Keep old function name for backward compatibility
function updateEngagementType() {
    updateDeploymentType();
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
        
        // Get deployment type and extract c2Mode and goadLab
        const deploymentType = document.getElementById('deployment-type')?.value || '';
        const deployConfig = DEPLOYMENT_CONFIGS[deploymentType] || {};
        
        // Get SSL configuration
        const enableSsl = document.getElementById('enable-ssl')?.checked ?? true;
        const sslProvider = document.getElementById('ssl-provider')?.value || 'letsencrypt';
        const adminEmail = document.getElementById('admin-email')?.value?.trim() || '';
        const sslAutoRetry = document.getElementById('ssl-auto-retry')?.checked ?? true;
        
        // Only validate admin email if deployment requires domain (C2-only or full red team)
        const requiresDomain = deployConfig.requiresDomain === true;
        if (requiresDomain && enableSsl && sslProvider === 'letsencrypt' && !adminEmail) {
            showMessage('Error: Admin email is required for Let\'s Encrypt SSL', 'error');
            document.getElementById('admin-email')?.focus();
            return;
        }
        
        const config = {
            deployment_type: deploymentType,
            engagement_type: deployConfig.c2Mode || '', // For backward compatibility
            goad_lab_type: deployConfig.goadLab || '',
            project_name: document.getElementById('project-name').value,
            environment: document.getElementById('environment').value,
            aws_region: document.getElementById('aws-region').value,
            key_pair_name: document.getElementById('key-pair-name').value,
            management_cidr_blocks: cidrBlocks,
            primary_domain_name: document.getElementById('primary-domain').value.trim(),
            backup_domains: backupDomains,
            c2_subdomain: document.getElementById('c2-subdomain').value.trim() || 'api',
            www_subdomain: document.getElementById('www-subdomain').value.trim() || 'www',
            cdn_subdomain: document.getElementById('cdn-subdomain').value.trim() || 'cdn',
            malleable_profile: document.getElementById('malleable-profile')?.value || 'default',
            // SSL configuration
            enable_ssl_certificate: enableSsl,
            ssl_provider: sslProvider,
            ssl_auto_retry: sslAutoRetry,
            admin_email: adminEmail,
            // Server configuration
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

/**
 * Clear all configuration - resets form and deletes saved config file
 */
async function clearConfig() {
    if (!confirm('⚠️ Clear All Configuration?\n\nThis will:\n• Reset all form fields to defaults\n• Delete the saved terraform.tfvars file\n\nAre you sure?')) {
        return;
    }
    
    try {
        // Delete the saved config file on backend
        const response = await fetch(`${API_BASE}/config/`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        // Reset all form fields to defaults
        const defaults = {
            'deployment-type': '',
            'project-name': '',
            'environment': 'dev',
            'aws-region': 'us-east-1',
            'key-pair-name': '',
            'management-cidr': '',
            'primary-domain': '',
            'backup-domains': '',
            'c2-subdomain': 'c2',
            'www-subdomain': 'www',
            'cdn-subdomain': 'cdn',
            'c2-server-count': '2',
            'c2-instance-type': 't3.medium'
        };
        
        Object.entries(defaults).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) element.value = value;
        });
        
        // Reset deployment type display
        updateDeploymentType();
        
        // Clear the deployment overview
        const overviewDiv = document.getElementById('deployment-overview');
        if (overviewDiv) {
            overviewDiv.innerHTML = '<p style="color: #666; text-align: center;">Select a deployment type above to see details</p>';
        }
        
        if (data.success) {
            showMessage('Configuration cleared successfully', 'success');
        } else {
            showMessage('Form cleared. Note: ' + (data.error || 'Could not delete saved file'), 'warning');
        }
    } catch (error) {
        // Still clear the form even if backend fails
        showMessage('Form cleared locally. Backend error: ' + error.message, 'warning');
    }
}

// ============================================================================
// DEPLOYMENT FUNCTIONS
// ============================================================================

/**
 * Load and display configuration summary on the Deploy page
 */
async function loadConfigSummary() {
    const summarySection = document.getElementById('config-summary-section');
    const summaryGrid = document.getElementById('config-summary-grid');
    const warningsDiv = document.getElementById('config-summary-warnings');
    
    if (!summarySection || !summaryGrid) return;
    
    try {
        const response = await fetch(`${API_BASE}/config`);
        const data = await response.json();
        
        if (!data.success || !data.config) {
            summarySection.style.display = 'none';
            return;
        }
        
        const config = data.config;
        const deploymentType = config.deployment_type || config.engagement_type || '';
        const deployConfig = DEPLOYMENT_CONFIGS[deploymentType];
        
        if (!deploymentType) {
            summarySection.style.display = 'none';
            return;
        }
        
        // Show the section
        summarySection.style.display = 'block';
        
        // Build summary items
        const summaryItems = [];
        const warnings = [];
        
        // Deployment Type
        summaryItems.push({
            icon: deployConfig?.type === 'goad' ? '🏰' : (deployConfig?.type === 'c2' ? '🎯' : '🔥'),
            label: 'Deployment Type',
            value: deployConfig?.title || deploymentType,
            color: '#7b1fa2'
        });
        
        // Project Name
        if (config.project_name) {
            summaryItems.push({
                icon: '📁',
                label: 'Project Name',
                value: config.project_name,
                color: '#1565c0'
            });
        } else {
            warnings.push('Project name not set');
        }
        
        // Environment
        if (config.environment) {
            summaryItems.push({
                icon: '🏷️',
                label: 'Environment',
                value: config.environment.toUpperCase(),
                color: config.environment === 'prod' ? '#c62828' : (config.environment === 'staging' ? '#f57c00' : '#2e7d32')
            });
        }
        
        // AWS Region
        if (config.aws_region) {
            summaryItems.push({
                icon: '🌍',
                label: 'AWS Region',
                value: config.aws_region,
                color: '#0277bd'
            });
        } else {
            warnings.push('AWS region not set');
        }
        
        // Management CIDR
        const cidrBlocks = config.management_cidr_blocks || [];
        if (cidrBlocks.length > 0) {
            summaryItems.push({
                icon: '🔒',
                label: 'Management CIDR',
                value: cidrBlocks.length === 1 ? cidrBlocks[0] : `${cidrBlocks.length} CIDR blocks`,
                color: '#2e7d32',
                tooltip: cidrBlocks.join(', ')
            });
        } else {
            warnings.push('⚠️ Management CIDR not set - you won\'t be able to access your infrastructure!');
        }
        
        // Key Pair (only for non-GOAD deployments)
        const isGoadOnly = deployConfig?.type === 'goad';
        if (!isGoadOnly) {
            if (config.key_pair_name) {
                summaryItems.push({
                    icon: '🔑',
                    label: 'Key Pair',
                    value: config.key_pair_name,
                    color: '#5d4037'
                });
            } else {
                warnings.push('Key pair name not set (required for C2/Combined)');
            }
        } else {
            summaryItems.push({
                icon: '🔑',
                label: 'SSH Keys',
                value: 'Auto-generated',
                color: '#4CAF50'
            });
        }
        
        // Domain (only for C2/Combined)
        if (deployConfig?.requiresDomain) {
            if (config.primary_domain_name) {
                summaryItems.push({
                    icon: '🌐',
                    label: 'Primary Domain',
                    value: config.primary_domain_name,
                    color: '#1565c0'
                });
            } else {
                warnings.push('Primary domain not configured (required for C2)');
            }
        }
        
        // Estimated Cost
        if (deployConfig?.components) {
            const costComp = deployConfig.components.find(c => c.label.includes('Cost'));
            if (costComp) {
                summaryItems.push({
                    icon: '💰',
                    label: 'Est. Monthly Cost',
                    value: costComp.value,
                    color: '#f57c00'
                });
            }
        }
        
        // Render summary grid
        summaryGrid.innerHTML = summaryItems.map(item => `
            <div style="background: white; padding: 12px; border-radius: 8px; border-left: 4px solid ${item.color};" ${item.tooltip ? `title="${item.tooltip}"` : ''}>
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                    <span style="font-size: 1.2em;">${item.icon}</span>
                    <span style="font-size: 0.8em; color: #666; text-transform: uppercase;">${item.label}</span>
                </div>
                <div style="font-weight: bold; color: #333; font-size: 0.95em; word-break: break-word;">${item.value}</div>
            </div>
        `).join('');
        
        // Render warnings if any
        if (warnings.length > 0) {
            warningsDiv.style.display = 'block';
            warningsDiv.innerHTML = `
                <div style="background: #fff3e0; border: 1px solid #ff9800; border-radius: 6px; padding: 12px;">
                    <div style="font-weight: bold; color: #e65100; margin-bottom: 8px;">⚠️ Configuration Issues:</div>
                    <ul style="margin: 0; padding-left: 20px; color: #bf360c;">
                        ${warnings.map(w => `<li style="margin-bottom: 4px;">${w}</li>`).join('')}
                    </ul>
                </div>
            `;
        } else {
            warningsDiv.style.display = 'none';
        }
        
    } catch (error) {
        console.error('Error loading config summary:', error);
        summarySection.style.display = 'none';
    }
}

let deploymentPollInterval = null;
let isPlanRunning = false;  // Flag to prevent polling from overwriting plan UI

async function checkDeploymentStatus() {
    // First update the deploy page based on selected deployment type
    updateDeployPageForType();
    
    // Immediately check if there's an active deployment
    await checkForActiveDeployment();
    
    // Then start polling
    pollDeploymentStatus();
}

/**
 * Check for active deployment and update UI immediately
 */
async function checkForActiveDeployment() {
    try {
        const response = await fetch(`${API_BASE}/deploy/status`);
        const data = await response.json();
        
        if (data.success && data.status) {
            const status = data.status;
            
            // If there's an active deployment, update UI immediately
            if (status.status === 'running') {
                updateDeploymentUI(status);
                disableDeployButton(true, 'Deployment in progress...');
            } else if (status.status === 'success') {
                updateDeploymentUI(status);
                disableDeployButton(false);
            } else if (status.status === 'error') {
                updateDeploymentUI(status);
                disableDeployButton(false);
            } else {
                // Idle/ready - enable button
                disableDeployButton(false);
            }
        }
    } catch (error) {
        console.error('Error checking deployment status:', error);
    }
}

/**
 * Enable/disable the deploy button
 */
function disableDeployButton(disabled, message = '') {
    const deployBtn = document.querySelector('button[onclick="startDeployment()"]');
    const runPlanBtn = document.querySelector('button[onclick="runPlan()"]');
    
    if (deployBtn) {
        deployBtn.disabled = disabled;
        if (disabled) {
            deployBtn.style.opacity = '0.5';
            deployBtn.style.cursor = 'not-allowed';
            if (message) {
                deployBtn.title = message;
            }
        } else {
            deployBtn.style.opacity = '1';
            deployBtn.style.cursor = 'pointer';
            deployBtn.title = '';
        }
    }
    
    if (runPlanBtn) {
        runPlanBtn.disabled = disabled;
        if (disabled) {
            runPlanBtn.style.opacity = '0.5';
            runPlanBtn.style.cursor = 'not-allowed';
        } else {
            runPlanBtn.style.opacity = '1';
            runPlanBtn.style.cursor = 'pointer';
        }
    }
}

/**
 * Update deployment UI with status
 */
function updateDeploymentUI(status) {
    const statusDiv = document.getElementById('deployment-status');
    const outputDiv = document.getElementById('deployment-output');
    if (!statusDiv) return;
    
    if (status.status === 'running') {
        // Build enhanced status display
        let statusHtml = `
            <div style="margin-bottom: 15px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <strong style="font-size: 1.1em;">🚀 ${status.current_phase || status.step || 'Deploying...'}</strong>
                    <span style="color: #666;">${status.progress_percent || 0}%</span>
                </div>
                
                <!-- Progress Bar -->
                <div style="background: #e0e0e0; border-radius: 10px; height: 8px; overflow: hidden;">
                    <div style="background: linear-gradient(90deg, #4CAF50, #8BC34A); height: 100%; width: ${status.progress_percent || 0}%; transition: width 0.5s ease;"></div>
                </div>
                
                <div style="margin-top: 10px; color: #666; font-size: 0.9em;">
                    ⏱️ Elapsed: ${status.elapsed_formatted || '0m 0s'}
                </div>
            </div>
        `;
        
        // Recent logs
        if (status.logs && status.logs.length > 0) {
            const recentLogs = status.logs.slice(-5);
            statusHtml += `
                <div style="background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 0.85em;">
                    ${recentLogs.map(log => {
                        const time = new Date(log.timestamp * 1000).toLocaleTimeString();
                        const color = log.type === 'error' ? '#f44336' : 
                                      log.type === 'success' ? '#4CAF50' : 
                                      log.type === 'warning' ? '#ff9800' : '#4ec9b0';
                        return `<div style="margin-bottom: 4px;"><span style="color: #888;">[${time}]</span> <span style="color: ${color};">${log.message}</span></div>`;
                    }).join('')}
                </div>
            `;
        }
        
        statusDiv.innerHTML = statusHtml;
        statusDiv.className = 'status-display info';
        
    } else if (status.status === 'success') {
        statusDiv.className = 'status-display success';
        statusDiv.innerHTML = `
            <div style="text-align: center; padding: 20px;">
                <div style="font-size: 3em; margin-bottom: 10px;">🎉</div>
                <h3 style="color: #2e7d32; margin: 0 0 10px 0;">Deployment Complete!</h3>
                <p style="color: #666;">Infrastructure has been successfully deployed.</p>
                <p style="color: #666; font-size: 0.9em;">Elapsed time: ${status.elapsed_formatted || 'Unknown'}</p>
                <div style="margin-top: 15px;">
                    <button class="btn btn-primary" onclick="APP.navigateTo('deployments')">
                        View Deployment Details →
                    </button>
                </div>
            </div>
        `;
        
        // Show post-deployment steps
        const postDeploySteps = document.getElementById('post-deployment-steps');
        if (postDeploySteps) {
            postDeploySteps.style.display = 'block';
        }
        
    } else if (status.status === 'error') {
        const errorLogs = status.logs ? status.logs.filter(log => log.type === 'error') : [];
        
        statusDiv.innerHTML = `
            <div style="padding: 15px;">
                <h3 style="color: #c62828; margin: 0 0 15px 0;">❌ Deployment Failed</h3>
                <p style="color: #666; margin-bottom: 15px;">Elapsed time: ${status.elapsed_formatted}</p>
                ${errorLogs.length > 0 ? `
                    <div style="background: #1a1a2e; color: #e2e8f0; padding: 16px; border-radius: 8px; font-family: 'SF Mono', 'Monaco', 'Menlo', monospace; font-size: 0.9em; line-height: 1.6;">
                        ${errorLogs.map(log => {
                            const time = new Date(log.timestamp * 1000).toLocaleTimeString();
                            return `<div style="margin-bottom: 8px;"><span style="color: #888;">[${time}]</span> <span style="color: #ff6b6b;">${log.message}</span></div>`;
                        }).join('')}
                    </div>
                ` : `
                    <div style="background: #1a1a2e; color: #ff6b6b; padding: 16px; border-radius: 8px; font-family: 'SF Mono', 'Monaco', 'Menlo', monospace; font-size: 0.9em;">
                        ${status.error || 'Unknown error occurred'}
                    </div>
                `}
                <div style="margin-top: 15px;">
                    <button class="btn btn-secondary" onclick="resetPlanAndRetry()" style="margin-right: 10px;">
                        🔄 Try Again
                    </button>
                </div>
            </div>
        `;
        statusDiv.className = 'status-display error';
    }
}

/**
 * Update deploy page UI based on selected deployment type
 */
function updateDeployPageForType() {
    const deployTypeInfo = document.getElementById('deploy-type-info');
    const deployTypeName = document.getElementById('deploy-type-name');
    const deployTypeArch = document.getElementById('deploy-type-arch');
    const deployTypeIcon = document.getElementById('deploy-type-icon');
    const domainPrereqSection = document.getElementById('domain-prereq-section');
    const warningDiv = document.getElementById('deployment-prereq-warning');
    
    // Get the selected deployment type from config
    const deploymentTypeSelect = document.getElementById('deployment-type');
    const deploymentType = deploymentTypeSelect?.value || '';
    const config = DEPLOYMENT_CONFIGS[deploymentType];
    
    if (config && deployTypeInfo) {
        // Show deployment type info
        deployTypeInfo.style.display = 'block';
        deployTypeInfo.style.background = config.color;
        
        if (deployTypeName) deployTypeName.textContent = config.title;
        if (deployTypeArch) deployTypeArch.textContent = config.architectureNote || '';
        
        // Set icon based on type
        if (deployTypeIcon) {
            if (config.type === 'c2') deployTypeIcon.textContent = '🎯';
            else if (config.type === 'goad') deployTypeIcon.textContent = '🏰';
            else deployTypeIcon.textContent = '🔥';
        }
        
        // Show/hide domain prereq based on whether it's required
        if (domainPrereqSection) {
            if (config.requiresDomain) {
                domainPrereqSection.style.display = 'block';
            } else {
                domainPrereqSection.style.display = 'none';
                // For GOAD-only, domain is not required so hide any domain warnings
            }
        }
        
        // Update warning message based on type
        if (warningDiv) {
            if (config.requiresDomain) {
                warningDiv.innerHTML = '<p><strong>⚠️ Prerequisites Missing:</strong> Domain configuration and Cobalt Strike file are required before deployment.</p>';
            } else {
                warningDiv.innerHTML = '<p><strong>⚠️ Prerequisites Missing:</strong> Cobalt Strike file is required before deployment.</p>';
            }
        }
    } else {
        // No deployment type selected
        if (deployTypeInfo) deployTypeInfo.style.display = 'none';
        if (domainPrereqSection) domainPrereqSection.style.display = 'block';
    }
}

function pollDeploymentStatus(projectName = null) {
    const statusDiv = document.getElementById('deployment-status');
    const outputDiv = document.getElementById('deployment-output');
    
    if (!statusDiv) return;
    
    // Clear existing interval
    if (deploymentPollInterval) {
        clearInterval(deploymentPollInterval);
        deploymentPollInterval = null;
    }
    
    // Store project name for polling
    if (projectName) {
        window.currentDeploymentProject = projectName;
    }
    
    // Immediately fetch status once before starting interval
    fetchAndUpdateDeploymentStatus();
    
    // Then poll every 3 seconds
    deploymentPollInterval = setInterval(fetchAndUpdateDeploymentStatus, 3000);
}

/**
 * Fetch deployment status and update UI
 */
async function fetchAndUpdateDeploymentStatus() {
    // Skip polling if a plan is currently running to avoid overwriting the UI
    if (isPlanRunning) {
        return;
    }
    
    try {
        // Build URL with project parameter if we have one
        let url = `${API_BASE}/deploy/status`;
        if (window.currentDeploymentProject) {
            url += `?project=${encodeURIComponent(window.currentDeploymentProject)}`;
        }
        
        const response = await fetch(url);
        const data = await response.json();
            
        // Only update UI if there's an ACTIVE deployment
        // Don't overwrite the "Ready to Deploy" state when idle/no deployment
        if (!data.success || !data.status) {
            disableDeployButton(false);
            return; // No status data, keep current UI
        }
        
        const status = data.status;
                
        // Skip if status is idle or not set - don't overwrite ready state
        if (!status.status || status.status === 'idle' || status.status === 'ready') {
            disableDeployButton(false);
            return;
        }
        
        // Update button state based on deployment status
                if (status.status === 'running') {
            disableDeployButton(true, 'Deployment in progress...');
        } else {
            disableDeployButton(false);
        }
        
        // Use the shared UI update function
        updateDeploymentUI(status);
        
        // Stop polling on completion
        if (status.status === 'success' || status.status === 'error') {
                    clearInterval(deploymentPollInterval);
                    deploymentPollInterval = null;
            // Clear the project tracking
            window.currentDeploymentProject = null;
                }
        
        } catch (error) {
        console.error('Error polling deployment status:', error);
        }
}

async function checkDomainConfig() {
    const statusDiv = document.getElementById('domain-status');
    const domainInfoDiv = document.getElementById('domain-info');
    const domainDetails = document.getElementById('domain-details');
    const deployBtn = document.getElementById('deploy-btn');
    const warningDiv = document.getElementById('deployment-prereq-warning');
    const domainPrereqSection = document.getElementById('domain-prereq-section');
    
    if (!statusDiv) return;
    
    // Check if domain is required based on deployment type
    const deploymentTypeSelect = document.getElementById('deployment-type');
    const deploymentType = deploymentTypeSelect?.value || '';
    const config = DEPLOYMENT_CONFIGS[deploymentType];
    const domainRequired = config ? config.requiresDomain : true;
    
    // If domain not required (GOAD-only), show success and skip check
    if (!domainRequired) {
        statusDiv.innerHTML = `
            <div class="status-display success">
                <p><strong>✅ Not Required</strong> - GOAD labs don't need domain configuration</p>
            </div>
        `;
        if (domainInfoDiv) domainInfoDiv.style.display = 'none';
        return;
    }
    
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
            
            // Check both prerequisites - but domain is only required for certain deployment types
            const deploymentTypeSelect = document.getElementById('deployment-type');
            const deploymentType = deploymentTypeSelect?.value || '';
            const deployConfig = DEPLOYMENT_CONFIGS[deploymentType];
            const requiresDomain = deployConfig?.requiresDomain || false;
            
            let hasDomain = true; // Default to true if domain not required
            if (requiresDomain) {
            const domainCheck = await fetch(`${API_BASE}/health/domain-config`);
            const domainData = await domainCheck.json();
                hasDomain = domainData.success && domainData.configured;
            }
            
            if (deployBtn) {
                // For GOAD-only, just need CS file. For C2/Combined, need both.
                const prereqsMet = requiresDomain ? (data.has_file && hasDomain) : data.has_file;
                if (prereqsMet) {
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
                if (requiresDomain && !hasDomain) missing.push('Domain configuration');
                
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
    // Get the selected deployment type to check requirements
    const deploymentTypeSelect = document.getElementById('deployment-type');
    const deploymentType = deploymentTypeSelect?.value || '';
    const config = DEPLOYMENT_CONFIGS[deploymentType];
    
    // Get project name from config
    const projectNameInput = document.getElementById('project-name');
    const projectName = projectNameInput?.value || '';
    
    if (!projectName) {
        alert('⚠️ Project name is required!\n\nPlease set a project name in the Configuration page.');
        return;
    }
    
    // All deployment types include CS (GOAD has it on jumpbox, C2 has it on team servers)
    const requiresCS = config ? config.requiresCS : true;
    // Only C2 and Combined need domain (for redirector SSL)
    const requiresDomain = config ? config.requiresDomain : true;
    
    const missing = [];
    
    // Check Cobalt Strike file - required for ALL deployments
    if (requiresCS) {
        const fileCheck = await fetch(`${API_BASE}/health/cobalt-strike-file`);
        const fileData = await fileCheck.json();
    if (!fileData.success || !fileData.has_file) {
        missing.push('Cobalt Strike file');
    }
    }
    
    // Only check domain for deployments that require it (C2 and Combined)
    if (requiresDomain) {
        const domainCheck = await fetch(`${API_BASE}/health/domain-config`);
        const domainData = await domainCheck.json();
    if (!domainData.success || !domainData.configured) {
        missing.push('Domain configuration');
        }
    }
    
    if (missing.length > 0) {
        alert(`⚠️ Prerequisites missing!\n\nPlease complete:\n- ${missing.join('\n- ')}`);
        return;
    }
    
    // Customize confirmation message based on deployment type
    const deploymentName = config ? config.title : 'Infrastructure';
    if (!confirm(`Are you sure you want to deploy ${deploymentName}?\n\nProject: ${projectName}\n\nThis will create AWS resources and may incur costs.`)) {
        return;
    }
    
    const statusDiv = document.getElementById('deployment-status');
    const outputDiv = document.getElementById('deployment-output');
    
    // Clear the plan output area when starting deployment
    if (outputDiv) {
        outputDiv.innerHTML = '';
    }
    
    // Show immediate feedback
    statusDiv.innerHTML = `
        <div style="text-align: center; padding: 20px;">
            <div class="spinner" style="margin: 0 auto 15px auto;"></div>
            <p><strong>🚀 Starting Deployment...</strong></p>
            <p style="color: #666; font-size: 0.9em;">Project: ${projectName}</p>
            <p style="color: #666; font-size: 0.9em;">Initializing Terraform workspace and preparing resources...</p>
        </div>
    `;
    statusDiv.className = 'status-display info';
    
    // Disable buttons during deployment
    disableDeployButton(true, 'Deployment starting...');
    
    // Store current project name for polling
    window.currentDeploymentProject = projectName;
    
    try {
        const response = await fetch(`${API_BASE}/deploy/deploy`, { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_name: projectName })
        });
        const data = await response.json();
        
        if (data.success) {
            // Start polling immediately with project name
            pollDeploymentStatus(projectName);
        } else {
            statusDiv.innerHTML = `
                <div style="padding: 15px;">
                    <h3 style="color: #c62828; margin: 0 0 10px 0;">❌ Deployment Failed to Start</h3>
                    <p style="color: #666;">${data.error || 'Unknown error'}</p>
                </div>
            `;
            statusDiv.className = 'status-display error';
            disableDeployButton(false);
        }
    } catch (error) {
        statusDiv.innerHTML = `
            <div style="padding: 15px;">
                <h3 style="color: #c62828; margin: 0 0 10px 0;">❌ Connection Error</h3>
                <p style="color: #666;">${error.message}</p>
            </div>
        `;
        statusDiv.className = 'status-display error';
        disableDeployButton(false);
    }
}

/**
 * Copy error output to clipboard
 */
function copyErrorOutput(button) {
    const container = button.closest('div').parentElement;
    const preElement = container.querySelector('pre');
    const text = preElement ? preElement.textContent : '';
    
    navigator.clipboard.writeText(text).then(() => {
        const originalText = button.textContent;
        button.textContent = '✓ Copied!';
        button.style.background = 'rgba(39, 202, 64, 0.3)';
        setTimeout(() => {
            button.textContent = originalText;
            button.style.background = 'rgba(255,255,255,0.1)';
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
}

/**
 * Copy plan output to clipboard
 */
function copyPlanOutput(button) {
    const container = button.closest('div').parentElement;
    const preElement = container.querySelector('pre');
    const text = preElement ? preElement.textContent : '';
    
    navigator.clipboard.writeText(text).then(() => {
        const originalText = button.textContent;
        button.textContent = '✓ Copied!';
        button.style.background = 'rgba(39, 202, 64, 0.3)';
        setTimeout(() => {
            button.textContent = originalText;
            button.style.background = 'rgba(255,255,255,0.1)';
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
}

/**
 * Reset plan state and retry - called when user clicks "Try Again"
 */
function resetPlanAndRetry() {
    isPlanRunning = false;
    const statusDiv = document.getElementById('deployment-status');
    const outputDiv = document.getElementById('deployment-output');
    
    // Clear the output
    if (outputDiv) outputDiv.innerHTML = '';
    
    // Show initial state briefly then run plan
    if (statusDiv) {
        statusDiv.innerHTML = '<p>Preparing to run plan...</p>';
        statusDiv.className = 'status-display info';
    }
    
    // Small delay then run plan
    setTimeout(() => runPlan(), 500);
}

async function runPlan() {
    const statusDiv = document.getElementById('deployment-status');
    const outputDiv = document.getElementById('deployment-output');
    
    // Set flag to prevent polling from overwriting our UI
    isPlanRunning = true;
    
    // Stage 1: Initial loading state
    let currentStage = 0;
    const stages = [
        { icon: '🔍', text: 'Checking prerequisites...', detail: 'Verifying Terraform and configuration files' },
        { icon: '🔄', text: 'Initializing Terraform...', detail: 'Downloading providers and modules' },
        { icon: '🔐', text: 'Authenticating with AWS...', detail: 'Validating credentials and permissions' },
        { icon: '📊', text: 'Analyzing infrastructure...', detail: 'Computing resource changes' },
        { icon: '📝', text: 'Generating plan...', detail: 'Creating execution plan' }
    ];
    
    function updateLoadingStage(stageIndex) {
        const stage = stages[stageIndex] || stages[stages.length - 1];
        const progressPercent = Math.min(((stageIndex + 1) / stages.length) * 100, 95);
        
        statusDiv.innerHTML = `
            <div style="display: flex; align-items: flex-start; gap: 15px;">
                <div class="spinner" style="flex-shrink: 0; margin-top: 3px;"></div>
                <div style="flex: 1;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                        <span style="font-size: 1.3em;">${stage.icon}</span>
                        <strong>${stage.text}</strong>
                    </div>
                    <div style="font-size: 0.85em; color: #666; margin-bottom: 12px;">${stage.detail}</div>
                    
                    <!-- Progress bar -->
                    <div style="background: #e0e0e0; border-radius: 10px; height: 8px; overflow: hidden; margin-bottom: 10px;">
                        <div style="background: linear-gradient(90deg, #4CAF50, #8BC34A); height: 100%; width: ${progressPercent}%; transition: width 0.5s ease-out; border-radius: 10px;"></div>
                    </div>
                    
                    <!-- Stage indicators -->
                    <div style="display: flex; justify-content: space-between; font-size: 0.75em; color: #888;">
                        ${stages.map((s, i) => `
                            <span style="color: ${i <= stageIndex ? '#4CAF50' : '#ccc'}; font-weight: ${i === stageIndex ? 'bold' : 'normal'};">
                                ${i < stageIndex ? '✓' : (i === stageIndex ? '●' : '○')}
                            </span>
                        `).join('')}
                    </div>
                </div>
            </div>
            <div style="margin-top: 15px; padding: 10px; background: rgba(255,255,255,0.5); border-radius: 6px; font-size: 0.85em; color: #666;">
                <strong>⏱️ Estimated time:</strong> 1-2 minutes depending on your network and AWS region
            </div>
        `;
    statusDiv.className = 'status-display info';
    }
    
    // Start with first stage
    updateLoadingStage(0);
    if (outputDiv) outputDiv.textContent = '';
    
    // Simulate stage progression while waiting for response
    const stageInterval = setInterval(() => {
        currentStage++;
        if (currentStage < stages.length) {
            updateLoadingStage(currentStage);
        }
    }, 2500); // Advance stage every 2.5 seconds
    
    try {
        const response = await fetch(`${API_BASE}/deploy/plan`);
        clearInterval(stageInterval);
        const data = await response.json();
        
        if (data.success) {
            // Plan succeeded - keep showing the result, don't resume polling
            // User needs to see the plan output before deploying
            statusDiv.innerHTML = `
                <div style="display: flex; align-items: center; gap: 12px;">
                    <span style="font-size: 1.5em;">✅</span>
                    <div>
                        <strong style="font-size: 1.1em;">Plan Completed Successfully</strong>
                        <p style="margin: 5px 0 0 0; color: #666; font-size: 0.9em;">Review the output below, then click "Deploy Infrastructure" to apply.</p>
                    </div>
                </div>
            `;
            statusDiv.className = 'status-display success';
            
            // Format output - simple scrollable terminal
            if (outputDiv) {
                const output = data.stdout || 'No changes detected';
                outputDiv.innerHTML = `
                    <div style="margin-top: 15px; background: #1a1a2e; border-radius: 8px; overflow: hidden;">
                        <div style="padding: 10px 15px; background: rgba(0,0,0,0.3); display: flex; justify-content: space-between; align-items: center;">
                            <span style="color: #94a3b8; font-size: 0.85em;">📋 Terraform Plan Output</span>
                            <button onclick="copyPlanOutput(this)" style="padding: 4px 10px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.15); border-radius: 4px; color: #e2e8f0; font-size: 0.75em; cursor: pointer;">Copy</button>
                        </div>
                        <pre style="margin: 0; padding: 15px; font-family: 'SF Mono', 'Monaco', 'Menlo', monospace; font-size: 0.85em; line-height: 1.6; color: #4ade80; white-space: pre-wrap; word-break: break-word;">${escapeHtml(output)}</pre>
                    </div>
                `;
            }
        } else {
            // Handle different error types with helpful messages
            const errorType = data.error_type || 'unknown';
            const helpText = data.help || 'Check the error details below.';
            const errorMsg = data.error || data.stderr || 'Unknown error occurred';
            
            let errorIcon = '❌';
            let errorTitle = 'Plan Failed';
            let actionButtons = '';
            
            switch (errorType) {
                case 'terraform_not_installed':
                    errorIcon = '🔧';
                    errorTitle = 'Terraform Not Installed';
                    actionButtons = `
                        <div style="margin-top: 15px;">
                            <button class="btn btn-info" onclick="APP.navigateTo('aws-check')" style="margin-right: 10px;">
                                Go to Prerequisites
                            </button>
                            <a href="https://developer.hashicorp.com/terraform/downloads" target="_blank" class="btn btn-secondary">
                                Download Terraform
                            </a>
                        </div>
                    `;
                    break;
                case 'config_missing':
                    errorIcon = '⚙️';
                    errorTitle = 'Configuration Missing';
                    actionButtons = `
                        <div style="margin-top: 15px;">
                            <button class="btn btn-primary" onclick="APP.navigateTo('configuration')">
                                Go to Configuration
                            </button>
                        </div>
                    `;
                    break;
                case 'aws_credentials':
                    errorIcon = '🔐';
                    errorTitle = 'AWS Credentials Issue';
                    actionButtons = `
                        <div style="margin-top: 15px;">
                            <button class="btn btn-info" onclick="APP.navigateTo('aws-check')">
                                Check Prerequisites
                            </button>
                        </div>
                        <div style="margin-top: 10px; padding: 10px; background: #fff3cd; border-radius: 6px; font-size: 0.9em;">
                            <strong>Quick Fix:</strong> Run <code style="background: #f5f5f5; padding: 2px 6px; border-radius: 3px;">aws configure</code> in your terminal
                        </div>
                    `;
                    break;
                case 'aws_permissions':
                    errorIcon = '🔑';
                    errorTitle = 'AWS Permissions Issue';
                    actionButtons = `
                        <div style="margin-top: 15px;">
                            <button class="btn btn-info" onclick="APP.navigateTo('aws-check')">
                                Check AWS Permissions
                            </button>
                        </div>
                    `;
                    break;
                case 'init_failed':
                    errorIcon = '🔄';
                    errorTitle = 'Terraform Initialization Failed';
                    break;
                case 'state_lock':
                    errorIcon = '🔒';
                    errorTitle = 'State Locked';
                    actionButtons = `
                        <div style="margin-top: 10px; padding: 10px; background: #fff3cd; border-radius: 6px; font-size: 0.9em;">
                            <strong>Note:</strong> Wait a moment and try again. If the issue persists, you may need to manually unlock the state.
                        </div>
                    `;
                    break;
            }
            
            statusDiv.innerHTML = `
                <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 15px;">
                    <span style="font-size: 1.5em;">${errorIcon}</span>
                    <strong style="font-size: 1.1em;">${errorTitle}</strong>
                </div>
                <p style="color: #666; margin: 0 0 15px 0; font-size: 0.9em;">${helpText}</p>
                ${actionButtons}
                <div style="margin-top: 15px; display: flex; gap: 10px;">
                    <button class="btn btn-secondary" onclick="resetPlanAndRetry()">🔄 Try Again</button>
                </div>
            `;
            statusDiv.className = 'status-display error';
            
            // Show detailed error in output - simple scrollable terminal
            if (outputDiv && (data.stderr || data.error)) {
                outputDiv.innerHTML = `
                    <div style="margin-top: 15px; background: #1a1a2e; border-radius: 8px; overflow: hidden;">
                        <div style="padding: 10px 15px; background: rgba(0,0,0,0.3); display: flex; justify-content: space-between; align-items: center;">
                            <span style="color: #94a3b8; font-size: 0.85em;">📋 Error Output</span>
                            <button onclick="copyErrorOutput(this)" style="padding: 4px 10px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.15); border-radius: 4px; color: #e2e8f0; font-size: 0.75em; cursor: pointer;">Copy</button>
                        </div>
                        <pre style="margin: 0; padding: 15px; font-family: 'SF Mono', 'Monaco', 'Menlo', monospace; font-size: 0.85em; line-height: 1.6; color: #ff6b6b; white-space: pre-wrap; word-break: break-word;">${escapeHtml(data.stderr || data.error)}</pre>
                    </div>
                `;
            }
        }
    } catch (error) {
        clearInterval(stageInterval);
        // Keep isPlanRunning = true so the error message stays visible
        statusDiv.innerHTML = `
            <div style="display: flex; align-items: flex-start; gap: 15px;">
                <span style="font-size: 2em;">⚠️</span>
                <div>
                    <strong>Connection Error</strong>
                    <div style="margin-top: 10px; color: #666;">
                        Could not connect to the backend server. Make sure the server is running.
                    </div>
                    <div style="margin-top: 10px; padding: 10px; background: rgba(255,255,255,0.5); border-radius: 6px; font-size: 0.9em;">
                        <strong>Error:</strong> ${error.message}
                    </div>
                </div>
            </div>
        `;
        statusDiv.className = 'status-display error';
    }
}

async function destroyInfrastructure(projectName = null) {
    // Try to get project name from various sources if not provided
    if (!projectName) {
        const projectNameInput = document.getElementById('project-name');
        projectName = projectNameInput?.value || null;
    }
    
    const projectInfo = projectName ? `\n\nProject: ${projectName}` : '';
    const confirmText = prompt(`Type "DESTROY" to confirm infrastructure destruction:${projectInfo}`);
    if (confirmText !== 'DESTROY') {
        return;
    }
    
    // Use the overview div on the Deployment Manager page
    const overviewDiv = document.getElementById('deployments-overview');
    if (overviewDiv) {
        overviewDiv.innerHTML = `
            <div class="status-display warning">
                <div class="spinner"></div>
                <p><strong>🗑️ Destroying Infrastructure${projectName ? ` (${projectName})` : ''}...</strong></p>
                <p style="font-size: 0.9em; color: #666;">This may take several minutes. Please wait.</p>
            </div>
        `;
    }
    
    // Disable buttons during destruction
    disableDeployButton(true, 'Destruction in progress...');
    
    // Store project name for polling
    if (projectName) {
        window.currentDeploymentProject = projectName;
    }
    
    try {
        const requestBody = { confirm: 'DESTROY' };
        if (projectName) {
            requestBody.project_name = projectName;
        }
        
        const response = await fetch(`${API_BASE}/deploy/destroy`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        
        const data = await response.json();
        
        if (data.success) {
            if (overviewDiv) {
                overviewDiv.innerHTML = `
                    <div class="status-display info">
                        <div class="spinner"></div>
                        <p><strong>🗑️ Destruction in progress${projectName ? ` for ${projectName}` : ''}...</strong></p>
                        <p style="font-size: 0.9em; color: #666;">Terraform is removing all resources. This page will update automatically.</p>
                    </div>
                `;
            }
            // Start polling for destruction status
            pollDestructionStatus(projectName);
        } else {
            if (overviewDiv) {
                overviewDiv.innerHTML = `
                    <div class="status-display error">
                        <p><strong>Error:</strong> ${data.error || 'Unknown error'}</p>
                    </div>
                `;
            }
            disableDeployButton(false);
        }
    } catch (error) {
        if (overviewDiv) {
            overviewDiv.innerHTML = `
                <div class="status-display error">
                    <p><strong>Error:</strong> ${error.message}</p>
                </div>
            `;
        }
        disableDeployButton(false);
    }
}

/**
 * Purge all resources from a failed deployment
 * This is used when deployment fails but leaves resources behind
 * @param {string} projectName - Optional project name to purge (for multi-project support)
 */
async function purgeFailedDeployment(projectName = null) {
    // Get resource count for confirmation message
    const resourceCount = allResources ? allResources.length : 0;
    
    // Try to get project name from various sources if not provided
    if (!projectName) {
        // Check if we have a current deployment project
        projectName = window.currentDeploymentProject;
        
        // If not, try to get from the project name input
        if (!projectName) {
            const projectNameInput = document.getElementById('project-name');
            projectName = projectNameInput?.value || null;
        }
    }
    
    const projectInfo = projectName ? `\nProject: ${projectName}` : '';
    
    const confirmText = prompt(
        `⚠️ PURGE ALL PROJECT RESOURCES?${projectInfo}\n\n` +
        `This will PERMANENTLY DELETE all ${resourceCount} AWS resources associated with this project.\n\n` +
        `Resources to be deleted:\n` +
        `• VPCs, Subnets, Security Groups\n` +
        `• EC2 Instances, EBS Volumes\n` +
        `• NAT Gateways, Elastic IPs\n` +
        `• IAM Roles, S3 Buckets\n` +
        `• All other project resources\n\n` +
        `This CANNOT be undone!\n\n` +
        `Type "PURGE" to confirm:`
    );
    
    if (confirmText !== 'PURGE') {
        return;
    }
    
    const overviewDiv = document.getElementById('deployments-overview');
    
    if (overviewDiv) {
        overviewDiv.innerHTML = `
            <div class="status-display warning" style="padding: 20px;">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <div class="spinner"></div>
                    <div>
                        <p style="margin: 0; font-weight: bold;">🧹 Starting Purge${projectName ? ` for ${projectName}` : ''}...</p>
                        <p style="margin: 5px 0 0 0; font-size: 0.9em; color: #666;">Initializing Terraform to remove all resources...</p>
                    </div>
                </div>
            </div>
        `;
    }
    
    // Disable buttons during purge
    disableDeployButton(true, 'Purge in progress...');
    
    // Store project name for polling
    if (projectName) {
        window.currentDeploymentProject = projectName;
    }
    
    try {
        const requestBody = { confirm: 'PURGE' };
        if (projectName) {
            requestBody.project_name = projectName;
        }
        
        const response = await fetch(`${API_BASE}/deploy/purge`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Start polling for purge status
            pollDestructionStatus(projectName);
        } else {
            if (overviewDiv) {
                overviewDiv.innerHTML = `
                    <div class="status-display error">
                        <p><strong>Error:</strong> ${data.error || 'Unknown error'}</p>
                    </div>
                `;
            }
            disableDeployButton(false);
        }
    } catch (error) {
        if (overviewDiv) {
            overviewDiv.innerHTML = `
                <div class="status-display error">
                    <p><strong>Error:</strong> ${error.message}</p>
                </div>
            `;
        }
        disableDeployButton(false);
    }
}

/**
 * Poll for destruction status
 * @param {string} projectName - Optional project name for multi-project support
 */
function pollDestructionStatus(projectName = null) {
    const pollInterval = setInterval(async () => {
        try {
            // Build URL with project parameter if we have one
            let url = `${API_BASE}/deploy/status`;
            if (projectName || window.currentDeploymentProject) {
                const project = projectName || window.currentDeploymentProject;
                url += `?project=${encodeURIComponent(project)}`;
            }
            
            const response = await fetch(url);
            const data = await response.json();
            
            if (data.success && data.status) {
                const status = data.status;
                const overviewDiv = document.getElementById('deployments-overview');
                
                if (status.status === 'running') {
                    // Still destroying - show progress with logs
                    if (overviewDiv) {
                        // Build logs HTML
                        let logsHtml = '';
                        if (status.logs && status.logs.length > 0) {
                            const recentLogs = status.logs.slice(-8);
                            logsHtml = `
                                <div style="background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 0.85em; margin-top: 15px; max-height: 200px; overflow-y: auto;">
                                    ${recentLogs.map(log => {
                                        const time = new Date(log.timestamp * 1000).toLocaleTimeString();
                                        const color = log.type === 'error' ? '#f44336' : 
                                                      log.type === 'success' ? '#4CAF50' : 
                                                      log.type === 'warning' ? '#ff9800' : '#4ec9b0';
                                        return `<div style="margin-bottom: 4px;"><span style="color: #888;">[${time}]</span> <span style="color: ${color};">${log.message}</span></div>`;
                                    }).join('')}
                                </div>
                            `;
                        }
                        
                        overviewDiv.innerHTML = `
                            <div class="status-display warning" style="padding: 20px;">
                                <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 10px;">
                                    <div class="spinner"></div>
                                    <div>
                                        <p style="margin: 0; font-weight: bold;">🧹 ${status.step || 'Purging resources...'}</p>
                                        <p style="margin: 5px 0 0 0; font-size: 0.9em; color: #666;">
                                            Progress: ${status.progress_percent || 0}% • Elapsed: ${status.elapsed_formatted || '0m 0s'}
                                        </p>
                                    </div>
                                </div>
                                ${logsHtml}
                            </div>
                        `;
                    }
                } else if (status.status === 'success') {
                    // Destruction complete
                    clearInterval(pollInterval);
                    disableDeployButton(false);
                    if (overviewDiv) {
                        overviewDiv.innerHTML = `
                            <div class="status-display success">
                                <p><strong>✅ Resources Purged Successfully</strong></p>
                                <p style="font-size: 0.9em; color: #666;">All resources have been removed. You can now deploy fresh infrastructure.</p>
                                <p style="margin-top: 15px;">
                                    <button class="btn btn-success" onclick="APP.navigateTo('deployment')">
                                        Deploy New Infrastructure →
                                    </button>
                                </p>
                            </div>
                        `;
                    }
                    // Refresh the page to update all sections
                    setTimeout(() => {
                        refreshDeployments();
                        loadResourceList();
                        renderDeploymentTimeline();
                    }, 2000);
                } else if (status.status === 'error') {
                    // Destruction failed
                    clearInterval(pollInterval);
                    disableDeployButton(false);
                    
                    // Build ALL logs (not just errors) to show full context
                    let allLogsHtml = '';
                    if (status.logs && status.logs.length > 0) {
                        allLogsHtml = `
                            <div style="background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 0.85em; margin-top: 15px; max-height: 300px; overflow-y: auto;">
                                ${status.logs.map(log => {
                                    const time = new Date(log.timestamp * 1000).toLocaleTimeString();
                                    const color = log.type === 'error' ? '#ff6b6b' : 
                                                  log.type === 'success' ? '#4CAF50' : 
                                                  log.type === 'warning' ? '#ff9800' : '#4ec9b0';
                                    return `<div style="margin-bottom: 4px; ${log.type === 'error' ? 'background: #3d1f1f; padding: 4px; border-radius: 3px;' : ''}"><span style="color: #888;">[${time}]</span> <span style="color: ${color};">${log.message}</span></div>`;
                                }).join('')}
                            </div>
                        `;
                    }
                    
                    if (overviewDiv) {
                        overviewDiv.innerHTML = `
                            <div class="status-display error" style="padding: 20px;">
                                <p><strong>❌ Purge Failed</strong></p>
                                <p style="font-size: 0.9em; color: #666;">${status.error || 'Unknown error occurred'}</p>
                                ${allLogsHtml}
                                <p style="margin-top: 15px;">
                                    <button class="btn btn-secondary" onclick="refreshDeployments()" style="margin-right: 10px;">
                                        🔄 Refresh Status
                                    </button>
                                    <button class="btn" onclick="purgeFailedDeployment()" style="background: #ff5722; color: white;">
                                        🧹 Try Again
                                    </button>
                                </p>
                            </div>
                        `;
                    }
                } else {
                    // Idle or unknown - stop polling
                    clearInterval(pollInterval);
                    disableDeployButton(false);
                    refreshDeployments();
                }
            }
        } catch (error) {
            console.error('Error polling destruction status:', error);
        }
    }, 3000); // Poll every 3 seconds
}

/**
 * Stop all EC2 instances (keep resources, stop compute charges)
 */
async function stopInfrastructure() {
    const confirmStop = confirm(
        '⏸️ Stop Infrastructure?\n\n' +
        'This will STOP all EC2 instances but keep all resources.\n\n' +
        '✅ Saves ~90% on compute costs\n' +
        '⚠️ Storage, Elastic IPs, NAT Gateway still billed\n' +
        '💾 All data and configuration preserved\n\n' +
        'You can restart anytime.'
    );
    
    if (!confirmStop) return;
    
    const overviewDiv = document.getElementById('deployments-overview');
    overviewDiv.innerHTML = `
        <div class="status-display warning">
            <div class="spinner"></div>
            <p>Stopping all EC2 instances...</p>
        </div>
    `;
    
    try {
        const response = await fetch(`${API_BASE}/deploy/stop`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (data.success) {
            overviewDiv.innerHTML = `
                <div class="status-display success">
                    <p><strong>✅ Infrastructure Stopped</strong></p>
                    <p>${data.stopped_count || 'All'} instances have been stopped.</p>
                    <p style="font-size: 0.9em; color: #666; margin-top: 10px;">
                        Storage and network resources are still active. Click "Start All Instances" to resume.
                    </p>
                </div>
            `;
            // Refresh to show updated status
            setTimeout(() => refreshDeployments(), 2000);
        } else {
            overviewDiv.innerHTML = `
                <div class="status-display error">
                    <p><strong>Error stopping instances:</strong> ${data.error || 'Unknown error'}</p>
                </div>
            `;
        }
    } catch (error) {
        overviewDiv.innerHTML = `
            <div class="status-display error">
                <p><strong>Error:</strong> ${error.message}</p>
            </div>
        `;
    }
}

/**
 * Start all stopped EC2 instances
 */
async function startInfrastructure() {
    const confirmStart = confirm(
        '▶️ Start Infrastructure?\n\n' +
        'This will START all stopped EC2 instances.\n\n' +
        '🔄 All instances will be brought online\n' +
        '⏱️ Takes ~2-5 minutes to fully boot\n' +
        '💰 Compute charges will resume'
    );
    
    if (!confirmStart) return;
    
    const overviewDiv = document.getElementById('deployments-overview');
    overviewDiv.innerHTML = `
        <div class="status-display info">
            <div class="spinner"></div>
            <p>Starting all EC2 instances...</p>
        </div>
    `;
    
    try {
        const response = await fetch(`${API_BASE}/deploy/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (data.success) {
            overviewDiv.innerHTML = `
                <div class="status-display success">
                    <p><strong>✅ Infrastructure Starting</strong></p>
                    <p>${data.started_count || 'All'} instances are starting up.</p>
                    <p style="font-size: 0.9em; color: #666; margin-top: 10px;">
                        Instances will be fully available in 2-5 minutes. Refreshing status...
                    </p>
                </div>
            `;
            // Refresh to show updated status
            setTimeout(() => refreshDeployments(), 5000);
        } else {
            overviewDiv.innerHTML = `
                <div class="status-display error">
                    <p><strong>Error starting instances:</strong> ${data.error || 'Unknown error'}</p>
                </div>
            `;
        }
    } catch (error) {
        overviewDiv.innerHTML = `
            <div class="status-display error">
                <p><strong>Error:</strong> ${error.message}</p>
            </div>
        `;
    }
}

/**
 * Stop EC2 instances for a specific project
 */
async function stopDeploymentResources(projectName) {
    if (!projectName) {
        alert('Project name is required');
        return;
    }
    
    const confirmStop = confirm(
        `⏸️ Stop EC2 Instances for "${projectName}"?\n\n` +
        'This will STOP all EC2 instances for this project.\n\n' +
        '✅ Saves ~90% on compute costs\n' +
        '⚠️ Storage, Elastic IPs, NAT Gateway still billed\n' +
        '💾 All data and configuration preserved\n\n' +
        'You can restart anytime.'
    );
    
    if (!confirmStop) return;
    
    try {
        const response = await fetch(`${API_BASE}/deploy/stop`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_name: projectName })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(`✅ Stopped ${data.stopped_count || 'all'} EC2 instances for project "${projectName}"`);
            // Refresh resources
            refreshDeployments();
        } else {
            alert(`❌ Error stopping instances: ${data.error || 'Unknown error'}`);
        }
    } catch (error) {
        alert(`❌ Error: ${error.message}`);
    }
}

// Make stopDeploymentResources available globally for onclick handlers
window.stopDeploymentResources = stopDeploymentResources;

/**
 * Start EC2 instances for a specific project
 */
async function startDeploymentResources(projectName) {
    if (!projectName) {
        alert('Project name is required');
        return;
    }
    
    const confirmStart = confirm(
        `▶️ Start EC2 Instances for "${projectName}"?\n\n` +
        'This will START all stopped EC2 instances.\n\n' +
        '🔄 All instances will be brought online\n' +
        '⏱️ Takes ~2-5 minutes to fully boot\n' +
        '💰 Compute charges will resume'
    );
    
    if (!confirmStart) return;
    
    try {
        const response = await fetch(`${API_BASE}/deploy/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_name: projectName })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(`✅ Started ${data.started_count || 'all'} EC2 instances for project "${projectName}"`);
            // Refresh resources
            refreshDeployments();
        } else {
            alert(`❌ Error starting instances: ${data.error || 'Unknown error'}`);
        }
    } catch (error) {
        alert(`❌ Error: ${error.message}`);
    }
}

// Make startDeploymentResources available globally for onclick handlers
window.startDeploymentResources = startDeploymentResources;

/**
 * Destroy infrastructure for a specific project
 */
async function destroyDeployment(projectName) {
    if (!projectName) {
        alert('Project name is required');
        return;
    }
    
    const confirmDestroy = confirm(
        `🗑️ DESTROY Infrastructure for "${projectName}"?\n\n` +
        '⚠️ WARNING: This will PERMANENTLY DELETE:\n' +
        '• All EC2 instances\n' +
        '• All VPCs and networking\n' +
        '• All storage (S3 buckets)\n' +
        '• All security groups\n' +
        '• All other AWS resources\n\n' +
        '❌ This action CANNOT be undone!\n\n' +
        'Type "DESTROY" in the next prompt to confirm.'
    );
    
    if (!confirmDestroy) return;
    
    const confirmText = prompt('Type "DESTROY" to confirm:');
    if (confirmText !== 'DESTROY') {
        alert('Destruction cancelled.');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/deploy/destroy`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                project_name: projectName,
                confirm: 'DESTROY'
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(`🗑️ Destruction started for project "${projectName}". This may take several minutes.`);
            // Start polling for destruction status
            pollDestructionStatus(projectName);
        } else {
            alert(`❌ Error: ${data.error || 'Unknown error'}`);
        }
    } catch (error) {
        alert(`❌ Error: ${error.message}`);
    }
}

// Make destroyDeployment available globally for onclick handlers
window.destroyDeployment = destroyDeployment;

/**
 * Load connection info for a specific project
 */
async function loadConnectionInfo(projectName, sessionId) {
    if (!projectName) return;
    
    const contentDiv = document.getElementById(`${sessionId}-connection-content`);
    if (!contentDiv) return;
    
    contentDiv.innerHTML = '<div class="spinner" style="margin: 10px auto;"></div> Loading connection details...';
    
    try {
        // Fetch Terraform outputs for this project
        const response = await fetch(`${API_BASE}/deploy/outputs?project=${encodeURIComponent(projectName)}`);
        const data = await response.json();
        
        if (data.success && data.outputs) {
            const outputs = data.outputs;
            const keyName = outputs.jumpbox_key_name || `${projectName}-goadmini-jumpbox-key`;
            
            // Build connection info HTML
            let html = '<div style="font-size: 0.95em;">';
            
            // SSH Key Download Button (always show first)
            html += `
                <div style="margin-bottom: 15px; padding: 12px; background: #fff8e1; border-radius: 6px; border-left: 4px solid #ffc107;">
                    <div style="font-weight: 600; color: #f57c00; margin-bottom: 8px;">🔑 SSH Key Setup</div>
                    <div style="margin-bottom: 10px; font-size: 0.9em; color: #666;">
                        Before connecting, you need to download the SSH key to your <code>~/.ssh</code> directory.
                    </div>
                    <button onclick="downloadSSHKey('${projectName}', 'jumpbox')" 
                            style="background: #ff9800; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: 500; margin-right: 10px;">
                        📥 Download SSH Key to ~/.ssh
                    </button>
                    <span id="ssh-key-status-${sessionId}" style="font-size: 0.85em; color: #666;"></span>
                </div>
            `;
            
            // Jumpbox SSH
            if (outputs.jumpbox_public_ip) {
                const sshCommand = `ssh -i ~/.ssh/${keyName}.pem ubuntu@${outputs.jumpbox_public_ip}`;
                const escapedSshCommand = sshCommand.replace(/'/g, "\\'");
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: #e8f5e9; border-radius: 6px; border-left: 4px solid #4CAF50;">
                        <div style="font-weight: 600; color: #2e7d32; margin-bottom: 8px;">🖥️ Jumpbox SSH Access</div>
                        <div style="margin-bottom: 5px;"><strong>Public IP:</strong> <code style="background: #fff; padding: 2px 6px; border-radius: 3px;">${outputs.jumpbox_public_ip}</code></div>
                        <div style="margin-bottom: 8px;"><strong>User:</strong> <code style="background: #fff; padding: 2px 6px; border-radius: 3px;">ubuntu</code></div>
                        <div style="position: relative; background: #1e1e1e; border-radius: 4px; overflow: hidden;">
                            <button onclick="copyToClipboard('${escapedSshCommand}', this)" 
                                    style="position: absolute; top: 8px; right: 8px; background: #333; color: #ccc; border: 1px solid #555; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 0.75em; z-index: 10;">
                                📋 Copy
                            </button>
                            <div style="color: #4ec9b0; padding: 12px; padding-right: 80px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.95em; overflow-x: auto; white-space: nowrap;">
                                ${sshCommand}
                            </div>
                        </div>
                    </div>
                `;
            }
            
            // Windows RDP via Jumpbox
            if (outputs.dc01_private_ip) {
                const tunnelCommand = `ssh -i ~/.ssh/${keyName}.pem -L 3389:${outputs.dc01_private_ip}:3389 ubuntu@${outputs.jumpbox_public_ip}`;
                const escapedTunnelCommand = tunnelCommand.replace(/'/g, "\\'");
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: #e3f2fd; border-radius: 6px; border-left: 4px solid #2196F3;">
                        <div style="font-weight: 600; color: #1565c0; margin-bottom: 8px;">🪟 Windows DC01 (via Jumpbox)</div>
                        <div style="margin-bottom: 5px;"><strong>Private IP:</strong> <code style="background: #fff; padding: 2px 6px; border-radius: 3px;">${outputs.dc01_private_ip}</code></div>
                        <div style="margin-bottom: 8px;"><strong>Access:</strong> RDP through SSH tunnel</div>
                        <div style="position: relative; background: #1e1e1e; border-radius: 4px; overflow: hidden;">
                            <button onclick="copyToClipboard('${escapedTunnelCommand}', this)" 
                                    style="position: absolute; top: 8px; right: 8px; background: #333; color: #ccc; border: 1px solid #555; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 0.75em; z-index: 10;">
                                📋 Copy
                            </button>
                            <div style="color: #4ec9b0; padding: 12px; padding-right: 80px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.95em; overflow-x: auto;">
                                <div style="color: #6a9955; margin-bottom: 4px;"># SSH tunnel for RDP</div>
                                <div style="white-space: nowrap;">${tunnelCommand}</div>
                            </div>
                        </div>
                        <div style="margin-top: 8px; font-size: 0.9em; color: #666;">Then connect RDP to <code style="background: #f5f5f5; padding: 2px 6px; border-radius: 3px;">localhost:3389</code></div>
                    </div>
                `;
            }
            
            // Team Server (if exists - Full C2 mode with public team server)
            if (outputs.team_server_public_ip) {
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: #fce4ec; border-radius: 6px; border-left: 4px solid #e91e63;">
                        <div style="font-weight: 600; color: #c2185b; margin-bottom: 8px;">🎯 Cobalt Strike Team Server (Direct)</div>
                        <div style="margin-bottom: 5px;"><strong>Public IP:</strong> <code style="background: #fff; padding: 2px 6px; border-radius: 3px;">${outputs.team_server_public_ip}</code></div>
                        <div style="margin-bottom: 8px;"><strong>Port:</strong> <code style="background: #fff; padding: 2px 6px; border-radius: 3px;">50050</code></div>
                        <div style="font-size: 0.9em; color: #666;">Connect your CS Client directly to this IP:port</div>
                    </div>
                `;
            }
            
            // Team Server (GOAD mode - internal Team Server)
            if (outputs.teamserver_private_ip) {
                const teamserverSshCommand = `ssh ubuntu@${outputs.teamserver_private_ip}`;
                const escapedTeamserverSshCommand = teamserverSshCommand.replace(/'/g, "\\'");
                
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: #ffebee; border-radius: 6px; border-left: 4px solid #f44336;">
                        <div style="font-weight: 600; color: #c62828; margin-bottom: 8px;">🔴 CS Team Server (Ubuntu)</div>
                        <div style="margin-bottom: 5px;"><strong>Private IP:</strong> <code style="background: #fff; padding: 2px 6px; border-radius: 3px;">${outputs.teamserver_private_ip}</code></div>
                        <div style="margin-bottom: 5px;"><strong>CS Port:</strong> <code style="background: #fff; padding: 2px 6px; border-radius: 3px;">50050</code></div>
                        <div style="margin-bottom: 10px; font-size: 0.9em; color: #666;">
                            Runs Cobalt Strike Team Server ONLY. Access via Jumpbox or from Windows Attack Box.
                        </div>
                        
                        <div style="font-weight: 500; color: #333; margin-bottom: 6px; font-size: 0.9em;">SSH to Team Server (from Jumpbox):</div>
                        <div style="position: relative; background: #1e1e1e; border-radius: 4px; overflow: hidden;">
                            <button onclick="copyToClipboard('${escapedTeamserverSshCommand}', this)" 
                                    style="position: absolute; top: 8px; right: 8px; background: #333; color: #ccc; border: 1px solid #555; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 0.75em; z-index: 10;">
                                📋 Copy
                            </button>
                            <div style="color: #4ec9b0; padding: 12px; padding-right: 80px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.95em;">
                                ${teamserverSshCommand}
                            </div>
                        </div>
                    </div>
                `;
            }
            
            // Windows Attack Box (GOAD + CS mode - Windows workstation with CS Client + Tools)
            if (outputs.attackbox_private_ip) {
                const rdpTunnelCommand = `ssh -i ~/.ssh/${keyName}.pem -L 3389:${outputs.attackbox_private_ip}:3389 ubuntu@${outputs.jumpbox_public_ip}`;
                const escapedRdpTunnelCommand = rdpTunnelCommand.replace(/'/g, "\\'");
                const localCsTunnelCommand = `ssh -i ~/.ssh/${keyName}.pem -L 50050:192.168.56.40:50050 ubuntu@${outputs.jumpbox_public_ip}`;
                const escapedLocalCsTunnelCommand = localCsTunnelCommand.replace(/'/g, "\\'");
                
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: #e8f5e9; border-radius: 6px; border-left: 4px solid #4CAF50;">
                        <div style="font-weight: 600; color: #2e7d32; margin-bottom: 8px;">🖥️ Windows Attack Box (CS Client + Tools)</div>
                        <div style="margin-bottom: 5px;"><strong>Private IP:</strong> <code style="background: #fff; padding: 2px 6px; border-radius: 3px;">${outputs.attackbox_private_ip}</code></div>
                        <div style="margin-bottom: 5px;"><strong>OS:</strong> <code style="background: #fff; padding: 2px 6px; border-radius: 3px;">Windows Server 2019</code></div>
                        <div style="margin-bottom: 5px;"><strong>Login:</strong> <code style="background: #fff; padding: 2px 6px; border-radius: 3px;">Administrator / AttackB0x!2024</code></div>
                        <div style="margin-bottom: 10px; font-size: 0.9em; color: #666;">
                            Your attack workstation with CS Client, PowerSploit, and WSL2 for SSH.
                        </div>
                        
                        <div style="font-weight: 500; color: #333; margin-bottom: 6px; font-size: 0.9em;">🔗 RDP to Attack Box (SSH Tunnel from your machine):</div>
                        <div style="position: relative; background: #1e1e1e; border-radius: 4px; overflow: hidden; margin-bottom: 12px;">
                            <button onclick="copyToClipboard('${escapedRdpTunnelCommand}', this)" 
                                    style="position: absolute; top: 8px; right: 8px; background: #333; color: #ccc; border: 1px solid #555; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 0.75em; z-index: 10;">
                                📋 Copy
                            </button>
                            <div style="color: #4ec9b0; padding: 12px; padding-right: 80px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.85em; overflow-x: auto;">
                                <div style="color: #6a9955; margin-bottom: 4px;"># Step 1: Create RDP tunnel (run on your local machine)</div>
                                <div style="white-space: nowrap; margin-bottom: 8px;">${rdpTunnelCommand}</div>
                                <div style="color: #6a9955; margin-bottom: 4px;"># Step 2: RDP to localhost:3389</div>
                                <div style="color: #6a9955;"># Login: Administrator / AttackB0x!2024</div>
                            </div>
                        </div>
                        
                        <div style="padding: 10px; background: #fff; border-radius: 4px; font-size: 0.85em;">
                            <div style="font-weight: 500; margin-bottom: 8px;">📦 Pre-installed Tools:</div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; color: #666;">
                                <div>• PowerSploit (C:\\Tools\\PowerSploit)</div>
                                <div>• WSL2 Ubuntu (ssh teamserver)</div>
                                <div>• PowerView, PowerUp</div>
                                <div>• Git, VS Code, Python</div>
                            </div>
                        </div>
                        
                        <div style="margin-top: 10px; padding: 8px; background: #e3f2fd; border-radius: 4px; font-size: 0.85em; color: #1565c0;">
                            <strong>💡 Workflow:</strong> RDP to Attack Box → Open WSL → <code>ssh teamserver</code> to connect to CS Team Server
                        </div>
                    </div>
                `;
                
                // LOCAL CS Client option (run CS from user's local machine)
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: #f3e5f5; border-radius: 6px; border-left: 4px solid #9c27b0;">
                        <div style="font-weight: 600; color: #7b1fa2; margin-bottom: 8px;">💻 Run CS Client from YOUR Local Machine</div>
                        <div style="margin-bottom: 10px; font-size: 0.9em; color: #666;">
                            Prefer to run Cobalt Strike Client on your own machine? Use SSH tunneling:
                        </div>
                        
                        <div style="font-weight: 500; color: #333; margin-bottom: 6px; font-size: 0.9em;">🔗 Option 1: SSH Tunnel to Team Server (Recommended)</div>
                        <div style="position: relative; background: #1e1e1e; border-radius: 4px; overflow: hidden; margin-bottom: 12px;">
                            <button onclick="copyToClipboard('${escapedLocalCsTunnelCommand}', this)" 
                                    style="position: absolute; top: 8px; right: 8px; background: #333; color: #ccc; border: 1px solid #555; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 0.75em; z-index: 10;">
                                📋 Copy
                            </button>
                            <div style="color: #4ec9b0; padding: 12px; padding-right: 80px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.85em; overflow-x: auto;">
                                <div style="color: #6a9955; margin-bottom: 4px;"># Step 1: Create SSH tunnel to Team Server (run on your local machine)</div>
                                <div style="white-space: nowrap; margin-bottom: 8px;">${localCsTunnelCommand}</div>
                                <div style="color: #6a9955; margin-bottom: 4px;"># Step 2: Keep terminal open, then launch your local CS Client</div>
                                <div style="color: #6a9955;"># Step 3: Connect CS Client to: localhost:50050</div>
                            </div>
                        </div>
                        
                        <div style="padding: 10px; background: #fff; border-radius: 4px; font-size: 0.85em; margin-bottom: 10px;">
                            <div style="font-weight: 500; margin-bottom: 6px; color: #333;">📋 Quick Steps:</div>
                            <ol style="margin: 0; padding-left: 20px; color: #666; line-height: 1.6;">
                                <li>Run the SSH tunnel command above (keep terminal open)</li>
                                <li>Launch Cobalt Strike on your local machine</li>
                                <li>Connect to: <code style="background: #f5f5f5; padding: 1px 4px; border-radius: 2px;">localhost:50050</code></li>
                                <li>Use the team server password you configured</li>
                            </ol>
                        </div>
                        
                        <div style="padding: 8px; background: #fff3e0; border-radius: 4px; font-size: 0.8em; color: #e65100;">
                            <strong>⚠️ Note:</strong> You must have Cobalt Strike installed locally. The tunnel forwards port 50050 from the Team Server through the Jumpbox to your machine.
                        </div>
                    </div>
                `;
            }
            
            // Redirector (if exists)
            if (outputs.redirector_public_ip) {
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: #fff3e0; border-radius: 6px; border-left: 4px solid #ff9800;">
                        <div style="font-weight: 600; color: #e65100; margin-bottom: 8px;">🔀 HTTPS Redirector</div>
                        <div style="margin-bottom: 5px;"><strong>Public IP:</strong> <code style="background: #fff; padding: 2px 6px; border-radius: 3px;">${outputs.redirector_public_ip}</code></div>
                        <div style="margin-bottom: 5px;"><strong>Domain:</strong> <code style="background: #fff; padding: 2px 6px; border-radius: 3px;">${outputs.redirector_domain || 'N/A'}</code></div>
                    </div>
                `;
            }
            
            // Key file location info
            html += `
                <div style="padding: 10px; background: #f5f5f5; border-radius: 6px; margin-top: 10px;">
                    <div style="font-weight: 500; margin-bottom: 5px;">📁 Key Files Location</div>
                    <code style="font-size: 0.9em; color: #666;">~/.ssh/${keyName}.pem</code>
                    <div style="margin-top: 5px; font-size: 0.85em; color: #888;">
                        The key file permissions are automatically set to 600 when downloaded.
                    </div>
                </div>
            `;
            
            html += '</div>';
            contentDiv.innerHTML = html;
        } else {
            contentDiv.innerHTML = `<div style="color: #666;">No connection details available. ${data.error || ''}</div>`;
        }
    } catch (error) {
        contentDiv.innerHTML = `<div style="color: #f44336;">Error loading connection info: ${error.message}</div>`;
    }
}

// Make loadConnectionInfo available globally for onclick handlers
window.loadConnectionInfo = loadConnectionInfo;

/**
 * Copy text to clipboard
 */
function copyToClipboard(text, button) {
    // Handle both direct text and event-based calls
    let textToCopy = text;
    let buttonElement = button;
    
    // If called from onclick with just text, button will be the element
    if (typeof text === 'string' && button && button.tagName) {
        textToCopy = text;
        buttonElement = button;
    }
    
    navigator.clipboard.writeText(textToCopy).then(() => {
        if (buttonElement && buttonElement.innerHTML !== undefined) {
            const originalText = buttonElement.innerHTML;
            buttonElement.innerHTML = '✅ Copied!';
            buttonElement.style.background = '#4CAF50';
            buttonElement.style.color = 'white';
            setTimeout(() => {
                buttonElement.innerHTML = originalText;
                buttonElement.style.background = '#333';
                buttonElement.style.color = '#ccc';
            }, 2000);
        }
    }).catch(err => {
        console.error('Failed to copy:', err);
        alert('Failed to copy to clipboard. Please copy manually.');
    });
}

// Make copyToClipboard available globally for onclick handlers
window.copyToClipboard = copyToClipboard;

/**
 * Download SSH key to ~/.ssh directory
 */
async function downloadSSHKey(projectName, keyType = 'jumpbox') {
    try {
        const response = await fetch(`${API_BASE}/deploy/ssh-key/download`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_name: projectName,
                key_type: keyType
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(`✅ SSH Key saved successfully!\n\nPath: ${data.path}\n\nYou can now use the SSH commands above.`);
        } else {
            alert(`❌ Failed to download SSH key:\n${data.error}`);
        }
    } catch (error) {
        alert(`❌ Error: ${error.message}`);
    }
}

/**
 * Copy GOAD step 1 command with project-specific key name
 */
function copyGoadStep1(projectName) {
    const command = `ssh -i ~/.ssh/${projectName}-goadmini-jumpbox-key.pem ubuntu@<JUMPBOX_IP>`;
    navigator.clipboard.writeText(command).then(() => {
        alert('✅ Copied! Remember to replace <JUMPBOX_IP> with the actual IP from Connection Info.');
    }).catch(err => {
        console.error('Failed to copy:', err);
        alert('Failed to copy to clipboard');
    });
}

// Make functions available globally for onclick handlers
window.copyGoadStep1 = copyGoadStep1;
window.downloadSSHKey = downloadSSHKey;

/**
 * Load credentials for a specific project
 */
async function loadCredentials(projectName, sessionId) {
    if (!projectName) return;
    
    const contentDiv = document.getElementById(`${sessionId}-credentials-content`);
    if (!contentDiv) return;
    
    contentDiv.innerHTML = '<div class="spinner" style="margin: 10px auto;"></div> Loading credentials...';
    
    try {
        const response = await fetch(`${API_BASE}/goad/credentials`);
        const data = await response.json();
        
        let creds;
        
        if (data.success && data.credentials) {
            creds = data.credentials;
        } else {
            // If no deployment marker found, show default GOAD-Mini credentials
            // This is common when infrastructure is deployed but Ansible hasn't run yet
            creds = getDefaultGoadCredentials(projectName);
        }
        
        let html = '<div style="font-size: 0.95em;">';
        
        // Lab Info
        if (creds.lab_name) {
            html += `
                <div style="margin-bottom: 10px; padding: 8px 12px; background: #e8eaf6; border-radius: 6px;">
                    <strong>Lab:</strong> ${creds.lab_display_name || creds.lab_name}
                </div>
            `;
        }
        
        // Default Password
        if (creds.default_password) {
            html += `
                <div style="margin-bottom: 15px; padding: 12px; background: #fff3e0; border-radius: 6px; border-left: 4px solid #ff9800;">
                    <div style="font-weight: 600; color: #e65100; margin-bottom: 8px;">🔐 Default Password</div>
                    <code style="background: #1e1e1e; color: #4ec9b0; padding: 10px 14px; border-radius: 4px; display: inline-block; font-size: 1.2em; font-family: 'SF Mono', Monaco, Consolas, monospace;">${creds.default_password}</code>
                    <div style="margin-top: 8px; font-size: 0.85em; color: #666;">Used for most AD accounts unless specified otherwise</div>
                </div>
            `;
        }
        
        // Default Users (Local Admin)
        if (creds.default_users && creds.default_users.length > 0) {
            html += `
                <div style="margin-bottom: 15px; padding: 12px; background: #ffebee; border-radius: 6px; border-left: 4px solid #f44336;">
                    <div style="font-weight: 600; color: #c62828; margin-bottom: 8px;">👤 Local Accounts</div>
                    <div style="display: grid; gap: 6px;">
            `;
            for (const user of creds.default_users) {
                html += `
                    <div style="background: white; padding: 8px; border-radius: 4px;">
                        <div><strong>${user.domain}:</strong> <code style="font-size: 1em;">${user.username}</code> / <code style="font-size: 1em;">${user.password}</code></div>
                        ${user.note ? `<div style="font-size: 0.85em; color: #666;">${user.note}</div>` : ''}
                    </div>
                `;
            }
            html += '</div></div>';
        }
        
        // Domain Admins
        if (creds.domain_admins && creds.domain_admins.length > 0) {
            html += `
                <div style="margin-bottom: 15px; padding: 12px; background: #e8f5e9; border-radius: 6px; border-left: 4px solid #4CAF50;">
                    <div style="font-weight: 600; color: #2e7d32; margin-bottom: 8px;">👑 Domain Admins</div>
                    <div style="display: grid; gap: 8px;">
            `;
            for (const admin of creds.domain_admins) {
                html += `
                    <div style="background: white; padding: 8px; border-radius: 4px;">
                        <div><strong>${admin.domain}\\${admin.username}</strong></div>
                        <div style="font-size: 0.9em; color: #666;">
                            Password: <code style="font-size: 1em;">${admin.password}</code>
                            ${admin.fqdn ? ` • FQDN: <code>${admin.fqdn}</code>` : ''}
                            ${admin.dc ? ` • DC: ${admin.dc}` : ''}
                        </div>
                    </div>
                `;
            }
            html += '</div></div>';
        }
        
        // Key Users
        if (creds.key_users && creds.key_users.length > 0) {
            html += `
                <div style="margin-bottom: 15px; padding: 12px; background: #e3f2fd; border-radius: 6px; border-left: 4px solid #2196F3;">
                    <div style="font-weight: 600; color: #1565c0; margin-bottom: 8px;">🎯 Key Users (Attack Paths)</div>
                    <div style="display: grid; gap: 6px; font-size: 0.95em;">
            `;
            for (const user of creds.key_users) {
                html += `
                    <div style="background: white; padding: 6px 10px; border-radius: 4px; display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <code style="font-size: 1em;">${user.domain ? user.domain + '\\\\' : ''}${user.username}</code>
                            <span style="color: #888; margin-left: 8px;">${user.password || creds.default_password}</span>
                        </div>
                        <span style="color: #666; font-size: 0.9em;">${user.role || ''}</span>
                    </div>
                `;
            }
            html += '</div></div>';
        }
        
        // Domain Trusts
        if (creds.trusts && creds.trusts.length > 0) {
            html += `
                <div style="margin-bottom: 15px; padding: 12px; background: #f3e5f5; border-radius: 6px; border-left: 4px solid #9c27b0;">
                    <div style="font-weight: 600; color: #7b1fa2; margin-bottom: 8px;">🔗 Domain Trusts</div>
                    <div style="font-size: 0.95em;">
                        ${creds.trusts.map(t => `<div style="margin-bottom: 4px;">${t.from} → ${t.to} <span style="color: #888;">(${t.type})</span></div>`).join('')}
                    </div>
                </div>
            `;
        }
        
        // Special Accounts
        if (creds.special_accounts && creds.special_accounts.length > 0) {
            html += `
                <div style="margin-bottom: 15px; padding: 12px; background: #fce4ec; border-radius: 6px; border-left: 4px solid #e91e63;">
                    <div style="font-weight: 600; color: #c2185b; margin-bottom: 8px;">⚠️ Special Accounts</div>
                    <div style="font-size: 0.95em;">
                        ${creds.special_accounts.map(a => `<div style="margin-bottom: 4px;"><strong>${a.name}:</strong> ${a.note}</div>`).join('')}
                    </div>
                </div>
            `;
        }
        
        // Note
        if (creds.note) {
            html += `
                <div style="padding: 10px; background: #f5f5f5; border-radius: 6px; font-size: 0.9em; color: #666;">
                    💡 ${creds.note}
                </div>
            `;
        }
        
        html += '</div>';
        contentDiv.innerHTML = html;
        
    } catch (error) {
        // On error, still show default credentials
        const creds = getDefaultGoadCredentials(projectName);
        contentDiv.innerHTML = buildCredentialsHtml(creds);
    }
}

// Make loadCredentials available globally for onclick handlers
window.loadCredentials = loadCredentials;

/**
 * Get default GOAD credentials based on project name
 */
function getDefaultGoadCredentials(projectName) {
    // Detect lab type from project name
    let labName = 'GOAD-Mini';
    let labDisplayName = 'GOAD Mini (Seven Kingdoms)';
    
    if (projectName) {
        const pn = projectName.toLowerCase();
        if (pn.includes('light')) {
            labName = 'GOAD-Light';
            labDisplayName = 'GOAD Light (Seven Kingdoms + North)';
        } else if (pn.includes('full') || pn.includes('goad_full')) {
            labName = 'GOAD';
            labDisplayName = 'GOAD Full (All Domains)';
        } else if (pn.includes('sccm')) {
            labName = 'SCCM';
            labDisplayName = 'GOAD SCCM Lab';
        } else if (pn.includes('nha')) {
            labName = 'NHA';
            labDisplayName = 'NHA Challenge Lab';
        }
    }
    
    // Default credentials for GOAD-Mini
    const credentials = {
        lab_name: labName,
        lab_display_name: labDisplayName,
        default_password: 'vagrant',
        default_users: [
            { username: 'Administrator', password: 'vagrant', domain: 'Local Admin', note: 'Local admin on all Windows VMs' },
            { username: 'vagrant', password: 'vagrant', domain: 'Local User', note: 'Default vagrant user (SSH/RDP)' }
        ],
        domain_admins: [
            { username: 'Administrator', password: 'vagrant', domain: 'SEVENKINGDOMS', fqdn: 'sevenkingdoms.local', dc: 'DC01' }
        ],
        key_users: [
            { username: 'cersei.lannister', password: 'vagrant', domain: 'SEVENKINGDOMS', role: 'Domain User' },
            { username: 'jaime.lannister', password: 'vagrant', domain: 'SEVENKINGDOMS', role: 'Domain User' },
            { username: 'tywin.lannister', password: 'vagrant', domain: 'SEVENKINGDOMS', role: 'Domain User' }
        ],
        trusts: [],
        special_accounts: [],
        note: 'Standard GOAD password is "vagrant" for all users. Run Ansible provisioning to fully configure the lab.'
    };
    
    // Add more domains for larger labs
    if (labName === 'GOAD-Light' || labName === 'GOAD') {
        credentials.domain_admins.push(
            { username: 'Administrator', password: 'vagrant', domain: 'NORTH', fqdn: 'north.sevenkingdoms.local', dc: 'DC02' }
        );
        credentials.key_users.push(
            { username: 'eddard.stark', password: 'vagrant', domain: 'NORTH', role: 'Domain User' },
            { username: 'robb.stark', password: 'vagrant', domain: 'NORTH', role: 'Domain User' }
        );
        credentials.trusts.push(
            { from: 'NORTH', to: 'SEVENKINGDOMS', type: 'Parent-Child' }
        );
    }
    
    if (labName === 'GOAD') {
        credentials.domain_admins.push(
            { username: 'Administrator', password: 'vagrant', domain: 'ESSOS', fqdn: 'essos.local', dc: 'DC03' }
        );
        credentials.key_users.push(
            { username: 'daenerys.targaryen', password: 'vagrant', domain: 'ESSOS', role: 'Domain User' }
        );
        credentials.trusts.push(
            { from: 'ESSOS', to: 'SEVENKINGDOMS', type: 'External (Bidirectional)' }
        );
    }
    
    return credentials;
}

// ============================================================================
// AWS CHECK FUNCTIONS
// ============================================================================

/**
 * Check if Terraform CLI is installed
 */
async function checkTerraform() {
    const statusDiv = document.getElementById('terraform-status');
    const helpDiv = document.getElementById('terraform-install-help');
    if (!statusDiv) return;
    
    statusDiv.innerHTML = '<div class="spinner"></div>Checking Terraform installation...';
    statusDiv.className = 'status-display info';
    if (helpDiv) helpDiv.style.display = 'none';
    
    try {
        const response = await fetch(`${API_BASE}/health/terraform`);
        const data = await response.json();
        
        if (data.success && data.installed) {
            statusDiv.innerHTML = `
                <div class="status-display success">
                    <p><strong>✅ Terraform is installed</strong></p>
                    <div style="margin-top: 10px; padding: 10px; background: white; border-radius: 5px;">
                        <p><strong>Version:</strong> <code style="background: #f5f5f5; padding: 3px 6px; border-radius: 3px;">${data.version || 'Unknown'}</code></p>
                        <p><strong>Path:</strong> <code style="background: #f5f5f5; padding: 3px 6px; border-radius: 3px; font-size: 0.85em;">${data.path || 'N/A'}</code></p>
                    </div>
                </div>
            `;
            if (helpDiv) helpDiv.style.display = 'none';
        } else {
            statusDiv.innerHTML = `
                <div class="status-display error">
                    <p><strong>❌ Terraform is NOT installed</strong></p>
                    <p style="margin-top: 10px; color: #666;">${data.error || 'Terraform CLI was not found in your system PATH.'}</p>
                </div>
            `;
            if (helpDiv) helpDiv.style.display = 'block';
        }
    } catch (error) {
        statusDiv.innerHTML = `
            <div class="status-display error">
                <p><strong>❌ Error checking Terraform</strong></p>
                <p>${error.message}</p>
            </div>
        `;
        if (helpDiv) helpDiv.style.display = 'block';
    }
}

/**
 * Check if AWS CLI is installed
 */
async function checkAWSCLI() {
    const statusDiv = document.getElementById('aws-cli-status');
    if (!statusDiv) return;
    
    statusDiv.innerHTML = '<div class="spinner"></div>Checking AWS CLI installation...';
    statusDiv.className = 'status-display info';
    
    try {
        const response = await fetch(`${API_BASE}/health/aws-cli`);
        const data = await response.json();
        
        if (data.success && data.installed) {
            statusDiv.innerHTML = `
                <div class="status-display success">
                    <p><strong>✅ AWS CLI is installed</strong></p>
                    <div style="margin-top: 10px; padding: 10px; background: white; border-radius: 5px;">
                        <p><strong>Version:</strong> <code style="background: #f5f5f5; padding: 3px 6px; border-radius: 3px;">${data.version || 'Unknown'}</code></p>
                        <p><strong>Path:</strong> <code style="background: #f5f5f5; padding: 3px 6px; border-radius: 3px; font-size: 0.85em;">${data.path || 'N/A'}</code></p>
                    </div>
                </div>
            `;
        } else {
            statusDiv.innerHTML = `
                <div class="status-display error">
                    <p><strong>❌ AWS CLI is NOT installed</strong></p>
                    <p style="margin-top: 10px; color: #666;">${data.error || 'AWS CLI was not found in your system PATH.'}</p>
                    <div style="margin-top: 15px; padding: 15px; background: white; border-radius: 5px; border-left: 4px solid #ff9800;">
                        <p><strong>How to install:</strong></p>
                        <p style="margin-top: 5px;"><code style="background: #1e1e1e; color: #4ec9b0; padding: 8px; border-radius: 4px; display: block;">brew install awscli</code></p>
                        <p style="margin-top: 10px; font-size: 0.9em; color: #666;">Or download from <a href="https://aws.amazon.com/cli/" target="_blank" style="color: #ff9800;">aws.amazon.com/cli</a></p>
                    </div>
                </div>
            `;
        }
    } catch (error) {
        statusDiv.innerHTML = `
            <div class="status-display error">
                <p><strong>❌ Error checking AWS CLI</strong></p>
                <p>${error.message}</p>
            </div>
        `;
    }
}

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
// GOAD LAB FUNCTIONS
// ============================================================================

// GOAD lab configurations (mirrors backend)
const GOAD_LABS = {
    'GOAD-Mini': {
        name: 'GOAD-Mini',
        displayName: 'GOAD Mini',
        vms: 1,
        domains: 1,
        forests: 1,
        description: 'Minimalist lab with single domain controller. Perfect for quick testing and learning basics.',
        estCost: 75,
        attacks: ['Kerberoasting', 'AS-REP Roasting', 'DCSync', 'Pass-the-Hash']
    },
    'MINILAB': {
        name: 'MINILAB',
        displayName: 'Mini Lab',
        vms: 2,
        domains: 1,
        forests: 1,
        description: 'Basic lab with one DC and one Workstation. Good for practicing basic attack chains.',
        estCost: 150,
        attacks: ['Kerberoasting', 'AS-REP Roasting', 'DCSync', 'Pass-the-Hash', 'Lateral Movement']
    },
    'GOAD-Light': {
        name: 'GOAD-Light',
        displayName: 'GOAD Light',
        vms: 3,
        domains: 2,
        forests: 1,
        description: 'Smaller lab with 2 domains. Covers most common AD attack scenarios.',
        estCost: 200,
        attacks: ['Kerberoasting', 'AS-REP Roasting', 'DCSync', 'Pass-the-Hash', 'Trust Attacks', 'Constrained Delegation']
    },
    'SCCM': {
        name: 'SCCM',
        displayName: 'SCCM Lab',
        vms: 4,
        domains: 1,
        forests: 1,
        description: 'Lab with Microsoft Configuration Manager (SCCM/ConfigMgr). For SCCM-specific attacks.',
        estCost: 300,
        attacks: ['SCCM Attacks', 'NAA Credentials', 'PXE Boot Attacks', 'Task Sequence Attacks']
    },
    'GOAD': {
        name: 'GOAD',
        displayName: 'GOAD Full',
        vms: 5,
        domains: 3,
        forests: 2,
        description: 'Full lab with 3 domains across 2 forests. Complete AD environment for comprehensive testing.',
        estCost: 350,
        attacks: ['Kerberoasting', 'AS-REP Roasting', 'DCSync', 'DCShadow', 'Pass-the-Hash', 'Golden Ticket', 'Silver Ticket', 'Trust Attacks', 'Forest Attacks']
    },
    'NHA': {
        name: 'NHA',
        displayName: 'NHA Challenge',
        vms: 5,
        domains: 2,
        forests: 1,
        description: 'Challenge lab with no hints provided. CTF-style for advanced practice.',
        estCost: 350,
        attacks: ['Unknown - Challenge Mode']
    }
};

/**
 * Update GOAD lab info (now handled by updateDeploymentType)
 * Kept for backward compatibility
 */
function updateGoadLabInfo() {
    // Now handled by updateDeploymentType()
    updateDeploymentType();
}

/**
 * Populate GOAD section with data (used by refreshDeployments)
 */
function populateGoadSection(data) {
    const section = document.getElementById('goad-lab-section');
    const details = document.getElementById('goad-lab-details');
    const actions = document.getElementById('goad-lab-actions');
    
    if (!section) return;
    
    // If no data or request failed, hide the section
    if (!data || !data.success) {
        section.style.display = 'none';
        return;
    }
    
    // If GOAD tools not available, only show warning if there's supposed to be a GOAD deployment
    // Don't show warning for C2-only deployments
    if (!data.goad_available) {
        // Only show warning if user has selected a GOAD deployment type
        const deploymentType = document.getElementById('deployment-type')?.value || '';
        const isGoadDeployment = deploymentType.includes('goad') || deploymentType.includes('combined');
        
        if (isGoadDeployment) {
            section.style.display = 'block';
            details.innerHTML = `
                <div class="status-display warning">
                    <p><strong>⚠️ GOAD Not Available</strong></p>
                    <p>GOAD tools not found. Run: <code>git submodule update --init</code></p>
                </div>
            `;
            actions.innerHTML = '';
        } else {
            section.style.display = 'none';
        }
        return;
    }
    
    // No GOAD deployment active
    if (!data.has_deployment) {
        section.style.display = 'none';
        return;
    }
    
    // Has GOAD deployment - show details
    section.style.display = 'block';
    const labInfo = data.deployment_info?.lab_info || {};
    const labName = data.deployed_lab;
    
    details.innerHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 15px; margin-bottom: 15px;">
            <div style="background: white; padding: 15px; border-radius: 5px; text-align: center;">
                <div style="font-size: 2em; font-weight: bold; color: #e65100;">${labInfo.vms || '?'}</div>
                <div style="color: #666; font-size: 0.9em;">VMs</div>
            </div>
            <div style="background: white; padding: 15px; border-radius: 5px; text-align: center;">
                <div style="font-size: 2em; font-weight: bold; color: #e65100;">${labInfo.domains || '?'}</div>
                <div style="color: #666; font-size: 0.9em;">Domains</div>
            </div>
            <div style="background: white; padding: 15px; border-radius: 5px; text-align: center;">
                <div style="font-size: 2em; font-weight: bold; color: #e65100;">${labInfo.forests || '?'}</div>
                <div style="color: #666; font-size: 0.9em;">Forests</div>
            </div>
        </div>
        <div style="background: white; padding: 15px; border-radius: 5px;">
            <p><strong>Lab Type:</strong> ${labInfo.display_name || labName}</p>
            <p style="color: #666; margin-top: 10px;">${labInfo.description || ''}</p>
            ${labInfo.domain_names ? `<p style="margin-top: 10px;"><strong>Domains:</strong> ${labInfo.domain_names.join(', ')}</p>` : ''}
        </div>
    `;
    
    actions.innerHTML = `
        <button class="btn btn-success" onclick="startGoadLab()">▶️ Start Lab</button>
        <button class="btn btn-warning" onclick="stopGoadLab()">⏸️ Stop Lab</button>
        <button class="btn btn-info" onclick="showGoadCredentials()">🔑 Credentials</button>
        <button class="btn btn-info" onclick="showGoadJumpbox()">🖥️ Jumpbox Info</button>
        <button class="btn btn-danger" onclick="destroyGoadLab()">🗑️ Destroy Lab</button>
    `;
}

/**
 * Load GOAD status for deployment manager (fetches data and populates)
 */
async function loadGoadStatus() {
    try {
        const response = await fetch(`${API_BASE}/goad/status`);
        const data = await response.json();
        populateGoadSection(data);
    } catch (error) {
        console.error('Error loading GOAD status:', error);
        const section = document.getElementById('goad-lab-section');
        if (section) section.style.display = 'none';
    }
}

/**
 * Deploy a GOAD lab
 */
async function deployGoadLab(labName) {
    if (!labName) {
        const select = document.getElementById('goad-lab-type');
        labName = select?.value;
    }
    
    if (!labName) {
        alert('Please select a GOAD lab type first');
        return;
    }
    
    if (!confirm(`Deploy ${labName} lab? This will create ${GOAD_LABS[labName]?.vms || '?'} VMs in AWS.`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/goad/deploy`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lab_name: labName })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(`GOAD ${labName} deployment initiated!\n\n${data.note || ''}\n\nNext steps:\n${data.next_steps?.join('\n') || ''}`);
        } else {
            alert(`Error: ${data.error}`);
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

/**
 * Start GOAD lab VMs
 */
async function startGoadLab() {
    if (!confirm('Start GOAD lab VMs?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/goad/start`, { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            alert('GOAD lab start command sent. VMs may take a few minutes to fully boot.');
            loadGoadStatus();
        } else {
            alert(`Error: ${data.error || data.stderr}`);
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

/**
 * Stop GOAD lab VMs to save costs
 */
async function stopGoadLab() {
    if (!confirm('Stop GOAD lab VMs? This will save costs but VMs will be unavailable.')) return;
    
    try {
        const response = await fetch(`${API_BASE}/goad/stop`, { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            alert('GOAD lab stop command sent. VMs are being stopped.');
            loadGoadStatus();
        } else {
            alert(`Error: ${data.error || data.stderr}`);
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

/**
 * Destroy GOAD lab
 */
async function destroyGoadLab() {
    const confirmText = prompt('Type "DESTROY" to confirm GOAD lab destruction:');
    if (confirmText !== 'DESTROY') return;
    
    try {
        const response = await fetch(`${API_BASE}/goad/destroy`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirm: 'DESTROY' })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('GOAD lab destroyed successfully.');
            loadGoadStatus();
        } else {
            alert(`Error: ${data.error}`);
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

/**
 * Show GOAD credentials
 */
async function showGoadCredentials() {
    try {
        const response = await fetch(`${API_BASE}/goad/credentials`);
        const data = await response.json();
        
        if (data.success) {
            const creds = data.credentials;
            let message = `GOAD Lab: ${creds.lab_name}\n\n`;
            message += `Domains: ${creds.domains?.join(', ') || 'N/A'}\n\n`;
            message += `Inventory Path:\n${creds.inventory_path}\n\n`;
            message += `Note: ${creds.note}`;
            alert(message);
        } else {
            alert(`Error: ${data.error}`);
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

/**
 * Show GOAD jumpbox info
 */
async function showGoadJumpbox() {
    try {
        const response = await fetch(`${API_BASE}/goad/jumpbox`);
        const data = await response.json();
        
        if (data.success) {
            const jb = data.jumpbox;
            let message = `GOAD Jumpbox Info\n\n`;
            message += `Lab: ${jb.lab_name}\n`;
            if (jb.public_ip) message += `Public IP: ${jb.public_ip}\n`;
            message += `\nSSH Command:\n${jb.commands?.ssh || 'N/A'}\n`;
            message += `\nSOCKS Proxy Command:\n${jb.commands?.socks_proxy || 'N/A'}\n`;
            message += `\nSSH Keys: ${jb.ssh_key_path}`;
            alert(message);
        } else {
            alert(`Error: ${data.error}`);
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
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
    
    // Show sections immediately (they start hidden)
    const resourceSection = document.getElementById('resource-list-section');
    const historySection = document.getElementById('deployment-history-section');
    if (resourceSection) resourceSection.style.display = 'block';
    if (historySection) historySection.style.display = 'block';
    
    // Load all data in parallel for faster page load
    await Promise.all([
        refreshDeployments(),
        loadResourceList(),
        loadDeploymentHistory()
    ]);
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
        // Fetch both C2 infrastructure and GOAD status
        const [infraResponse, goadResponse] = await Promise.all([
            fetch(`${API_BASE}/deploy/infrastructure`),
            fetch(`${API_BASE}/goad/status`)
        ]);
        
        const data = await infraResponse.json();
        const goadData = await goadResponse.json();
        
        // Update last updated time
        if (lastUpdatedSpan) {
            lastUpdatedSpan.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
        }
        
        // Check if we have any deployment (C2 or GOAD)
        const hasC2Deployment = data.success && data.has_deployment;
        const hasGoadDeployment = goadData.success && goadData.has_deployment;
        const hasAnyDeployment = hasC2Deployment || hasGoadDeployment;
        
        if (!data.success && !hasGoadDeployment) {
            overviewDiv.innerHTML = `
                <div class="status-display error">
                    <p><strong>Error:</strong> ${data.error || 'Failed to load infrastructure'}</p>
                </div>
            `;
            return;
        }
        
        if (!hasAnyDeployment) {
            // No deployment - show empty state
            hideAllInfrastructureSections();
            if (noDeploymentDiv) noDeploymentDiv.style.display = 'block';
            if (overviewDiv) overviewDiv.innerHTML = '';
            document.getElementById('connection-info-section').style.display = 'none';
            document.getElementById('destroy-section').style.display = 'none';
            document.getElementById('goad-lab-section').style.display = 'none';
            // Hide lifecycle section when no deployment
            const lifecycleSection = document.getElementById('lifecycle-section');
            if (lifecycleSection) lifecycleSection.style.display = 'none';
            return;
        }
        
        // Has deployment - show infrastructure
        if (noDeploymentDiv) noDeploymentDiv.style.display = 'none';
        
        // Show lifecycle section and update project tag
        const lifecycleSection = document.getElementById('lifecycle-section');
        if (lifecycleSection) {
            lifecycleSection.style.display = 'block';
            // Update the project tag display
            const projectTagSpan = document.getElementById('aws-project-tag');
            if (projectTagSpan && data.success) {
                // Try to get project name from config or use a default
                projectTagSpan.textContent = data.project_name || 'your-project-name';
            }
        }
        
        // Show destroy section
        document.getElementById('destroy-section').style.display = 'block';
        
        // Build overview summary including GOAD
        const summary = data.success && data.has_deployment ? (data.summary || {}) : {};
        const goadInfo = hasGoadDeployment ? goadData.deployment_info?.lab_info : null;
        
        let overviewHtml = `
            <div class="status-display success">
                <p><strong>✅ Infrastructure Active</strong></p>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 15px; margin-top: 15px;">
        `;
        
        if (hasC2Deployment) {
            overviewHtml += `
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
            `;
        }
        
        if (hasGoadDeployment && goadInfo) {
            overviewHtml += `
                    <div style="text-align: center; padding: 15px; background: white; border-radius: 8px; border: 2px solid #ff9800;">
                        <div style="font-size: 2em; font-weight: bold; color: #e65100;">${goadInfo.vms || 0}</div>
                        <div style="color: #666; font-size: 0.9em;">GOAD VMs</div>
                    </div>
            `;
        }
        
        overviewHtml += `
                </div>
        `;
        
        if (hasC2Deployment) {
            overviewHtml += `<p style="margin-top: 15px; color: #666;"><strong>C2 Deployment Mode:</strong> ${data.deployment_mode || 'N/A'}</p>`;
        }
        if (hasGoadDeployment) {
            overviewHtml += `<p style="margin-top: 5px; color: #666;"><strong>GOAD Lab:</strong> ${goadData.deployed_lab || 'N/A'}</p>`;
        }
        
        overviewHtml += `</div>`;
        overviewDiv.innerHTML = overviewHtml;
        
        // Populate C2 sections if we have C2 deployment
        if (hasC2Deployment) {
            populateBastionSection(data.bastion);
            populateC2ServersSection(data.c2_servers, data.deployment_mode);
            populateRedirectorsSection(data.redirectors);
            populateNetworkSection(data.network, data.security_groups);
            await populateConnectionInfo(data);
        } else {
            hideAllInfrastructureSections();
        }
        
        // Populate GOAD section with already-fetched data (don't call loadGoadStatus again)
        populateGoadSection(goadData);
        
        // Show destroy section when there's an active deployment
        const destroySection = document.getElementById('destroy-section');
        if (destroySection) {
            destroySection.style.display = hasAnyDeployment ? 'block' : 'none';
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

// =============================================================================
// RESOURCE LIST FUNCTIONS
// =============================================================================

// Store all resources for filtering
let allResources = [];

/**
 * Load and display all deployed resources
 */
async function loadResourceList() {
    const section = document.getElementById('resource-list-section');
    const tableBody = document.getElementById('resource-table-body');
    const countDiv = document.getElementById('resource-count');
    
    if (!section || !tableBody) return;
    
    try {
        // Fetch resources from ALL known projects
        const response = await fetch(`${API_BASE}/deploy/resources?all_projects=true`);
        const data = await response.json();
        
        if (!data.success) {
            tableBody.innerHTML = `<tr><td colspan="5" style="padding: 20px; text-align: center; color: #666;">No resources found or error loading resources</td></tr>`;
            return;
        }
        
        allResources = data.resources || [];
        
        if (allResources.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="5" style="padding: 20px; text-align: center; color: #666;">No deployed resources</td></tr>`;
            countDiv.textContent = '0 resources';
            return;
        }
        
        // Show section
        section.style.display = 'block';
        
        // Render resources
        renderResourceTable(allResources);
        
    } catch (error) {
        console.error('Error loading resources:', error);
        tableBody.innerHTML = `<tr><td colspan="5" style="padding: 20px; text-align: center; color: #c62828;">Error loading resources: ${error.message}</td></tr>`;
    }
}

/**
 * Render resource table with given resources
 */
function renderResourceTable(resources) {
    const tableBody = document.getElementById('resource-table-body');
    const countDiv = document.getElementById('resource-count');
    
    if (!tableBody) return;
    
    // Filter out deleted/terminated resources - they no longer exist
    const activeResources = resources.filter(r => {
        const state = (r.state || '').toLowerCase();
        return state !== 'deleted' && state !== 'terminated' && state !== 'deleting';
    });
    
    const typeIcons = {
        'ec2': '🖥️',
        'vpc': '🌐',
        'subnet': '📡',
        'sg': '🔒',
        'eip': '🔗',
        'nat': '🚪',
        's3': '📦',
        'igw': '🌍',
        'rtb': '🛣️',
        'eni': '🔌',
        'keypair': '🔑',
        'pcx': '🔀',
        'iam-role': '👤',
        'iam-profile': '🎭',
        'route53-zone': '🌐',
        'acm-cert': '🔐'
    };
    
    const stateColors = {
        'running': '#4CAF50',
        'available': '#4CAF50',
        'active': '#4CAF50',
        'stopped': '#ff9800',
        'pending': '#2196F3',
        'terminated': '#f44336',
        'deleted': '#f44336'
    };
    
    if (activeResources.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="6" style="padding: 20px; text-align: center; color: #666;">No active resources</td></tr>`;
        countDiv.textContent = '0 resources';
        return;
    }
    
    tableBody.innerHTML = activeResources.map((r, idx) => `
        <tr style="background: ${idx % 2 === 0 ? '#fff' : '#f9f9f9'};">
            <td style="padding: 10px; border-bottom: 1px solid #eee;">
                <span style="font-size: 1.2em;">${typeIcons[r.type] || '📄'}</span>
                <span style="margin-left: 5px; text-transform: uppercase; font-size: 0.8em; color: #666;">${r.type}</span>
            </td>
            <td style="padding: 10px; border-bottom: 1px solid #eee; font-weight: 500;">${r.name || '-'}</td>
            <td style="padding: 10px; border-bottom: 1px solid #eee;">
                <code style="background: #f5f5f5; padding: 3px 8px; border-radius: 3px; font-size: 0.85em;">${r.id || '-'}</code>
            </td>
            <td style="padding: 10px; border-bottom: 1px solid #eee;">
                <span style="background: ${stateColors[r.state?.toLowerCase()] || '#9e9e9e'}; color: white; padding: 3px 10px; border-radius: 12px; font-size: 0.8em; text-transform: uppercase;">${r.state || 'unknown'}</span>
            </td>
            <td style="padding: 10px; border-bottom: 1px solid #eee; font-size: 0.8em; color: #1565c0;">
                ${r.project ? `<span style="background: #e3f2fd; padding: 3px 8px; border-radius: 4px;">${r.project}</span>` : '-'}
            </td>
            <td style="padding: 10px; border-bottom: 1px solid #eee; font-size: 0.85em; color: #666;">${r.details || '-'}</td>
        </tr>
    `).join('');
    
    countDiv.textContent = `${activeResources.length} resource${activeResources.length !== 1 ? 's' : ''} found`;
}

/**
 * Filter resources based on type and search
 */
function filterResources() {
    const typeFilter = document.getElementById('resource-type-filter')?.value || 'all';
    const searchFilter = document.getElementById('resource-search')?.value.toLowerCase() || '';
    
    let filtered = allResources;
    
    if (typeFilter !== 'all') {
        filtered = filtered.filter(r => r.type === typeFilter);
    }
    
    if (searchFilter) {
        filtered = filtered.filter(r => 
            (r.name && r.name.toLowerCase().includes(searchFilter)) ||
            (r.id && r.id.toLowerCase().includes(searchFilter)) ||
            (r.details && r.details.toLowerCase().includes(searchFilter))
        );
    }
    
    renderResourceTable(filtered);
}

/**
 * Refresh resource list
 */
async function refreshResourceList() {
    await loadResourceList();
    showMessage('Resource list refreshed', 'success');
}

/**
 * Export resource list to CSV
 */
function exportResourceList() {
    if (allResources.length === 0) {
        showMessage('No resources to export', 'warning');
        return;
    }
    
    const headers = ['Type', 'Name', 'Resource ID', 'State', 'Details'];
    const rows = allResources.map(r => [
        r.type || '',
        r.name || '',
        r.id || '',
        r.state || '',
        r.details || ''
    ]);
    
    const csv = [headers.join(','), ...rows.map(r => r.map(c => `"${c}"`).join(','))].join('\n');
    
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `aws-resources-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    
    showMessage('Resource list exported', 'success');
}

// =============================================================================
// DEPLOYMENT HISTORY & LOGS FUNCTIONS
// =============================================================================

// Store deployment logs in memory and localStorage
let deploymentLogs = [];
let archivedLogs = [];
const LOGS_STORAGE_KEY = 'red_team_deployment_logs';
const ARCHIVED_LOGS_KEY = 'red_team_archived_logs';
const MAX_LOGS = 500;
const MAX_ARCHIVED = 2000;

/**
 * Initialize deployment logs from localStorage
 */
function initDeploymentLogs() {
    try {
        const stored = localStorage.getItem(LOGS_STORAGE_KEY);
        if (stored) {
            deploymentLogs = JSON.parse(stored);
        }
        // Also load archived logs
        const archived = localStorage.getItem(ARCHIVED_LOGS_KEY);
        if (archived) {
            archivedLogs = JSON.parse(archived);
        }
    } catch (e) {
        console.error('Error loading deployment logs:', e);
        deploymentLogs = [];
    }
}

/**
 * Save deployment logs to localStorage
 */
function saveDeploymentLogs() {
    try {
        // Keep only last MAX_LOGS entries for current view
        if (deploymentLogs.length > MAX_LOGS) {
            deploymentLogs = deploymentLogs.slice(-MAX_LOGS);
        }
        localStorage.setItem(LOGS_STORAGE_KEY, JSON.stringify(deploymentLogs));
    } catch (e) {
        console.error('Error saving deployment logs:', e);
    }
}

/**
 * Save archived logs to localStorage
 */
function saveArchivedLogs() {
    try {
        // Keep only last MAX_ARCHIVED entries
        if (archivedLogs.length > MAX_ARCHIVED) {
            archivedLogs = archivedLogs.slice(-MAX_ARCHIVED);
        }
        localStorage.setItem(ARCHIVED_LOGS_KEY, JSON.stringify(archivedLogs));
    } catch (e) {
        console.error('Error saving archived logs:', e);
    }
}

/**
 * Add a log entry (also adds to archive automatically)
 */
function addDeploymentLog(message, level = 'info', details = null) {
    const entry = {
        timestamp: new Date().toISOString(),
        level: level,
        message: message,
        details: details
    };
    
    // Add to current logs
    deploymentLogs.push(entry);
    saveDeploymentLogs();
    
    // Also add to archive automatically
    archivedLogs.push(entry);
    saveArchivedLogs();
    
    // Update UI if on deployments page
    if (APP.currentPage === 'deployments') {
        renderDeploymentLogs();
    }
}

/**
 * Load deployment history section
 */
async function loadDeploymentHistory() {
    const section = document.getElementById('deployment-history-section');
    if (!section) return;
    
    // Initialize logs from storage
    initDeploymentLogs();
    
    // Show section if there are logs or active deployment
    section.style.display = 'block';
    
    // Render timeline and logs
    renderDeploymentTimeline();
    renderDeploymentLogs();
    
    // Also fetch any recent deployment status from backend
    try {
        const response = await fetch(`${API_BASE}/deploy/history`);
        const data = await response.json();
        
        if (data.success && data.history) {
            // Merge server history with local logs AND archive
            data.history.forEach(h => {
                // Add to current logs if not exists
                const existsInLogs = deploymentLogs.some(l => 
                    l.timestamp === h.timestamp && l.message === h.message
                );
                if (!existsInLogs) {
                    deploymentLogs.push(h);
                }
                
                // Add to archive if not exists
                const existsInArchive = archivedLogs.some(l => 
                    l.timestamp === h.timestamp && l.message === h.message
                );
                if (!existsInArchive) {
                    archivedLogs.push(h);
                }
            });
            
            // Sort by timestamp
            deploymentLogs.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
            archivedLogs.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
            
            saveDeploymentLogs();
            saveArchivedLogs();
            
            renderDeploymentTimeline();
            renderDeploymentLogs();
        }
    } catch (e) {
        console.log('No server deployment history available');
    }
}

/**
 * Render deployment timeline
 */
// Track expanded deployment sessions
let expandedSessions = new Set();

function renderDeploymentTimeline() {
    const timelineContent = document.getElementById('timeline-content');
    if (!timelineContent) return;
    
    // Get unique deployment sessions (group by date + project_name)
    // This allows multiple deployments on the same day to be shown separately
    const sessions = {};
    deploymentLogs.forEach(log => {
        const date = log.timestamp.split('T')[0];
        // Use project_name from log if available, otherwise use date as fallback
        const projectName = log.project_name || null;
        const sessionKey = projectName ? `${date}-${projectName}` : date;
        
        if (!sessions[sessionKey]) {
            sessions[sessionKey] = { 
                date,
                sessionKey,
                logs: [], 
                hasError: false, 
                hasSuccess: false,
                projectName: projectName,
                deploymentType: null,
                firstTime: null,
                lastTime: null
            };
        }
        sessions[sessionKey].logs.push(log);
        if (log.level === 'error') sessions[sessionKey].hasError = true;
        if (log.level === 'success') sessions[sessionKey].hasSuccess = true;
        
        // Extract deployment type from log messages like "Starting deployment: goad-mini"
        if (log.message && log.message.includes('Starting deployment:')) {
            const match = log.message.match(/Starting deployment:\s*(\S+)/);
            if (match) {
                sessions[sessionKey].deploymentType = match[1];
            }
        }
        
        // If project_name wasn't in log, try to extract from message
        if (!sessions[sessionKey].projectName && log.message) {
            // Pattern: project_name-component (e.g., "goad_mini_dev_001-goadmini-vpc")
            const projectMatch = log.message.match(/([a-z0-9_]+_[a-z0-9_]+_[a-z0-9_]+)-/i);
            if (projectMatch) {
                sessions[sessionKey].projectName = projectMatch[1];
            }
            
            // Also check for "Project:" or "project_name" patterns
            const projectNameMatch = log.message.match(/project[_\s]*name[:\s]+["']?([^"'\s,]+)/i);
            if (projectNameMatch) {
                sessions[sessionKey].projectName = projectNameMatch[1];
            }
            
            // Check for patterns like "project 'name'" or "for project 'name'"
            const quotedProjectMatch = log.message.match(/project\s+['"]([^'"]+)['"]/i);
            if (quotedProjectMatch) {
                sessions[sessionKey].projectName = quotedProjectMatch[1];
            }
        }
        
        // Track first and last times
        const logTime = new Date(log.timestamp);
        if (!sessions[sessionKey].firstTime || logTime < sessions[sessionKey].firstTime) {
            sessions[sessionKey].firstTime = logTime;
        }
        if (!sessions[sessionKey].lastTime || logTime > sessions[sessionKey].lastTime) {
            sessions[sessionKey].lastTime = logTime;
        }
    });
    
    const sessionList = Object.values(sessions).reverse().slice(0, 10);
    
    if (sessionList.length === 0) {
        timelineContent.innerHTML = '<div style="color: #888; text-align: center;">No deployment history yet</div>';
        return;
    }
    
    timelineContent.innerHTML = sessionList.map((s, index) => {
        const sessionId = `session-${s.sessionKey}`;
        const isExpanded = expandedSessions.has(sessionId);
        
        // Check if this deployment was destroyed (look for destroy/purge success messages)
        const wasDestroyed = s.logs.some(log => 
            (log.message && (
                log.message.includes('Resources purged successfully') ||
                log.message.includes('Resources force-purged successfully') ||
                log.message.includes('All resources have been purged') ||
                log.message.includes('Infrastructure destroyed') ||
                log.message.includes('terraform destroy') && log.level === 'success'
            ))
        );
        
        // Determine status - destroyed takes precedence over success
        let statusIcon, statusColor, statusText;
        if (wasDestroyed) {
            statusIcon = '🗑️';
            statusColor = '#9e9e9e';
            statusText = 'Destroyed';
        } else if (s.hasError) {
            statusIcon = '❌';
            statusColor = '#f44336';
            statusText = 'Failed';
        } else if (s.hasSuccess) {
            statusIcon = '✅';
            statusColor = '#4CAF50';
            statusText = 'Success';
        } else {
            statusIcon = '🔄';
            statusColor = '#2196F3';
            statusText = 'In Progress';
        }
        
        const logCount = s.logs.length;
        const lastLog = s.logs[s.logs.length - 1];
        
        // Format time range
        const startTime = s.firstTime ? s.firstTime.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '';
        const endTime = s.lastTime ? s.lastTime.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '';
        const timeRange = startTime === endTime ? startTime : `${startTime} - ${endTime}`;
        
        // Calculate duration
        let duration = '';
        if (s.firstTime && s.lastTime) {
            const durationMs = s.lastTime - s.firstTime;
            const durationMin = Math.floor(durationMs / 60000);
            const durationSec = Math.floor((durationMs % 60000) / 1000);
            duration = durationMin > 0 ? `${durationMin}m ${durationSec}s` : `${durationSec}s`;
        }
        
        // Project name - the actual project name (e.g., goad_mini_dev_001)
        const projectName = s.projectName || 'Unknown Project';
        
        // Deployment type badge (e.g., goad-mini, c2-full)
        const deploymentTypeBadge = s.deploymentType ? `<span style="background: #e3f2fd; color: #1565c0; padding: 3px 8px; border-radius: 4px; font-size: 0.75em; font-weight: 500;">${s.deploymentType}</span>` : '';
        
        // Show purge button for failed deployments (but not if already destroyed)
        const purgeButton = (s.hasError && !wasDestroyed) ? `
            <button onclick="event.stopPropagation(); purgeFailedDeployment('${projectName}')" class="btn" style="background: #ff5722; color: white; font-size: 0.75em; padding: 6px 12px; margin-left: 10px;" title="Clean up resources from this failed deployment">
                🧹 Purge
            </button>
        ` : '';
        
        // Build expanded content
        const expandedContent = isExpanded ? buildSessionDetails(s, sessionId) : '';
        
        // Last log message - show more characters
        const lastLogMessage = lastLog.message.replace(/\x1b\[[0-9;]*m/g, ''); // Clean ANSI codes
        const truncatedMessage = lastLogMessage.length > 80 ? lastLogMessage.substring(0, 80) + '...' : lastLogMessage;
        
        return `
            <div style="margin-bottom: 16px;">
                <!-- Clickable Header -->
                <div onclick="toggleSessionExpand('${sessionId}')" style="display: flex; align-items: center; gap: 15px; padding: 16px 20px; background: white; border-radius: ${isExpanded ? '8px 8px 0 0' : '8px'}; border-left: 5px solid ${statusColor}; cursor: pointer; transition: all 0.2s; box-shadow: 0 2px 4px rgba(0,0,0,0.05);" onmouseover="this.style.background='#f8f9fa'; this.style.boxShadow='0 4px 8px rgba(0,0,0,0.1)'" onmouseout="this.style.background='white'; this.style.boxShadow='0 2px 4px rgba(0,0,0,0.05)'">
                    <span style="font-size: 1em; transition: transform 0.2s; transform: rotate(${isExpanded ? '90deg' : '0deg'}); color: #666;">▶</span>
                    <span style="font-size: 1.8em;">${statusIcon}</span>
                    <div style="flex: 1; min-width: 0;">
                        <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 6px;">
                            <span style="font-weight: 700; color: #1a1a2e; font-size: 1.1em;">${projectName}</span>
                            ${deploymentTypeBadge}
                            <span style="background: ${statusColor}15; color: ${statusColor}; padding: 3px 10px; border-radius: 4px; font-size: 0.75em; font-weight: 600; text-transform: uppercase;">${statusText}</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 12px; color: #666; font-size: 0.85em;">
                            <span>📅 ${formatDate(s.date)}</span>
                            <span>🕐 ${timeRange}</span>
                            <span>⏱️ ${duration || 'N/A'}</span>
                            <span>📊 ${logCount} events</span>
                        </div>
                        <div style="font-size: 0.85em; color: #888; margin-top: 8px; font-style: italic;">
                            Last: ${truncatedMessage}
                        </div>
                    </div>
                    <div style="display: flex; align-items: center;">
                        ${purgeButton}
                    </div>
                </div>
                
                <!-- Expanded Details -->
                ${expandedContent}
            </div>
        `;
    }).join('');
}

/**
 * Build detailed session content when expanded
 */
function buildSessionDetails(session, sessionId) {
    // Extract resources from logs
    const deployedResources = extractResourcesFromLogs(session.logs, 'created');
    const purgedResources = extractResourcesFromLogs(session.logs, 'destroyed');
    
    // Group logs by phase/step
    const phases = [];
    let currentPhase = { name: 'Initialization', logs: [], status: 'info' };
    
    session.logs.forEach(log => {
        // Detect phase changes
        if (log.message.includes('Started:') || log.message.includes('Starting')) {
            if (currentPhase.logs.length > 0) {
                phases.push(currentPhase);
            }
            const phaseName = log.message.replace('Started:', '').replace('Starting', '').trim();
            currentPhase = { name: phaseName || 'Processing', logs: [], status: 'info' };
        }
        
        currentPhase.logs.push(log);
        
        if (log.level === 'error') currentPhase.status = 'error';
        else if (log.level === 'success' && currentPhase.status !== 'error') currentPhase.status = 'success';
    });
    
    if (currentPhase.logs.length > 0) {
        phases.push(currentPhase);
    }
    
    // Build phase timeline
    const phaseHtml = phases.map((phase, idx) => {
        const phaseIcon = phase.status === 'error' ? '❌' : (phase.status === 'success' ? '✅' : '🔄');
        const phaseColor = phase.status === 'error' ? '#f44336' : (phase.status === 'success' ? '#4CAF50' : '#2196F3');
        
        return `
            <div style="display: flex; align-items: flex-start; gap: 10px; padding: 8px 0; ${idx < phases.length - 1 ? 'border-bottom: 1px solid #eee;' : ''}">
                <span style="font-size: 1em;">${phaseIcon}</span>
                <div style="flex: 1;">
                    <div style="font-weight: 500; color: #333; font-size: 0.9em;">${phase.name}</div>
                    <div style="font-size: 0.8em; color: #666; margin-top: 2px;">${phase.logs.length} log entries</div>
                </div>
                <span style="font-size: 0.75em; color: ${phaseColor}; text-transform: uppercase; font-weight: 500;">${phase.status}</span>
            </div>
        `;
    }).join('');
    
    // Get error logs for display
    const errorLogs = session.logs.filter(l => l.level === 'error');
    const errorSection = errorLogs.length > 0 ? `
        <div style="margin-top: 15px;">
            <div style="font-weight: 600; color: #c62828; margin-bottom: 8px; font-size: 0.9em;">⚠️ Errors (${errorLogs.length})</div>
            <div style="background: #1e1e1e; color: #ff6b6b; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 0.8em; max-height: 150px; overflow-y: auto;">
                ${errorLogs.map(log => {
                    const time = new Date(log.timestamp).toLocaleTimeString();
                    // Clean ANSI codes from message
                    const cleanMsg = log.message.replace(/\x1b\[[0-9;]*m/g, '').substring(0, 200);
                    return `<div style="margin-bottom: 6px;"><span style="color: #888;">[${time}]</span> ${cleanMsg}</div>`;
                }).join('')}
            </div>
        </div>
    ` : '';
    
    // Summary stats
    const successCount = session.logs.filter(l => l.level === 'success').length;
    const warningCount = session.logs.filter(l => l.level === 'warning').length;
    const infoCount = session.logs.filter(l => l.level === 'info').length;
    
    // Build deployed resources section (from logs - fallback)
    const deployedSection = buildResourcesSection(deployedResources, 'Deployed Resources (from logs)', '🚀', '#4CAF50', 'created');
    
    // Build purged resources section
    const purgedSection = buildResourcesSection(purgedResources, 'Purged Resources', '🗑️', '#f44336', 'destroyed');
    
    // Project name for fetching actual resources
    const projectName = session.projectName || '';
    
    // Only show management buttons for successful deployments
    const isSuccess = session.hasSuccess && !session.hasError;
    const managementButtons = isSuccess ? `
        <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
            <div style="font-weight: 600; color: #333; margin-bottom: 12px; font-size: 0.95em;">⚙️ Deployment Management</div>
            <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <button onclick="stopDeploymentResources('${projectName}')" class="btn" style="background: #ff9800; color: white; font-size: 0.85em; padding: 8px 16px;">
                    ⏸️ Stop EC2 Instances
                </button>
                <button onclick="startDeploymentResources('${projectName}')" class="btn" style="background: #4CAF50; color: white; font-size: 0.85em; padding: 8px 16px;">
                    ▶️ Start EC2 Instances
                </button>
                <button onclick="destroyDeployment('${projectName}')" class="btn" style="background: #f44336; color: white; font-size: 0.85em; padding: 8px 16px;">
                    🗑️ Destroy Infrastructure
                </button>
            </div>
            <div style="margin-top: 10px; font-size: 0.8em; color: #666; background: #fff3e0; padding: 8px 12px; border-radius: 4px; border-left: 3px solid #ff9800;">
                ⚠️ <strong>Note:</strong> Stop/Start only affects EC2 instances. Other resources (VPC, S3, NAT Gateway, etc.) remain active and may still incur charges.
            </div>
        </div>
    ` : '';
    
    // Connection info section for successful deployments
    const connectionSection = isSuccess ? `
        <div id="${sessionId}-connection" style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <div style="font-weight: 600; color: #333; font-size: 0.95em;">🔗 Connection Info</div>
                <button onclick="loadConnectionInfo('${projectName}', '${sessionId}')" class="btn btn-secondary" style="font-size: 0.75em; padding: 4px 10px;">
                    🔄 Load Connection Details
                </button>
            </div>
            <div id="${sessionId}-connection-content" style="color: #666; font-size: 0.9em;">
                Click "Load Connection Details" to fetch SSH commands and access information
            </div>
        </div>
    ` : '';
    
    // Credentials section for successful deployments
    const credentialsSection = isSuccess ? `
        <div id="${sessionId}-credentials" style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <div style="font-weight: 600; color: #333; font-size: 0.95em;">🔐 Credentials</div>
                <button onclick="loadCredentials('${projectName}', '${sessionId}')" class="btn btn-secondary" style="font-size: 0.75em; padding: 4px 10px;">
                    🔄 Load Credentials
                </button>
            </div>
            <div id="${sessionId}-credentials-content" style="color: #666; font-size: 0.9em;">
                Click "Load Credentials" to fetch GOAD lab credentials and access details
            </div>
        </div>
    ` : '';
    
    // GOAD Provisioning Instructions (for GOAD deployments)
    const isGoadDeployment = projectName.toLowerCase().includes('goad') || 
                             projectName.toLowerCase().includes('mini') ||
                             projectName.toLowerCase().includes('nha') ||
                             projectName.toLowerCase().includes('sccm');
    
    const goadProvisioningSection = (isSuccess && isGoadDeployment) ? `
        <div style="background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%); padding: 20px; border-radius: 8px; margin-bottom: 15px; border: 2px solid #ff9800;">
            <div style="font-weight: 700; color: #e65100; margin-bottom: 15px; font-size: 1.1em; display: flex; align-items: center; gap: 8px;">
                ⚠️ IMPORTANT: Active Directory Not Yet Configured!
            </div>
            
            <div style="background: white; padding: 15px; border-radius: 6px; margin-bottom: 15px;">
                <p style="margin: 0 0 10px 0; color: #333; font-size: 0.9em;">
                    <strong>What's deployed:</strong> AWS infrastructure (VMs, networking, Jumpbox, Team Server, Windows Attack Box) is ready.<br>
                    <strong>What's NOT deployed:</strong> Active Directory configuration, domain controllers, users, groups, GPOs, and vulnerabilities.
                </p>
                <p style="margin: 0; color: #666; font-size: 0.85em;">
                    The GOAD lab requires <strong>Ansible provisioning</strong> from your <strong>local machine</strong> or a Linux box with Ansible installed. This takes approximately <strong>30-60 minutes</strong>.
                </p>
            </div>
            
            <div style="font-weight: 600; color: #333; margin-bottom: 10px; font-size: 0.95em;">📋 Manual Steps Required:</div>
            
            <div style="background: #1e1e1e; border-radius: 6px; overflow: hidden; margin-bottom: 15px;">
                <div style="background: #333; padding: 8px 12px; display: flex; justify-content: space-between; align-items: center;">
                    <span style="color: #4ec9b0; font-size: 0.8em; font-weight: 500;">Step 1: Clone GOAD Repository (on your local machine)</span>
                    <button onclick="copyToClipboard('git clone https://github.com/Orange-Cyberdefense/GOAD.git && cd GOAD', this)" style="background: #555; color: #ccc; border: none; padding: 3px 8px; border-radius: 3px; cursor: pointer; font-size: 0.7em;">📋 Copy</button>
                </div>
                <div style="padding: 12px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.85em; color: #d4d4d4; line-height: 1.6;">
                    <div style="color: #6a9955;"># Clone the official GOAD repository</div>
                    <div style="color: #4ec9b0;">git clone https://github.com/Orange-Cyberdefense/GOAD.git</div>
                    <div style="color: #4ec9b0;">cd GOAD</div>
                </div>
            </div>
            
            <div style="background: #1e1e1e; border-radius: 6px; overflow: hidden; margin-bottom: 15px;">
                <div style="background: #333; padding: 8px 12px; display: flex; justify-content: space-between; align-items: center;">
                    <span style="color: #4ec9b0; font-size: 0.8em; font-weight: 500;">Step 2: Install Ansible Requirements</span>
                    <button onclick="copyToClipboard('pip install ansible pywinrm && ansible-galaxy install -r ansible/requirements.yml', this)" style="background: #555; color: #ccc; border: none; padding: 3px 8px; border-radius: 3px; cursor: pointer; font-size: 0.7em;">📋 Copy</button>
                </div>
                <div style="padding: 12px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.85em; color: #d4d4d4; line-height: 1.6;">
                    <div style="color: #6a9955;"># Install Ansible and dependencies</div>
                    <div style="color: #4ec9b0;">pip install ansible pywinrm</div>
                    <div style="color: #4ec9b0;">ansible-galaxy install -r ansible/requirements.yml</div>
                </div>
            </div>
            
            <div style="background: #1e1e1e; border-radius: 6px; overflow: hidden; margin-bottom: 15px;">
                <div style="background: #333; padding: 8px 12px; display: flex; justify-content: space-between; align-items: center;">
                    <span style="color: #4ec9b0; font-size: 0.8em; font-weight: 500;">Step 3: Create SSH Tunnel for WinRM Access</span>
                    <button onclick="copyGoadStep1('${projectName}')" style="background: #555; color: #ccc; border: none; padding: 3px 8px; border-radius: 3px; cursor: pointer; font-size: 0.7em;">📋 Copy</button>
                </div>
                <div style="padding: 12px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.85em; color: #d4d4d4; line-height: 1.6;">
                    <div style="color: #6a9955;"># Create SSH tunnel to access Windows VMs via WinRM</div>
                    <div style="color: #4ec9b0;">ssh -i ~/.ssh/${projectName}-goadmini-jumpbox-key.pem -L 5985:192.168.56.10:5985 ubuntu@&lt;JUMPBOX_IP&gt;</div>
                    <div style="color: #6a9955; margin-top: 8px;"># Keep this terminal open while running Ansible</div>
                </div>
            </div>
            
            <div style="background: #1e1e1e; border-radius: 6px; overflow: hidden; margin-bottom: 15px;">
                <div style="background: #333; padding: 8px 12px; display: flex; justify-content: space-between; align-items: center;">
                    <span style="color: #4ec9b0; font-size: 0.8em; font-weight: 500;">Step 4: Run Ansible Provisioning (30-60 min)</span>
                    <button onclick="copyToClipboard('cd ansible && ansible-playbook -i ../ad/GOAD-Mini/data/inventory -i ../ad/GOAD-Mini/providers/aws/inventory goad.yml', this)" style="background: #555; color: #ccc; border: none; padding: 3px 8px; border-radius: 3px; cursor: pointer; font-size: 0.7em;">📋 Copy</button>
                </div>
                <div style="padding: 12px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.85em; color: #d4d4d4; line-height: 1.6;">
                    <div style="color: #6a9955;"># Run Ansible to configure Active Directory</div>
                    <div style="color: #6a9955;"># This will take 30-60 minutes</div>
                    <div style="color: #4ec9b0;">cd ansible</div>
                    <div style="color: #4ec9b0;">ansible-playbook -i ../ad/GOAD-Mini/data/inventory -i ../ad/GOAD-Mini/providers/aws/inventory goad.yml</div>
                </div>
            </div>
            
            <div style="background: #e8f5e9; padding: 12px; border-radius: 6px; border-left: 4px solid #4CAF50;">
                <div style="font-weight: 600; color: #2e7d32; margin-bottom: 5px; font-size: 0.85em;">✅ After Ansible Completes:</div>
                <ul style="margin: 0; padding-left: 20px; color: #333; font-size: 0.85em; line-height: 1.6;">
                    <li>Active Directory domains will be configured</li>
                    <li>Domain controllers will be promoted</li>
                    <li>Users, groups, and GPOs will be created</li>
                    <li>Vulnerabilities will be configured for attack practice</li>
                    <li>RDP to Windows Attack Box and use PowerSploit to attack!</li>
                </ul>
            </div>
            
            <div style="margin-top: 15px; padding: 10px; background: #e3f2fd; border-radius: 6px; font-size: 0.8em; color: #1565c0;">
                💡 <strong>Tip:</strong> See the official <a href="https://orange-cyberdefense.github.io/GOAD/providers/aws/" target="_blank" style="color: #1565c0;">GOAD AWS Documentation</a> for detailed provisioning instructions.
            </div>
        </div>
    ` : '';

    return `
        <div id="${sessionId}-details" style="background: #fafafa; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px; padding: 20px;">
            <!-- Summary Stats -->
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px;">
                <div style="background: white; padding: 12px; border-radius: 8px; text-align: center; border: 1px solid #e0e0e0;">
                    <div style="font-size: 1.5em; font-weight: bold; color: #2196F3;">${infoCount}</div>
                    <div style="font-size: 0.75em; color: #666;">Info</div>
                </div>
                <div style="background: white; padding: 12px; border-radius: 8px; text-align: center; border: 1px solid #e0e0e0;">
                    <div style="font-size: 1.5em; font-weight: bold; color: #4CAF50;">${successCount}</div>
                    <div style="font-size: 0.75em; color: #666;">Success</div>
                </div>
                <div style="background: white; padding: 12px; border-radius: 8px; text-align: center; border: 1px solid #e0e0e0;">
                    <div style="font-size: 1.5em; font-weight: bold; color: #ff9800;">${warningCount}</div>
                    <div style="font-size: 0.75em; color: #666;">Warnings</div>
                </div>
                <div style="background: white; padding: 12px; border-radius: 8px; text-align: center; border: 1px solid #e0e0e0;">
                    <div style="font-size: 1.5em; font-weight: bold; color: #f44336;">${errorLogs.length}</div>
                    <div style="font-size: 0.75em; color: #666;">Errors</div>
                </div>
            </div>
            
            <!-- Management Buttons (for successful deployments) -->
            ${managementButtons}
            
            <!-- Deployment Info -->
            <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                <div style="font-weight: 600; color: #333; margin-bottom: 12px; font-size: 0.95em;">📋 Deployment Details</div>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; font-size: 0.85em;">
                    <div><span style="color: #666;">Project:</span> <strong>${session.projectName || 'Unknown'}</strong></div>
                    <div><span style="color: #666;">Date:</span> <strong>${formatDate(session.date)}</strong></div>
                    <div><span style="color: #666;">Started:</span> <strong>${session.firstTime ? session.firstTime.toLocaleTimeString() : 'N/A'}</strong></div>
                    <div><span style="color: #666;">Ended:</span> <strong>${session.lastTime ? session.lastTime.toLocaleTimeString() : 'N/A'}</strong></div>
                </div>
            </div>
            
            <!-- Connection Info (for successful deployments) -->
            ${connectionSection}
            
            <!-- Credentials (for successful deployments) -->
            ${credentialsSection}
            
            <!-- GOAD Provisioning Instructions (for GOAD deployments) -->
            ${goadProvisioningSection}
            
            <!-- AWS Resources Section (loaded dynamically) -->
            <div id="${sessionId}-resources" style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <div style="font-weight: 600; color: #333; font-size: 0.95em;">☁️ AWS Resources</div>
                    <button onclick="loadProjectResources('${projectName}', '${sessionId}')" class="btn btn-secondary" style="font-size: 0.75em; padding: 4px 10px;">
                        🔄 Load Resources
                    </button>
                </div>
                <div id="${sessionId}-resources-content" style="color: #666; font-size: 0.9em;">
                    Click "Load Resources" to fetch live resource status from AWS
                </div>
            </div>
            
            <!-- Purged Resources -->
            ${purgedSection}
            
            <!-- Phase Timeline -->
            <div style="background: white; padding: 15px; border-radius: 8px; border: 1px solid #e0e0e0; margin-bottom: 15px;">
                <div style="font-weight: 600; color: #333; margin-bottom: 12px; font-size: 0.95em;">📊 Deployment Phases</div>
                ${phaseHtml}
            </div>
            
            ${errorSection}
            
            <!-- View Full Logs Button -->
            <div style="margin-top: 20px; text-align: center;">
                <button onclick="showSessionLogs('${session.sessionKey}')" class="btn btn-secondary" style="font-size: 0.85em;">
                    📜 View Full Log Output
                </button>
            </div>
        </div>
    `;
}

/**
 * Extract resources from log messages
 */
function extractResourcesFromLogs(logs, action) {
    const resources = [];
    const resourcePatterns = [
        // Terraform create patterns
        { regex: /module\.(\w+)\.aws_(\w+)\.(\w+).*Creating/i, action: 'created' },
        { regex: /module\.(\w+)\.aws_(\w+)\.(\w+).*Creation complete/i, action: 'created' },
        { regex: /aws_(\w+)\.(\w+).*Creating/i, action: 'created' },
        { regex: /aws_(\w+)\.(\w+).*Creation complete/i, action: 'created' },
        // Terraform destroy patterns
        { regex: /module\.(\w+)\.aws_(\w+)\.(\w+).*Destroying/i, action: 'destroyed' },
        { regex: /module\.(\w+)\.aws_(\w+)\.(\w+).*Destruction complete/i, action: 'destroyed' },
        { regex: /aws_(\w+)\.(\w+).*Destroying/i, action: 'destroyed' },
        { regex: /aws_(\w+)\.(\w+).*Destruction complete/i, action: 'destroyed' },
        // Resource ID patterns
        { regex: /(vpc-[a-z0-9]+)/i, type: 'vpc' },
        { regex: /(subnet-[a-z0-9]+)/i, type: 'subnet' },
        { regex: /(sg-[a-z0-9]+)/i, type: 'security_group' },
        { regex: /(i-[a-z0-9]+)/i, type: 'ec2' },
        { regex: /(nat-[a-z0-9]+)/i, type: 'nat_gateway' },
        { regex: /(igw-[a-z0-9]+)/i, type: 'internet_gateway' },
        { regex: /(eipalloc-[a-z0-9]+)/i, type: 'elastic_ip' },
        { regex: /(rtb-[a-z0-9]+)/i, type: 'route_table' },
        { regex: /(eni-[a-z0-9]+)/i, type: 'network_interface' },
        { regex: /(key-[a-z0-9]+)/i, type: 'key_pair' },
    ];
    
    const seenResources = new Set();
    
    logs.forEach(log => {
        const msg = log.message.replace(/\x1b\[[0-9;]*m/g, ''); // Clean ANSI codes
        
        // Check for resource creation/destruction
        resourcePatterns.forEach(pattern => {
            if (pattern.action === action) {
                const match = msg.match(pattern.regex);
                if (match) {
                    let resourceType, resourceName;
                    if (match.length >= 4) {
                        // module.X.aws_Y.Z pattern
                        resourceType = match[2];
                        resourceName = `${match[1]}.${match[3]}`;
                    } else if (match.length >= 3) {
                        // aws_X.Y pattern
                        resourceType = match[1];
                        resourceName = match[2];
                    }
                    
                    if (resourceType && resourceName) {
                        const key = `${resourceType}:${resourceName}`;
                        if (!seenResources.has(key)) {
                            seenResources.add(key);
                            resources.push({
                                type: resourceType,
                                name: resourceName,
                                status: action === 'created' ? 'active' : 'deleted',
                                timestamp: log.timestamp
                            });
                        }
                    }
                }
            }
            
            // Also extract resource IDs
            if (pattern.type && !pattern.action) {
                const match = msg.match(pattern.regex);
                if (match && match[1]) {
                    const key = `${pattern.type}:${match[1]}`;
                    if (!seenResources.has(key)) {
                        // Determine if this is create or destroy based on context
                        const isDestroy = msg.toLowerCase().includes('destroy') || msg.toLowerCase().includes('deleted');
                        const isCreate = msg.toLowerCase().includes('creat') || msg.toLowerCase().includes('complete');
                        
                        if ((action === 'destroyed' && isDestroy) || (action === 'created' && isCreate)) {
                            seenResources.add(key);
                            resources.push({
                                type: pattern.type,
                                name: match[1],
                                id: match[1],
                                status: action === 'created' ? 'active' : 'deleted',
                                timestamp: log.timestamp
                            });
                        }
                    }
                }
            }
        });
    });
    
    return resources;
}

/**
 * Load and display resources for a specific project
 */
async function loadProjectResources(projectName, sessionId) {
    const contentDiv = document.getElementById(`${sessionId}-resources-content`);
    if (!contentDiv) return;
    
    if (!projectName) {
        contentDiv.innerHTML = '<span style="color: #f44336;">❌ No project name available</span>';
        return;
    }
    
    contentDiv.innerHTML = '<div style="display: flex; align-items: center; gap: 10px;"><div class="spinner" style="width: 20px; height: 20px;"></div> Loading resources from AWS...</div>';
    
    try {
        const response = await fetch(`${API_BASE}/deploy/resources/project/${encodeURIComponent(projectName)}?refresh=true`);
        const data = await response.json();
        
        if (!data.success) {
            contentDiv.innerHTML = `<span style="color: #f44336;">❌ ${data.error || 'Failed to load resources'}</span>`;
            return;
        }
        
        if (!data.resources || data.resources.length === 0) {
            contentDiv.innerHTML = '<span style="color: #666;">No resources found for this project</span>';
            return;
        }
        
        // Build resources display
        contentDiv.innerHTML = buildProjectResourcesHTML(data);
        
    } catch (error) {
        contentDiv.innerHTML = `<span style="color: #f44336;">❌ Error: ${error.message}</span>`;
    }
}

// Make loadProjectResources available globally for onclick handlers
window.loadProjectResources = loadProjectResources;

/**
 * Build HTML for project resources display
 */
function buildProjectResourcesHTML(data) {
    const resources = data.resources;
    const grouped = data.resources_grouped || {};
    
    // Resource type icons and labels
    const typeConfig = {
        'ec2': { icon: '🖥️', label: 'EC2 Instances' },
        'vpc': { icon: '🌐', label: 'VPCs' },
        'subnet': { icon: '📦', label: 'Subnets' },
        'security_group': { icon: '🔒', label: 'Security Groups' },
        'nat_gateway': { icon: '🚪', label: 'NAT Gateways' },
        'elastic_ip': { icon: '📍', label: 'Elastic IPs' },
        's3_bucket': { icon: '🪣', label: 'S3 Buckets' },
        'internet_gateway': { icon: '🌍', label: 'Internet Gateways' },
        'route_table': { icon: '🛣️', label: 'Route Tables' },
        'key_pair': { icon: '🔑', label: 'Key Pairs' },
        'network_interface': { icon: '🔌', label: 'Network Interfaces' },
        'iam_role': { icon: '👤', label: 'IAM Roles' },
        'iam_instance_profile': { icon: '🎭', label: 'IAM Instance Profiles' }
    };
    
    // State colors
    const stateColors = {
        'running': '#4CAF50',
        'stopped': '#ff9800',
        'terminated': '#f44336',
        'available': '#4CAF50',
        'active': '#4CAF50',
        'associated': '#4CAF50',
        'pending': '#2196F3',
        'deleted': '#9e9e9e',
        'deleting': '#ff9800'
    };
    
    let html = `
        <div style="margin-bottom: 10px; font-size: 0.85em; color: #666;">
            <strong>${resources.length}</strong> resources • 
            Deployed: ${data.deployed_at ? new Date(data.deployed_at).toLocaleString() : 'Unknown'} •
            Region: ${data.region || 'Unknown'}
        </div>
    `;
    
    // Build sections for each resource type
    const typeOrder = ['ec2', 'vpc', 'subnet', 'security_group', 'nat_gateway', 'elastic_ip', 's3_bucket', 'internet_gateway', 'route_table', 'key_pair', 'network_interface', 'iam_role', 'iam_instance_profile'];
    
    for (const type of typeOrder) {
        const typeResources = grouped[type];
        if (!typeResources || typeResources.length === 0) continue;
        
        const config = typeConfig[type] || { icon: '📦', label: type };
        
        html += `
            <div style="margin-bottom: 15px;">
                <div style="font-weight: 500; color: #333; margin-bottom: 8px; font-size: 0.9em;">
                    ${config.icon} ${config.label} (${typeResources.length})
                </div>
                <div style="display: flex; flex-direction: column; gap: 6px;">
        `;
        
        for (const resource of typeResources) {
            const stateColor = stateColors[resource.state] || '#666';
            const stateIcon = resource.state === 'running' ? '🟢' : 
                             resource.state === 'stopped' ? '🟠' : 
                             resource.state === 'terminated' ? '🔴' :
                             resource.state === 'available' || resource.state === 'active' ? '🟢' : '⚪';
            
            // Build details string
            let details = [];
            if (resource.role) details.push(resource.role);
            if (resource.instance_type) details.push(resource.instance_type);
            if (resource.public_ip) details.push(`Public: ${resource.public_ip}`);
            if (resource.private_ip) details.push(`Private: ${resource.private_ip}`);
            if (resource.cidr) details.push(resource.cidr);
            if (resource.az) details.push(resource.az);
            if (resource.key_type) details.push(`Type: ${resource.key_type}`);
            if (resource.route_count) details.push(`${resource.route_count} routes`);
            if (resource.role_count) details.push(`${resource.role_count} roles`);
            
            html += `
                <div style="display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: #f5f5f5; border-radius: 6px; font-size: 0.85em;">
                    <span>${stateIcon}</span>
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-weight: 500; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                            ${resource.name || resource.id}
                        </div>
                        <div style="font-size: 0.85em; color: #888; font-family: monospace;">
                            ${resource.id}
                        </div>
                        ${details.length > 0 ? `
                            <div style="font-size: 0.8em; color: #666; margin-top: 2px;">
                                ${details.join(' • ')}
                            </div>
                        ` : ''}
                    </div>
                    <span style="font-size: 0.75em; padding: 2px 8px; border-radius: 4px; background: ${stateColor}20; color: ${stateColor}; font-weight: 500; text-transform: uppercase;">
                        ${resource.state}
                    </span>
                </div>
            `;
        }
        
        html += `
                </div>
            </div>
        `;
    }
    
    // Add any remaining types not in the order
    for (const type of Object.keys(grouped)) {
        if (typeOrder.includes(type)) continue;
        
        const typeResources = grouped[type];
        if (!typeResources || typeResources.length === 0) continue;
        
        const config = typeConfig[type] || { icon: '📦', label: type };
        
        html += `
            <div style="margin-bottom: 15px;">
                <div style="font-weight: 500; color: #333; margin-bottom: 8px; font-size: 0.9em;">
                    ${config.icon} ${config.label} (${typeResources.length})
                </div>
                <div style="font-size: 0.85em; color: #666;">
                    ${typeResources.map(r => r.name || r.id).join(', ')}
                </div>
            </div>
        `;
    }
    
    return html;
}

/**
 * Build resources section HTML
 */
function buildResourcesSection(resources, title, icon, color, action) {
    if (resources.length === 0) {
        return '';
    }
    
    const typeIcons = {
        'vpc': '🌐',
        'subnet': '📡',
        'security_group': '🔒',
        'sg': '🔒',
        'ec2': '🖥️',
        'instance': '🖥️',
        'nat_gateway': '🚪',
        'nat': '🚪',
        'internet_gateway': '🌍',
        'igw': '🌍',
        'elastic_ip': '🔗',
        'eip': '🔗',
        'route_table': '🛣️',
        'rtb': '🛣️',
        'network_interface': '🔌',
        'eni': '🔌',
        'key_pair': '🔑',
        's3_bucket': '📦',
        'iam_role': '👤',
        'iam_instance_profile': '🎭',
        'default': '📄'
    };
    
    // Group resources by type
    const grouped = {};
    resources.forEach(r => {
        const type = r.type.replace(/_/g, ' ');
        if (!grouped[type]) grouped[type] = [];
        grouped[type].push(r);
    });
    
    const resourceRows = Object.entries(grouped).map(([type, items]) => {
        const typeIcon = typeIcons[type.replace(/ /g, '_')] || typeIcons['default'];
        return items.map(item => `
            <div style="display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: ${action === 'created' ? '#e8f5e9' : '#ffebee'}; border-radius: 6px; margin-bottom: 6px;">
                <span style="font-size: 1.1em;">${typeIcon}</span>
                <div style="flex: 1; min-width: 0;">
                    <div style="font-weight: 500; color: #333; font-size: 0.85em; text-transform: capitalize;">${type.replace(/_/g, ' ')}</div>
                    <div style="font-size: 0.8em; color: #666; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${item.name || item.id || 'Unknown'}</div>
                </div>
                <span style="background: ${action === 'created' ? '#4CAF50' : '#f44336'}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.7em; text-transform: uppercase;">${item.status}</span>
            </div>
        `).join('');
    }).join('');
    
    return `
        <div style="background: white; padding: 15px; border-radius: 8px; border: 1px solid #e0e0e0; margin-bottom: 15px;">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
                <div style="font-weight: 600; color: ${color}; font-size: 0.95em;">${icon} ${title}</div>
                <span style="background: ${color}15; color: ${color}; padding: 3px 10px; border-radius: 12px; font-size: 0.8em; font-weight: 500;">${resources.length} resources</span>
            </div>
            <div style="max-height: 250px; overflow-y: auto;">
                ${resourceRows}
            </div>
        </div>
    `;
}

/**
 * Toggle session expansion
 */
function toggleSessionExpand(sessionId) {
    if (expandedSessions.has(sessionId)) {
        expandedSessions.delete(sessionId);
    } else {
        expandedSessions.add(sessionId);
    }
    renderDeploymentTimeline();
}

/**
 * Show full logs for a specific session in a modal
 */
function showSessionLogs(sessionKey) {
    // sessionKey is either "date" or "date-projectName"
    const parts = sessionKey.split('-');
    const date = parts.slice(0, 3).join('-'); // YYYY-MM-DD
    const projectName = parts.length > 3 ? parts.slice(3).join('-') : null;
    
    // Filter logs by date and optionally by project name
    const sessionLogs = deploymentLogs.filter(log => {
        const matchesDate = log.timestamp.startsWith(date);
        if (!matchesDate) return false;
        if (projectName) {
            return log.project_name === projectName;
        }
        return true;
    });
    
    if (sessionLogs.length === 0) {
        alert('No logs found for this session.');
        return;
    }
    
    // Create modal
    const modal = document.createElement('div');
    modal.id = 'session-logs-modal';
    modal.style.cssText = `
        position: fixed; top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0,0,0,0.8); z-index: 10000;
        display: flex; align-items: center; justify-content: center;
        padding: 20px;
    `;
    
    const levelColors = {
        'info': '#4ec9b0',
        'success': '#4CAF50',
        'warning': '#ff9800',
        'error': '#f44336'
    };
    
    modal.innerHTML = `
        <div style="background: #1e1e1e; border-radius: 12px; max-width: 900px; width: 100%; max-height: 80vh; overflow: hidden; display: flex; flex-direction: column;">
            <div style="padding: 20px; border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between; align-items: center;">
                <h2 style="margin: 0; color: white;">📜 Full Deployment Logs - ${formatDate(date)}</h2>
                <button onclick="closeSessionLogsModal()" style="background: none; border: none; color: white; font-size: 24px; cursor: pointer;">&times;</button>
            </div>
            <div style="flex: 1; overflow-y: auto; padding: 15px; font-family: 'SF Mono', Monaco, monospace; font-size: 0.85em; line-height: 1.6;">
                ${sessionLogs.map(log => {
                    const time = new Date(log.timestamp).toLocaleTimeString();
                    const color = levelColors[log.level] || '#d4d4d4';
                    // Clean ANSI codes
                    const cleanMsg = log.message.replace(/\x1b\[[0-9;]*m/g, '');
                    return `<div style="margin-bottom: 6px; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                        <span style="color: #888;">[${time}]</span>
                        <span style="color: ${color}; background: ${color}20; padding: 1px 6px; border-radius: 3px; font-size: 0.8em; margin: 0 8px;">${log.level.toUpperCase()}</span>
                        <span style="color: #d4d4d4;">${cleanMsg}</span>
                    </div>`;
                }).join('')}
            </div>
            <div style="padding: 15px; border-top: 1px solid rgba(255,255,255,0.1); text-align: right;">
                <button onclick="copySessionLogs('${date}')" class="btn btn-secondary" style="margin-right: 10px;">📋 Copy All</button>
                <button onclick="closeSessionLogsModal()" class="btn btn-primary">Close</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeSessionLogsModal();
    });
}

/**
 * Close session logs modal
 */
function closeSessionLogsModal() {
    const modal = document.getElementById('session-logs-modal');
    if (modal) modal.remove();
}

/**
 * Copy session logs to clipboard
 */
function copySessionLogs(date) {
    const sessionLogs = deploymentLogs.filter(log => log.timestamp.startsWith(date));
    const text = sessionLogs.map(log => {
        const time = new Date(log.timestamp).toLocaleTimeString();
        const cleanMsg = log.message.replace(/\x1b\[[0-9;]*m/g, '');
        return `[${time}] [${log.level.toUpperCase()}] ${cleanMsg}`;
    }).join('\n');
    
    navigator.clipboard.writeText(text).then(() => {
        showMessage('Logs copied to clipboard!', 'success');
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
}

/**
 * Render deployment logs
 */
function renderDeploymentLogs() {
    const logsDiv = document.getElementById('deployment-logs');
    if (!logsDiv) return;
    
    // Get filter states
    const showInfo = document.getElementById('log-filter-info')?.checked ?? true;
    const showSuccess = document.getElementById('log-filter-success')?.checked ?? true;
    const showWarning = document.getElementById('log-filter-warning')?.checked ?? true;
    const showError = document.getElementById('log-filter-error')?.checked ?? true;
    
    const filtered = deploymentLogs.filter(log => {
        if (log.level === 'info' && !showInfo) return false;
        if (log.level === 'success' && !showSuccess) return false;
        if (log.level === 'warning' && !showWarning) return false;
        if (log.level === 'error' && !showError) return false;
        return true;
    });
    
    if (filtered.length === 0) {
        logsDiv.innerHTML = '<div style="color: #888;">No logs match the current filter</div>';
        return;
    }
    
    const levelColors = {
        'info': '#64b5f6',
        'success': '#81c784',
        'warning': '#ffb74d',
        'error': '#e57373'
    };
    
    logsDiv.innerHTML = filtered.slice(-100).reverse().map(log => {
        const time = formatTimestamp(log.timestamp);
        const color = levelColors[log.level] || '#888';
        const levelBadge = `<span style="color: ${color}; font-weight: bold;">[${log.level.toUpperCase()}]</span>`;
        
        let html = `<div style="margin-bottom: 8px;"><span style="color: #888;">${time}</span> ${levelBadge} <span style="color: #fff;">${escapeHtml(log.message)}</span></div>`;
        
        if (log.details) {
            html += `<div style="margin-left: 20px; margin-bottom: 12px; padding: 8px; background: #2d2d2d; border-radius: 4px; color: #aaa; font-size: 0.9em; white-space: pre-wrap;">${escapeHtml(log.details)}</span></div>`;
        }
        
        return html;
    }).join('');
    
    // Scroll to bottom
    logsDiv.scrollTop = logsDiv.scrollHeight;
}

/**
 * Filter logs based on checkboxes
 */
function filterLogs() {
    renderDeploymentLogs();
}

/**
 * Refresh deployment history
 */
async function refreshDeploymentHistory() {
    await loadDeploymentHistory();
    showMessage('Deployment history refreshed', 'success');
}

/**
 * Clear deployment logs (current view only - archive is preserved)
 */
function clearDeploymentLogs() {
    if (!confirm('Clear current deployment logs?\n\nNote: All logs are automatically saved to the archive and remain accessible via "View Archived" button.')) {
        return;
    }
    
    deploymentLogs = [];
    localStorage.removeItem(LOGS_STORAGE_KEY);
    renderDeploymentTimeline();
    renderDeploymentLogs();
    showMessage('Current logs cleared (archive preserved)', 'success');
}

/**
 * View archived logs in a modal
 */
function viewArchivedLogs() {
    initDeploymentLogs(); // Ensure archived logs are loaded
    
    if (archivedLogs.length === 0) {
        alert('No archived logs available.');
        return;
    }
    
    // Create modal
    const modal = document.createElement('div');
    modal.id = 'archived-logs-modal';
    modal.style.cssText = `
        position: fixed; top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0,0,0,0.7); z-index: 10000;
        display: flex; align-items: center; justify-content: center;
        padding: 20px;
    `;
    
    // Group logs by date
    const logsByDate = {};
    archivedLogs.forEach(log => {
        const date = new Date(log.timestamp).toLocaleDateString();
        if (!logsByDate[date]) logsByDate[date] = [];
        logsByDate[date].push(log);
    });
    
    // Filter state
    let currentFilter = 'all';
    
    function renderArchivedContent() {
        const filteredLogs = currentFilter === 'all' 
            ? archivedLogs 
            : archivedLogs.filter(l => l.level === currentFilter);
        
        return `
            <div style="background: #1e293b; border-radius: 12px; max-width: 900px; width: 100%; max-height: 80vh; overflow: hidden; display: flex; flex-direction: column;">
                <div style="padding: 20px; border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between; align-items: center;">
                    <h2 style="margin: 0; color: white;">📚 Archived Logs (${archivedLogs.length} total)</h2>
                    <button onclick="closeArchivedLogsModal()" style="background: none; border: none; color: white; font-size: 24px; cursor: pointer;">&times;</button>
                </div>
                
                <!-- Filters -->
                <div style="padding: 15px 20px; background: rgba(0,0,0,0.2); display: flex; gap: 10px; flex-wrap: wrap; align-items: center;">
                    <span style="color: #94a3b8; font-size: 0.9em;">Filter:</span>
                    <button onclick="filterArchivedLogs('all')" class="filter-btn ${currentFilter === 'all' ? 'active' : ''}" style="padding: 6px 14px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.2); background: ${currentFilter === 'all' ? '#3b82f6' : 'transparent'}; color: white; cursor: pointer; font-size: 0.85em;">
                        All (${archivedLogs.length})
                    </button>
                    <button onclick="filterArchivedLogs('info')" class="filter-btn ${currentFilter === 'info' ? 'active' : ''}" style="padding: 6px 14px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.2); background: ${currentFilter === 'info' ? '#3b82f6' : 'transparent'}; color: white; cursor: pointer; font-size: 0.85em;">
                        ℹ️ Info (${archivedLogs.filter(l => l.level === 'info').length})
                    </button>
                    <button onclick="filterArchivedLogs('success')" class="filter-btn ${currentFilter === 'success' ? 'active' : ''}" style="padding: 6px 14px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.2); background: ${currentFilter === 'success' ? '#22c55e' : 'transparent'}; color: white; cursor: pointer; font-size: 0.85em;">
                        ✅ Success (${archivedLogs.filter(l => l.level === 'success').length})
                    </button>
                    <button onclick="filterArchivedLogs('error')" class="filter-btn ${currentFilter === 'error' ? 'active' : ''}" style="padding: 6px 14px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.2); background: ${currentFilter === 'error' ? '#ef4444' : 'transparent'}; color: white; cursor: pointer; font-size: 0.85em;">
                        ❌ Errors (${archivedLogs.filter(l => l.level === 'error').length})
                    </button>
                    <button onclick="filterArchivedLogs('warning')" class="filter-btn ${currentFilter === 'warning' ? 'active' : ''}" style="padding: 6px 14px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.2); background: ${currentFilter === 'warning' ? '#f59e0b' : 'transparent'}; color: white; cursor: pointer; font-size: 0.85em;">
                        ⚠️ Warnings (${archivedLogs.filter(l => l.level === 'warning').length})
                    </button>
                </div>
                
                <!-- Logs content -->
                <div id="archived-logs-content" style="flex: 1; overflow-y: auto; padding: 20px;">
                    ${filteredLogs.length === 0 ? `
                        <p style="text-align: center; color: #94a3b8;">No logs matching filter.</p>
                    ` : filteredLogs.slice().reverse().map(log => {
                        const time = new Date(log.timestamp).toLocaleString();
                        const levelColors = {
                            info: '#3b82f6',
                            success: '#22c55e',
                            error: '#ef4444',
                            warning: '#f59e0b'
                        };
                        const levelIcons = {
                            info: 'ℹ️',
                            success: '✅',
                            error: '❌',
                            warning: '⚠️'
                        };
                        return `
                            <div style="padding: 12px; margin-bottom: 8px; background: rgba(255,255,255,0.05); border-radius: 8px; border-left: 3px solid ${levelColors[log.level] || '#666'};">
                                <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                                    <span style="color: ${levelColors[log.level] || '#fff'}; font-weight: 500;">
                                        ${levelIcons[log.level] || ''} ${log.level.toUpperCase()}
                                    </span>
                                    <span style="color: #64748b; font-size: 0.85em;">${time}</span>
                                </div>
                                <div style="color: #e2e8f0; font-size: 0.9em;">${escapeHtml(log.message)}</div>
                                ${log.details ? `<div style="color: #94a3b8; font-size: 0.8em; margin-top: 5px; font-family: monospace;">${escapeHtml(log.details)}</div>` : ''}
                            </div>
                        `;
                    }).join('')}
                </div>
                
                <!-- Footer -->
                <div style="padding: 15px 20px; border-top: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: flex-end;">
                    <button onclick="downloadArchivedLogs()" style="padding: 8px 16px; background: #3b82f6; border: none; border-radius: 6px; color: white; cursor: pointer; font-size: 0.9em;">
                        📥 Download All
                    </button>
                </div>
            </div>
        `;
    }
    
    modal.innerHTML = renderArchivedContent();
    document.body.appendChild(modal);
    
    // Store filter function globally for button clicks
    window.filterArchivedLogs = (filter) => {
        currentFilter = filter;
        modal.innerHTML = renderArchivedContent();
    };
    
    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeArchivedLogsModal();
    });
}

function closeArchivedLogsModal() {
    const modal = document.getElementById('archived-logs-modal');
    if (modal) modal.remove();
}

function clearArchivedLogs() {
    if (!confirm('Permanently delete all archived logs? This cannot be undone.')) {
        return;
    }
    archivedLogs = [];
    localStorage.removeItem(ARCHIVED_LOGS_KEY);
    closeArchivedLogsModal();
    showMessage('Archived logs cleared', 'success');
}

function downloadArchivedLogs() {
    const logText = archivedLogs.map(log => 
        `[${log.timestamp}] [${log.level.toUpperCase()}] ${log.message}${log.details ? '\n  ' + log.details : ''}`
    ).join('\n');
    
    const blob = new Blob([logText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `archived-deployment-logs-${new Date().toISOString().split('T')[0]}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    
    showMessage('Archived logs downloaded', 'success');
}

/**
 * Copy logs to clipboard
 */
function copyLogs() {
    const logText = deploymentLogs.map(log => 
        `[${log.timestamp}] [${log.level.toUpperCase()}] ${log.message}${log.details ? '\n  ' + log.details : ''}`
    ).join('\n');
    
    navigator.clipboard.writeText(logText).then(() => {
        showMessage('Logs copied to clipboard', 'success');
    }).catch(err => {
        showMessage('Failed to copy logs', 'error');
    });
}

/**
 * Download logs as file
 */
function downloadLogs() {
    const logText = deploymentLogs.map(log => 
        `[${log.timestamp}] [${log.level.toUpperCase()}] ${log.message}${log.details ? '\n  ' + log.details : ''}`
    ).join('\n');
    
    const blob = new Blob([logText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `deployment-logs-${new Date().toISOString().split('T')[0]}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    
    showMessage('Logs downloaded', 'success');
}

// Helper functions
function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
}

function formatTime(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleString('en-US', { 
        month: 'short', day: 'numeric', 
        hour: '2-digit', minute: '2-digit', second: '2-digit' 
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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
    
    // Load SSL status for redirectors
    loadSSLStatus(publicIps);
}

/**
 * Load SSL status for redirectors
 */
async function loadSSLStatus(redirectorIps) {
    const sslContent = document.getElementById('ssl-status-content');
    if (!sslContent) return;
    
    if (!redirectorIps || redirectorIps.length === 0) {
        sslContent.innerHTML = '<p style="color: #666;">No redirectors deployed</p>';
        return;
    }
    
    // For now, show status based on config (actual status would require SSM or API call to redirector)
    try {
        const configResponse = await fetch(`${API_BASE}/config/`);
        const configData = await configResponse.json();
        
        if (!configData.success) {
            sslContent.innerHTML = '<p style="color: #666;">Unable to load SSL configuration</p>';
            return;
        }
        
        const config = configData.config || {};
        const sslProvider = config.ssl_provider || 'letsencrypt';
        const adminEmail = config.admin_email || '';
        const sslAutoRetry = config.ssl_auto_retry !== false;
        const enableSsl = config.enable_ssl_certificate !== false;
        
        if (!enableSsl) {
            sslContent.innerHTML = `
                <div style="display: flex; align-items: center; gap: 10px; padding: 10px; background: #fff3e0; border-radius: 6px;">
                    <span style="font-size: 1.5em;">⚠️</span>
                    <div>
                        <strong style="color: #e65100;">SSL Disabled</strong>
                        <p style="margin: 5px 0 0 0; font-size: 0.9em; color: #666;">HTTPS is not configured on redirectors</p>
                    </div>
                </div>
            `;
            return;
        }
        
        let statusHtml = '';
        
        if (sslProvider === 'letsencrypt') {
            statusHtml = `
                <div style="display: grid; gap: 15px;">
                    <div style="display: flex; align-items: center; gap: 10px; padding: 12px; background: #e3f2fd; border-radius: 6px;">
                        <span style="font-size: 1.5em;">🔒</span>
                        <div>
                            <strong style="color: #1565c0;">Let's Encrypt</strong>
                            <p style="margin: 5px 0 0 0; font-size: 0.9em; color: #666;">
                                Auto-renewal enabled • Notifications to: ${adminEmail || 'Not set'}
                            </p>
                        </div>
                    </div>
                    
                    <div style="font-size: 0.9em;">
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px;">
                            <div style="padding: 10px; background: #f5f5f5; border-radius: 4px;">
                                <strong>Auto-Retry:</strong> ${sslAutoRetry ? '✅ Enabled' : '❌ Disabled'}
                            </div>
                            <div style="padding: 10px; background: #f5f5f5; border-radius: 4px;">
                                <strong>Certificate Validity:</strong> 90 days
                            </div>
                        </div>
                    </div>
                    
                    <div style="padding: 12px; background: #fff8e1; border-radius: 6px; font-size: 0.85em;">
                        <strong>📋 Certificate Status Check:</strong>
                        <p style="margin: 8px 0 0 0; color: #666;">
                            SSH into a redirector and run: <code style="background: #f5f5f5; padding: 2px 6px; border-radius: 3px;">cat /opt/ssl-status.json</code>
                        </p>
                        <p style="margin: 5px 0 0 0; color: #666;">
                            Or check logs: <code style="background: #f5f5f5; padding: 2px 6px; border-radius: 3px;">tail -f /var/log/ssl-auto-request.log</code>
                        </p>
                    </div>
                </div>
            `;
        } else {
            statusHtml = `
                <div style="display: flex; align-items: center; gap: 10px; padding: 12px; background: #fff3e0; border-radius: 6px;">
                    <span style="font-size: 1.5em;">⚠️</span>
                    <div>
                        <strong style="color: #e65100;">Self-Signed Certificate</strong>
                        <p style="margin: 5px 0 0 0; font-size: 0.9em; color: #666;">
                            Browsers will show security warnings. Consider switching to Let's Encrypt.
                        </p>
                    </div>
                </div>
            `;
        }
        
        sslContent.innerHTML = statusHtml;
        
    } catch (error) {
        console.error('Error loading SSL status:', error);
        sslContent.innerHTML = '<p style="color: #c62828;">Error loading SSL status</p>';
    }
}

/**
 * Refresh SSL status
 */
async function refreshSSLStatus() {
    const sslContent = document.getElementById('ssl-status-content');
    if (sslContent) {
        sslContent.innerHTML = '<p style="color: #666; font-style: italic;">Refreshing...</p>';
    }
    
    // Get redirector IPs from the page
    const redirectorDetails = document.getElementById('redirectors-details');
    if (redirectorDetails) {
        const ipMatches = redirectorDetails.innerHTML.match(/\d+\.\d+\.\d+\.\d+/g) || [];
        await loadSSLStatus(ipMatches);
    }
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
async function populateConnectionInfo(data) {
    const section = document.getElementById('connection-info-section');
    const commands = document.getElementById('connection-commands');
    
    if (!data.has_deployment) {
        section.style.display = 'none';
        return;
    }
    
    section.style.display = 'block';
    
    // Get the configured key pair name from config
    let keyPairName = 'your-key';
    try {
        const configResponse = await fetch(`${API_BASE}/config/`);
        const configData = await configResponse.json();
        if (configData.success && configData.config?.key_pair_name) {
            keyPairName = configData.config.key_pair_name;
        }
    } catch (e) {
        console.log('Could not fetch key pair name from config');
    }
    
    let html = '';
    
    // Bastion RDP command
    if (data.bastion && data.bastion.public_ip) {
        html += `
            <div style="margin-bottom: 20px;">
                <h4 style="margin: 0 0 10px 0;">🖥️ Connect to Bastion (RDP)</h4>
                <code style="background: #1e1e1e; color: #4ec9b0; padding: 10px 15px; border-radius: 5px; display: block; overflow-x: auto;">
                    mstsc /v:${data.bastion.public_ip}
                </code>
                <p style="color: #666; font-size: 0.85em; margin-top: 8px;">
                    Username: <code>Administrator</code> | Get password from AWS Console using your key pair
                </p>
            </div>
        `;
    }
    
    // SSH to C2 servers via bastion
    const c2Ips = data.c2_servers?.private_ips || [];
    if (c2Ips.length > 0 && data.bastion?.public_ip) {
        html += `
            <div style="margin-bottom: 20px;">
                <h4 style="margin: 0 0 10px 0;">🎯 SSH to C2 Servers (via Bastion WSL2)</h4>
                <p style="color: #666; font-size: 0.9em; margin-bottom: 10px;">
                    Connect through the Windows Bastion's WSL2 environment.
                </p>
                ${c2Ips.map((ip, idx) => `
                    <div style="margin-bottom: 10px;">
                        <span style="color: #666;">C2 Server ${idx + 1}:</span>
                        <code style="background: #1e1e1e; color: #4ec9b0; padding: 10px 15px; border-radius: 5px; display: block; margin-top: 5px; overflow-x: auto;">
                            ssh -i ~/.ssh/${keyPairName}.pem ubuntu@${ip}
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
                <p style="color: #666; font-size: 0.9em; margin-bottom: 10px;">
                    Direct SSH access. Redirectors run Ubuntu.
                </p>
                ${redirectorIps.map((ip, idx) => `
                    <div style="margin-bottom: 10px;">
                        <span style="color: #666;">Redirector ${idx + 1}:</span>
                        <code style="background: #1e1e1e; color: #4ec9b0; padding: 10px 15px; border-radius: 5px; display: block; margin-top: 5px; overflow-x: auto;">
                            ssh -i ~/.ssh/${keyPairName}.pem ubuntu@${ip}
                        </code>
                    </div>
                `).join('')}
                
                <details style="margin-top: 15px;">
                    <summary style="cursor: pointer; color: #1976d2; font-weight: 500;">
                        📋 Common Redirector Commands
                    </summary>
                    <div style="margin-top: 10px; padding: 15px; background: #f5f5f5; border-radius: 5px; font-size: 0.9em;">
                        <p style="margin: 0 0 10px 0;"><strong>Check SSL Status:</strong></p>
                        <code style="background: #1e1e1e; color: #4ec9b0; padding: 8px 12px; border-radius: 4px; display: block;">cat /opt/ssl-status.json</code>
                        
                        <p style="margin: 15px 0 10px 0;"><strong>View Nginx Config:</strong></p>
                        <code style="background: #1e1e1e; color: #4ec9b0; padding: 8px 12px; border-radius: 4px; display: block;">sudo cat /etc/nginx/sites-enabled/default</code>
                        
                        <p style="margin: 15px 0 10px 0;"><strong>Edit Nginx (for URI changes):</strong></p>
                        <code style="background: #1e1e1e; color: #4ec9b0; padding: 8px 12px; border-radius: 4px; display: block;">sudo nano /etc/nginx/sites-enabled/default</code>
                        
                        <p style="margin: 15px 0 10px 0;"><strong>Reload Nginx After Changes:</strong></p>
                        <code style="background: #1e1e1e; color: #4ec9b0; padding: 8px 12px; border-radius: 4px; display: block;">sudo nginx -t && sudo systemctl reload nginx</code>
                        
                        <p style="margin: 15px 0 10px 0;"><strong>View Access Logs:</strong></p>
                        <code style="background: #1e1e1e; color: #4ec9b0; padding: 8px 12px; border-radius: 4px; display: block;">sudo tail -f /var/log/nginx/access.log</code>
                        
                        <p style="margin: 15px 0 10px 0;"><strong>Manual Let's Encrypt Request:</strong></p>
                        <code style="background: #1e1e1e; color: #4ec9b0; padding: 8px 12px; border-radius: 4px; display: block;">sudo certbot --nginx -d yourdomain.com</code>
                    </div>
                </details>
            </div>
        `;
    }
    
    // GOAD Jumpbox (fetch from GOAD API)
    try {
        const goadResponse = await fetch(`${API_BASE}/goad/jumpbox`);
        const goadData = await goadResponse.json();
        
        if (goadData.success && goadData.jumpbox) {
            const jb = goadData.jumpbox;
            
            // Also fetch credentials
            let credsHtml = '';
            try {
                const credsResponse = await fetch(`${API_BASE}/goad/credentials`);
                const credsData = await credsResponse.json();
                
                if (credsData.success && credsData.credentials) {
                    const creds = credsData.credentials;
                    credsHtml = `
                        <details style="margin-top: 15px;">
                            <summary style="cursor: pointer; color: #d32f2f; font-weight: 500;">
                                🔑 GOAD Default Credentials
                            </summary>
                            <div style="margin-top: 10px; padding: 15px; background: #ffebee; border-radius: 5px; font-size: 0.9em;">
                                <p style="margin: 0 0 15px 0; color: #c62828;">
                                    <strong>⚠️ Intentionally Vulnerable:</strong> These are default GOAD credentials for the <strong>${creds.lab_display_name || creds.lab_name}</strong> lab.
                                </p>
                                
                                <div style="background: white; padding: 12px; border-radius: 5px; margin-bottom: 10px;">
                                    <p style="margin: 0 0 8px 0;"><strong>Default Password (All Users):</strong></p>
                                    <code style="background: #1e1e1e; color: #f44336; padding: 8px 15px; border-radius: 4px; display: inline-block; font-size: 1.1em;">
                                        ${creds.default_password || 'vagrant'}
                                    </code>
                                </div>
                                
                                ${creds.domains && creds.domains.length > 0 ? `
                                    <p style="margin: 15px 0 10px 0;"><strong>Domains in this Lab:</strong></p>
                                    <table style="width: 100%; border-collapse: collapse; font-size: 0.9em; margin-bottom: 15px;">
                                        <thead>
                                            <tr style="background: #e3f2fd;">
                                                <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Domain</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">FQDN</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">DC</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            ${creds.domains.map(d => `
                                                <tr>
                                                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>${d.name}</strong></td>
                                                    <td style="padding: 8px; border: 1px solid #ddd;"><code>${d.fqdn}</code></td>
                                                    <td style="padding: 8px; border: 1px solid #ddd;">${d.dc}</td>
                                                </tr>
                                            `).join('')}
                                        </tbody>
                                    </table>
                                ` : ''}
                                
                                ${creds.domain_admins && creds.domain_admins.length > 0 ? `
                                    <p style="margin: 15px 0 10px 0;"><strong>Domain Administrators:</strong></p>
                                    <table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                                        <thead>
                                            <tr style="background: #f5f5f5;">
                                                <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Domain</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Username</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Password</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            ${creds.domain_admins.map(admin => `
                                                <tr>
                                                    <td style="padding: 8px; border: 1px solid #ddd;">${admin.domain}</td>
                                                    <td style="padding: 8px; border: 1px solid #ddd;"><code>${admin.username}</code></td>
                                                    <td style="padding: 8px; border: 1px solid #ddd;"><code style="color: #d32f2f;">${admin.password}</code></td>
                                                </tr>
                                            `).join('')}
                                        </tbody>
                                    </table>
                                ` : ''}
                                
                                ${creds.key_users && creds.key_users.length > 0 ? `
                                    <p style="margin: 15px 0 10px 0;"><strong>Key Domain Users:</strong></p>
                                    <table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                                        <thead>
                                            <tr style="background: #fff3e0;">
                                                <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Domain</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Username</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Password</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Role</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            ${creds.key_users.map(user => `
                                                <tr>
                                                    <td style="padding: 8px; border: 1px solid #ddd;">${user.domain}</td>
                                                    <td style="padding: 8px; border: 1px solid #ddd;"><code>${user.username}</code></td>
                                                    <td style="padding: 8px; border: 1px solid #ddd;"><code style="color: #d32f2f;">${user.password}</code></td>
                                                    <td style="padding: 8px; border: 1px solid #ddd; font-size: 0.85em;">${user.role}</td>
                                                </tr>
                                            `).join('')}
                                        </tbody>
                                    </table>
                                ` : ''}
                                
                                ${creds.trusts && creds.trusts.length > 0 ? `
                                    <p style="margin: 15px 0 10px 0;"><strong>Domain Trusts:</strong></p>
                                    <table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                                        <thead>
                                            <tr style="background: #f3e5f5;">
                                                <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">From</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">To</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Type</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            ${creds.trusts.map(trust => `
                                                <tr>
                                                    <td style="padding: 8px; border: 1px solid #ddd;">${trust.from}</td>
                                                    <td style="padding: 8px; border: 1px solid #ddd;">${trust.to}</td>
                                                    <td style="padding: 8px; border: 1px solid #ddd;">${trust.type}</td>
                                                </tr>
                                            `).join('')}
                                        </tbody>
                                    </table>
                                ` : ''}
                                
                                ${creds.special_accounts && creds.special_accounts.length > 0 ? `
                                    <p style="margin: 15px 0 10px 0;"><strong>Special Accounts (Lab-Specific):</strong></p>
                                    <div style="background: #fff8e1; padding: 10px; border-radius: 5px;">
                                        ${creds.special_accounts.map(acc => `
                                            <p style="margin: 5px 0;"><strong>${acc.name}:</strong> ${acc.note}</p>
                                        `).join('')}
                                    </div>
                                ` : ''}
                                
                                <p style="margin: 15px 0 10px 0;"><strong>Local Accounts (All VMs):</strong></p>
                                <table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                                    <thead>
                                        <tr style="background: #f5f5f5;">
                                            <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Account</th>
                                            <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Username</th>
                                            <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Password</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        <tr>
                                            <td style="padding: 8px; border: 1px solid #ddd;">Local Admin</td>
                                            <td style="padding: 8px; border: 1px solid #ddd;"><code>Administrator</code></td>
                                            <td style="padding: 8px; border: 1px solid #ddd;"><code style="color: #d32f2f;">vagrant</code></td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 8px; border: 1px solid #ddd;">Vagrant User</td>
                                            <td style="padding: 8px; border: 1px solid #ddd;"><code>vagrant</code></td>
                                            <td style="padding: 8px; border: 1px solid #ddd;"><code style="color: #d32f2f;">vagrant</code></td>
                                        </tr>
                                    </tbody>
                                </table>
                                
                                <p style="margin: 15px 0 0 0; font-size: 0.85em; color: #666;">
                                    📁 Full inventory: <code>${creds.inventory_path || '/opt/goad/ad/&lt;lab&gt;/data/inventory'}</code>
                                </p>
                            </div>
                        </details>
                    `;
                }
            } catch (e) {
                console.log('Could not fetch GOAD credentials');
            }
            
            html += `
                <div style="margin-bottom: 20px;">
                    <h4 style="margin: 0 0 10px 0;">🎮 GOAD Jumpbox (Ubuntu)</h4>
                    <p style="color: #666; font-size: 0.9em; margin-bottom: 10px;">
                        Access the GOAD lab management server. Lab: <strong>${jb.lab_name || 'GOAD'}</strong>
                    </p>
                    
                    ${jb.public_ip ? `
                        <div style="margin-bottom: 10px;">
                            <span style="color: #666;">SSH Access:</span>
                            <code style="background: #1e1e1e; color: #4ec9b0; padding: 10px 15px; border-radius: 5px; display: block; margin-top: 5px; overflow-x: auto;">
                                ${jb.commands?.ssh || `ssh -i ${jb.ssh_key_path || '~/.ssh/goad-key.pem'} ubuntu@${jb.public_ip}`}
                            </code>
                        </div>
                        
                        <div style="margin-bottom: 10px;">
                            <span style="color: #666;">SOCKS Proxy (for accessing AD network):</span>
                            <code style="background: #1e1e1e; color: #4ec9b0; padding: 10px 15px; border-radius: 5px; display: block; margin-top: 5px; overflow-x: auto;">
                                ${jb.commands?.socks_proxy || `ssh -D 1080 -i ${jb.ssh_key_path || '~/.ssh/goad-key.pem'} ubuntu@${jb.public_ip}`}
                            </code>
                        </div>
                    ` : `
                        <p style="color: #f57c00;">⚠️ Jumpbox IP not available yet. The lab may still be deploying.</p>
                    `}
                    
                    ${credsHtml}
                    
                    <details style="margin-top: 15px;">
                        <summary style="cursor: pointer; color: #1976d2; font-weight: 500;">
                            📋 Common GOAD Commands
                        </summary>
                        <div style="margin-top: 10px; padding: 15px; background: #f5f5f5; border-radius: 5px; font-size: 0.9em;">
                            <p style="margin: 0 0 10px 0;"><strong>Check Lab Status:</strong></p>
                            <code style="background: #1e1e1e; color: #4ec9b0; padding: 8px 12px; border-radius: 4px; display: block;">cd /opt/goad && ./goad.sh -t check -l GOAD -p aws</code>
                            
                            <p style="margin: 15px 0 10px 0;"><strong>Run Ansible Provisioning:</strong></p>
                            <code style="background: #1e1e1e; color: #4ec9b0; padding: 8px 12px; border-radius: 4px; display: block;">cd /opt/goad && ./goad.sh -t install -l GOAD -p aws</code>
                            
                            <p style="margin: 15px 0 10px 0;"><strong>View Ansible Inventory:</strong></p>
                            <code style="background: #1e1e1e; color: #4ec9b0; padding: 8px 12px; border-radius: 4px; display: block;">cat /opt/goad/ad/GOAD/providers/aws/inventory</code>
                            
                            <p style="margin: 15px 0 10px 0;"><strong>Test WinRM to DC:</strong></p>
                            <code style="background: #1e1e1e; color: #4ec9b0; padding: 8px 12px; border-radius: 4px; display: block;">evil-winrm -i DC_IP -u Administrator -p 'vagrant'</code>
                        </div>
                    </details>
                </div>
            `;
        }
    } catch (e) {
        console.log('No GOAD jumpbox info available');
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
// DEPLOYMENT DETAILS FUNCTIONS
// ============================================================================

/**
 * Load comprehensive deployment details for the Deployment Manager UI
 */
async function loadDeploymentDetails() {
    const detailsPanel = document.getElementById('deployment-details');
    
    if (!detailsPanel) {
        console.log('Deployment details panel not found');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/deploy/deployment-details`);
        const data = await response.json();
        
        if (!data.success || !data.has_deployment) {
            detailsPanel.style.display = 'none';
            return;
        }
        
        // Show the panel
        detailsPanel.style.display = 'block';
        
        // Populate Quick Connect
        updateQuickConnect(data);
        
        // Populate Cobalt Strike connection
        populateCobaltStrikeInfo(data);
        
        // Populate infrastructure IPs
        populateInfrastructureIPs(data);
        
        // Populate GOAD info if deployed
        if (data.goad && data.goad.deployed) {
            populateGoadDetails(data.goad);
        }
        
        // Populate access instructions
        populateAccessInstructions(data);
        
    } catch (error) {
        console.error('Error loading deployment details:', error);
        detailsPanel.style.display = 'none';
    }
}

/**
 * Update Quick Connect summary section
 */
function updateQuickConnect(data) {
    const quickConnectDiv = document.getElementById('quick-connect-info');
    if (!quickConnectDiv) return;
    
    const arch = data.architecture;
    let html = '';
    
    if (arch === 'goad-only') {
        html = `
            <div style="display: flex; align-items: center; gap: 15px; padding: 15px; background: #e8f5e9; border-radius: 8px;">
                <span style="font-size: 2em;">🎯</span>
                <div>
                    <strong>Direct Connection</strong>
                    <p style="margin: 5px 0 0 0; color: #2e7d32;">
                        Connect CS client directly to <code>${data.cobalt_strike.host || 'jumpbox_ip'}:${data.cobalt_strike.port}</code>
                    </p>
                </div>
            </div>
        `;
    } else if (arch === 'combined') {
        html = `
            <div style="display: flex; align-items: center; gap: 15px; padding: 15px; background: #fff3e0; border-radius: 8px;">
                <span style="font-size: 2em;">🔗</span>
                <div>
                    <strong>SSH Tunnel Required</strong>
                    <p style="margin: 5px 0 0 0; color: #e65100;">
                        RDP to bastion, then SSH tunnel to C2 server. GOAD accessible via VPC peering.
                    </p>
                </div>
            </div>
        `;
    } else {
        html = `
            <div style="display: flex; align-items: center; gap: 15px; padding: 15px; background: #e3f2fd; border-radius: 8px;">
                <span style="font-size: 2em;">🔒</span>
                <div>
                    <strong>SSH Tunnel Required</strong>
                    <p style="margin: 5px 0 0 0; color: #1565c0;">
                        RDP to bastion at <code>${data.infrastructure?.bastion?.ip || 'bastion_ip'}</code>, then create SSH tunnel to C2 server.
                    </p>
                </div>
            </div>
        `;
    }
    
    quickConnectDiv.innerHTML = html;
}

/**
 * Populate Cobalt Strike connection info
 */
function populateCobaltStrikeInfo(data) {
    const csHost = document.getElementById('cs-host');
    const csPort = document.getElementById('cs-port');
    const csMethod = document.getElementById('cs-method');
    
    if (csHost) csHost.textContent = data.cobalt_strike?.host || '-';
    if (csPort) csPort.textContent = data.cobalt_strike?.port || '50050';
    if (csMethod) {
        csMethod.textContent = data.cobalt_strike?.method === 'direct' 
            ? '🔗 Direct Connection' 
            : '🔒 SSH Tunnel Required';
    }
}

/**
 * Populate infrastructure IP sections
 */
function populateInfrastructureIPs(data) {
    const isGoadOnly = data.architecture === 'goad-only';
    const isCombined = data.architecture === 'combined';
    const isC2Only = data.architecture === 'c2-only';
    
    // C2 Server info
    const c2ServerInfo = document.getElementById('c2-server-info');
    if (c2ServerInfo) {
        if (isC2Only || isCombined) {
            c2ServerInfo.style.display = 'block';
            const c2PrivateIp = document.getElementById('c2-private-ip');
            const c2PublicIp = document.getElementById('c2-public-ip');
            if (c2PrivateIp) c2PrivateIp.textContent = data.infrastructure?.c2_server?.private_ip || '-';
            if (c2PublicIp) c2PublicIp.textContent = data.infrastructure?.c2_server?.public_ip || 'N/A (private)';
        } else {
            c2ServerInfo.style.display = 'none';
        }
    }
    
    // Redirectors
    const redirectorsInfo = document.getElementById('redirectors-info');
    if (redirectorsInfo) {
        const redirectors = data.infrastructure?.redirectors || [];
        if ((isC2Only || isCombined) && redirectors.length > 0) {
            redirectorsInfo.style.display = 'block';
            const redirectorList = document.getElementById('redirector-list');
            if (redirectorList) {
                redirectorList.innerHTML = redirectors.map((ip, i) => `
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 5px;">
                        <span>Redirector ${i + 1}:</span>
                        <code id="redirector-${i}">${ip}</code>
                        <button onclick="copyElementToClipboard('redirector-${i}')" style="padding: 2px 8px;">📋</button>
                    </div>
                `).join('');
            }
        } else {
            redirectorsInfo.style.display = 'none';
        }
    }
    
    // Bastion
    const bastionInfo = document.getElementById('bastion-info');
    if (bastionInfo) {
        if ((isC2Only || isCombined) && data.infrastructure?.bastion?.ip) {
            bastionInfo.style.display = 'block';
            const bastionIp = document.getElementById('bastion-ip');
            if (bastionIp) bastionIp.textContent = data.infrastructure.bastion.ip;
        } else {
            bastionInfo.style.display = 'none';
        }
    }
    
    // GOAD Jumpbox
    const goadJumpboxInfo = document.getElementById('goad-jumpbox-info');
    if (goadJumpboxInfo) {
        if ((isGoadOnly || isCombined) && data.goad?.jumpbox?.public_ip) {
            goadJumpboxInfo.style.display = 'block';
            const jumpboxPublicIp = document.getElementById('jumpbox-public-ip');
            const jumpboxSshCmd = document.getElementById('jumpbox-ssh-cmd');
            if (jumpboxPublicIp) jumpboxPublicIp.textContent = data.goad.jumpbox.public_ip;
            if (jumpboxSshCmd) jumpboxSshCmd.textContent = `ssh -i goad-jumpbox.pem goad@${data.goad.jumpbox.public_ip}`;
        } else {
            goadJumpboxInfo.style.display = 'none';
        }
    }
}

/**
 * Populate GOAD lab details
 */
function populateGoadDetails(goadData) {
    // GOAD VMs section
    const goadVmsSection = document.getElementById('goad-vms-section');
    if (goadVmsSection && goadData.vms && goadData.vms.length > 0) {
        goadVmsSection.style.display = 'block';
        const vmList = document.getElementById('goad-vm-list');
        if (vmList) {
            vmList.innerHTML = goadData.vms.map(vm => `
                <tr>
                    <td><strong>${vm.hostname || vm.id}</strong></td>
                    <td>${vm.role || '-'}</td>
                    <td><code>${vm.private_ip || '-'}</code></td>
                    <td>${vm.domain || '-'}</td>
                </tr>
            `).join('');
        }
    } else if (goadVmsSection) {
        goadVmsSection.style.display = 'none';
    }
    
    // GOAD Credentials section
    const goadCredsSection = document.getElementById('goad-creds-section');
    if (goadCredsSection && goadData.credentials) {
        goadCredsSection.style.display = 'block';
        const credsList = document.getElementById('goad-creds-list');
        if (credsList) {
            // Show a note about default credentials
            credsList.innerHTML = `
                <tr>
                    <td colspan="4" style="text-align: center; color: #666;">
                        See <a href="https://orange-cyberdefense.github.io/GOAD/" target="_blank">GOAD Documentation</a> for full credential list
                    </td>
                </tr>
            `;
        }
    } else if (goadCredsSection) {
        goadCredsSection.style.display = 'none';
    }
}

/**
 * Populate access instructions
 */
function populateAccessInstructions(data) {
    const stepsList = document.getElementById('access-steps');
    if (!stepsList) return;
    
    const instructions = data.access_instructions;
    if (instructions && instructions.steps) {
        stepsList.innerHTML = instructions.steps.map(step => `<li>${step}</li>`).join('');
    } else {
        stepsList.innerHTML = '<li>No access instructions available</li>';
    }
}

/**
 * Copy text to clipboard (for element-based copying)
 */
function copyElementToClipboard(elementId) {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    const text = element.textContent || element.innerText;
    navigator.clipboard.writeText(text).then(() => {
        // Show brief feedback
        const originalText = element.textContent;
        element.style.background = '#c8e6c9';
        setTimeout(() => {
            element.style.background = '';
        }, 500);
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
}

/**
 * Toggle password visibility
 */
function togglePassword(elementIdOrElement) {
    let element;
    if (typeof elementIdOrElement === 'string') {
        element = document.getElementById(elementIdOrElement);
    } else {
        element = elementIdOrElement;
    }
    
    if (!element) return;
    
    const isHidden = element.textContent === '••••••••';
    const actualValue = element.dataset.value || '';
    
    if (isHidden) {
        element.textContent = actualValue;
    } else {
        element.textContent = '••••••••';
    }
}

/**
 * Download SSH key
 */
async function downloadSshKey(keyType) {
    try {
        const response = await fetch(`${API_BASE}/deploy/ssh-key/${keyType}`);
        const data = await response.json();
        
        if (data.success) {
            alert(`SSH key saved to: ${data.path}\n\nRun: ${data.chmod_command}`);
        } else {
            alert(`Error: ${data.error}`);
        }
    } catch (error) {
        alert(`Error downloading key: ${error.message}`);
    }
}

// ============================================================================
// APPLICATION INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    APP.init();
});
