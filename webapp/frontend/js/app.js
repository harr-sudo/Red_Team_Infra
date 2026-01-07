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
                'deployment-type': config.deployment_type || config.engagement_type || '',
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
            
            // Update the deployment overview based on loaded type
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
            { icon: '💰', label: 'Est. Cost', value: '~$105/mo' }
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
            { icon: '💰', label: 'Est. Cost', value: '~$135/mo' }
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
            { icon: '💰', label: 'Est. Cost', value: '~$165/mo' }
        ],
        details: 'Phase-based C2: Staging → Post-Ex → Long-Haul. Full operational capability.',
        bestFor: 'Full red team engagements, long-term campaigns',
        phases: ['🚀 Staging', '⚡ Post-Ex', '🔒 Long-Haul'],
        architectureNote: 'Full C2 infrastructure with redirectors for internet-facing operations.'
    },
    // GOAD Lab options (Simplified: Jumpbox + CS combined, no redirectors)
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
            { icon: '🎯', label: 'Jumpbox+CS', value: '1' },
            { icon: '🌲', label: 'Domains', value: '1' },
            { icon: '💰', label: 'Est. Cost', value: '~$100/mo' }
        ],
        details: 'Single DC with Cobalt Strike on jumpbox. Direct internal access for training.',
        bestFor: 'Learning AD attacks, quick testing',
        attacks: ['Kerberoasting', 'AS-REP Roasting', 'DCSync', 'Pass-the-Hash'],
        architectureNote: '🔒 Training Lab: CS on jumpbox, no redirectors. Connect directly to jumpbox:50050.'
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
            { icon: '🎯', label: 'Jumpbox+CS', value: '1' },
            { icon: '🌲', label: 'Domains', value: '1' },
            { icon: '💰', label: 'Est. Cost', value: '~$175/mo' }
        ],
        details: 'DC + Workstation with Cobalt Strike on jumpbox.',
        bestFor: 'Attack chains, lateral movement practice',
        attacks: ['Kerberoasting', 'AS-REP Roasting', 'DCSync', 'Lateral Movement'],
        architectureNote: '🔒 Training Lab: CS on jumpbox, no redirectors. Connect directly to jumpbox:50050.'
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
            { icon: '🎯', label: 'Jumpbox+CS', value: '1' },
            { icon: '🌲', label: 'Domains', value: '2' },
            { icon: '💰', label: 'Est. Cost', value: '~$225/mo' }
        ],
        details: 'Multi-domain lab with Cobalt Strike on jumpbox.',
        bestFor: 'Trust attacks, cross-domain techniques',
        attacks: ['Trust Attacks', 'Constrained Delegation', 'Cross-domain attacks'],
        architectureNote: '🔒 Training Lab: CS on jumpbox, no redirectors. Connect directly to jumpbox:50050.'
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
            { icon: '🎯', label: 'Jumpbox+CS', value: '1' },
            { icon: '⚙️', label: 'SCCM', value: '✓' },
            { icon: '💰', label: 'Est. Cost', value: '~$325/mo' }
        ],
        details: 'SCCM environment with Cobalt Strike on jumpbox.',
        bestFor: 'SCCM attacks, enterprise environments',
        attacks: ['NAA Credentials', 'PXE Boot Attacks', 'Task Sequence Attacks'],
        architectureNote: '🔒 Training Lab: CS on jumpbox, no redirectors. Connect directly to jumpbox:50050.'
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
            { icon: '🎯', label: 'Jumpbox+CS', value: '1' },
            { icon: '🌲', label: 'Forests', value: '2' },
            { icon: '💰', label: 'Est. Cost', value: '~$375/mo' }
        ],
        details: 'Complete 3-domain, 2-forest lab with Cobalt Strike on jumpbox.',
        bestFor: 'Comprehensive AD training, forest attacks',
        attacks: ['Forest Attacks', 'Golden/Silver Tickets', 'DCShadow', 'ACL Abuse'],
        architectureNote: '🔒 Training Lab: CS on jumpbox, no redirectors. Connect directly to jumpbox:50050.'
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
            { icon: '🎯', label: 'Jumpbox+CS', value: '1' },
            { icon: '🏆', label: 'CTF', value: '✓' },
            { icon: '💰', label: 'Est. Cost', value: '~$375/mo' }
        ],
        details: 'Challenge lab (no hints) with Cobalt Strike on jumpbox.',
        bestFor: 'CTF practice, skill assessment',
        attacks: ['Unknown - Challenge Mode!'],
        architectureNote: '🔒 Training Lab: CS on jumpbox, no redirectors. Connect directly to jumpbox:50050.'
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
            { icon: '💰', label: 'Est. Cost', value: '~$205/mo' }
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
            { icon: '💰', label: 'Est. Cost', value: '~$330/mo' }
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
            { icon: '💰', label: 'Est. Cost', value: '~$540/mo' }
        ],
        details: 'Complete phased C2 (Staging/Post-Ex/Long-Haul) + Full GOAD lab.',
        bestFor: 'Full-scale red team exercises with realistic AD targets',
        phases: ['🚀 Staging', '⚡ Post-Ex', '🔒 Long-Haul'],
        architectureNote: '🔥 Full Infrastructure: Beacons route through redirectors. Realistic C2 operations.'
    }
};

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
    
    // Get domain config section (we'll show/hide based on deployment type)
    const domainConfigSection = document.getElementById('domain-config-section');
    
    const config = DEPLOYMENT_CONFIGS[deploymentType];
    
    if (config) {
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
        
        // Show/hide domain config based on whether it's required
        if (domainConfigSection) {
            if (config.requiresDomain) {
                domainConfigSection.style.display = 'block';
            } else {
                domainConfigSection.style.display = 'none';
            }
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
    // First update the deploy page based on selected deployment type
    updateDeployPageForType();
    pollDeploymentStatus();
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
 * Load GOAD status for deployment manager
 */
async function loadGoadStatus() {
    const section = document.getElementById('goad-lab-section');
    const details = document.getElementById('goad-lab-details');
    const actions = document.getElementById('goad-lab-actions');
    
    if (!section) return;
    
    try {
        const response = await fetch(`${API_BASE}/goad/status`);
        const data = await response.json();
        
        if (!data.success) {
            section.style.display = 'none';
            return;
        }
        
        if (!data.goad_available) {
            section.style.display = 'block';
            details.innerHTML = `
                <div class="status-display warning">
                    <p><strong>⚠️ GOAD Not Available</strong></p>
                    <p>GOAD tools not found. Run: <code>git submodule update --init</code></p>
                </div>
            `;
            actions.innerHTML = '';
            return;
        }
        
        if (!data.has_deployment) {
            section.style.display = 'none';
            return;
        }
        
        // Has GOAD deployment
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
        
    } catch (error) {
        console.error('Error loading GOAD status:', error);
        section.style.display = 'none';
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
    await refreshDeployments();
    await loadGoadStatus();  // Also load GOAD lab status
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
            return;
        }
        
        // Has deployment - show infrastructure
        if (noDeploymentDiv) noDeploymentDiv.style.display = 'none';
        
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
            populateConnectionInfo(data);
        } else {
            hideAllInfrastructureSections();
        }
        
        // Load GOAD status separately (it has its own section)
        await loadGoadStatus();
        
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
