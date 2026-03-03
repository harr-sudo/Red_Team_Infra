// Red Team Infrastructure Manager - Frontend JavaScript
// Complete redesign with robust tab system

const API_BASE = '/api';

// ============================================================================
// APPLICATION CORE - Tab Management System
// ============================================================================

const APP = {
    currentPage: 'dashboard',
    pages: ['dashboard', 'configuration', 'deployment', 'deployments', 'aws-check', 'architecture', 'settings'],
    
    /**
     * Initialize the application
     */
    init() {
        console.log('🚀 Initializing Red Team Infrastructure Manager...');

        // Apply saved theme
        this.initTheme();

        // Setup tab navigation
        this.setupNavigation();

        // Load initial page
        this.navigateTo('dashboard');

        // Setup event handlers
        this.setupEventHandlers();

        console.log('✅ Application initialized successfully');
    },

    /**
     * Initialize theme from localStorage
     */
    initTheme() {
        const saved = localStorage.getItem('theme');
        if (saved === 'light') {
            document.documentElement.setAttribute('data-theme', 'light');
        }
        this.updateThemeIcon();

        const toggleBtn = document.getElementById('theme-toggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => this.toggleTheme());
        }
    },

    /**
     * Toggle between dark and light mode
     */
    toggleTheme() {
        const current = document.documentElement.getAttribute('data-theme');
        const next = current === 'light' ? 'dark' : 'light';

        if (next === 'light') {
            document.documentElement.setAttribute('data-theme', 'light');
        } else {
            document.documentElement.removeAttribute('data-theme');
        }

        localStorage.setItem('theme', next);
        this.updateThemeIcon();
    },

    /**
     * Update the theme toggle icon
     */
    updateThemeIcon() {
        const icon = document.getElementById('theme-icon');
        if (icon) {
            const isLight = document.documentElement.getAttribute('data-theme') === 'light';
            icon.innerHTML = isLight ? '&#9728;' : '&#9790;';
        }
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
                    checkCSClientFile();
                    checkSSHPublicKey();
                    break;
                case 'deployments':
                    loadDeploymentsPage();
                    loadDeploymentDetails();  // Load comprehensive details
                    break;
                case 'aws-check':
                    // AWS page is interactive, no auto-load
                    console.log('AWS Check page ready');
                    break;
                case 'architecture':
                    if (typeof initArchitecturePage === 'function') {
                        initArchitecturePage();
                    }
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
        // File upload form (CS Archive for Team Server)
        const uploadForm = document.getElementById('upload-cs-form');
        if (uploadForm) {
            uploadForm.addEventListener('submit', handleFileUpload);
        }
        
        // Delete file button (CS Archive)
        const deleteBtn = document.getElementById('delete-file-btn');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', handleFileDelete);
        }
        
        // CS Client upload form (for Attack Box)
        const csClientUploadForm = document.getElementById('upload-cs-client-form');
        if (csClientUploadForm) {
            csClientUploadForm.addEventListener('submit', handleCSClientUpload);
        }
        
        // Delete CS Client file button
        const deleteCSClientBtn = document.getElementById('delete-cs-client-file-btn');
        if (deleteCSClientBtn) {
            deleteCSClientBtn.addEventListener('click', handleCSClientDelete);
        }
        
        // Project name input - validate on input with debounce
        const projectNameInput = document.getElementById('project-name');
        if (projectNameInput) {
            projectNameInput.addEventListener('input', debouncedProjectNameCheck);
            projectNameInput.addEventListener('blur', () => validateProjectName(true));
        }
        
        // SSL configuration handlers
        this.setupSSLHandlers();

        // Domain fronting handlers
        this.setupDomainFrontingHandlers();

        // Malleable C2 profile preview handlers
        this.setupMalleableProfileHandlers();
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
    },

    /**
     * Setup Domain Fronting configuration event handlers
     */
    setupDomainFrontingHandlers() {
        const enableDfCheckbox = document.getElementById('enable-domain-fronting');
        if (enableDfCheckbox) {
            enableDfCheckbox.addEventListener('change', function() {
                const dfOptions = document.getElementById('domain-fronting-options');
                if (dfOptions) {
                    dfOptions.style.opacity = this.checked ? '1' : '0.5';
                    dfOptions.style.pointerEvents = this.checked ? 'auto' : 'none';
                }
                // Update SSL section — domain fronting overrides manual SSL config
                APP.updateSSLForDomainFronting(this.checked);
                // Show/hide front domain input in malleable profile section
                APP.updateFrontDomainVisibility(this.checked);
                // Re-render profile preview with/without domain fronting snippet
                APP.updateProfilePreview();
            });
        }

        // Front domain input — update profile preview on change
        const frontDomainInput = document.getElementById('front-domain');
        if (frontDomainInput) {
            frontDomainInput.addEventListener('input', () => APP.updateProfilePreview());
        }
    },

    /**
     * Update SSL section when domain fronting is toggled.
     * When domain fronting is enabled: ACM handles public SSL, redirector uses self-signed.
     * When disabled: manual SSL options (Let's Encrypt / self-signed) are available.
     */
    updateSSLForDomainFronting(domainFrontingEnabled) {
        const overrideBanner = document.getElementById('ssl-domain-fronting-override');
        const manualOptions = document.getElementById('ssl-manual-options');

        if (overrideBanner) {
            overrideBanner.style.display = domainFrontingEnabled ? 'block' : 'none';
        }
        if (manualOptions) {
            manualOptions.style.opacity = domainFrontingEnabled ? '0.4' : '1';
            manualOptions.style.pointerEvents = domainFrontingEnabled ? 'none' : 'auto';
        }
    },

    /**
     * Show/hide the front domain input based on domain fronting state
     */
    updateFrontDomainVisibility(domainFrontingEnabled) {
        const frontDomainGroup = document.getElementById('front-domain-group');
        if (frontDomainGroup) {
            frontDomainGroup.style.display = domainFrontingEnabled ? 'block' : 'none';
        }
    },

    /**
     * Setup Malleable C2 Profile preview handlers
     */
    setupMalleableProfileHandlers() {
        const profileSelect = document.getElementById('malleable-profile');
        if (profileSelect) {
            profileSelect.addEventListener('change', () => this.updateProfilePreview());
            // Render initial preview
            this.updateProfilePreview();
        }

        // Tab switching
        document.querySelectorAll('.profile-preview-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                const targetTab = e.target.dataset.tab;
                // Update tab styles
                document.querySelectorAll('.profile-preview-tab').forEach(t => {
                    t.style.background = 'var(--bg-elevated)';
                    t.style.color = 'var(--text-secondary)';
                    t.classList.remove('active');
                });
                e.target.style.background = 'var(--brand)';
                e.target.style.color = 'var(--text-primary)';
                e.target.classList.add('active');
                // Show/hide content
                document.querySelectorAll('.profile-preview-content').forEach(c => {
                    c.style.display = 'none';
                });
                const content = document.getElementById(`preview-tab-${targetTab}`);
                if (content) content.style.display = 'block';
            });
        });
    },

    /**
     * Update the profile preview based on selected profile type
     * When domain fronting is enabled and a front domain is provided,
     * appends a domain fronting config block to the CS profile preview.
     */
    updateProfilePreview() {
        const profileType = document.getElementById('malleable-profile')?.value || 'default';
        const csCode = document.getElementById('cs-profile-code');
        const nginxCode = document.getElementById('nginx-uris-code');
        if (!csCode || !nginxCode) return;

        const profiles = this.getMalleableProfiles();
        const profile = profiles[profileType] || profiles['default'];

        let csContent = profile.cs;

        // If domain fronting is enabled, append the Host header config
        const dfEnabled = document.getElementById('enable-domain-fronting')?.checked ?? false;
        if (dfEnabled) {
            const frontDomain = document.getElementById('front-domain')?.value?.trim() || '';
            const primaryDomain = document.getElementById('primary-domain')?.value?.trim() || 'your-domain.com';
            const cfDistro = `d<ID>.cloudfront.net`;

            csContent += `\n\n# ==========================================================\n`;
            csContent += `# DOMAIN FRONTING CONFIGURATION\n`;
            csContent += `# ==========================================================\n`;
            csContent += `# Your CloudFront distribution: ${cfDistro}\n`;
            csContent += `# Your primary domain alias:    ${primaryDomain}\n`;
            if (frontDomain) {
                csContent += `# Front domain (high-rep):      ${frontDomain}\n`;
            }
            csContent += `#\n`;
            csContent += `# The beacon connects to the FRONT domain (their SSL cert),\n`;
            csContent += `# but the Host header points to YOUR CloudFront distribution.\n`;
            csContent += `# CloudFront routes based on Host header → your redirector.\n`;
            csContent += `# Blue team only sees HTTPS traffic to the front domain.\n`;
            csContent += `# ==========================================================\n\n`;

            if (frontDomain) {
                csContent += `# Add this to your http-get AND http-post client blocks:\n`;
                csContent += `#\n`;
                csContent += `#   client {\n`;
                csContent += `#       header "Host" "${primaryDomain}";\n`;
                csContent += `#       ...\n`;
                csContent += `#   }\n`;
                csContent += `#\n`;
                csContent += `# Listener configuration in Cobalt Strike:\n`;
                csContent += `#   HTTPS Host (Stager):  ${frontDomain}\n`;
                csContent += `#   HTTPS Host (Header):  ${primaryDomain}\n`;
                csContent += `#   HTTPS Port:           443\n`;
            } else {
                csContent += `# Enter a front domain above to generate the Host header config.\n`;
                csContent += `# Use FindFrontableDomains after deployment to discover\n`;
                csContent += `# frontable domains sharing CloudFront.\n`;
            }
        }

        csCode.textContent = csContent;
        nginxCode.textContent = profile.nginx;
    },

    /**
     * Malleable C2 profile data for each profile type
     */
    getMalleableProfiles() {
        return {
            'default': {
                cs: `# jQuery Malleable C2 Profile
# Mimics jQuery CDN requests — blends with common web traffic

set sleeptime "30000";
set jitter    "20";
set useragent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

https-certificate {
    set CN       "cdn.jsdelivr.net";
    set O        "jQuery Foundation";
    set validity "365";
}

http-get {
    set uri "/jquery-3.3.1.min.js";

    client {
        header "Accept" "application/javascript, text/javascript, */*; q=0.01";
        header "Referer" "https://code.jquery.com/";
        header "Accept-Language" "en-US,en;q=0.9";

        metadata {
            base64url;
            append ";session=";
            header "Cookie";
        }
    }

    server {
        header "Content-Type" "application/javascript; charset=utf-8";
        header "Cache-Control" "max-age=0, no-cache";
        header "Server" "NetDNA-cache/2.2";

        output {
            base64url;
            prepend "/*! jQuery v3.3.1 | (c) JS Foundation and other contributors | jquery.org/license */\\n";
            append "\\n/* End jQuery */";
            print;
        }
    }
}

http-post {
    set uri "/api/telemetry";
    set verb "POST";

    client {
        header "Content-Type" "application/json";
        header "Accept" "application/json";

        id {
            base64url;
            header "X-Request-ID";
        }

        output {
            base64url;
            print;
        }
    }

    server {
        header "Content-Type" "application/json";

        output {
            base64url;
            prepend "{\\"status\\":\\"ok\\",\\"data\\":\\"";
            append "\\"}";
            print;
        }
    }
}

http-stager {
    set uri_x86 "/assets/js/analytics.min.js";
    set uri_x64 "/assets/js/analytics.x64.min.js";

    client {
        header "Accept" "application/javascript, */*";
    }

    server {
        header "Content-Type" "application/javascript";
    }
}`,
                nginx: `# Nginx URI patterns for jQuery profile
# Deploy these in /etc/nginx/sites-available/c2-redirector

# GET beacon (http-get uri: /jquery-3.3.1.min.js)
location ~ ^/jquery-3\\.[0-9]+\\.[0-9]+\\.min\\.js$ {
    if ($http_accept !~* "application/javascript|text/javascript|\\*/\\*") {
        return 404;
    }
    proxy_pass https://c2_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 60s;
    proxy_read_timeout 300s;
}

# POST beacon (http-post uri: /api/telemetry)
location = /api/telemetry {
    if ($request_method != POST) {
        return 405;
    }
    proxy_pass https://c2_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 100M;
}

# Stager (http-stager uri: /assets/js/analytics.*.min.js)
location ~ ^/assets/js/analytics\\.(min|x64\\.min)\\.js$ {
    proxy_pass https://c2_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}`
            },
            'amazon': {
                cs: `# Amazon CDN Malleable C2 Profile
# Mimics Amazon CloudFront / AWS API traffic

set sleeptime "45000";
set jitter    "25";
set useragent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

https-certificate {
    set CN       "*.cloudfront.net";
    set O        "Amazon.com Inc.";
    set validity "365";
}

http-get {
    set uri "/latest/meta-data/instance-id";

    client {
        header "Accept" "text/html, application/json, */*";
        header "Accept-Language" "en-US,en;q=0.9";
        header "Connection" "keep-alive";

        metadata {
            base64url;
            header "X-Amz-Security-Token";
        }
    }

    server {
        header "Content-Type" "text/plain; charset=utf-8";
        header "Server" "AmazonEC2";
        header "X-Amz-Request-Id" "a]b]c]d]e]f]1]2]3]4";

        output {
            base64url;
            prepend "i-";
            append "\\n";
            print;
        }
    }
}

http-post {
    set uri "/2/content/save";
    set verb "POST";

    client {
        header "Content-Type" "application/x-amz-json-1.1";
        header "X-Amz-Target" "ContentService.SaveContent";

        id {
            base64url;
            header "X-Amz-Request-Id";
        }

        output {
            base64url;
            print;
        }
    }

    server {
        header "Content-Type" "application/x-amz-json-1.1";
        header "Server" "AmazonEC2";

        output {
            base64url;
            prepend "{\\"RequestId\\":\\"";
            append "\\",\\"Status\\":\\"Accepted\\"}";
            print;
        }
    }
}

http-stager {
    set uri_x86 "/latest/api/plugins/versionCheck";
    set uri_x64 "/latest/api/plugins/versionCheck64";

    client {
        header "Accept" "application/octet-stream, */*";
        header "Connection" "keep-alive";
    }

    server {
        header "Content-Type" "application/octet-stream";
        header "Server" "AmazonEC2";
    }
}`,
                nginx: `# Nginx URI patterns for Amazon CDN profile
# Deploy these in /etc/nginx/sites-available/c2-redirector

# GET beacon (http-get uri: /latest/meta-data/instance-id)
location ~ ^/latest/(meta-data|api/plugins)/ {
    proxy_pass https://c2_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 60s;
    proxy_read_timeout 300s;
}

# POST beacon (http-post uri: /2/content/save)
location ~ ^/[0-9]+/content/(save|update|sync)$ {
    if ($request_method != POST) {
        return 405;
    }
    proxy_pass https://c2_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 100M;
}

# Stager (http-stager uri: /latest/api/plugins/versionCheck*)
location ~ ^/latest/api/plugins/versionCheck(64)?$ {
    proxy_pass https://c2_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}`
            },
            'google': {
                cs: `# Google APIs Malleable C2 Profile
# Mimics Google Safe Browsing / Drive API traffic

set sleeptime "30000";
set jitter    "15";
set useragent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

https-certificate {
    set CN       "*.googleapis.com";
    set O        "Google LLC";
    set validity "365";
}

http-get {
    set uri "/safebrowsing/v4/threatListUpdates:fetch";

    client {
        header "Accept" "application/json";
        header "Accept-Language" "en-US,en;q=0.9";
        header "X-GoogApps-Allowed-Domains" "*";

        metadata {
            base64url;
            parameter "key";
        }
    }

    server {
        header "Content-Type" "application/json; charset=UTF-8";
        header "Server" "GSE";
        header "X-Frame-Options" "SAMEORIGIN";
        header "Alt-Svc" "h3=\\":443\\"; ma=2592000";

        output {
            base64url;
            prepend "{\\"listUpdateResponses\\":[{\\"threatType\\":\\"MALWARE\\",\\"data\\":\\"";
            append "\\"}]}";
            print;
        }
    }
}

http-post {
    set uri "/drive/v3/files/upload";
    set verb "POST";

    client {
        header "Content-Type" "multipart/related; boundary=batch_boundary";
        header "X-Upload-Content-Type" "application/octet-stream";

        id {
            base64url;
            header "X-Goog-Upload-ID";
        }

        output {
            base64url;
            print;
        }
    }

    server {
        header "Content-Type" "application/json; charset=UTF-8";
        header "Server" "UploadServer";

        output {
            base64url;
            prepend "{\\"kind\\":\\"drive#file\\",\\"id\\":\\"";
            append "\\",\\"mimeType\\":\\"application/octet-stream\\"}";
            print;
        }
    }
}

http-stager {
    set uri_x86 "/safebrowsing/v4/fullHashes:find";
    set uri_x64 "/safebrowsing/v5/fullHashes:find";

    client {
        header "Accept" "application/json";
    }

    server {
        header "Content-Type" "application/json";
        header "Server" "GSE";
    }
}`,
                nginx: `# Nginx URI patterns for Google APIs profile
# Deploy these in /etc/nginx/sites-available/c2-redirector

# GET beacon (http-get uri: /safebrowsing/v4/threatListUpdates:fetch)
location ~ ^/safebrowsing/v[0-9]+/(threatListUpdates|fullHashes):(fetch|find)$ {
    proxy_pass https://c2_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 60s;
    proxy_read_timeout 300s;
}

# POST beacon (http-post uri: /drive/v3/files/upload)
location ~ ^/drive/v[0-9]+/files/(upload|copy|export)$ {
    if ($request_method != POST) {
        return 405;
    }
    proxy_pass https://c2_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 100M;
}

# Stager (http-stager uri: /safebrowsing/v*/fullHashes:find)
location ~ ^/safebrowsing/v[0-9]+/fullHashes:find$ {
    proxy_pass https://c2_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}`
            },
            'microsoft': {
                cs: `# Microsoft Azure Malleable C2 Profile
# Mimics Azure AD / Microsoft Graph API traffic

set sleeptime "60000";
set jitter    "20";
set useragent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0";

https-certificate {
    set CN       "login.microsoftonline.com";
    set O        "Microsoft Corporation";
    set validity "365";
}

http-get {
    set uri "/common/oauth2/v2.0/token";

    client {
        header "Accept" "application/json";
        header "client-request-id" "a]b]c]d]-e]f]1]2]-3]4]5]6]-7]8]9]0]a]b]c]d]e]f]1]2";
        header "Accept-Language" "en-US";

        metadata {
            base64url;
            parameter "code";
        }
    }

    server {
        header "Content-Type" "application/json; charset=utf-8";
        header "Server" "Microsoft-IIS/10.0";
        header "X-Content-Type-Options" "nosniff";
        header "Strict-Transport-Security" "max-age=31536000";

        output {
            base64url;
            prepend "{\\"token_type\\":\\"Bearer\\",\\"access_token\\":\\"";
            append "\\",\\"expires_in\\":3600}";
            print;
        }
    }
}

http-post {
    set uri "/v1.0/me/drive/root/children";
    set verb "POST";

    client {
        header "Content-Type" "application/json";
        header "Authorization" "Bearer eyJ0eXAi...";
        header "ConsistencyLevel" "eventual";

        id {
            base64url;
            header "x-ms-request-id";
        }

        output {
            base64url;
            print;
        }
    }

    server {
        header "Content-Type" "application/json; odata.metadata=minimal";
        header "Server" "Microsoft-IIS/10.0";

        output {
            base64url;
            prepend "{\\"@odata.context\\":\\"https://graph.microsoft.com\\",\\"value\\":\\"";
            append "\\"}";
            print;
        }
    }
}

http-stager {
    set uri_x86 "/connect/oauth2/authorize";
    set uri_x64 "/connect/oauth2/authorize64";

    client {
        header "Accept" "text/html, application/json";
    }

    server {
        header "Content-Type" "text/html; charset=utf-8";
        header "Server" "Microsoft-IIS/10.0";
    }
}`,
                nginx: `# Nginx URI patterns for Microsoft Azure profile
# Deploy these in /etc/nginx/sites-available/c2-redirector

# GET beacon (http-get uri: /common/oauth2/v2.0/token)
location ~ ^/common/oauth2/v[0-9]+\\.[0-9]+/(token|authorize)$ {
    proxy_pass https://c2_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 60s;
    proxy_read_timeout 300s;
}

# POST beacon (http-post uri: /v1.0/me/drive/root/children)
location ~ ^/v[0-9]+\\.[0-9]+/me/drive/ {
    if ($request_method != POST) {
        return 405;
    }
    proxy_pass https://c2_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 100M;
}

# Stager (http-stager uri: /connect/oauth2/authorize*)
location ~ ^/connect/oauth2/authorize(64)?$ {
    proxy_pass https://c2_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}`
            },
            'custom': {
                cs: `# Custom Malleable C2 Profile Template
# Replace the URIs, headers, and encoding to match your operational profile
#
# Key sections to customize:
#   http-get  { uri }   — Beacon check-in (GET)
#   http-post { uri }   — Beacon data exfil (POST)
#   http-stager { uri } — Payload staging

set sleeptime "60000";
set jitter    "30";
set useragent "<YOUR_USER_AGENT>";

https-certificate {
    set CN       "<YOUR_DOMAIN>";
    set O        "<YOUR_ORG>";
    set validity "365";
}

http-get {
    set uri "<YOUR_GET_URI>";

    client {
        header "Accept" "<MIME_TYPE>";

        metadata {
            base64url;
            # Choose: header, parameter, uri-append
            header "Cookie";
        }
    }

    server {
        header "Content-Type" "<MIME_TYPE>";

        output {
            base64url;
            print;
        }
    }
}

http-post {
    set uri "<YOUR_POST_URI>";
    set verb "POST";

    client {
        header "Content-Type" "<MIME_TYPE>";

        id {
            base64url;
            header "X-Request-ID";
        }

        output {
            base64url;
            print;
        }
    }

    server {
        header "Content-Type" "<MIME_TYPE>";

        output {
            base64url;
            print;
        }
    }
}

http-stager {
    set uri_x86 "<YOUR_STAGER_URI_X86>";
    set uri_x64 "<YOUR_STAGER_URI_X64>";
}`,
                nginx: `# Custom Nginx URI patterns
# Replace <YOUR_*_URI> with the URIs from your CS Malleable profile
#
# Each location block must match the corresponding CS profile section:
#   http-get  { uri }   → GET  location block
#   http-post { uri }   → POST location block
#   http-stager { uri } → Stager location blocks

# GET beacon
location = <YOUR_GET_URI> {
    proxy_pass https://c2_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 60s;
    proxy_read_timeout 300s;
}

# POST beacon
location = <YOUR_POST_URI> {
    if ($request_method != POST) {
        return 405;
    }
    proxy_pass https://c2_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 100M;
}

# Stager (x86)
location = <YOUR_STAGER_URI_X86> {
    proxy_pass https://c2_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# Stager (x64)
location = <YOUR_STAGER_URI_X64> {
    proxy_pass https://c2_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}`
            }
        };
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
                'aws-region': config.aws_region || 'eu-central-1',
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
            
            // Restore malleable profile selection and update preview
            const malleableSelect = document.getElementById('malleable-profile');
            if (malleableSelect && config.malleable_profile) {
                malleableSelect.value = config.malleable_profile;
            }
            APP.updateProfilePreview();

            // Restore attack box configuration
            const enableAttackBox = config.enable_attack_box !== false; // Default true
            const abCheckbox = document.getElementById('enable-attack-box');
            if (abCheckbox) {
                abCheckbox.checked = enableAttackBox;
                const abOptions = document.getElementById('attack-box-options');
                if (abOptions) {
                    abOptions.style.opacity = enableAttackBox ? '1' : '0.5';
                    abOptions.style.pointerEvents = enableAttackBox ? 'auto' : 'none';
                }
            }
            const abInstanceType = document.getElementById('attack-box-instance-type');
            if (abInstanceType && config.attack_box_instance_type) {
                abInstanceType.value = config.attack_box_instance_type;
            }
            const abDiskSize = document.getElementById('attack-box-disk-size');
            if (abDiskSize && config.attack_box_root_volume_size) {
                abDiskSize.value = config.attack_box_root_volume_size;
            }

            // Restore domain fronting checkbox state
            const enableDomainFronting = config.enable_domain_fronting === true;
            const dfCheckbox = document.getElementById('enable-domain-fronting');
            if (dfCheckbox) {
                dfCheckbox.checked = enableDomainFronting;
                const dfOptions = document.getElementById('domain-fronting-options');
                if (dfOptions) {
                    dfOptions.style.opacity = enableDomainFronting ? '1' : '0.5';
                    dfOptions.style.pointerEvents = enableDomainFronting ? 'auto' : 'none';
                }
            }
            // Restore SSL override and front domain visibility based on domain fronting
            APP.updateSSLForDomainFronting(enableDomainFronting);
            APP.updateFrontDomainVisibility(enableDomainFronting);

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
        color: 'var(--brand)',
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
            { icon: '💻', label: 'Attack Box', value: '1 (Win)' },
            { icon: '💰', label: 'Est. Cost', value: '~$175/mo' }
        ],
        details: 'Quick, minimal setup for one-off tests. Single C2 server with standard proxy infrastructure.',
        bestFor: 'Quick security tests, POCs, training',
        architectureNote: 'Full C2 infrastructure with redirectors, bastion, and Windows attack box for operations.'
    },
    'c2-purple': {
        title: 'C2: Purple Team Deployment',
        color: 'var(--brand)',
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
            { icon: '💻', label: 'Attack Box', value: '1 (Win)' },
            { icon: '💰', label: 'Est. Cost', value: '~$205/mo' }
        ],
        details: 'Redundant C2 infrastructure for collaborative exercises. High availability.',
        bestFor: 'Purple team exercises, collaborative testing',
        architectureNote: 'Full C2 infrastructure with redirectors, bastion, and Windows attack box for operations.'
    },
    'c2-full': {
        title: 'C2: Full Red Team Deployment',
        color: 'var(--brand)',
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
            { icon: '💻', label: 'Attack Box', value: '1 (Win)' },
            { icon: '💰', label: 'Est. Cost', value: '~$235/mo' }
        ],
        details: 'Phase-based C2: Staging → Post-Ex → Long-Haul. Full operational capability.',
        bestFor: 'Full red team engagements, long-term campaigns',
        phases: ['🚀 Staging', '⚡ Post-Ex', '🔒 Long-Haul'],
        architectureNote: 'Full C2 infrastructure with redirectors, bastion, and Windows attack box for operations.'
    },
    // GOAD Lab options (Proper architecture: Jumpbox → Team Server + Windows Attack Box)
    'goad-mini': {
        title: 'GOAD Mini + Cobalt Strike',
        color: 'var(--brand)',
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
    'goad-light': {
        title: 'GOAD Light + Cobalt Strike',
        color: 'var(--brand)',
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
        color: 'var(--brand)',
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
        color: 'var(--brand)',
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
        color: 'var(--brand)',
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
        color: 'var(--brand)',
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
            { icon: '💻', label: 'Attack Box', value: '1 (Win)' },
            { icon: '💰', label: 'Est. Cost', value: '~$290/mo' }
        ],
        details: 'Full C2 with redirectors + GOAD Mini. VPCs peered for realistic beacon traffic.',
        bestFor: 'Testing C2 tradecraft against AD targets',
        architectureNote: '🔥 Full Infrastructure: Beacons route through redirectors. Realistic C2 operations.'
    },
    'combined-adhoc-light': {
        title: 'Full C2 Ad-Hoc + GOAD Light',
        color: 'var(--brand)',
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
            { icon: '💻', label: 'Attack Box', value: '1 (Win)' },
            { icon: '💰', label: 'Est. Cost', value: '~$450/mo' }
        ],
        details: 'Full C2 with redirectors + GOAD Light (multi-domain).',
        bestFor: 'Realistic red team training with trust attacks',
        architectureNote: '🔥 Full Infrastructure: Beacons route through redirectors. Realistic C2 operations.'
    },
    'combined-full-full': {
        title: 'Full C2 Red Team + GOAD Full',
        color: 'var(--brand)',
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
            { icon: '💻', label: 'Attack Box', value: '1 (Win)' },
            { icon: '💰', label: 'Est. Cost', value: '~$670/mo' }
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
        projectNameInput.style.borderColor = 'var(--border)';
        return false;
    }

    // Check if still contains XXX placeholder
    if (name.includes('XXX')) {
        projectNameInput.style.borderColor = 'var(--warning)';
        if (statusSpan) {
            statusSpan.innerHTML = '<span style="color: var(--warning-text);">⚠️ Replace XXX with a unique identifier</span>';
            statusSpan.style.display = 'block';
        }
        return false;
    }

    // Check for valid characters (letters, numbers, underscores, hyphens, must start with letter)
    if (!/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(name)) {
        projectNameInput.style.borderColor = 'var(--danger)';
        if (statusSpan) {
            statusSpan.innerHTML = '<span style="color: var(--danger-text);">❌ Must start with letter, use only letters/numbers/_/-</span>';
            statusSpan.style.display = 'block';
        }
        return false;
    }

    // Basic format is valid
    projectNameInput.style.borderColor = 'var(--success)';
    
    // Optionally check backend for availability
    if (checkBackend) {
        try {
            if (statusSpan) {
                statusSpan.innerHTML = '<span style="color: var(--text-muted);">🔍 Checking availability...</span>';
                statusSpan.style.display = 'block';
            }
            
            const response = await fetch(`${API_BASE}/deploy/check-project-name?name=${encodeURIComponent(name)}`);
            const data = await response.json();
            
            if (data.success) {
                if (data.available) {
                    projectNameInput.style.borderColor = 'var(--success)';
                    if (statusSpan) {
                        // AWS check failed — warn user
                        if (data.aws_warning) {
                            projectNameInput.style.borderColor = 'var(--warning)';
                            statusSpan.innerHTML = '<span style="color: var(--warning-text);">⚠️ Available locally — AWS check failed, verify manually</span>';
                        // History warning
                        } else if (data.history && data.history.previously_used) {
                            const h = data.history;
                            let warningText = '⚠️ Previously used';
                            if (h.was_purged) {
                                warningText += ' (purged)';
                            } else if (h.had_errors) {
                                warningText += ' (had errors)';
                            }
                            projectNameInput.style.borderColor = 'var(--warning)';
                            statusSpan.innerHTML = `<span style="color: var(--warning-text);">${warningText} - consider using a new name</span>`;
                        } else {
                            statusSpan.innerHTML = '<span style="color: var(--success-text);">✅ Available</span>';
                        }
                        statusSpan.style.display = 'block';
                    }
                    return true;
                } else {
                    projectNameInput.style.borderColor = 'var(--danger)';
                    if (statusSpan) {
                        let reason = '';
                        if (data.reason === 'currently_deploying') {
                            reason = '🚀 Currently deploying';
                        } else if (data.reason === 'aws_resources_exist') {
                            // Comprehensive AWS check — show service breakdown
                            if (data.breakdown) {
                                reason = `☁️ In use — ${data.resource_count} AWS resources (${data.breakdown})`;
                            } else {
                                reason = `☁️ In use — ${data.resource_count} AWS resource(s)`;
                            }
                        } else if (data.reason === 'has_local_resources') {
                            reason = `📁 Local Terraform state: ${data.resource_count} resources`;
                        } else if (data.reason === 'has_resources') {
                            reason = `⚠️ Exists (${data.resource_count} resources)`;
                        } else {
                            reason = data.message || 'Not available';
                        }
                        statusSpan.innerHTML = `<span style="color: var(--danger-text);">❌ ${reason}</span>`;
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
                keyPairInput.style.backgroundColor = 'var(--bg-container)';
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
                keyPairHint.innerHTML = '<span style="color: var(--success-text);">✅ GOAD deployments use YOUR SSH key. Upload your public key in the Deploy tab before deploying.</span>';
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

        // Show/hide Domain Fronting section for C2 deployments
        const domainFrontingSection = document.getElementById('domain-fronting-section');
        if (domainFrontingSection) {
            const hasC2 = config.type === 'c2' || config.type === 'combined';
            domainFrontingSection.style.display = hasC2 ? 'block' : 'none';
        }

        // Show/hide Attack Box config section (available for all deployment types)
        const attackBoxSection = document.getElementById('attack-box-config-section');
        if (attackBoxSection) {
            attackBoxSection.style.display = 'block';

            // Wire up checkbox toggle for attack box options
            const abCheckbox = document.getElementById('enable-attack-box');
            const abOptions = document.getElementById('attack-box-options');
            if (abCheckbox && abOptions) {
                // Set initial state
                abOptions.style.opacity = abCheckbox.checked ? '1' : '0.5';
                abOptions.style.pointerEvents = abCheckbox.checked ? 'auto' : 'none';

                // Remove old listener to avoid duplicates, then add new one
                abCheckbox.onchange = function() {
                    abOptions.style.opacity = this.checked ? '1' : '0.5';
                    abOptions.style.pointerEvents = this.checked ? 'auto' : 'none';
                };
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
                <div style="font-size: 0.88em; opacity: 0.9;">${comp.label}</div>
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
                <div style="margin-top: 12px; padding: 8px 12px; background: rgba(255,255,255,0.2); border-radius: 6px; font-size: 0.88em;">
                    ${config.architectureNote}
                </div>
            `;
        }
        
        // Add phases for full-red-team
        if (config.phases) {
            detailsHtml += `
                <div style="margin-top: 12px; display: flex; gap: 10px; flex-wrap: wrap;">
                    ${config.phases.map(phase => `
                        <span style="background: rgba(255,255,255,0.2); padding: 5px 12px; border-radius: 15px; font-size: 0.88em;">
                            ${phase}
                        </span>
                    `).join('')}
                </div>
            `;
        }
        
        // Add attacks for GOAD labs
        if (config.attacks) {
            detailsHtml += `
                <div style="margin-top: 12px; font-size: 0.88em;">
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
        
        // When domain fronting is enabled, force self-signed on redirector (ACM handles public SSL)
        const domainFrontingEnabled = document.getElementById('enable-domain-fronting')?.checked ?? false;
        const effectiveSslProvider = domainFrontingEnabled ? 'self-signed' : sslProvider;

        // Only validate admin email if deployment requires domain and not using domain fronting
        const requiresDomain = deployConfig.requiresDomain === true;
        if (requiresDomain && !domainFrontingEnabled && enableSsl && sslProvider === 'letsencrypt' && !adminEmail) {
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
            // SSL configuration (domain fronting overrides to self-signed)
            enable_ssl_certificate: enableSsl,
            ssl_provider: effectiveSslProvider,
            ssl_auto_retry: domainFrontingEnabled ? false : sslAutoRetry,
            admin_email: domainFrontingEnabled ? '' : adminEmail,
            // Domain fronting
            enable_domain_fronting: document.getElementById('enable-domain-fronting')?.checked ?? false,
            // Server configuration
            c2_server_count: parseInt(document.getElementById('c2-server-count').value),
            c2_server_instance_type: document.getElementById('c2-instance-type').value,
            // Attack Box configuration
            enable_attack_box: document.getElementById('enable-attack-box')?.checked ?? true,
            attack_box_instance_type: document.getElementById('attack-box-instance-type')?.value || 't2.large',
            attack_box_root_volume_size: parseInt(document.getElementById('attack-box-disk-size')?.value || '100')
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
        
        // Get deployment type and extract engagement info
        const deploymentType = document.getElementById('deployment-type')?.value || '';
        const deployConfig = DEPLOYMENT_CONFIGS[deploymentType] || {};

        const config = {
            deployment_type: deploymentType,
            engagement_type: deployConfig.c2Mode || '',
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
            c2_server_instance_type: document.getElementById('c2-instance-type').value,
            enable_domain_fronting: document.getElementById('enable-domain-fronting')?.checked ?? false,
            // Attack Box configuration
            enable_attack_box: document.getElementById('enable-attack-box')?.checked ?? true,
            attack_box_instance_type: document.getElementById('attack-box-instance-type')?.value || 't2.large',
            attack_box_root_volume_size: parseInt(document.getElementById('attack-box-disk-size')?.value || '100')
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
            'aws-region': 'eu-central-1',
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

        // Reset malleable profile and front domain
        const malleableSelect = document.getElementById('malleable-profile');
        if (malleableSelect) malleableSelect.value = 'default';
        const frontDomainInput = document.getElementById('front-domain');
        if (frontDomainInput) frontDomainInput.value = '';
        APP.updateProfilePreview();

        // Reset attack box fields
        const attackBoxCheckbox = document.getElementById('enable-attack-box');
        if (attackBoxCheckbox) {
            attackBoxCheckbox.checked = true; // Default: enabled
            const attackBoxOptions = document.getElementById('attack-box-options');
            if (attackBoxOptions) {
                attackBoxOptions.style.opacity = '1';
                attackBoxOptions.style.pointerEvents = 'auto';
            }
        }
        const attackBoxInstanceType = document.getElementById('attack-box-instance-type');
        if (attackBoxInstanceType) attackBoxInstanceType.value = 't2.large';
        const attackBoxDiskSize = document.getElementById('attack-box-disk-size');
        if (attackBoxDiskSize) attackBoxDiskSize.value = '100';

        // Reset checkboxes
        const dfCheckbox = document.getElementById('enable-domain-fronting');
        if (dfCheckbox) {
            dfCheckbox.checked = false;
            const dfOptions = document.getElementById('domain-fronting-options');
            if (dfOptions) {
                dfOptions.style.opacity = '0.5';
                dfOptions.style.pointerEvents = 'none';
            }
        }
        // Reset SSL section and front domain visibility
        APP.updateSSLForDomainFronting(false);
        APP.updateFrontDomainVisibility(false);

        // Reset deployment type display
        updateDeploymentType();
        
        // Clear the deployment overview
        const overviewDiv = document.getElementById('deployment-overview');
        if (overviewDiv) {
            overviewDiv.innerHTML = '<p style="color: var(--text-muted); text-align: center;">Select a deployment type above to see details</p>';
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
            color: 'var(--brand)'
        });

        // Project Name
        if (config.project_name) {
            summaryItems.push({
                icon: '📁',
                label: 'Project Name',
                value: config.project_name,
                color: 'var(--info)'
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
                color: config.environment === 'prod' ? 'var(--danger)' : (config.environment === 'staging' ? 'var(--warning)' : 'var(--success)')
            });
        }
        
        // AWS Region
        if (config.aws_region) {
            summaryItems.push({
                icon: '🌍',
                label: 'AWS Region',
                value: config.aws_region,
                color: 'var(--info)'
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
                color: 'var(--success)',
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
                    color: 'var(--text-muted)'
                });
            } else {
                warnings.push('Key pair name not set (required for C2/Combined)');
            }
        } else {
            summaryItems.push({
                icon: '🔑',
                label: 'SSH Keys',
                value: 'Auto-generated',
                color: 'var(--success)'
            });
        }

        // Domain (only for C2/Combined)
        if (deployConfig?.requiresDomain) {
            if (config.primary_domain_name) {
                summaryItems.push({
                    icon: '🌐',
                    label: 'Primary Domain',
                    value: config.primary_domain_name,
                    color: 'var(--info)'
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
                    color: 'var(--warning)'
                });
            }
        }

        // Render summary grid
        summaryGrid.innerHTML = summaryItems.map(item => `
            <div style="background: var(--bg-card); padding: 12px; border-radius: 8px; border-left: 4px solid ${item.color};" ${item.tooltip ? `title="${item.tooltip}"` : ''}>
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                    <span style="font-size: 1.2em;">${item.icon}</span>
                    <span style="font-size: 0.8em; color: var(--text-muted); text-transform: uppercase;">${item.label}</span>
                </div>
                <div style="font-weight: bold; color: var(--text-primary); font-size: 0.95em; word-break: break-word;">${item.value}</div>
            </div>
        `).join('');
        
        // Render warnings if any
        if (warnings.length > 0) {
            warningsDiv.style.display = 'block';
            warningsDiv.innerHTML = `
                <div style="background: var(--warning-bg); border: 1px solid var(--warning-border); border-radius: 6px; padding: 12px;">
                    <div style="font-weight: bold; color: var(--warning-text); margin-bottom: 8px;">⚠️ Configuration Issues:</div>
                    <ul style="margin: 0; padding-left: 20px; color: var(--warning-text);">
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
                    <span style="color: var(--text-muted);">${status.progress_percent || 0}%</span>
                </div>

                <!-- Progress Bar -->
                <div style="background: var(--bg-elevated); border-radius: 10px; height: 8px; overflow: hidden;">
                    <div style="background: var(--success); height: 100%; width: ${status.progress_percent || 0}%; transition: width 0.5s ease;"></div>
                </div>

                <div style="margin-top: 10px; color: var(--text-muted); font-size: 0.9em;">
                    ⏱️ Elapsed: ${status.elapsed_formatted || '0m 0s'}
                </div>
            </div>
        `;
        
        // Recent logs
        if (status.logs && status.logs.length > 0) {
            const recentLogs = status.logs.slice(-5);
            statusHtml += `
                <div style="background: var(--bg-terminal); color: var(--text-secondary); padding: 12px; border-radius: 6px; font-family: monospace; font-size: 0.88em;">
                    ${recentLogs.map(log => {
                        const time = new Date(log.timestamp * 1000).toLocaleTimeString();
                        const color = log.type === 'error' ? 'var(--danger-text)' :
                                      log.type === 'success' ? 'var(--success-text)' :
                                      log.type === 'warning' ? 'var(--warning-text)' : 'var(--accent-muted)';
                        return `<div style="margin-bottom: 4px;"><span style="color: var(--text-muted);">[${time}]</span> <span style="color: ${color};">${log.message}</span></div>`;
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
                <h3 style="color: var(--success-text); margin: 0 0 10px 0;">Deployment Complete!</h3>
                <p style="color: var(--text-secondary);">Infrastructure has been successfully deployed.</p>
                <p style="color: var(--text-secondary); font-size: 0.9em;">Elapsed time: ${status.elapsed_formatted || 'Unknown'}</p>
                <div style="margin-top: 15px;">
                    <button class="btn btn-primary" onclick="APP.navigateTo('deployments')">
                        View Deployment Details →
                    </button>
                </div>
            </div>
        `;
        
        // Show post-deployment steps based on deployment type
        const postDeploySteps = document.getElementById('post-deployment-steps');
        if (postDeploySteps) {
            // Get the deployment type to show appropriate next steps
            const deploymentType = status.deployment_type || '';
            const isGoadOnly = deploymentType.startsWith('goad-');
            const isC2Only = deploymentType.startsWith('c2-');
            const isCombined = deploymentType.startsWith('combined-');
            
            if (isGoadOnly) {
                // GOAD training lab - show jumpbox connection info
                postDeploySteps.innerHTML = `
                    <h4 style="margin: 0 0 15px 0; color: var(--success-text);">✅ GOAD Lab Deployed - Next Steps</h4>

                    <div style="margin-bottom: 15px;">
                        <h5 style="margin: 0 0 8px 0; color: var(--success-text);">1. Connect to Jumpbox</h5>
                        <p style="margin: 0; font-size: 0.9em; color: var(--text-secondary);">
                            SSH to the jumpbox using your key (the one you uploaded before deployment):
                        </p>
                        <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 8px 12px; border-radius: 4px; display: block; margin-top: 8px; font-size: 0.88em;">
                            ssh -i ~/.ssh/goad_key ubuntu@JUMPBOX_PUBLIC_IP
                        </code>
                    </div>

                    <div style="margin-bottom: 15px;">
                        <h5 style="margin: 0 0 8px 0; color: var(--success-text);">2. Access Team Server (from Jumpbox)</h5>
                        <p style="margin: 0; font-size: 0.9em; color: var(--text-secondary);">
                            Once on the jumpbox, connect to the Team Server:
                        </p>
                        <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 8px 12px; border-radius: 4px; display: block; margin-top: 8px; font-size: 0.88em;">
                            ssh teamserver
                        </code>
                    </div>

                    <div style="margin-bottom: 15px;">
                        <h5 style="margin: 0 0 8px 0; color: var(--success-text);">3. Connect Cobalt Strike Client</h5>
                        <p style="margin: 0; font-size: 0.9em; color: var(--text-secondary);">
                            Create an SSH tunnel from your local machine to access the Team Server:
                        </p>
                        <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 8px 12px; border-radius: 4px; display: block; margin-top: 8px; font-size: 0.88em;">
                            ssh -i ~/.ssh/goad_key -L 50050:192.168.56.40:50050 ubuntu@JUMPBOX_PUBLIC_IP
                        </code>
                        <p style="margin: 8px 0 0 0; font-size: 0.88em; color: var(--text-muted);">
                            Then connect your CS client to <strong>localhost:50050</strong>
                        </p>
                    </div>

                    <div style="margin-bottom: 15px;">
                        <h5 style="margin: 0 0 8px 0; color: var(--success-text);">4. RDP to Windows VMs</h5>
                        <p style="margin: 0 0 8px 0; font-size: 0.9em; color: var(--text-secondary);">
                            Step 1: Create an SSH tunnel for RDP access to AD VMs (run on YOUR local machine):
                        </p>
                        <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 8px 12px; border-radius: 4px; display: block; margin-bottom: 12px; font-size: 0.88em;">
                            ssh -i ~/.ssh/goad_key -L 3389:192.168.56.10:3389 ubuntu@JUMPBOX_PUBLIC_IP
                        </code>

                        <div style="padding: 12px; background: var(--bg-card); border: 2px solid var(--success); border-radius: 6px; margin-top: 8px;">
                            <div style="font-weight: 600; color: var(--success-text); margin-bottom: 6px; font-size: 0.95em;">📌 Step 2: Connect RDP Client</div>
                            <div style="font-size: 0.9em; color: var(--text-primary); margin-bottom: 6px;">
                                With the SSH tunnel running, connect your RDP client to:
                            </div>
                            <div style="text-align: center; padding: 10px; background: var(--success-bg); border-radius: 4px;">
                                <code style="font-size: 1.3em; font-weight: 600; color: var(--success-text);">localhost:3389</code>
                            </div>
                        </div>
                    </div>

                    <div>
                        <p style="margin: 0; font-size: 0.9em; color: var(--text-secondary);">
                            💡 <strong>Tip:</strong> Go to the Deployment Manager page for IPs and connection details.
                        </p>
                    </div>
                `;
                postDeploySteps.style.display = 'block';
            } else if (isC2Only || isCombined) {
                // C2 deployment - show DNS/SSL steps (original content)
                postDeploySteps.style.display = 'block';
            } else {
                // Unknown type - hide
                postDeploySteps.style.display = 'none';
            }
        }
        
    } else if (status.status === 'error') {
        const errorLogs = status.logs ? status.logs.filter(log => log.type === 'error') : [];
        
        statusDiv.innerHTML = `
            <div style="padding: 15px;">
                <h3 style="color: var(--danger-text); margin: 0 0 15px 0;">❌ Deployment Failed</h3>
                <p style="color: var(--text-secondary); margin-bottom: 15px;">Elapsed time: ${status.elapsed_formatted}</p>
                ${errorLogs.length > 0 ? `
                    <div style="background: var(--bg-terminal); color: var(--text-secondary); padding: 16px; border-radius: 8px; font-family: 'SF Mono', 'Monaco', 'Menlo', monospace; font-size: 0.9em; line-height: 1.6;">
                        ${errorLogs.map(log => {
                            const time = new Date(log.timestamp * 1000).toLocaleTimeString();
                            return `<div style="margin-bottom: 8px;"><span style="color: var(--text-muted);">[${time}]</span> <span style="color: var(--danger-text);">${log.message}</span></div>`;
                        }).join('')}
                    </div>
                ` : `
                    <div style="background: var(--bg-terminal); color: var(--danger-text); padding: 16px; border-radius: 8px; font-family: 'SF Mono', 'Monaco', 'Menlo', monospace; font-size: 0.9em;">
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
    const uploadFormContainer = document.getElementById('cs-upload-form-container');
    
    if (!statusDiv) return;
    
    try {
        const response = await fetch(`${API_BASE}/deploy/cobalt-strike-file`);
        const data = await response.json();
        
        if (data.success) {
            if (data.has_file && data.latest_file) {
                const file = data.latest_file;
                
                // Hide upload form, show compact file info
                if (uploadFormContainer) uploadFormContainer.style.display = 'none';
                statusDiv.style.display = 'none';
                
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
                // Show upload form, hide file info
                if (uploadFormContainer) uploadFormContainer.style.display = 'block';
                statusDiv.style.display = 'none';
                if (fileInfoDiv) fileInfoDiv.style.display = 'none';
            }
            
            // Update unified prerequisites check
            updateDeploymentPrerequisites();
        }
    } catch (error) {
        statusDiv.style.display = 'block';
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
            // Show upload form again
            const uploadFormContainer = document.getElementById('cs-upload-form-container');
            const fileInfoDiv = document.getElementById('cs-file-info');
            if (uploadFormContainer) uploadFormContainer.style.display = 'block';
            if (fileInfoDiv) fileInfoDiv.style.display = 'none';
            
            // Clear file input
            const fileInput = document.getElementById('cs-file-input');
            if (fileInput) fileInput.value = '';
            
            // Update prerequisites
            updateDeploymentPrerequisites();
        } else {
            alert('Error deleting file: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

// =============================================================================
// COBALT STRIKE CLIENT UPLOAD (for Attack Box)
// =============================================================================

async function checkCSClientFile() {
    const statusDiv = document.getElementById('cs-client-file-status');
    const fileInfoDiv = document.getElementById('cs-client-file-info');
    const fileDetails = document.getElementById('cs-client-file-details');
    const uploadFormContainer = document.getElementById('cs-client-upload-form-container');
    
    if (!statusDiv) return;
    
    try {
        const response = await fetch(`${API_BASE}/deploy/cs-client-file`);
        const data = await response.json();
        
        if (data.success) {
            if (data.has_file && data.latest_file) {
                const file = data.latest_file;
                
                // Hide upload form, show compact file info
                if (uploadFormContainer) uploadFormContainer.style.display = 'none';
                statusDiv.style.display = 'none';
                
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
                // Show upload form, hide file info
                if (uploadFormContainer) uploadFormContainer.style.display = 'block';
                statusDiv.style.display = 'none';
                if (fileInfoDiv) fileInfoDiv.style.display = 'none';
            }
        }
    } catch (error) {
        statusDiv.style.display = 'block';
        statusDiv.innerHTML = `<p>Error checking CS Client file: ${error.message}</p>`;
    }
}

async function handleCSClientUpload(e) {
    e.preventDefault();
    
    const fileInput = document.getElementById('cs-client-file-input');
    const uploadBtn = document.getElementById('upload-cs-client-btn');
    const progressDiv = document.getElementById('cs-client-upload-progress');
    const progressFill = document.getElementById('cs-client-progress-fill');
    const progressText = document.getElementById('cs-client-progress-text');
    const statusDiv = document.getElementById('cs-client-file-status');
    
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
                        checkCSClientFile();
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
        
        xhr.open('POST', `${API_BASE}/deploy/upload-cs-client`);
        xhr.send(formData);
        
    } catch (error) {
        statusDiv.innerHTML = `<p>Error: ${error.message}</p>`;
        progressDiv.style.display = 'none';
        uploadBtn.disabled = false;
    }
}

async function handleCSClientDelete() {
    if (!confirm('Are you sure you want to delete the CS Client file?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/deploy/cs-client-file`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: 'latest' })
        });
        
        const data = await response.json();
        if (data.success) {
            // Show upload form again
            const uploadFormContainer = document.getElementById('cs-client-upload-form-container');
            const fileInfoDiv = document.getElementById('cs-client-file-info');
            if (uploadFormContainer) uploadFormContainer.style.display = 'block';
            if (fileInfoDiv) fileInfoDiv.style.display = 'none';
            
            // Clear file input
            const fileInput = document.getElementById('cs-client-file-input');
            if (fileInput) fileInput.value = '';
        } else {
            alert('Error deleting file: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

// =============================================================================
// SSH PUBLIC KEY MANAGEMENT
// =============================================================================

async function checkSSHPublicKey() {
    const statusDiv = document.getElementById('ssh-key-status');
    const keyInfoDiv = document.getElementById('ssh-key-info');
    const keyDetails = document.getElementById('ssh-key-details');
    const formContainer = document.getElementById('ssh-key-form-container');
    
    if (!statusDiv) return;
    
    try {
        const response = await fetch(`${API_BASE}/deploy/ssh-public-key`);
        const data = await response.json();
        
        if (data.success) {
            if (data.has_key && data.valid) {
                // Key is configured and valid - show compact view
                if (formContainer) formContainer.style.display = 'none';
                statusDiv.style.display = 'none';
                
                if (keyInfoDiv) {
                    keyInfoDiv.style.display = 'block';
                    if (keyDetails) {
                        keyDetails.innerHTML = `
                            <strong>Type:</strong> ${data.key_type}<br>
                            <strong>Fingerprint:</strong> ${data.fingerprint}<br>
                            ${data.comment ? `<strong>Comment:</strong> ${data.comment}` : ''}
                        `;
                    }
                }
                
            } else if (data.has_key && !data.valid) {
                // Key exists but is invalid - show form with error
                if (formContainer) formContainer.style.display = 'block';
                if (keyInfoDiv) keyInfoDiv.style.display = 'none';
                statusDiv.style.display = 'block';
                statusDiv.innerHTML = `
                    <div class="status-display error" style="margin-bottom: 15px;">
                        <p><strong>❌ Invalid SSH Key:</strong> ${data.error || 'The stored key is not valid'}</p>
                    </div>
                `;
                
            } else {
                // No key configured - show form
                if (formContainer) formContainer.style.display = 'block';
                if (keyInfoDiv) keyInfoDiv.style.display = 'none';
                statusDiv.style.display = 'none';
            }
            
            // Update prerequisites check
            updateDeploymentPrerequisites();
        }
    } catch (error) {
        statusDiv.style.display = 'block';
        statusDiv.innerHTML = `<p>Error checking SSH key: ${error.message}</p>`;
    }
}

async function saveSSHPublicKey() {
    const keyInput = document.getElementById('ssh-public-key-input');
    const saveBtn = document.getElementById('save-ssh-key-btn');
    const statusDiv = document.getElementById('ssh-key-status');
    
    if (!keyInput) return;
    
    const publicKey = keyInput.value.trim();
    
    if (!publicKey) {
        alert('Please paste your SSH public key');
        return;
    }
    
    // Basic client-side validation
    if (!publicKey.startsWith('ssh-ed25519') && 
        !publicKey.startsWith('ssh-rsa') && 
        !publicKey.startsWith('ecdsa-sha2-')) {
        alert('Invalid SSH public key format.\n\nExpected format: ssh-ed25519 AAAA... or ssh-rsa AAAA...\n\nMake sure you\'re pasting the PUBLIC key (from .pub file), not the private key.');
        return;
    }
    
    // Check if it looks like a private key
    if (publicKey.includes('PRIVATE KEY')) {
        alert('⚠️ This looks like a PRIVATE key!\n\nPlease paste your PUBLIC key instead.\n\nYour public key is in the .pub file (e.g., ~/.ssh/goad_key.pub)');
        return;
    }
    
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = '💾 Saving...';
    }
    
    try {
        const response = await fetch(`${API_BASE}/deploy/ssh-public-key`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ public_key: publicKey })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show success message
            if (statusDiv) {
                statusDiv.innerHTML = `
                    <div class="status-display success">
                        <p><strong>✅ SSH Key Saved Successfully!</strong></p>
                        <p><strong>Type:</strong> ${data.key_type}</p>
                        <p><strong>Fingerprint:</strong> <code>${data.fingerprint}</code></p>
                        ${data.warning ? `<p style="color: var(--warning-text);"><strong>⚠️ Note:</strong> ${data.warning}</p>` : ''}
                    </div>
                `;
            }
            
            // Refresh the display
            setTimeout(() => checkSSHPublicKey(), 1000);
            
        } else {
            alert('Error saving SSH key: ' + (data.error || 'Unknown error'));
        }
        
    } catch (error) {
        alert('Error: ' + error.message);
    } finally {
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.textContent = '💾 Save SSH Public Key';
        }
    }
}

function editSSHKey() {
    const formContainer = document.getElementById('ssh-key-form-container');
    const keyInput = document.getElementById('ssh-public-key-input');
    const keyInfoDiv = document.getElementById('ssh-key-info');
    
    // Show the form, hide the info
    if (formContainer) formContainer.style.display = 'block';
    if (keyInfoDiv) keyInfoDiv.style.display = 'none';
    
    // Clear and focus input
    if (keyInput) {
        keyInput.value = '';
        keyInput.focus();
    }
}

async function deleteSSHKey() {
    if (!confirm('Are you sure you want to delete your SSH public key?\n\nYou will need to add a new key before deploying.')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/deploy/ssh-public-key`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show form, hide info
            const formContainer = document.getElementById('ssh-key-form-container');
            const keyInfoDiv = document.getElementById('ssh-key-info');
            const keyInput = document.getElementById('ssh-public-key-input');
            
            if (formContainer) formContainer.style.display = 'block';
            if (keyInfoDiv) keyInfoDiv.style.display = 'none';
            if (keyInput) keyInput.value = '';
            
            // Update prerequisites
            updateDeploymentPrerequisites();
        } else {
            alert('Error deleting SSH key: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

// Update deployment prerequisites to include SSH key check
async function updateDeploymentPrerequisites() {
    const deployBtn = document.getElementById('deploy-btn');
    const warningDiv = document.getElementById('deployment-prereq-warning');
    
    // Get deployment type config
    const deploymentTypeSelect = document.getElementById('deployment-type');
    const deploymentType = deploymentTypeSelect?.value || '';
    const config = DEPLOYMENT_CONFIGS[deploymentType];
    const requiresDomain = config?.requiresDomain || false;
    
    const missing = [];
    
    // Check SSH public key - ALWAYS required
    try {
        const sshResponse = await fetch(`${API_BASE}/deploy/ssh-public-key`);
        const sshData = await sshResponse.json();
        if (!sshData.has_key || !sshData.valid) {
            missing.push('SSH public key');
        }
    } catch (e) {
        missing.push('SSH public key');
    }
    
    // Check Cobalt Strike file
    try {
        const csResponse = await fetch(`${API_BASE}/deploy/cobalt-strike-file`);
        const csData = await csResponse.json();
        if (!csData.has_file) {
            missing.push('Cobalt Strike file');
        }
    } catch (e) {
        missing.push('Cobalt Strike file');
    }
    
    // Check domain (only if required)
    if (requiresDomain) {
        try {
            const domainResponse = await fetch(`${API_BASE}/health/domain-config`);
            const domainData = await domainResponse.json();
            if (!domainData.success || !domainData.configured) {
                missing.push('Domain configuration');
            }
        } catch (e) {
            missing.push('Domain configuration');
        }
    }
    
    // Update UI
    if (deployBtn) {
        if (missing.length === 0) {
            deployBtn.disabled = false;
            deployBtn.style.opacity = '1';
        } else {
            deployBtn.disabled = true;
            deployBtn.style.opacity = '0.5';
        }
    }
    
    if (warningDiv) {
        if (missing.length > 0) {
            warningDiv.style.display = 'block';
            warningDiv.innerHTML = `<p><strong>⚠️ Prerequisites Missing:</strong> ${missing.join(', ')} required before deployment.</p>`;
        } else {
            warningDiv.style.display = 'none';
        }
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
    
    // Check SSH public key - ALWAYS required for lab access
    try {
        const sshCheck = await fetch(`${API_BASE}/deploy/ssh-public-key`);
        const sshData = await sshCheck.json();
        if (!sshData.has_key || !sshData.valid) {
            missing.push('SSH public key');
        }
    } catch (e) {
        missing.push('SSH public key');
    }
    
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
    
    // IMPORTANT: Reset the plan flag so status polling can work
    isPlanRunning = false;
    
    // Clear the plan output area when starting deployment
    if (outputDiv) {
        outputDiv.innerHTML = '';
    }
    
    // Show immediate feedback
    statusDiv.innerHTML = `
        <div style="text-align: center; padding: 20px;">
            <div class="spinner" style="margin: 0 auto 15px auto;"></div>
            <p><strong>🚀 Starting Deployment...</strong></p>
            <p style="color: var(--text-secondary); font-size: 0.9em;">Project: ${projectName}</p>
            <p style="color: var(--text-secondary); font-size: 0.9em;">Initializing Terraform workspace and preparing resources...</p>
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
                    <h3 style="color: var(--danger-text); margin: 0 0 10px 0;">❌ Deployment Failed to Start</h3>
                    <p style="color: var(--text-secondary);">${data.error || 'Unknown error'}</p>
                </div>
            `;
            statusDiv.className = 'status-display error';
            disableDeployButton(false);
        }
    } catch (error) {
        statusDiv.innerHTML = `
            <div style="padding: 15px;">
                <h3 style="color: var(--danger-text); margin: 0 0 10px 0;">❌ Connection Error</h3>
                <p style="color: var(--text-secondary);">${error.message}</p>
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
        button.style.background = 'rgba(74, 154, 86, 0.3)';
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
        button.style.background = 'rgba(74, 154, 86, 0.3)';
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
                    <div style="font-size: 0.88em; color: var(--text-muted); margin-bottom: 12px;">${stage.detail}</div>

                    <!-- Progress bar -->
                    <div style="background: var(--bg-elevated); border-radius: 10px; height: 8px; overflow: hidden; margin-bottom: 10px;">
                        <div style="background: var(--success); height: 100%; width: ${progressPercent}%; transition: width 0.5s ease-out; border-radius: 10px;"></div>
                    </div>

                    <!-- Stage indicators -->
                    <div style="display: flex; justify-content: space-between; font-size: 0.75em; color: var(--text-muted);">
                        ${stages.map((s, i) => `
                            <span style="color: ${i <= stageIndex ? 'var(--success-text)' : 'var(--border)'}; font-weight: ${i === stageIndex ? 'bold' : 'normal'};">
                                ${i < stageIndex ? '✓' : (i === stageIndex ? '●' : '○')}
                            </span>
                        `).join('')}
                    </div>
                </div>
            </div>
            <div style="margin-top: 15px; padding: 10px; background: rgba(41,47,74,0.5); border-radius: 6px; font-size: 0.88em; color: var(--text-muted);">
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
                        <p style="margin: 5px 0 0 0; color: var(--text-secondary); font-size: 0.9em;">Review the output below, then click "Deploy Infrastructure" to apply.</p>
                    </div>
                </div>
            `;
            statusDiv.className = 'status-display success';
            
            // Format output - simple scrollable terminal
            if (outputDiv) {
                const output = data.stdout || 'No changes detected';
                outputDiv.innerHTML = `
                    <div style="margin-top: 15px; background: var(--bg-terminal); border-radius: 8px; overflow: hidden;">
                        <div style="padding: 10px 15px; background: rgba(0,0,0,0.3); display: flex; justify-content: space-between; align-items: center;">
                            <span style="color: var(--text-muted); font-size: 0.88em;">📋 Terraform Plan Output</span>
                            <button onclick="copyPlanOutput(this)" style="padding: 4px 10px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.15); border-radius: 4px; color: var(--text-secondary); font-size: 0.75em; cursor: pointer;">Copy</button>
                        </div>
                        <pre style="margin: 0; padding: 15px; font-family: 'SF Mono', 'Monaco', 'Menlo', monospace; font-size: 0.88em; line-height: 1.6; color: var(--success-text); white-space: pre-wrap; word-break: break-word;">${escapeHtml(output)}</pre>
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
                        <div style="margin-top: 10px; padding: 10px; background: var(--warning-bg); border-radius: 6px; font-size: 0.9em;">
                            <strong>Quick Fix:</strong> Run <code style="background: var(--bg-terminal); padding: 2px 6px; border-radius: 3px;">aws configure</code> in your terminal
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
                        <div style="margin-top: 10px; padding: 10px; background: var(--warning-bg); border-radius: 6px; font-size: 0.9em;">
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
                <p style="color: var(--text-secondary); margin: 0 0 15px 0; font-size: 0.9em;">${helpText}</p>
                ${actionButtons}
                <div style="margin-top: 15px; display: flex; gap: 10px;">
                    <button class="btn btn-secondary" onclick="resetPlanAndRetry()">🔄 Try Again</button>
                </div>
            `;
            statusDiv.className = 'status-display error';
            
            // Show detailed error in output - simple scrollable terminal
            if (outputDiv && (data.stderr || data.error)) {
                outputDiv.innerHTML = `
                    <div style="margin-top: 15px; background: var(--bg-terminal); border-radius: 8px; overflow: hidden;">
                        <div style="padding: 10px 15px; background: rgba(0,0,0,0.3); display: flex; justify-content: space-between; align-items: center;">
                            <span style="color: var(--text-muted); font-size: 0.88em;">📋 Error Output</span>
                            <button onclick="copyErrorOutput(this)" style="padding: 4px 10px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.15); border-radius: 4px; color: var(--text-secondary); font-size: 0.75em; cursor: pointer;">Copy</button>
                        </div>
                        <pre style="margin: 0; padding: 15px; font-family: 'SF Mono', 'Monaco', 'Menlo', monospace; font-size: 0.88em; line-height: 1.6; color: var(--danger-text); white-space: pre-wrap; word-break: break-word;">${escapeHtml(data.stderr || data.error)}</pre>
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
                    <div style="margin-top: 10px; color: var(--text-secondary);">
                        Could not connect to the backend server. Make sure the server is running.
                    </div>
                    <div style="margin-top: 10px; padding: 10px; background: rgba(41,47,74,0.5); border-radius: 6px; font-size: 0.9em;">
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
                <p style="font-size: 0.9em; color: var(--text-secondary);">This may take several minutes. Please wait.</p>
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
                        <p style="font-size: 0.9em; color: var(--text-secondary);">Terraform is removing all resources. This page will update automatically.</p>
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
    // Try to get project name from various sources if not provided
    if (!projectName) {
        projectName = window.currentDeploymentProject;
        if (!projectName) {
            const projectNameInput = document.getElementById('project-name');
            projectName = projectNameInput?.value || null;
        }
    }

    if (!projectName) {
        showMessage('No project name found — cannot purge', 'error');
        return;
    }

    // Fetch resources for this project from cache to show in review
    const cached = loadResourceCache();
    const projectResources = cached
        ? (cached.resources || []).filter(r => r.project === projectName)
        : [];

    // Show review modal
    showPurgeReviewModal(projectName, projectResources);
}

/**
 * Show a review modal before purge/destroy, listing resources and commands
 */
function showPurgeReviewModal(projectName, resources, mode = 'purge') {
    // Remove existing modal if any
    const existing = document.getElementById('purge-review-modal');
    if (existing) existing.remove();

    const isPurge = mode === 'purge';
    const title = isPurge ? 'Purge Review' : 'Destroy Review';
    const confirmWord = isPurge ? 'PURGE' : 'DESTROY';
    const btnColor = isPurge ? 'var(--warning)' : 'var(--danger)';

    // Build resource list HTML
    const typeIcons = {
        'ec2': '🖥️', 'vpc': '🌐', 'subnet': '📡', 'sg': '🔒', 'eip': '🔗',
        'nat': '🚪', 's3': '📦', 'igw': '🌍', 'rtb': '🛣️', 'eni': '🔌',
        'keypair': '🔑', 'pcx': '🔀', 'iam-role': '👤', 'iam-profile': '🎭',
        'route53-zone': '🌐', 'acm-cert': '🔐'
    };

    let resourcesHtml = '';
    if (resources.length > 0) {
        const rows = resources.map(r => {
            const icon = typeIcons[r.type] || '📄';
            return `<tr style="border-bottom: 1px solid var(--border);">
                <td style="padding: 6px 10px;">${icon} <span style="text-transform: uppercase; font-size: 0.88em;">${r.type}</span></td>
                <td style="padding: 6px 10px;">${r.name || '-'}</td>
                <td style="padding: 6px 10px;"><code style="background: var(--bg-terminal); padding: 2px 6px; border-radius: 3px; font-size: 0.88em;">${r.id || '-'}</code></td>
            </tr>`;
        }).join('');
        resourcesHtml = `
            <div style="margin-top: 15px;">
                <p style="color: var(--text-secondary); margin-bottom: 8px;"><strong>${resources.length} resource${resources.length !== 1 ? 's' : ''}</strong> tagged with this project:</p>
                <div style="max-height: 200px; overflow-y: auto; border: 1px solid var(--border); border-radius: var(--radius);">
                    <table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                        <thead><tr style="background: var(--bg-section);">
                            <th style="padding: 6px 10px; text-align: left;">Type</th>
                            <th style="padding: 6px 10px; text-align: left;">Name</th>
                            <th style="padding: 6px 10px; text-align: left;">ID</th>
                        </tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            </div>`;
    } else {
        resourcesHtml = `
            <div style="margin-top: 15px; padding: 12px; background: var(--warning-bg); border-left: 3px solid var(--warning); border-radius: var(--radius-sm);">
                <p style="margin: 0; color: var(--warning-text);">No tagged resources found for this project. Terraform state may still contain resources to clean up.</p>
            </div>`;
    }

    // Build commands preview — matches actual backend execution
    // Backend uses project_name directly as workspace name and workspace-specific tfvars
    const tfvarsFile = `../configs/${projectName}.tfvars`;
    const commandsHtml = `
        <div style="margin-top: 15px;">
            <p style="color: var(--text-secondary); margin-bottom: 8px;"><strong>Commands that will run:</strong></p>
            <div style="background: var(--bg-terminal); padding: 12px 15px; border-radius: var(--radius); font-family: 'SF Mono', Monaco, monospace; font-size: 0.88em; line-height: 1.8; color: var(--text-terminal);">
                <div><span style="color: var(--text-muted);"># 1. Select Terraform workspace</span></div>
                <div>$ terraform workspace select ${projectName}</div>
                <div style="margin-top: 8px;"><span style="color: var(--text-muted);"># 2. Refresh state to sync with AWS (eu-central-1)</span></div>
                <div>$ terraform refresh -var-file=${tfvarsFile}</div>
                <div style="margin-top: 8px;"><span style="color: var(--text-muted);"># 3. Destroy all managed resources (eu-central-1 only)</span></div>
                <div>$ terraform destroy -auto-approve -var-file=${tfvarsFile}</div>
                ${isPurge ? `<div style="margin-top: 8px;"><span style="color: var(--text-muted);"># 4. Fallback if step 3 fails (force destroy without refresh)</span></div>
                <div>$ terraform destroy -auto-approve -refresh=false -var-file=${tfvarsFile}</div>` : ''}
            </div>
            <p style="margin-top: 8px; font-size: 0.88em; color: var(--text-muted);">Region: <strong>eu-central-1</strong> &middot; State: terraform.tfstate.d/${projectName}/ &middot; Config: configs/${projectName}.tfvars</p>
        </div>`;

    const modal = document.createElement('div');
    modal.id = 'purge-review-modal';
    modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); z-index: 10000; display: flex; align-items: center; justify-content: center; padding: 20px;';

    modal.innerHTML = `
        <div style="background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; max-width: 700px; width: 100%; max-height: 85vh; overflow: hidden; display: flex; flex-direction: column;">
            <div style="padding: 20px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
                <h2 style="margin: 0; color: var(--gold);">${title} — ${projectName}</h2>
                <button onclick="closePurgeReviewModal()" style="background: none; border: none; color: var(--text-primary); font-size: 24px; cursor: pointer;">&times;</button>
            </div>
            <div style="flex: 1; overflow-y: auto; padding: 20px;">
                <div style="padding: 12px; background: var(--danger-bg); border-left: 3px solid var(--danger); border-radius: var(--radius-sm); margin-bottom: 15px;">
                    <p style="margin: 0; color: var(--danger-text); font-weight: 600;">This action cannot be undone. All resources managed by this project's Terraform state will be permanently deleted.</p>
                </div>
                ${resourcesHtml}
                ${commandsHtml}
                <div style="margin-top: 20px;">
                    <label style="display: block; color: var(--text-secondary); margin-bottom: 6px;">Type <strong>${confirmWord}</strong> to confirm:</label>
                    <input type="text" id="purge-confirm-input" placeholder="${confirmWord}" style="width: 100%; padding: 10px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius); color: var(--text-primary); font-size: 1em; box-sizing: border-box;">
                </div>
            </div>
            <div style="padding: 15px 20px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 10px;">
                <button onclick="closePurgeReviewModal()" class="btn btn-secondary">Cancel</button>
                <button id="purge-confirm-btn" onclick="executePurgeFromModal('${projectName}', '${mode}')" class="btn" style="background: ${btnColor}; color: var(--text-inverse); opacity: 0.5; cursor: not-allowed;" disabled>
                    ${isPurge ? '🧹 Purge' : '🗑️ Destroy'}
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Enable confirm button only when correct word is typed
    const input = document.getElementById('purge-confirm-input');
    const btn = document.getElementById('purge-confirm-btn');
    input.addEventListener('input', () => {
        const match = input.value.trim() === confirmWord;
        btn.disabled = !match;
        btn.style.opacity = match ? '1' : '0.5';
        btn.style.cursor = match ? 'pointer' : 'not-allowed';
    });
    input.focus();

    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closePurgeReviewModal();
    });
}

function closePurgeReviewModal() {
    const modal = document.getElementById('purge-review-modal');
    if (modal) modal.remove();
}

/**
 * Execute the purge/destroy after modal confirmation
 */
async function executePurgeFromModal(projectName, mode) {
    closePurgeReviewModal();

    const overviewDiv = document.getElementById('deployments-overview');
    const isPurge = mode === 'purge';
    const endpoint = isPurge ? 'purge' : 'destroy';
    const confirmWord = isPurge ? 'PURGE' : 'DESTROY';
    const label = isPurge ? 'Purge' : 'Destroy';

    if (overviewDiv) {
        overviewDiv.innerHTML = `
            <div class="status-display warning" style="padding: 20px;">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <div class="spinner"></div>
                    <div>
                        <p style="margin: 0; font-weight: bold;">🧹 Starting ${label} for ${projectName}...</p>
                        <p style="margin: 5px 0 0 0; font-size: 0.9em; color: var(--text-secondary);">Running terraform ${isPurge ? 'refresh + destroy' : 'destroy'}...</p>
                    </div>
                </div>
            </div>
        `;
    }

    disableDeployButton(true, `${label} in progress...`);

    if (projectName) {
        window.currentDeploymentProject = projectName;
    }

    try {
        const response = await fetch(`${API_BASE}/deploy/${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_name: projectName, confirm: confirmWord })
        });

        const data = await response.json();

        if (data.success) {
            pollDestructionStatus(projectName);
        } else {
            if (overviewDiv) {
                overviewDiv.innerHTML = `<div class="status-display error"><p><strong>Error:</strong> ${data.error || 'Unknown error'}</p></div>`;
            }
            disableDeployButton(false);
        }
    } catch (error) {
        if (overviewDiv) {
            overviewDiv.innerHTML = `<div class="status-display error"><p><strong>Error:</strong> ${error.message}</p></div>`;
        }
        disableDeployButton(false);
    }
}

/**
 * Poll for destruction status
 * @param {string} projectName - Optional project name for multi-project support
 */
function pollDestructionStatus(projectName = null) {
    const trackedProject = projectName || window.currentDeploymentProject || null;

    const pollInterval = setInterval(async () => {
        try {
            let url = `${API_BASE}/deploy/status`;
            if (trackedProject) {
                url += `?project=${encodeURIComponent(trackedProject)}`;
            }

            const response = await fetch(url);
            const data = await response.json();

            if (data.success && data.status) {
                const status = data.status;
                const overviewDiv = document.getElementById('deployments-overview');

                if (status.status === 'running') {
                    // Still destroying - show progress with recent logs
                    if (overviewDiv) {
                        let logsHtml = '';
                        if (status.logs && status.logs.length > 0) {
                            const recentLogs = status.logs.slice(-8);
                            logsHtml = `
                                <div style="background: var(--bg-terminal); color: var(--text-secondary); padding: 12px; border-radius: 6px; font-family: monospace; font-size: 0.88em; margin-top: 15px; max-height: 200px; overflow-y: auto;">
                                    ${recentLogs.map(log => {
                                        const time = new Date(log.timestamp * 1000).toLocaleTimeString();
                                        const color = log.type === 'error' ? 'var(--danger-text)' :
                                                      log.type === 'success' ? 'var(--success-text)' :
                                                      log.type === 'warning' ? 'var(--warning-text)' : 'var(--accent-muted)';
                                        return `<div style="margin-bottom: 4px;"><span style="color: var(--text-muted);">[${time}]</span> <span style="color: ${color};">${log.message}</span></div>`;
                                    }).join('')}
                                </div>`;
                        }

                        overviewDiv.innerHTML = `
                            <div class="status-display warning" style="padding: 20px;">
                                <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 10px;">
                                    <div class="spinner"></div>
                                    <div>
                                        <p style="margin: 0; font-weight: bold;">🧹 ${status.step || 'Purging resources...'}</p>
                                        <p style="margin: 5px 0 0 0; font-size: 0.9em; color: var(--text-secondary);">
                                            Progress: ${status.progress_percent || 0}% &bull; Elapsed: ${status.elapsed_formatted || '0m 0s'}
                                        </p>
                                    </div>
                                </div>
                                ${logsHtml}
                            </div>`;
                    }

                } else if (status.status === 'success') {
                    clearInterval(pollInterval);
                    disableDeployButton(false);

                    // Log purge results to Deployment History
                    const pr = status.purge_result;
                    if (pr) {
                        const destroyed = pr.terraform_destroyed_count || 0;
                        const remaining = pr.resources_after || 0;
                        const details = (pr.terraform_destroyed || []).map(d => `${d.address} (${d.duration})`).join('\n');
                        addDeploymentLog(
                            `Purge completed: ${destroyed} resource${destroyed !== 1 ? 's' : ''} destroyed, ${remaining} remaining` +
                            (trackedProject ? ` [${trackedProject}]` : ''),
                            remaining > 0 ? 'warning' : 'success',
                            details || null
                        );
                    } else {
                        addDeploymentLog(
                            `Purge completed successfully` + (trackedProject ? ` [${trackedProject}]` : ''),
                            'success'
                        );
                    }

                    if (overviewDiv) {
                        overviewDiv.innerHTML = buildPurgeResultHtml(status, trackedProject, 'success');
                    }
                    refreshAfterAction();

                } else if (status.status === 'error') {
                    clearInterval(pollInterval);
                    disableDeployButton(false);

                    // Log purge failure to Deployment History
                    const pr2 = status.purge_result;
                    const errMsg = status.error || 'Unknown error';
                    if (pr2) {
                        const destroyed = pr2.terraform_destroyed_count || 0;
                        const errors = pr2.terraform_error_count || 0;
                        addDeploymentLog(
                            `Purge failed: ${destroyed} destroyed, ${errors} error${errors !== 1 ? 's' : ''}` +
                            (trackedProject ? ` [${trackedProject}]` : ''),
                            'error',
                            errMsg
                        );
                    } else {
                        addDeploymentLog(
                            `Purge failed` + (trackedProject ? ` [${trackedProject}]` : '') + `: ${errMsg.substring(0, 200)}`,
                            'error'
                        );
                    }

                    if (overviewDiv) {
                        overviewDiv.innerHTML = buildPurgeResultHtml(status, trackedProject, 'error');
                    }
                    refreshAfterAction();

                } else {
                    clearInterval(pollInterval);
                    disableDeployButton(false);
                    refreshAll();
                }
            }
        } catch (error) {
            console.error('Error polling destruction status:', error);
        }
    }, 3000);
}

/**
 * Build the HTML for purge/destroy result display (success or error).
 * Shows: 3-column stats grid, destroyed resources list, remaining resources warning, errors, full logs.
 */
function buildPurgeResultHtml(status, trackedProject, outcome) {
    const pr = status.purge_result;
    const isSuccess = outcome === 'success';
    const cssClass = isSuccess ? 'success' : 'error';
    const title = isSuccess ? '&#10004; Purge Completed' : '&#10060; Purge Failed';

    // Build structured summary if purge_result is available
    let summaryHtml = '';
    let destroyedListHtml = '';
    let remainingHtml = '';
    let errorsHtml = '';

    if (pr) {
        const beforeCount = pr.resources_before || 0;
        const destroyedCount = pr.terraform_destroyed_count || 0;
        const afterCount = pr.resources_after || 0;

        // 3-column stats grid
        summaryHtml = `
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 15px 0;">
                <div style="background: var(--bg-terminal); padding: 12px; border-radius: 6px; text-align: center;">
                    <div style="font-size: 1.6em; color: var(--text-secondary); font-weight: bold;">${beforeCount}</div>
                    <div style="font-size: 0.88em; color: var(--text-muted);">Before</div>
                </div>
                <div style="background: var(--bg-terminal); padding: 12px; border-radius: 6px; text-align: center;">
                    <div style="font-size: 1.6em; color: var(--success-text); font-weight: bold;">${destroyedCount}</div>
                    <div style="font-size: 0.88em; color: var(--text-muted);">Destroyed</div>
                </div>
                <div style="background: var(--bg-terminal); padding: 12px; border-radius: 6px; text-align: center;">
                    <div style="font-size: 1.6em; color: ${afterCount > 0 ? 'var(--warning-text)' : 'var(--success-text)'}; font-weight: bold;">${afterCount}</div>
                    <div style="font-size: 0.88em; color: var(--text-muted);">Remaining</div>
                </div>
            </div>`;

        // Collapsible destroyed resources list
        if (pr.terraform_destroyed && pr.terraform_destroyed.length > 0) {
            const rows = pr.terraform_destroyed.map(d =>
                `<div style="padding: 3px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                    <span style="color: var(--success-text);">&#10003;</span>
                    <code style="color: var(--accent-muted);">${d.address}</code>
                    <span style="color: var(--text-muted); font-size: 0.88em;">(${d.duration})</span>
                </div>`
            ).join('');
            destroyedListHtml = `
                <details style="margin-top: 12px;">
                    <summary style="cursor: pointer; color: var(--success-text); font-weight: bold;">
                        ${destroyedCount} resource${destroyedCount !== 1 ? 's' : ''} destroyed
                    </summary>
                    <div style="background: var(--bg-terminal); padding: 10px; border-radius: 6px; margin-top: 6px; max-height: 250px; overflow-y: auto; font-family: monospace; font-size: 0.88em;">
                        ${rows}
                    </div>
                </details>`;
        }

        // Remaining resources warning
        if (afterCount > 0) {
            const breakdown = Object.entries(pr.resources_after_by_service || {})
                .sort((a, b) => b[1] - a[1])
                .map(([svc, count]) => `${count} ${svc}`)
                .join(', ');
            remainingHtml = `
                <div style="margin-top: 12px; padding: 10px; background: rgba(143, 164, 100, 0.1); border-left: 3px solid var(--warning-text); border-radius: 4px;">
                    <strong style="color: var(--warning-text);">&#9888; ${afterCount} resource${afterCount !== 1 ? 's' : ''} still remain</strong>
                    <span style="color: var(--text-secondary); font-size: 0.9em;"> (${breakdown})</span>
                    <p style="margin: 8px 0 0 0; font-size: 0.88em; color: var(--text-muted);">
                        These may take a few minutes to fully deregister, or may require manual cleanup.
                    </p>
                </div>`;
        }

        // Terraform errors
        if (pr.terraform_errors && pr.terraform_errors.length > 0) {
            errorsHtml = `
                <details ${isSuccess ? '' : 'open'} style="margin-top: 12px;">
                    <summary style="cursor: pointer; color: var(--danger-text); font-weight: bold;">
                        ${pr.terraform_error_count} error${pr.terraform_error_count !== 1 ? 's' : ''}
                    </summary>
                    <div style="background: var(--danger-bg); padding: 10px; border-radius: 6px; margin-top: 6px; max-height: 200px; overflow-y: auto; font-family: monospace; font-size: 0.88em; color: var(--danger-text);">
                        ${pr.terraform_errors.map(e =>
                            `<div style="padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">${escapeHtml(e)}</div>`
                        ).join('')}
                    </div>
                </details>`;
        }
    }

    // Collapsible full logs
    let logsHtml = '';
    if (status.logs && status.logs.length > 0) {
        logsHtml = `
            <details style="margin-top: 12px;">
                <summary style="cursor: pointer; color: var(--text-secondary);">
                    Full logs (${status.logs.length} entries)
                </summary>
                <div style="background: var(--bg-terminal); color: var(--text-secondary); padding: 12px; border-radius: 6px; font-family: monospace; font-size: 0.88em; margin-top: 6px; max-height: 300px; overflow-y: auto;">
                    ${status.logs.map(log => {
                        const time = new Date(log.timestamp * 1000).toLocaleTimeString();
                        const color = log.type === 'error' ? 'var(--danger-text)' :
                                      log.type === 'success' ? 'var(--success-text)' :
                                      log.type === 'warning' ? 'var(--warning-text)' : 'var(--accent-muted)';
                        return `<div style="margin-bottom: 4px; ${log.type === 'error' ? 'background: var(--danger-bg); padding: 4px; border-radius: 3px;' : ''}"><span style="color: var(--text-muted);">[${time}]</span> <span style="color: ${color};">${log.message}</span></div>`;
                    }).join('')}
                </div>
            </details>`;
    }

    // Error message (only for error outcome)
    const errorMsgHtml = !isSuccess && status.error
        ? `<p style="font-size: 0.9em; color: var(--text-secondary); margin-top: 8px;">${escapeHtml((status.error || '').substring(0, 500))}</p>`
        : '';

    // Action buttons
    const retryBtn = (pr && pr.resources_after > 0) || !isSuccess
        ? `<button class="btn" onclick="purgeFailedDeployment('${trackedProject || ''}')" style="background: var(--danger); color: var(--text-primary); margin-left: 10px;">
               🧹 ${isSuccess ? 'Retry Remaining' : 'Try Again'}
           </button>`
        : '';

    const deployBtn = isSuccess
        ? `<button class="btn btn-success" onclick="APP.navigateTo('deployment')">Deploy New Infrastructure &rarr;</button>`
        : `<button class="btn btn-secondary" onclick="refreshAll()">Refresh All</button>`;

    const dismissBtn = `<button class="btn btn-secondary" onclick="refreshAll()" style="margin-left: 10px;">Dismiss</button>`;

    return `
        <div class="status-display ${cssClass}" style="padding: 20px;">
            <p><strong>${title}</strong></p>
            ${errorMsgHtml}
            ${summaryHtml}
            ${destroyedListHtml}
            ${remainingHtml}
            ${errorsHtml}
            ${logsHtml}
            <p style="margin-top: 15px;">
                ${deployBtn}
                ${retryBtn}
                ${dismissBtn}
            </p>
        </div>`;
}

/**
 * Fetch current instance states and render a summary list inside the given container element.
 * Shows running/stopped/pending instances with color-coded indicators.
 */
async function appendInstanceStateSummary(containerSelector) {
    try {
        const response = await fetch(`${API_BASE}/deploy/instance-status`);
        const data = await response.json();

        if (!data.success || !data.instances || data.instances.length === 0) return;

        // Filter out terminated instances
        const active = data.instances.filter(i => i.state !== 'terminated');
        if (active.length === 0) return;

        const stateIcon = (state) => {
            if (state === 'running') return '<span style="color: var(--success-text);">&#9679;</span>';
            if (state === 'stopped') return '<span style="color: var(--warning-text);">&#9724;</span>';
            if (state === 'stopping') return '<span style="color: var(--warning-text);">&#9660;</span>';
            if (state === 'pending') return '<span style="color: var(--info-text);">&#9650;</span>';
            return '<span style="color: var(--text-muted);">&#9675;</span>';
        };

        const stateLabel = (state) => {
            const colors = { running: 'var(--success-text)', stopped: 'var(--warning-text)', stopping: 'var(--warning-text)', pending: 'var(--info-text)' };
            return `<span style="color: ${colors[state] || 'var(--text-muted)'}; font-weight: 600; text-transform: uppercase; font-size: 0.8em;">${state}</span>`;
        };

        const rows = active.map(i =>
            `<div style="display: flex; align-items: center; gap: 8px; padding: 5px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                ${stateIcon(i.state)}
                <strong style="color: var(--text-primary); flex: 1;">${escapeHtml(i.name)}</strong>
                <span style="color: var(--text-muted); font-size: 0.85em;">${i.type}</span>
                ${stateLabel(i.state)}
            </div>`
        ).join('');

        const counts = data.status_counts || {};
        const running = counts.running || 0;
        const stopped = counts.stopped || 0;

        const summaryDiv = document.createElement('div');
        summaryDiv.style.cssText = 'margin-top: 14px; background: var(--bg-terminal); padding: 12px; border-radius: 6px;';
        summaryDiv.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <strong style="color: var(--text-secondary); font-size: 0.9em;">Current Instance States</strong>
                <span style="font-size: 0.85em; color: var(--text-muted);">
                    <span style="color: var(--success-text);">${running} running</span>
                    ${stopped > 0 ? ` &middot; <span style="color: var(--warning-text);">${stopped} stopped</span>` : ''}
                </span>
            </div>
            <div style="font-family: monospace; font-size: 0.88em;">${rows}</div>
        `;

        // Find the target container and append
        const container = document.querySelector(containerSelector);
        if (container) {
            container.appendChild(summaryDiv);
        }
    } catch (err) {
        console.warn('Could not fetch instance states:', err.message);
    }
}

/**
 * Stop all EC2 instances (keep resources, stop compute charges)
 */
async function stopInfrastructure() {
    const confirmStop = confirm(
        'Stop Infrastructure?\n\n' +
        'This will STOP all EC2 instances but keep all resources.\n\n' +
        'Saves ~90% on compute costs\n' +
        'Storage, Elastic IPs, NAT Gateway still billed\n' +
        'All data and configuration preserved\n\n' +
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
            if (data.stopped_count === 0) {
                overviewDiv.innerHTML = `
                    <div class="status-display info" style="padding: 20px;">
                        <p><strong>No Running Instances</strong></p>
                        <p>All instances are already stopped.</p>
                        <p style="margin-top: 15px;">
                            <button class="btn" onclick="startInfrastructure()" style="background: var(--success); color: var(--text-primary);">Start All Instances</button>
                            <button class="btn btn-secondary" onclick="refreshAll()" style="margin-left: 10px;">Dismiss</button>
                        </p>
                    </div>
                `;
                appendInstanceStateSummary('#deployments-overview .status-display');
                return;
            }

            // Build instance details list
            const instanceList = (data.instances || []).map(i =>
                `<div style="padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                    <span style="color: var(--warning-text);">&#9724;</span>
                    <strong style="color: var(--text-primary);">${escapeHtml(i.name)}</strong>
                    <span style="color: var(--text-muted); font-size: 0.88em;">(${i.id} &middot; ${i.type})</span>
                </div>`
            ).join('');

            const detailsSection = `
                <details open style="margin-top: 12px;">
                    <summary style="cursor: pointer; color: var(--warning-text); font-weight: bold;">
                        ${data.stopped_count} instance${data.stopped_count !== 1 ? 's' : ''} stopped
                    </summary>
                    <div style="background: var(--bg-terminal); padding: 10px; border-radius: 6px; margin-top: 6px; font-family: monospace; font-size: 0.88em;">
                        ${instanceList}
                    </div>
                </details>`;

            overviewDiv.innerHTML = `
                <div class="status-display warning" style="padding: 20px;">
                    <p><strong>&#9724; Infrastructure Stopped</strong></p>
                    <p>${data.stopped_count} instance${data.stopped_count !== 1 ? 's have' : ' has'} been stopped.</p>
                    ${detailsSection}
                    <p style="font-size: 0.9em; color: var(--text-secondary); margin-top: 10px;">
                        Storage and network resources are still active. Click "Start All Instances" to resume.
                    </p>
                    <p style="margin-top: 15px;">
                        <button class="btn" onclick="startInfrastructure()" style="background: var(--success); color: var(--text-primary);">Start All Instances</button>
                        <button class="btn btn-secondary" onclick="refreshAll()" style="margin-left: 10px;">Dismiss</button>
                    </p>
                </div>
            `;

            // Log to Deployment History
            const names = (data.instances || []).map(i => i.name).join(', ');
            addDeploymentLog(
                `Stopped ${data.stopped_count} EC2 instance${data.stopped_count !== 1 ? 's' : ''}: ${names}`,
                'warning'
            );

            // Append full instance state summary showing all instances
            appendInstanceStateSummary('#deployments-overview .status-display');

            refreshAfterAction();
        } else {
            overviewDiv.innerHTML = `
                <div class="status-display error">
                    <p><strong>Error stopping instances:</strong> ${data.error || 'Unknown error'}</p>
                    <p style="margin-top: 10px;"><button class="btn btn-secondary" onclick="refreshAll()">Dismiss</button></p>
                </div>
            `;
            addDeploymentLog(`Failed to stop instances: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        overviewDiv.innerHTML = `
            <div class="status-display error">
                <p><strong>Error:</strong> ${error.message}</p>
                <p style="margin-top: 10px;"><button class="btn btn-secondary" onclick="refreshAll()">Dismiss</button></p>
            </div>
        `;
        addDeploymentLog(`Failed to stop instances: ${error.message}`, 'error');
    }
}

/**
 * Start all stopped EC2 instances
 */
async function startInfrastructure() {
    const confirmStart = confirm(
        'Start Infrastructure?\n\n' +
        'This will START all stopped EC2 instances.\n\n' +
        'All instances will be brought online\n' +
        'Takes ~2-5 minutes to fully boot\n' +
        'Compute charges will resume'
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
            if (data.started_count === 0) {
                overviewDiv.innerHTML = `
                    <div class="status-display info" style="padding: 20px;">
                        <p><strong>No Stopped Instances</strong></p>
                        <p>All instances are already running.</p>
                        <p style="margin-top: 10px;"><button class="btn btn-secondary" onclick="refreshAll()">Dismiss</button></p>
                    </div>
                `;
                return;
            }

            // Build instance details list
            const instanceList = (data.instances || []).map(i =>
                `<div style="padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                    <span style="color: var(--success-text);">&#9654;</span>
                    <strong style="color: var(--text-primary);">${escapeHtml(i.name)}</strong>
                    <span style="color: var(--text-muted); font-size: 0.88em;">(${i.id} &middot; ${i.type})</span>
                </div>`
            ).join('');

            const detailsSection = instanceList ? `
                <details open style="margin-top: 12px;">
                    <summary style="cursor: pointer; color: var(--success-text); font-weight: bold;">
                        ${data.started_count} instance${data.started_count !== 1 ? 's' : ''} starting
                    </summary>
                    <div style="background: var(--bg-terminal); padding: 10px; border-radius: 6px; margin-top: 6px; font-family: monospace; font-size: 0.88em;">
                        ${instanceList}
                    </div>
                </details>` : '';

            overviewDiv.innerHTML = `
                <div class="status-display success" style="padding: 20px;">
                    <p><strong>&#9654; Infrastructure Starting</strong></p>
                    <p>${data.started_count} instance${data.started_count !== 1 ? 's are' : ' is'} starting up.</p>
                    ${detailsSection}
                    <p style="font-size: 0.9em; color: var(--text-secondary); margin-top: 10px;">
                        Instances will be fully available in 2-5 minutes.
                    </p>
                    <p style="margin-top: 15px;">
                        <button class="btn btn-secondary" onclick="refreshAll()">Dismiss</button>
                    </p>
                </div>
            `;

            // Log to Deployment History
            const names = (data.instances || []).map(i => i.name).join(', ');
            addDeploymentLog(
                `Started ${data.started_count} EC2 instance${data.started_count !== 1 ? 's' : ''}: ${names}`,
                'success'
            );

            // Append full instance state summary
            appendInstanceStateSummary('#deployments-overview .status-display');

            refreshAfterAction();
        } else {
            overviewDiv.innerHTML = `
                <div class="status-display error">
                    <p><strong>Error starting instances:</strong> ${data.error || 'Unknown error'}</p>
                    <p style="margin-top: 10px;"><button class="btn btn-secondary" onclick="refreshAll()">Dismiss</button></p>
                </div>
            `;
            addDeploymentLog(`Failed to start instances: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        overviewDiv.innerHTML = `
            <div class="status-display error">
                <p><strong>Error:</strong> ${error.message}</p>
                <p style="margin-top: 10px;"><button class="btn btn-secondary" onclick="refreshAll()">Dismiss</button></p>
            </div>
        `;
        addDeploymentLog(`Failed to start instances: ${error.message}`, 'error');
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
        `Stop EC2 Instances for "${projectName}"?\n\n` +
        'This will STOP all EC2 instances for this project.\n\n' +
        'Saves ~90% on compute costs\n' +
        'Storage, Elastic IPs, NAT Gateway still billed\n' +
        'All data and configuration preserved\n\n' +
        'You can restart anytime.'
    );

    if (!confirmStop) return;

    const overviewDiv = document.getElementById('deployments-overview');
    if (overviewDiv) {
        overviewDiv.innerHTML = `
            <div class="status-display warning">
                <div class="spinner"></div>
                <p>Stopping EC2 instances for "${escapeHtml(projectName)}"...</p>
            </div>
        `;
    }

    try {
        const response = await fetch(`${API_BASE}/deploy/stop`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_name: projectName })
        });

        const data = await response.json();

        if (data.success) {
            if (data.stopped_count === 0) {
                if (overviewDiv) {
                    overviewDiv.innerHTML = `
                        <div class="status-display info" style="padding: 20px;">
                            <p><strong>No Running Instances</strong></p>
                            <p>All instances for "${escapeHtml(projectName)}" are already stopped.</p>
                            <p style="margin-top: 15px;">
                                <button class="btn" onclick="startDeploymentResources('${projectName}')" style="background: var(--success); color: var(--text-primary);">Start Instances</button>
                                <button class="btn btn-secondary" onclick="refreshAll()" style="margin-left: 10px;">Dismiss</button>
                            </p>
                        </div>
                    `;
                }
                appendInstanceStateSummary('#deployments-overview .status-display');
                return;
            }

            const instanceList = (data.instances || []).map(i =>
                `<div style="padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                    <span style="color: var(--warning-text);">&#9724;</span>
                    <strong style="color: var(--text-primary);">${escapeHtml(i.name)}</strong>
                    <span style="color: var(--text-muted); font-size: 0.88em;">(${i.id} &middot; ${i.type})</span>
                </div>`
            ).join('');

            const detailsSection = `
                <details open style="margin-top: 12px;">
                    <summary style="cursor: pointer; color: var(--warning-text); font-weight: bold;">
                        ${data.stopped_count} instance${data.stopped_count !== 1 ? 's' : ''} stopped
                    </summary>
                    <div style="background: var(--bg-terminal); padding: 10px; border-radius: 6px; margin-top: 6px; font-family: monospace; font-size: 0.88em;">
                        ${instanceList}
                    </div>
                </details>`;

            if (overviewDiv) {
                overviewDiv.innerHTML = `
                    <div class="status-display warning" style="padding: 20px;">
                        <p><strong>&#9724; Infrastructure Stopped — ${escapeHtml(projectName)}</strong></p>
                        <p>${data.stopped_count} instance${data.stopped_count !== 1 ? 's' : ''} stopped.</p>
                        ${detailsSection}
                        <p style="font-size: 0.9em; color: var(--text-secondary); margin-top: 10px;">
                            Storage and network resources are still active.
                        </p>
                        <p style="margin-top: 15px;">
                            <button class="btn" onclick="startDeploymentResources('${projectName}')" style="background: var(--success); color: var(--text-primary);">Start Instances</button>
                            <button class="btn btn-secondary" onclick="refreshAll()" style="margin-left: 10px;">Dismiss</button>
                        </p>
                    </div>
                `;
            }

            const names = (data.instances || []).map(i => i.name).join(', ');
            addDeploymentLog(
                `Stopped ${data.stopped_count} EC2 instance${data.stopped_count !== 1 ? 's' : ''} [${projectName}]: ${names}`,
                'warning'
            );
            appendInstanceStateSummary('#deployments-overview .status-display');
            refreshAfterAction();
        } else {
            if (overviewDiv) {
                overviewDiv.innerHTML = `
                    <div class="status-display error">
                        <p><strong>Error stopping instances:</strong> ${data.error || 'Unknown error'}</p>
                        <p style="margin-top: 10px;"><button class="btn btn-secondary" onclick="refreshAll()">Dismiss</button></p>
                    </div>
                `;
            }
            addDeploymentLog(`Failed to stop instances [${projectName}]: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        if (overviewDiv) {
            overviewDiv.innerHTML = `
                <div class="status-display error">
                    <p><strong>Error:</strong> ${error.message}</p>
                    <p style="margin-top: 10px;"><button class="btn btn-secondary" onclick="refreshAll()">Dismiss</button></p>
                </div>
            `;
        }
        addDeploymentLog(`Failed to stop instances [${projectName}]: ${error.message}`, 'error');
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
        `Start EC2 Instances for "${projectName}"?\n\n` +
        'This will START all stopped EC2 instances.\n\n' +
        'All instances will be brought online\n' +
        'Takes ~2-5 minutes to fully boot\n' +
        'Compute charges will resume'
    );

    if (!confirmStart) return;

    const overviewDiv = document.getElementById('deployments-overview');
    if (overviewDiv) {
        overviewDiv.innerHTML = `
            <div class="status-display info">
                <div class="spinner"></div>
                <p>Starting EC2 instances for "${escapeHtml(projectName)}"...</p>
            </div>
        `;
    }

    try {
        const response = await fetch(`${API_BASE}/deploy/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_name: projectName })
        });

        const data = await response.json();

        if (data.success) {
            if (data.started_count === 0) {
                if (overviewDiv) {
                    overviewDiv.innerHTML = `
                        <div class="status-display info" style="padding: 20px;">
                            <p><strong>No Stopped Instances</strong></p>
                            <p>All instances for "${escapeHtml(projectName)}" are already running.</p>
                            <p style="margin-top: 10px;"><button class="btn btn-secondary" onclick="refreshAll()">Dismiss</button></p>
                        </div>
                    `;
                }
                return;
            }

            const instanceList = (data.instances || []).map(i =>
                `<div style="padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                    <span style="color: var(--success-text);">&#9654;</span>
                    <strong style="color: var(--text-primary);">${escapeHtml(i.name)}</strong>
                    <span style="color: var(--text-muted); font-size: 0.88em;">(${i.id} &middot; ${i.type})</span>
                </div>`
            ).join('');

            const detailsSection = instanceList ? `
                <details open style="margin-top: 12px;">
                    <summary style="cursor: pointer; color: var(--success-text); font-weight: bold;">
                        ${data.started_count} instance${data.started_count !== 1 ? 's' : ''} starting
                    </summary>
                    <div style="background: var(--bg-terminal); padding: 10px; border-radius: 6px; margin-top: 6px; font-family: monospace; font-size: 0.88em;">
                        ${instanceList}
                    </div>
                </details>` : '';

            if (overviewDiv) {
                overviewDiv.innerHTML = `
                    <div class="status-display success" style="padding: 20px;">
                        <p><strong>&#9654; Infrastructure Starting — ${escapeHtml(projectName)}</strong></p>
                        <p>${data.started_count} instance${data.started_count !== 1 ? 's are' : ' is'} starting up.</p>
                        ${detailsSection}
                        <p style="font-size: 0.9em; color: var(--text-secondary); margin-top: 10px;">
                            Instances will be fully available in 2-5 minutes.
                        </p>
                        <p style="margin-top: 15px;">
                            <button class="btn btn-secondary" onclick="refreshAll()">Dismiss</button>
                        </p>
                    </div>
                `;
            }

            const names = (data.instances || []).map(i => i.name).join(', ');
            addDeploymentLog(
                `Started ${data.started_count} EC2 instance${data.started_count !== 1 ? 's' : ''} [${projectName}]: ${names}`,
                'success'
            );
            appendInstanceStateSummary('#deployments-overview .status-display');
            refreshAfterAction();
        } else {
            if (overviewDiv) {
                overviewDiv.innerHTML = `
                    <div class="status-display error">
                        <p><strong>Error starting instances:</strong> ${data.error || 'Unknown error'}</p>
                        <p style="margin-top: 10px;"><button class="btn btn-secondary" onclick="refreshAll()">Dismiss</button></p>
                    </div>
                `;
            }
            addDeploymentLog(`Failed to start instances [${projectName}]: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        if (overviewDiv) {
            overviewDiv.innerHTML = `
                <div class="status-display error">
                    <p><strong>Error:</strong> ${error.message}</p>
                    <p style="margin-top: 10px;"><button class="btn btn-secondary" onclick="refreshAll()">Dismiss</button></p>
                </div>
            `;
        }
        addDeploymentLog(`Failed to start instances [${projectName}]: ${error.message}`, 'error');
    }
}

// Make startDeploymentResources available globally for onclick handlers
window.startDeploymentResources = startDeploymentResources;

/**
 * Destroy infrastructure for a specific project
 */
async function destroyDeployment(projectName) {
    if (!projectName) {
        showMessage('Project name is required', 'error');
        return;
    }

    // Get resources from cache for this project
    const cached = loadResourceCache();
    const projectResources = cached
        ? (cached.resources || []).filter(r => r.project === projectName)
        : [];

    // Show review modal in destroy mode
    showPurgeReviewModal(projectName, projectResources, 'destroy');
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
        
        if (!data.success || !data.outputs) {
            contentDiv.innerHTML = `<div style="color: var(--text-secondary);">No connection details available. ${data.error || ''}</div>`;
            return;
        }
        
        const outputs = data.outputs;
        
        // Get user's key path from their uploaded public key comment
        let userKeyPath = '~/.ssh/your_key';  // Default fallback
        let keyComment = null;
        
        try {
            const sshKeyResponse = await fetch(`${API_BASE}/deploy/ssh-public-key`);
            const sshKeyData = await sshKeyResponse.json();
            if (sshKeyData.success && sshKeyData.has_key && sshKeyData.comment) {
                keyComment = sshKeyData.comment;
                // Try to extract key path from comment
                // Common patterns: user@host, ~/.ssh/keyname, /path/to/key, email@domain.com
                if (keyComment.includes('/.ssh/')) {
                    // Comment contains a path like ~/.ssh/id_ed25519 or /home/user/.ssh/mykey
                    userKeyPath = keyComment.trim();
                } else if (keyComment.match(/^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+$/)) {
                    // It's an email - use default key names based on key type
                    if (sshKeyData.key_type === 'ssh-ed25519') {
                        userKeyPath = '~/.ssh/id_ed25519';
                    } else if (sshKeyData.key_type === 'ssh-rsa') {
                        userKeyPath = '~/.ssh/id_rsa';
                    }
                } else if (!keyComment.includes('@') && !keyComment.includes(' ')) {
                    // Simple comment like "mykey" - assume it's in ~/.ssh/
                    userKeyPath = `~/.ssh/${keyComment}`;
                }
            }
        } catch (e) {
            console.log('Could not fetch SSH key info, using default path');
        }
        
        // Build connection info HTML
        let html = '<div style="font-size: 0.95em;">';
        
        const keyPathDisplay = userKeyPath.replace('~/', '~/');
        const isDefaultPath = userKeyPath === '~/.ssh/your_key';
        
        // SSH Key Info Section - Secure Architecture
        html += `
            <div style="margin-bottom: 15px; padding: 15px; background: var(--success-bg); border-radius: 8px; border-left: 4px solid var(--success);">
                <div style="font-weight: 600; color: var(--success-text); margin-bottom: 10px; font-size: 1.05em;">🔐 Secure SSH Access</div>
                <div style="margin-bottom: 12px; font-size: 0.9em; color: var(--text-primary); line-height: 1.5;">
                    <strong>You use YOUR OWN SSH key</strong> — the same public key you provided before deployment.
                    Your private key never leaves your machine.
                </div>
                ${!isDefaultPath ? `
                <div style="background: var(--bg-card); padding: 10px 12px; border-radius: 6px; margin-bottom: 10px; border: 1px solid var(--success-border);">
                    <div style="font-size: 0.9em; color: var(--success-text);">
                        <strong>🔑 Your key:</strong> <code style="background: var(--success-bg); padding: 2px 6px; border-radius: 3px;">${keyPathDisplay}</code>
                        ${keyComment ? `<span style="color: var(--text-muted); font-size: 0.88em; margin-left: 8px;">(from: ${keyComment})</span>` : ''}
                    </div>
                </div>
                ` : `
                <div style="background: var(--bg-card); padding: 12px; border-radius: 6px; margin-bottom: 10px;">
                    <div style="font-weight: 500; color: var(--info-text); margin-bottom: 8px;">📋 How it works:</div>
                    <ol style="margin: 0; padding-left: 20px; color: var(--text-secondary); font-size: 0.88em; line-height: 1.7;">
                        <li>You generated your key pair locally: <code style="background: var(--bg-terminal); padding: 1px 4px; border-radius: 2px;">ssh-keygen -t ed25519</code></li>
                        <li>You uploaded your <strong>public key</strong> before deployment</li>
                        <li>Your <strong>private key</strong> stays on your machine — never transmitted</li>
                        <li>The jumpbox was provisioned with your public key in <code>authorized_keys</code></li>
                    </ol>
                </div>
                `}
                <div style="font-size: 0.88em; color: var(--text-muted); display: flex; align-items: center; gap: 6px;">
                    <span style="color: var(--success-text);">✅</span> No private keys are stored on servers or transmitted via API
                </div>
            </div>
        `;
        
        // Jumpbox SSH
        if (outputs.jumpbox_public_ip) {
            const sshCommand = `ssh -i ${userKeyPath} ubuntu@${outputs.jumpbox_public_ip}`;
            const escapedSshCommand = sshCommand.replace(/'/g, "\\'");
            html += `
                <div style="margin-bottom: 15px; padding: 12px; background: var(--success-bg); border-radius: 6px; border-left: 4px solid var(--success);">
                    <div style="font-weight: 600; color: var(--success-text); margin-bottom: 8px;">🖥️ Jumpbox SSH Access</div>
                    <div style="margin-bottom: 5px;"><strong>Public IP:</strong> <code style="background: var(--bg-terminal); padding: 2px 6px; border-radius: 3px;">${outputs.jumpbox_public_ip}</code></div>
                    <div style="margin-bottom: 8px;"><strong>User:</strong> <code style="background: var(--bg-terminal); padding: 2px 6px; border-radius: 3px;">ubuntu</code></div>
                    <div style="position: relative; background: var(--bg-terminal); border-radius: 4px; overflow: hidden;">
                        <button onclick="copyToClipboard('${escapedSshCommand}', this)" 
                                style="position: absolute; top: 8px; right: 8px; background: var(--bg-elevated); color: var(--text-secondary); border: 1px solid var(--border-light); padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 0.75em; z-index: 10;">
                            📋 Copy
                        </button>
                        <div style="color: var(--accent-muted); padding: 12px; padding-right: 80px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.95em; overflow-x: auto; white-space: nowrap;">
                            ${sshCommand}
                        </div>
                    </div>
                    ${isDefaultPath ? `
                    <div style="margin-top: 8px; font-size: 0.88em; color: var(--text-secondary);">
                        💡 Replace <code>your_key</code> with the path to your private key (e.g., <code>~/.ssh/id_ed25519</code>)
                    </div>
                    ` : ''}
                </div>
            `;
        }
            
            // Windows RDP via Jumpbox
            if (outputs.dc01_private_ip) {
                const tunnelCommand = `ssh -i ${userKeyPath} -L 3389:${outputs.dc01_private_ip}:3389 ubuntu@${outputs.jumpbox_public_ip}`;
                const escapedTunnelCommand = tunnelCommand.replace(/'/g, "\\'");
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: var(--info-bg); border-radius: 6px; border-left: 4px solid var(--info);">
                        <div style="font-weight: 600; color: var(--info-text); margin-bottom: 8px;">🪟 Windows DC01 (via Jumpbox)</div>
                        <div style="margin-bottom: 5px;"><strong>Private IP:</strong> <code style="background: var(--bg-terminal); padding: 2px 6px; border-radius: 3px;">${outputs.dc01_private_ip}</code></div>
                        <div style="margin-bottom: 8px;"><strong>Access:</strong> RDP through SSH tunnel</div>
                        
                        <div style="font-weight: 500; color: var(--text-primary); margin-bottom: 6px; font-size: 0.9em;">Step 1: Create SSH Tunnel (run on YOUR local machine)</div>
                        <div style="position: relative; background: var(--bg-terminal); border-radius: 4px; overflow: hidden; margin-bottom: 12px;">
                            <button onclick="copyToClipboard('${escapedTunnelCommand}', this)" 
                                    style="position: absolute; top: 8px; right: 8px; background: var(--bg-elevated); color: var(--text-secondary); border: 1px solid var(--border-light); padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 0.75em; z-index: 10;">
                                📋 Copy
                            </button>
                            <div style="color: var(--accent-muted); padding: 12px; padding-right: 80px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.95em; overflow-x: auto;">
                                <div style="color: var(--text-muted); margin-bottom: 4px;"># SSH tunnel for RDP</div>
                                <div style="white-space: nowrap;">${tunnelCommand}</div>
                            </div>
                        </div>
                        
                        <div style="padding: 15px; background: var(--bg-card); border-radius: 6px; border: 2px solid var(--info); margin-top: 12px;">
                            <div style="font-weight: 600; color: var(--info-text); margin-bottom: 8px; font-size: 1.1em;">📌 Step 2: Connect RDP Client</div>
                            <div style="font-size: 1.05em; color: var(--text-primary); margin-bottom: 8px;">
                                With the SSH tunnel running, connect your RDP client to:
                            </div>
                            <div style="text-align: center; padding: 12px; background: var(--info-bg); border-radius: 4px; border: 1px solid var(--info-border);">
                                <code style="font-size: 1.3em; font-weight: 600; color: var(--info-text); font-family: 'SF Mono', Monaco, Consolas, monospace;">localhost:3389</code>
                            </div>
                            <div style="margin-top: 10px; font-size: 0.9em; color: var(--text-secondary);">
                                💡 Use your Windows RDP client (Remote Desktop Connection on Windows, Microsoft Remote Desktop on Mac)
                            </div>
                        </div>
                        
                        <div style="margin-top: 12px; padding: 10px; background: var(--warning-bg); border-radius: 4px; border-left: 3px solid var(--warning);">
                            <div style="font-weight: 500; color: var(--warning-text); margin-bottom: 6px; font-size: 0.88em;">🔧 Advanced: Creating tunnel FROM the jumpbox</div>
                            <div style="font-size: 0.8em; color: var(--text-secondary); line-height: 1.5;">
                                If you're already on the jumpbox and want to create an RDP tunnel, use the internal key:
                            </div>
                            <code style="display: block; margin-top: 6px; background: var(--bg-terminal); padding: 6px 8px; border-radius: 3px; font-size: 0.75em; color: var(--text-primary);">
                                ssh -i ~/.ssh/jumpbox_internal_key -L 3389:${outputs.dc01_private_ip}:3389 ubuntu@${outputs.jumpbox_public_ip}
                            </code>
                        </div>
                    </div>
                `;
            }
            
            // Team Server (if exists - Full C2 mode with public team server)
            if (outputs.team_server_public_ip) {
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: var(--danger-bg); border-radius: 6px; border-left: 4px solid var(--danger);">
                        <div style="font-weight: 600; color: var(--danger-text); margin-bottom: 8px;">🎯 Cobalt Strike Team Server (Direct)</div>
                        <div style="margin-bottom: 5px;"><strong>Public IP:</strong> <code style="background: var(--bg-terminal); padding: 2px 6px; border-radius: 3px;">${outputs.team_server_public_ip}</code></div>
                        <div style="margin-bottom: 8px;"><strong>Port:</strong> <code style="background: var(--bg-terminal); padding: 2px 6px; border-radius: 3px;">50050</code></div>
                        
                        <!-- License Activation Notice -->
                        <div style="margin: 10px 0; padding: 10px; background: var(--warning-bg); border-radius: 4px; border: 1px solid var(--warning-border);">
                            <div style="font-weight: 600; color: var(--warning-text); margin-bottom: 6px; font-size: 0.9em;">⚠️ License Activation & Password Setup Required</div>
                            <div style="font-size: 0.88em; color: var(--text-primary); line-height: 1.4; margin-bottom: 8px;">
                                SSH to the server and run <code style="background: var(--bg-terminal); padding: 1px 4px; border-radius: 2px;">cd /opt/cobaltstrike && sudo ./update</code> to activate your license.
                            </div>
                            <div style="font-size: 0.88em; color: var(--text-primary); line-height: 1.4;">
                                Then start with password: <code style="background: var(--bg-terminal); padding: 1px 4px; border-radius: 2px;">cd /opt/cobaltstrike/server && sudo ./teamserver ${outputs.team_server_public_ip} YourPassword</code>
                            </div>
                        </div>
                        
                        <div style="font-size: 0.9em; color: var(--text-secondary);">Connect your CS Client directly to this IP:port after license activation</div>
                    </div>
                `;
            }
            
            // Team Server (GOAD mode - internal Team Server)
            if (outputs.teamserver_private_ip) {
                const teamserverSshCommand = `ssh ubuntu@${outputs.teamserver_private_ip}`;
                const escapedTeamserverSshCommand = teamserverSshCommand.replace(/'/g, "\\'");
                const activateLicenseCmd = `cd /opt/cobaltstrike && sudo ./update`;
                const escapedActivateLicenseCmd = activateLicenseCmd.replace(/'/g, "\\'");
                
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: var(--danger-bg); border-radius: 6px; border-left: 4px solid var(--danger);">
                        <div style="font-weight: 600; color: var(--danger-text); margin-bottom: 8px;">🔴 CS Team Server (Ubuntu)</div>
                        <div style="margin-bottom: 5px;"><strong>Private IP:</strong> <code style="background: var(--bg-terminal); padding: 2px 6px; border-radius: 3px;">${outputs.teamserver_private_ip}</code></div>
                        <div style="margin-bottom: 5px;"><strong>CS Port:</strong> <code style="background: var(--bg-terminal); padding: 2px 6px; border-radius: 3px;">50050</code></div>
                        
                        <!-- License Activation Notice -->
                        <div style="margin: 12px 0; padding: 12px; background: var(--warning-bg); border-radius: 6px; border: 1px solid var(--warning-border);">
                            <div style="font-weight: 600; color: var(--warning-text); margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                                <span style="font-size: 1.1em;">⚠️</span> License Activation & Password Setup Required
                            </div>
                            <div style="font-size: 0.9em; color: var(--text-primary); margin-bottom: 10px; line-height: 1.5;">
                                Before the Team Server can run, you must activate your Cobalt Strike license and set a password.
                                This is a <strong>one-time manual step</strong> that requires your license key.
                            </div>
                            <div style="font-weight: 500; color: var(--text-primary); margin-bottom: 6px; font-size: 0.88em;">Steps to activate:</div>
                            <div style="background: var(--bg-terminal); border-radius: 4px; padding: 10px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.88em; margin-bottom: 8px;">
                                <div style="color: var(--text-muted); margin-bottom: 4px;"># 1. SSH to Team Server (from Jumpbox)</div>
                                <div style="color: var(--accent-muted); margin-bottom: 8px;">ssh teamserver</div>
                                <div style="color: var(--text-muted); margin-bottom: 4px;"># 2. Run the license activation</div>
                                <div style="color: var(--accent-muted); margin-bottom: 8px;">${activateLicenseCmd}</div>
                                <div style="color: var(--text-muted); margin-bottom: 4px;"># 3. Enter your license key when prompted</div>
                            </div>
                        </div>
                        
                        <!-- Password Setup Notice -->
                        <div style="margin: 12px 0; padding: 12px; background: var(--info-bg); border-radius: 6px; border: 1px solid var(--info-border);">
                            <div style="font-weight: 600; color: var(--info-text); margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                                <span style="font-size: 1.1em;">🔑</span> Set Team Server Password
                            </div>
                            <div style="font-size: 0.9em; color: var(--text-primary); margin-bottom: 10px; line-height: 1.5;">
                                After license activation, you must <strong>manually start the team server with a password</strong>.
                                Choose a strong password - you'll need it to connect the CS Client.
                            </div>
                            <div style="font-weight: 500; color: var(--text-primary); margin-bottom: 6px; font-size: 0.88em;">Start team server with password:</div>
                            <div style="background: var(--bg-terminal); border-radius: 4px; padding: 10px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.88em; margin-bottom: 8px;">
                                <div style="color: var(--text-muted); margin-bottom: 4px;"># Start the team server</div>
                                <div style="color: var(--accent-muted); margin-bottom: 4px;">cd /opt/cobaltstrike/server</div>
                                <div style="color: var(--accent-muted);">sudo ./teamserver ${outputs.teamserver_private_ip} YourPasswordHere</div>
                            </div>
                            <div style="font-size: 0.8em; color: var(--text-secondary); padding: 8px; background: var(--bg-card); border-radius: 4px; margin-bottom: 8px;">
                                💡 <strong>Keep it running:</strong> Use <code style="background: var(--bg-terminal); padding: 1px 4px; border-radius: 2px;">screen</code> or <code style="background: var(--bg-terminal); padding: 1px 4px; border-radius: 2px;">tmux</code> to run in background: <code style="background: var(--bg-terminal); padding: 1px 4px; border-radius: 2px;">screen -S teamserver</code> then start the server.
                            </div>
                            <div style="font-size: 0.8em; color: var(--text-secondary); padding: 8px; background: var(--bg-card); border-radius: 4px;">
                                💡 <strong>Remember this password!</strong> You'll use it to connect the CS Client to this team server on port 50050.
                            </div>
                            <div style="font-size: 0.8em; color: var(--info-text); padding: 8px; background: var(--info-bg); border-radius: 4px; margin-top: 8px;">
                                ℹ️ <strong>Why ${outputs.teamserver_private_ip}?</strong> Using the actual IP (not 0.0.0.0) ensures beacons know where to connect back. All GOAD VMs and the attack box can reach this internal IP directly.
                            </div>
                        </div>
                        
                        <div style="font-weight: 500; color: var(--text-primary); margin-bottom: 6px; font-size: 0.9em;">Verify team server is running:</div>
                        <div style="background: var(--bg-terminal); border-radius: 4px; padding: 10px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.88em; margin-bottom: 12px;">
                            <div style="color: var(--accent-muted); margin-bottom: 4px;">sudo systemctl status teamserver</div>
                            <div style="color: var(--accent-muted);">sudo netstat -tlnp | grep 50050</div>
                        </div>
                    </div>
                `;
            }
            
            // Windows Attack Box (GOAD + CS mode - Windows workstation with CS Client + Tools)
            if (outputs.attackbox_private_ip) {
                const rdpTunnelCommand = `ssh -i ${userKeyPath} -L 3389:${outputs.attackbox_private_ip}:3389 ubuntu@${outputs.jumpbox_public_ip}`;
                const escapedRdpTunnelCommand = rdpTunnelCommand.replace(/'/g, "\\'");
                const localCsTunnelCommand = `ssh -i ${userKeyPath} -L 50050:192.168.56.40:50050 ubuntu@${outputs.jumpbox_public_ip}`;
                const escapedLocalCsTunnelCommand = localCsTunnelCommand.replace(/'/g, "\\'");
                
                // Get password - use from outputs if available, otherwise show placeholder
                const attackboxPassword = outputs.attackbox_password || '(see Terraform outputs)';
                
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: var(--success-bg); border-radius: 6px; border-left: 4px solid var(--success);">
                        <div style="font-weight: 600; color: var(--success-text); margin-bottom: 8px;">🖥️ Windows Attack Box (CS Client + Tools)</div>
                        <div style="margin-bottom: 5px;"><strong>Private IP:</strong> <code style="background: var(--bg-terminal); padding: 2px 6px; border-radius: 3px;">${outputs.attackbox_private_ip}</code></div>
                        <div style="margin-bottom: 5px;"><strong>OS:</strong> <code style="background: var(--bg-terminal); padding: 2px 6px; border-radius: 3px;">Windows Server 2019</code></div>
                        <div style="margin-bottom: 5px;"><strong>Login:</strong> <code style="background: var(--bg-terminal); padding: 2px 6px; border-radius: 3px;">Administrator / ${attackboxPassword}</code></div>
                        <div style="margin-bottom: 10px; font-size: 0.9em; color: var(--text-secondary);">
                            Your attack workstation with CS Client, PowerSploit, and WSL2.
                        </div>
                        
                        <div style="font-weight: 500; color: var(--text-primary); margin-bottom: 6px; font-size: 0.9em;">🔗 Option 1: RDP via SSH Tunnel (Graphical Access)</div>
                        <div style="font-size: 0.88em; color: var(--text-secondary); margin-bottom: 8px;">
                            Step 1: Create SSH Tunnel (run on YOUR local machine)
                        </div>
                        <div style="position: relative; background: var(--bg-terminal); border-radius: 4px; overflow: hidden; margin-bottom: 12px;">
                            <button onclick="copyToClipboard('${escapedRdpTunnelCommand}', this)" 
                                    style="position: absolute; top: 8px; right: 8px; background: var(--bg-elevated); color: var(--text-secondary); border: 1px solid var(--border-light); padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 0.75em; z-index: 10;">
                                📋 Copy
                            </button>
                            <div style="color: var(--accent-muted); padding: 12px; padding-right: 80px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.88em; overflow-x: auto;">
                                <div style="color: var(--text-muted); margin-bottom: 4px;"># SSH tunnel for RDP</div>
                                <div style="white-space: nowrap;">${rdpTunnelCommand}</div>
                            </div>
                        </div>
                        
                        <div style="padding: 12px; background: var(--bg-card); border-radius: 4px; border: 2px solid var(--success); margin-bottom: 12px;">
                            <div style="font-weight: 600; color: var(--success-text); margin-bottom: 6px;">📌 Step 2: Connect RDP Client</div>
                            <div style="font-size: 0.95em; color: var(--text-primary); margin-bottom: 6px;">
                                With the SSH tunnel running, connect your RDP client to:
                            </div>
                            <div style="text-align: center; padding: 10px; background: var(--success-bg); border-radius: 4px;">
                                <code style="font-size: 1.2em; font-weight: 600; color: var(--success-text); font-family: 'SF Mono', Monaco, Consolas, monospace;">localhost:3389</code>
                            </div>
                            <div style="margin-top: 8px; font-size: 0.88em; color: var(--text-secondary);">
                                Login: Administrator / ${attackboxPassword}
                            </div>
                        </div>
                        
                        <div style="font-weight: 500; color: var(--text-primary); margin-bottom: 6px; font-size: 0.9em;">🔗 Option 2: SSH from Jumpbox (Command Line)</div>
                        <div style="position: relative; background: var(--bg-terminal); border-radius: 4px; overflow: hidden; margin-bottom: 12px;">
                            <div style="color: var(--accent-muted); padding: 12px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.88em;">
                                <div style="color: var(--text-muted); margin-bottom: 4px;"># From the jumpbox, SSH directly to Attack Box</div>
                                <div>ssh attackbox</div>
                                <div style="color: var(--text-muted); margin-top: 4px;"># Or: ssh Administrator@192.168.56.50</div>
                            </div>
                        </div>
                        
                        <div style="padding: 10px; background: var(--bg-card); border-radius: 4px; font-size: 0.88em;">
                            <div style="font-weight: 500; margin-bottom: 8px;">📦 Pre-installed Tools:</div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; color: var(--text-secondary);">
                                <div>• PowerSploit (C:\\Tools\\PowerSploit)</div>
                                <div>• WSL2 Ubuntu</div>
                                <div>• PowerView, PowerUp</div>
                                <div>• Git, Python, AWS CLI</div>
                            </div>
                        </div>
                    </div>
                `;
                
                // LOCAL CS Client option (run CS from user's local machine)
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: var(--bg-section); border-radius: 6px; border-left: 4px solid var(--brand);">
                        <div style="font-weight: 600; color: var(--accent-muted); margin-bottom: 8px;">💻 Run CS Client from YOUR Local Machine</div>
                        <div style="margin-bottom: 10px; font-size: 0.9em; color: var(--text-secondary);">
                            Prefer to run Cobalt Strike Client on your own machine? Use SSH tunneling:
                        </div>
                        
                        <div style="font-weight: 500; color: var(--text-primary); margin-bottom: 6px; font-size: 0.9em;">🔗 Option 1: SSH Tunnel to Team Server (Recommended)</div>
                        <div style="position: relative; background: var(--bg-terminal); border-radius: 4px; overflow: hidden; margin-bottom: 12px;">
                            <button onclick="copyToClipboard('${escapedLocalCsTunnelCommand}', this)" 
                                    style="position: absolute; top: 8px; right: 8px; background: var(--bg-elevated); color: var(--text-secondary); border: 1px solid var(--border-light); padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 0.75em; z-index: 10;">
                                📋 Copy
                            </button>
                            <div style="color: var(--accent-muted); padding: 12px; padding-right: 80px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.88em; overflow-x: auto;">
                                <div style="color: var(--text-muted); margin-bottom: 4px;"># Step 1: Create SSH tunnel to Team Server (run on your local machine)</div>
                                <div style="white-space: nowrap; margin-bottom: 8px;">${localCsTunnelCommand}</div>
                                <div style="color: var(--text-muted); margin-bottom: 4px;"># Step 2: Keep terminal open, then launch your local CS Client</div>
                                <div style="color: var(--text-muted);"># Step 3: Connect CS Client to: localhost:50050</div>
                            </div>
                        </div>
                        
                        <div style="padding: 10px; background: var(--bg-card); border-radius: 4px; font-size: 0.88em; margin-bottom: 10px;">
                            <div style="font-weight: 500; margin-bottom: 6px; color: var(--text-primary);">📋 Quick Steps:</div>
                            <ol style="margin: 0; padding-left: 20px; color: var(--text-secondary); line-height: 1.6;">
                                <li>Run the SSH tunnel command above (keep terminal open)</li>
                                <li>Launch Cobalt Strike on your local machine</li>
                                <li>Connect to: <code style="background: var(--bg-terminal); padding: 1px 4px; border-radius: 2px;">localhost:50050</code></li>
                                <li>Use the team server password you configured</li>
                            </ol>
                        </div>
                        
                        <div style="padding: 8px; background: var(--warning-bg); border-radius: 4px; font-size: 0.8em; color: var(--warning-text);">
                            <strong>⚠️ Note:</strong> You must have Cobalt Strike installed locally. The tunnel forwards port 50050 from the Team Server through the Jumpbox to your machine.
                        </div>
                    </div>
                `;
            }
            
            // Redirector (if exists)
            if (outputs.redirector_public_ip) {
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: var(--warning-bg); border-radius: 6px; border-left: 4px solid var(--warning);">
                        <div style="font-weight: 600; color: var(--warning-text); margin-bottom: 8px;">🔀 HTTPS Redirector</div>
                        <div style="margin-bottom: 5px;"><strong>Public IP:</strong> <code style="background: var(--bg-terminal); padding: 2px 6px; border-radius: 3px;">${outputs.redirector_public_ip}</code></div>
                        <div style="margin-bottom: 5px;"><strong>Domain:</strong> <code style="background: var(--bg-terminal); padding: 2px 6px; border-radius: 3px;">${outputs.redirector_domain || 'N/A'}</code></div>
                    </div>
                `;
            }
            
            // Internal Access Info (from Jumpbox) - show if teamserver or attackbox exists
            if (outputs.teamserver_private_ip || outputs.attackbox_private_ip) {
                html += `
                    <div style="padding: 15px; background: var(--bg-section); border-radius: 8px; margin-top: 10px; border: 1px solid var(--border-light);">
                        <div style="font-weight: 600; margin-bottom: 10px; color: var(--accent-muted);">🔗 Internal Access (from Jumpbox)</div>
                        <div style="font-size: 0.9em; color: var(--text-primary); margin-bottom: 12px;">
                            Once connected to the jumpbox, you can access internal hosts using the pre-configured SSH aliases:
                        </div>
                        <div style="background: var(--bg-terminal); border-radius: 6px; padding: 12px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.9em;">
                            ${outputs.teamserver_private_ip ? `<div style="color: var(--accent-muted); margin-bottom: 6px;"><span style="color: var(--text-muted);"># SSH to Team Server</span></div><div style="color: var(--accent-muted); margin-bottom: 10px;">ssh teamserver</div>` : ''}
                            ${outputs.attackbox_private_ip ? `<div style="color: var(--accent-muted); margin-bottom: 6px;"><span style="color: var(--text-muted);"># SSH to Attack Box</span></div><div style="color: var(--accent-muted); margin-bottom: 10px;">ssh attackbox</div>` : ''}
                            <div style="color: var(--accent-muted); margin-bottom: 6px;"><span style="color: var(--text-muted);"># SSH to Windows DC (by IP)</span></div>
                            <div style="color: var(--accent-muted);">ssh 192.168.56.10</div>
                        </div>
                        <div style="margin-top: 10px; font-size: 0.88em; color: var(--info-text);">
                            💡 The jumpbox has pre-configured SSH keys for internal access. No additional keys needed.
                        </div>
                    </div>
                `;
            }
            
            html += '</div>';
            contentDiv.innerHTML = html;
    } catch (error) {
        contentDiv.innerHTML = `<div style="color: var(--danger-text);">Error loading connection info: ${error.message}</div>`;
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
            buttonElement.style.background = 'var(--success)';
            buttonElement.style.color = 'var(--text-primary)';
            setTimeout(() => {
                buttonElement.innerHTML = originalText;
                buttonElement.style.background = 'var(--bg-elevated)';
                buttonElement.style.color = 'var(--text-secondary)';
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
 * @deprecated This function is deprecated. The new secure architecture uses user-provided keys.
 * Private keys are no longer generated or distributed by the system.
 */
async function downloadSSHKey(projectName, keyType = 'jumpbox') {
    // Show deprecation notice
    alert(`⚠️ SSH Key Download Deprecated\n\n` +
          `The new secure architecture no longer distributes private keys.\n\n` +
          `How it works now:\n` +
          `1. You generate your own key pair locally\n` +
          `2. You upload your PUBLIC key before deployment\n` +
          `3. Your PRIVATE key stays on your machine\n\n` +
          `Use your own private key to connect:\n` +
          `ssh -i ~/.ssh/your_key ubuntu@<jumpbox-ip>`);
}

/**
 * Copy GOAD step 1 command with user's own key
 */
function copyGoadStep1(projectName) {
    const command = `ssh -i ~/.ssh/your_key ubuntu@<JUMPBOX_IP>`;
    navigator.clipboard.writeText(command).then(() => {
        alert('✅ Copied!\n\nRemember to:\n1. Replace "your_key" with your private key path (e.g., ~/.ssh/id_ed25519)\n2. Replace <JUMPBOX_IP> with the actual IP from Connection Info');
    }).catch(err => {
        console.error('Failed to copy:', err);
        alert('Failed to copy to clipboard');
    });
}

/**
 * Start GOAD AD provisioning via the jumpbox
 */
async function startGoadProvisioning(sessionId) {
    const btn = document.getElementById(`${sessionId}-provision-btn`);
    const statusDiv = document.getElementById(`${sessionId}-provision-status`);
    const msgSpan = document.getElementById(`${sessionId}-provision-msg`);
    const logDiv = document.getElementById(`${sessionId}-provision-log`);

    if (!btn || !statusDiv) return;

    // Determine lab name from the current deployment type
    // Mapping: goad-mini/combined-adhoc-mini → GOAD-Mini, goad-light/combined-adhoc-light → GOAD-Light,
    //          goad-full/combined-full-full → GOAD, goad-sccm → SCCM, goad-nha → NHA
    const deploymentType = document.getElementById('deployment-type')?.value || '';
    let labName = 'GOAD-Mini'; // default
    if (deploymentType.includes('sccm')) labName = 'SCCM';
    else if (deploymentType.includes('nha')) labName = 'NHA';
    else if (deploymentType.includes('light')) labName = 'GOAD-Light';
    else if (deploymentType.includes('full')) labName = 'GOAD';
    else if (deploymentType.includes('mini')) labName = 'GOAD-Mini';

    // Disable button, show status
    btn.disabled = true;
    btn.style.opacity = '0.6';
    btn.textContent = '⏳ Provisioning Started...';
    statusDiv.style.display = 'block';
    msgSpan.textContent = `Starting AD provisioning for ${labName}...`;

    try {
        const response = await fetch(`${API_BASE}/goad/provision`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lab_name: labName })
        });

        const data = await response.json();

        if (data.success) {
            addDeploymentLog(`AD provisioning started for ${labName} on jumpbox ${data.jumpbox_ip} (PID: ${data.remote_pid})`, 'info');
            msgSpan.textContent = `AD provisioning running on jumpbox (${data.jumpbox_ip})`;
            logDiv.innerHTML = `
                <div style="color: var(--accent-muted);">Remote PID: ${data.remote_pid}</div>
                <div style="color: var(--text-muted);">Estimated time: ${data.estimated_time}</div>
                <div style="color: var(--text-muted);">Log file: ${data.log_file}</div>
                <div style="color: var(--text-muted); margin-top: 8px;">Monitor progress: <span style="color: var(--accent-muted);">${data.monitor_cmd}</span></div>
            `;
            btn.textContent = '⏳ Provisioning In Progress...';

            // Poll for completion
            pollProvisionStatus(sessionId);
        } else {
            addDeploymentLog(`AD provisioning failed to start: ${data.error || 'Unknown error'}`, 'error');
            msgSpan.style.color = 'var(--danger-text)';
            msgSpan.textContent = 'Provisioning failed to start';
            logDiv.innerHTML = `<div style="color: var(--danger-text);">${data.error || 'Unknown error'}</div>`;
            if (data.hint) {
                logDiv.innerHTML += `<div style="color: var(--warning-text); margin-top: 5px;">${data.hint}</div>`;
            }
            btn.textContent = '🚀 Retry Provisioning';
            btn.disabled = false;
            btn.style.opacity = '1';
        }
    } catch (err) {
        addDeploymentLog(`AD provisioning error: ${err.message}`, 'error');
        msgSpan.style.color = 'var(--danger-text)';
        msgSpan.textContent = 'Error connecting to API';
        logDiv.innerHTML = `<div style="color: var(--danger-text);">${err.message}</div>`;
        btn.textContent = '🚀 Retry Provisioning';
        btn.disabled = false;
        btn.style.opacity = '1';
    }
}

/**
 * Poll GOAD provision status
 */
async function pollProvisionStatus(sessionId) {
    const msgSpan = document.getElementById(`${sessionId}-provision-msg`);
    const btn = document.getElementById(`${sessionId}-provision-btn`);
    const logDiv = document.getElementById(`${sessionId}-provision-log`);

    try {
        const response = await fetch(`${API_BASE}/goad/provision-status`);
        const data = await response.json();

        if (data.success && !data.provisioning) {
            const status = data.data?.status || 'unknown';
            const logTail = data.log_tail || data.data?.log_tail || '';

            if (status === 'completed') {
                addDeploymentLog('AD provisioning completed successfully', 'success');
                if (msgSpan) {
                    msgSpan.style.color = 'var(--success-text)';
                    msgSpan.textContent = 'AD provisioning completed successfully!';
                }
                if (btn) {
                    btn.textContent = 'AD Provisioned';
                    btn.style.background = 'var(--success)';
                }
            } else {
                // Failed or unknown
                const exitCode = data.data?.exit_code || 'unknown';
                const error = data.data?.error || '';
                addDeploymentLog(`AD provisioning failed (exit code: ${exitCode})`, 'error', logTail);
                if (msgSpan) {
                    msgSpan.style.color = 'var(--danger-text)';
                    msgSpan.textContent = 'AD provisioning failed';
                }
                if (logDiv) {
                    logDiv.innerHTML += `<div style="color: var(--danger-text); margin-top: 8px;">Exit code: ${exitCode}${error ? ' - ' + error : ''}</div>
                        <div style="color: var(--warning-text); margin-top: 4px;">Check log: ssh ubuntu@${data.data?.jumpbox_ip || 'JUMPBOX'} cat /home/ubuntu/goad-provision.log</div>`;
                    if (logTail) {
                        logDiv.innerHTML += `<div style="margin-top: 8px; color: var(--text-muted); font-size: 0.88em;">Last log output:</div>
                            <pre style="color: var(--danger-text); white-space: pre-wrap; margin: 4px 0;">${logTail}</pre>`;
                    }
                }
                if (btn) {
                    btn.textContent = 'Retry Provisioning';
                    btn.disabled = false;
                    btn.style.opacity = '1';
                    btn.style.background = 'var(--warning)';
                }
            }
            return;
        }

        // Still running — update log tail if available
        if (data.success && data.provisioning && data.log_tail && logDiv) {
            const existingLogTail = logDiv.querySelector('.provision-log-tail');
            if (existingLogTail) {
                existingLogTail.textContent = data.log_tail;
            } else {
                logDiv.innerHTML += `<div style="margin-top: 8px; color: var(--text-muted); font-size: 0.88em;">Ansible Log (last 20 lines):</div>
                    <pre class="provision-log-tail" style="color: var(--accent-muted); white-space: pre-wrap; margin: 4px 0; max-height: 200px; overflow-y: auto;">${data.log_tail}</pre>`;
            }
        }

        // Still running, poll again in 30 seconds
        setTimeout(() => pollProvisionStatus(sessionId), 30000);
    } catch (err) {
        // Network error, try again
        setTimeout(() => pollProvisionStatus(sessionId), 30000);
    }
}

// Make functions available globally for onclick handlers
window.copyGoadStep1 = copyGoadStep1;
window.startGoadProvisioning = startGoadProvisioning;
window.downloadSSHKey = downloadSSHKey;
window.startGoadProvisionFromPanel = startGoadProvisionFromPanel;
window.verifyGoadAD = verifyGoadAD;

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
                <div style="margin-bottom: 10px; padding: 8px 12px; background: var(--info-bg); border-radius: 6px;">
                    <strong>Lab:</strong> ${creds.lab_display_name || creds.lab_name}
                </div>
            `;
        }
        
        // Default Password
        if (creds.default_password) {
            html += `
                <div style="margin-bottom: 15px; padding: 12px; background: var(--warning-bg); border-radius: 6px; border-left: 4px solid var(--warning);">
                    <div style="font-weight: 600; color: var(--warning-text); margin-bottom: 8px;">🔐 Default Password</div>
                    <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 10px 14px; border-radius: 4px; display: inline-block; font-size: 1.2em; font-family: 'SF Mono', Monaco, Consolas, monospace;">${creds.default_password}</code>
                    <div style="margin-top: 8px; font-size: 0.88em; color: var(--text-secondary);">Used for most AD accounts unless specified otherwise</div>
                </div>
            `;
        }
        
        // Default Users (Local Admin)
        if (creds.default_users && creds.default_users.length > 0) {
            html += `
                <div style="margin-bottom: 15px; padding: 12px; background: var(--danger-bg); border-radius: 6px; border-left: 4px solid var(--danger);">
                    <div style="font-weight: 600; color: var(--danger-text); margin-bottom: 8px;">👤 Local Accounts</div>
                    <div style="display: grid; gap: 6px;">
            `;
            for (const user of creds.default_users) {
                html += `
                    <div style="background: var(--bg-card); padding: 8px; border-radius: 4px;">
                        <div><strong>${user.domain}:</strong> <code style="font-size: 1em;">${user.username}</code> / <code style="font-size: 1em;">${user.password}</code></div>
                        ${user.note ? `<div style="font-size: 0.88em; color: var(--text-secondary);">${user.note}</div>` : ''}
                    </div>
                `;
            }
            html += '</div></div>';
        }
        
        // Domain Admins
        if (creds.domain_admins && creds.domain_admins.length > 0) {
            html += `
                <div style="margin-bottom: 15px; padding: 12px; background: var(--success-bg); border-radius: 6px; border-left: 4px solid var(--success);">
                    <div style="font-weight: 600; color: var(--success-text); margin-bottom: 8px;">👑 Domain Admins</div>
                    <div style="display: grid; gap: 8px;">
            `;
            for (const admin of creds.domain_admins) {
                html += `
                    <div style="background: var(--bg-card); padding: 8px; border-radius: 4px;">
                        <div><strong>${admin.domain}\\${admin.username}</strong></div>
                        <div style="font-size: 0.9em; color: var(--text-secondary);">
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
                <div style="margin-bottom: 15px; padding: 12px; background: var(--info-bg); border-radius: 6px; border-left: 4px solid var(--info);">
                    <div style="font-weight: 600; color: var(--info-text); margin-bottom: 8px;">🎯 Key Users (Attack Paths)</div>
                    <div style="display: grid; gap: 6px; font-size: 0.95em;">
            `;
            for (const user of creds.key_users) {
                html += `
                    <div style="background: var(--bg-card); padding: 6px 10px; border-radius: 4px; display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <code style="font-size: 1em;">${user.domain ? user.domain + '\\\\' : ''}${user.username}</code>
                            <span style="color: var(--text-muted); margin-left: 8px;">${user.password || creds.default_password}</span>
                        </div>
                        <span style="color: var(--text-secondary); font-size: 0.9em;">${user.role || ''}</span>
                    </div>
                `;
            }
            html += '</div></div>';
        }
        
        // Domain Trusts
        if (creds.trusts && creds.trusts.length > 0) {
            html += `
                <div style="margin-bottom: 15px; padding: 12px; background: var(--bg-section); border-radius: 6px; border-left: 4px solid var(--brand);">
                    <div style="font-weight: 600; color: var(--accent-muted); margin-bottom: 8px;">🔗 Domain Trusts</div>
                    <div style="font-size: 0.95em;">
                        ${creds.trusts.map(t => `<div style="margin-bottom: 4px;">${t.from} → ${t.to} <span style="color: var(--text-muted);">(${t.type})</span></div>`).join('')}
                    </div>
                </div>
            `;
        }
        
        // Special Accounts
        if (creds.special_accounts && creds.special_accounts.length > 0) {
            html += `
                <div style="margin-bottom: 15px; padding: 12px; background: var(--danger-bg); border-radius: 6px; border-left: 4px solid var(--danger);">
                    <div style="font-weight: 600; color: var(--danger-text); margin-bottom: 8px;">⚠️ Special Accounts</div>
                    <div style="font-size: 0.95em;">
                        ${creds.special_accounts.map(a => `<div style="margin-bottom: 4px;"><strong>${a.name}:</strong> ${a.note}</div>`).join('')}
                    </div>
                </div>
            `;
        }
        
        // Note
        if (creds.note) {
            html += `
                <div style="padding: 10px; background: var(--bg-container); border-radius: 6px; font-size: 0.9em; color: var(--text-secondary);">
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
            statusDiv.className = 'status-display success';
            statusDiv.innerHTML = `
                <p><strong>Terraform is installed</strong></p>
                <div style="margin-top: 10px; padding: 10px; background: var(--bg-card); border-radius: 5px;">
                    <p><strong>Version:</strong> <code>${data.version || 'Unknown'}</code></p>
                    <p><strong>Path:</strong> <code style="font-size: 0.88em;">${data.path || 'N/A'}</code></p>
                </div>
            `;
            if (helpDiv) helpDiv.style.display = 'none';
        } else {
            statusDiv.className = 'status-display error';
            statusDiv.innerHTML = `
                <p><strong>Terraform is NOT installed</strong></p>
                <p style="margin-top: 10px;">${data.error || 'Terraform CLI was not found in your system PATH.'}</p>
            `;
            if (helpDiv) helpDiv.style.display = 'block';
        }
    } catch (error) {
        statusDiv.className = 'status-display error';
        statusDiv.innerHTML = `
            <p><strong>Error checking Terraform</strong></p>
            <p>${error.message}</p>
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
            statusDiv.className = 'status-display success';
            statusDiv.innerHTML = `
                <p><strong>AWS CLI is installed</strong></p>
                <div style="margin-top: 10px; padding: 10px; background: var(--bg-card); border-radius: 5px;">
                    <p><strong>Version:</strong> <code>${data.version || 'Unknown'}</code></p>
                    <p><strong>Path:</strong> <code style="font-size: 0.88em;">${data.path || 'N/A'}</code></p>
                </div>
            `;
        } else {
            statusDiv.className = 'status-display error';
            statusDiv.innerHTML = `
                <p><strong>AWS CLI is NOT installed</strong></p>
                <p style="margin-top: 10px;">${data.error || 'AWS CLI was not found in your system PATH.'}</p>
                <div style="margin-top: 15px; padding: 15px; background: var(--bg-card); border-radius: 5px; border-left: 3px solid var(--warning);">
                    <p><strong>How to install:</strong></p>
                    <p style="margin-top: 5px;"><code style="display: block; padding: 8px;">brew install awscli</code></p>
                    <p style="margin-top: 10px; font-size: 0.9em;">Or download from <a href="https://aws.amazon.com/cli/" target="_blank">aws.amazon.com/cli</a></p>
                </div>
            `;
        }
    } catch (error) {
        statusDiv.className = 'status-display error';
        statusDiv.innerHTML = `
            <p><strong>Error checking AWS CLI</strong></p>
            <p>${error.message}</p>
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
            statusDiv.className = 'status-display success';
            statusDiv.innerHTML = `
                <p><strong>${data.message || 'AWS credentials are valid'}</strong></p>
                <div style="margin-top: 15px; padding: 15px; background: var(--bg-card); border-radius: 5px;">
                    <p><strong>Account ID:</strong> <code>${data.account || 'N/A'}</code></p>
                    <p><strong>User ARN:</strong> <code style="font-size: 0.9em; word-break: break-all;">${data.user || 'N/A'}</code></p>
                    ${data.user_id ? `<p><strong>User ID:</strong> <code>${data.user_id}</code></p>` : ''}
                </div>
            `;
        } else {
            statusDiv.className = 'status-display error';
            statusDiv.innerHTML = `
                <p><strong>${data.message || 'AWS credentials are not configured or invalid'}</strong></p>
                ${data.error ? `<p><strong>Error:</strong> ${data.error}</p>` : ''}
                <div style="margin-top: 15px; padding: 15px; background: var(--bg-card); border-radius: 5px; border-left: 3px solid var(--warning);">
                    <p><strong>How to fix:</strong></p>
                    <p>Run: <code>aws configure</code></p>
                </div>
            `;
        }
    } catch (error) {
        statusDiv.className = 'status-display error';
        statusDiv.innerHTML = `<p><strong>Error:</strong> ${error.message}</p>`;
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
                statusDiv.className = 'status-display success';
                statusDiv.innerHTML = `
                    <p><strong>✅ ${data.message || 'GitHub CLI authenticated with repo access'}</strong></p>
                    <div style="margin-top: 15px; padding: 15px; background: var(--bg-card); border-radius: 5px;">
                        ${data.username ? `<p><strong>Logged in as:</strong> <code style="background: var(--bg-terminal); padding: 3px 6px; border-radius: 3px;">@${data.username}</code></p>` : ''}
                        ${data.account_type ? `<p><strong>Auth Type:</strong> <code style="background: var(--bg-terminal); padding: 3px 6px; border-radius: 3px;">${data.account_type}</code></p>` : ''}
                        <p style="margin-top: 10px;"><strong>✅ Tools Repository Access:</strong> <span style="color: var(--success-text);">Confirmed</span></p>
                        ${data.repo_visibility ? `<p><strong>Repo Visibility:</strong> <code style="background: var(--bg-terminal); padding: 3px 6px; border-radius: 3px;">${data.repo_visibility}</code></p>` : ''}
                        <p style="margin-top: 10px;"><a href="${data.tools_repo}" target="_blank" style="color: var(--accent-muted);">${data.tools_repo}</a></p>
                    </div>
                `;
            } else {
                // Authenticated but no repo access
                const accessInfo = data.access_request_info || {};
                statusDiv.className = 'status-display warning';
                statusDiv.innerHTML = `
                    <p><strong>⚠️ GitHub CLI authenticated but NO access to tools repository</strong></p>
                    <div style="margin-top: 15px; padding: 15px; background: var(--bg-card); border-radius: 5px;">
                        ${data.username ? `<p><strong>Logged in as:</strong> <code style="background: var(--bg-terminal); padding: 3px 6px; border-radius: 3px;">@${data.username}</code></p>` : ''}
                        <p style="margin-top: 10px;"><strong>❌ Tools Repository Access:</strong> <span style="color: var(--danger-text);">Denied</span></p>
                    </div>
                    <div style="margin-top: 15px; padding: 15px; background: var(--warning-bg); border-radius: 5px; border-left: 4px solid var(--warning);">
                        <p><strong>🔐 Access Required</strong></p>
                        <p style="margin-top: 10px;">The tools repository is private. To get access:</p>
                        <ol style="margin-left: 20px; margin-top: 10px;">
                            <li><strong>Contact Harris</strong> and request access to the repository</li>
                            <li>Provide your GitHub username: <code style="background: var(--bg-terminal); padding: 3px 6px; border-radius: 3px;">@${data.username || 'your-username'}</code></li>
                            <li>Once granted, click "Check GitHub CLI" again to verify</li>
                        </ol>
                        <p style="margin-top: 15px;"><strong>Repository:</strong> <a href="${data.tools_repo}" target="_blank" style="color: var(--accent-muted);">${data.tools_repo}</a></p>
                    </div>
                `;
            }
        } else {
            // Not authenticated at all
            statusDiv.className = 'status-display error';
            statusDiv.innerHTML = `
                <p><strong>❌ ${data.message || 'GitHub CLI is not authenticated'}</strong></p>
                ${data.error ? `<p><strong>Error:</strong> ${data.error}</p>` : ''}
                <div style="margin-top: 15px; padding: 15px; background: var(--warning-bg); border-radius: 5px; border-left: 4px solid var(--warning);">
                    <p><strong>How to fix:</strong></p>
                    <p>1. Install GitHub CLI: <a href="https://cli.github.com/" target="_blank">https://cli.github.com/</a></p>
                    <p>2. Run: <code style="background: var(--bg-container); padding: 5px;">gh auth login</code></p>
                    <p style="margin-top: 10px;"><strong>Required for:</strong> Accessing the private tools repository at <a href="${data.tools_repo || 'https://github.com/harr-sudo/red-team-tools'}" target="_blank" style="color: var(--accent-muted);">${data.tools_repo || 'https://github.com/harr-sudo/red-team-tools'}</a></p>
                </div>
            `;
        }
    } catch (error) {
        statusDiv.className = 'status-display error';
        statusDiv.innerHTML = `<p><strong>Error:</strong> ${error.message}</p>`;
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
            
            statusDiv.className = `status-display ${statusClass}`;
            let html = `
                    <p><strong>${data.status_icon || '📊'} ${data.status_text || 'Checking permissions...'}</strong></p>
                    <p><strong>Method:</strong> ${data.method === 'policy_simulation' ? 'Policy Simulation (Accurate)' : 'Simple Check (Best Effort)'}</p>

                    <div style="margin-top: 15px; padding: 15px; background: var(--bg-card); border-radius: 5px;">
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 15px;">
                            <div style="text-align: center; padding: 10px; background: var(--bg-container); border-radius: 5px;">
                                <div style="font-size: 1.5em; font-weight: bold; color: var(--info-text);">${data.total_required || 0}</div>
                                <div style="color: var(--text-secondary); font-size: 0.9em;">Total Required</div>
                            </div>
                            <div style="text-align: center; padding: 10px; background: var(--success-bg); border-radius: 5px;">
                                <div style="font-size: 1.5em; font-weight: bold; color: var(--success-text);">${data.total_available || 0}</div>
                                <div style="color: var(--text-secondary); font-size: 0.9em;">Available</div>
                            </div>
                            <div style="text-align: center; padding: 10px; background: var(--danger-bg); border-radius: 5px;">
                                <div style="font-size: 1.5em; font-weight: bold; color: var(--danger-text);">${data.total_missing || 0}</div>
                                <div style="color: var(--text-secondary); font-size: 0.9em;">Missing</div>
                            </div>
                        </div>
            `;
            
            if (data.missing_permissions && data.missing_permissions.length > 0) {
                html += '<h4 style="margin-top: 20px; margin-bottom: 10px;">Missing Permissions:</h4><ul style="list-style: none; padding: 0; max-height: 300px; overflow-y: auto;">';
                data.missing_permissions.slice(0, 30).forEach(perm => {
                    html += `<li style="padding: 5px; margin-bottom: 5px; background: var(--warning-bg); border-radius: 3px;"><code style="background: var(--bg-terminal); padding: 2px 6px; border-radius: 3px;">${perm}</code></li>`;
                });
                if (data.missing_permissions.length > 30) {
                    html += `<li style="padding: 5px; color: var(--text-secondary); font-style: italic;">... and ${data.missing_permissions.length - 30} more</li>`;
                }
                html += '</ul>';
            }
            
            html += '</div>';
            statusDiv.innerHTML = html;
        } else {
            statusDiv.className = 'status-display error';
            statusDiv.innerHTML = `<p><strong>Error:</strong> ${data.message || data.error || 'Unknown error'}</p>`;
        }
    } catch (error) {
        statusDiv.className = 'status-display error';
        statusDiv.innerHTML = `<p><strong>Error:</strong> ${error.message}</p>`;
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
        description: 'Network Hacking Academy - CTF-style challenge lab. Ninja-themed corporate network.',
        estCost: 350,
        attacks: ['Challenge Mode - Discover attack paths yourself']
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
            <div style="background: var(--bg-card); padding: 15px; border-radius: 5px; text-align: center;">
                <div style="font-size: 2em; font-weight: bold; color: var(--warning-text);">${labInfo.vms || '?'}</div>
                <div style="color: var(--text-secondary); font-size: 0.9em;">VMs</div>
            </div>
            <div style="background: var(--bg-card); padding: 15px; border-radius: 5px; text-align: center;">
                <div style="font-size: 2em; font-weight: bold; color: var(--warning-text);">${labInfo.domains || '?'}</div>
                <div style="color: var(--text-secondary); font-size: 0.9em;">Domains</div>
            </div>
            <div style="background: var(--bg-card); padding: 15px; border-radius: 5px; text-align: center;">
                <div style="font-size: 2em; font-weight: bold; color: var(--warning-text);">${labInfo.forests || '?'}</div>
                <div style="color: var(--text-secondary); font-size: 0.9em;">Forests</div>
            </div>
        </div>
        <div style="background: var(--bg-card); padding: 15px; border-radius: 5px;">
            <p><strong>Lab Type:</strong> ${labInfo.display_name || labName}</p>
            <p style="color: var(--text-secondary); margin-top: 10px;">${labInfo.description || ''}</p>
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

    // Show provision section and check provisioning status
    const provSection = document.getElementById('goad-provision-section');
    if (provSection) {
        provSection.style.display = 'block';
        checkAndResumeProvisioning();
    }
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
// GOAD PROVISIONING PANEL FUNCTIONS
// ============================================================================

/**
 * Check provisioning status on page load and resume polling if running.
 * Also renders initial state of the provisioning panel.
 */
async function checkAndResumeProvisioning() {
    const panel = document.getElementById('goad-provision-status-panel');
    if (!panel) return;

    try {
        const response = await fetch(`${API_BASE}/goad/provision-status`);
        const data = await response.json();

        if (data.success && data.provisioning) {
            // Still running — show running state and start polling
            updateGoadProvisioningUI({ status: 'running', ...data.data }, true, data.log_tail);
            pollProvisionStatusFromPanel();
        } else if (data.success && data.data) {
            // Has stored status (completed/failed)
            updateGoadProvisioningUI(data.data, false, data.log_tail || data.data.log_tail);
        } else {
            // No provisioning yet — show provision button
            updateGoadProvisioningUI(null, false, '');
        }
    } catch (err) {
        // API not reachable — show provision button as default
        updateGoadProvisioningUI(null, false, '');
    }
}

/**
 * Render the provisioning panel based on current state.
 * @param {Object|null} provData - Provisioning data from API (null = no provisioning yet)
 * @param {boolean} isRunning - Whether provisioning is currently running
 * @param {string} logTail - Last N lines of the Ansible log
 */
function updateGoadProvisioningUI(provData, isRunning, logTail) {
    const panel = document.getElementById('goad-provision-status-panel');
    if (!panel) return;

    const status = provData?.status || 'none';

    if (status === 'none' || !provData) {
        // No provisioning — show "Provision AD" button
        panel.innerHTML = `
            <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
                <button onclick="startGoadProvisionFromPanel()" class="btn" style="background: var(--warning); color: white; font-weight: 600; padding: 10px 24px;">
                    Provision Active Directory
                </button>
                <button onclick="verifyGoadAD()" class="btn" style="background: var(--info); color: white; font-weight: 600; padding: 10px 24px;">
                    Verify AD Health
                </button>
                <span style="color: var(--text-muted); font-size: 0.88em;">Ansible provisioning (30-60 min) to configure domains, users, GPOs, and vulnerabilities</span>
            </div>
            <div style="margin-top: 8px; font-size: 0.8em; color: var(--text-muted);">
                Verify runs: your machine → SSH to jumpbox → WinRM ping to each AD VM
            </div>
        `;
        return;
    }

    if (isRunning || status === 'running') {
        // Running — show spinner + log tail
        panel.innerHTML = `
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                <div class="spinner" style="width: 18px; height: 18px; border: 2px solid var(--border); border-top: 2px solid var(--warning); border-radius: 50%; animation: spin 1s linear infinite;"></div>
                <span style="color: var(--warning-text); font-weight: 600;">AD provisioning in progress...</span>
                <span style="color: var(--text-muted); font-size: 0.88em;">Jumpbox: ${provData.jumpbox_ip || 'unknown'} | PID: ${provData.remote_pid || '?'}</span>
            </div>
            ${logTail ? `
            <div style="background: var(--bg-terminal); border-radius: 6px; padding: 12px; margin-top: 8px;">
                <div style="color: var(--text-muted); font-size: 0.75em; margin-bottom: 6px;">Ansible Log (last 20 lines):</div>
                <pre id="goad-panel-log-tail" style="color: var(--text-secondary); font-family: monospace; font-size: 0.8em; white-space: pre-wrap; max-height: 200px; overflow-y: auto; margin: 0;">${escapeHtml(logTail)}</pre>
            </div>` : '<div style="color: var(--text-muted); font-size: 0.88em;">Waiting for log output...</div>'}
        `;
        return;
    }

    if (status === 'completed') {
        // Completed — show success + verify button
        panel.innerHTML = `
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                <span style="color: var(--success-text); font-weight: 600; font-size: 1em;">AD provisioning completed successfully</span>
            </div>
            <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <button onclick="verifyGoadAD()" class="btn" style="background: var(--info); color: white; font-weight: 600; padding: 10px 24px;">
                    Verify AD Health
                </button>
                <button onclick="startGoadProvisionFromPanel()" class="btn" style="background: var(--border); color: white; padding: 10px 24px;">
                    Re-provision
                </button>
            </div>
            <div style="margin-top: 8px; font-size: 0.8em; color: var(--text-muted);">
                Verify runs: your machine → SSH to jumpbox → WinRM ping to each AD VM
            </div>
            <div id="goad-verify-results"></div>
        `;
        return;
    }

    if (status === 'failed') {
        // Failed — show error + retry button + log tail
        const exitCode = provData.exit_code || 'unknown';
        const error = provData.error || '';
        panel.innerHTML = `
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                <span style="color: var(--danger-text); font-weight: 600; font-size: 1em;">AD provisioning failed (exit code: ${exitCode})</span>
            </div>
            ${error ? `<div style="color: var(--danger-text); font-size: 0.9em; margin-bottom: 8px;">${escapeHtml(error)}</div>` : ''}
            <div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 10px;">
                <button onclick="startGoadProvisionFromPanel()" class="btn" style="background: var(--warning); color: white; font-weight: 600; padding: 10px 24px;">
                    Retry Provisioning
                </button>
                <button onclick="verifyGoadAD()" class="btn" style="background: var(--info); color: white; font-weight: 600; padding: 10px 24px;">
                    Verify AD Health
                </button>
            </div>
            <div style="margin-top: 4px; font-size: 0.8em; color: var(--text-muted);">
                Verify runs: your machine → SSH to jumpbox → WinRM ping to each AD VM
            </div>
            ${logTail ? `
            <div style="background: var(--bg-terminal); border-radius: 6px; padding: 12px; margin-top: 8px;">
                <div style="color: var(--danger-text); font-size: 0.75em; margin-bottom: 6px;">Last log output:</div>
                <pre style="color: var(--danger-text); font-family: monospace; font-size: 0.8em; white-space: pre-wrap; max-height: 200px; overflow-y: auto; margin: 0;">${escapeHtml(logTail)}</pre>
            </div>` : ''}
            <div id="goad-verify-results"></div>
        `;
        return;
    }
}

/**
 * Start AD provisioning from the GOAD infrastructure panel.
 * Determines lab name from the GOAD status data.
 */
async function startGoadProvisionFromPanel() {
    const panel = document.getElementById('goad-provision-status-panel');
    if (!panel) return;

    // Get lab name from GOAD status
    let labName = 'GOAD-Mini'; // default
    try {
        const statusResp = await fetch(`${API_BASE}/goad/status`);
        const statusData = await statusResp.json();
        if (statusData.success && statusData.deployed_lab) {
            labName = statusData.deployed_lab;
        }
    } catch (e) {
        console.warn('Could not fetch GOAD status for lab name, using default');
    }

    // Also try from deployment type selector as fallback
    if (labName === 'GOAD-Mini') {
        const deploymentType = document.getElementById('deployment-type')?.value || '';
        if (deploymentType.includes('sccm')) labName = 'SCCM';
        else if (deploymentType.includes('nha')) labName = 'NHA';
        else if (deploymentType.includes('light')) labName = 'GOAD-Light';
        else if (deploymentType.includes('full')) labName = 'GOAD';
    }

    if (!confirm(`Start AD provisioning for ${labName}? This takes 30-60 minutes.`)) return;

    // Show starting state
    panel.innerHTML = `
        <div style="display: flex; align-items: center; gap: 10px;">
            <div class="spinner" style="width: 18px; height: 18px; border: 2px solid var(--border); border-top: 2px solid var(--warning); border-radius: 50%; animation: spin 1s linear infinite;"></div>
            <span style="color: var(--warning-text); font-weight: 600;">Starting AD provisioning for ${labName}...</span>
        </div>
    `;

    addDeploymentLog(`AD provisioning started for ${labName}`, 'info');

    try {
        const response = await fetch(`${API_BASE}/goad/provision`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lab_name: labName })
        });
        const data = await response.json();

        if (data.success) {
            addDeploymentLog(`AD provisioning running on jumpbox ${data.jumpbox_ip} (PID: ${data.remote_pid})`, 'info');
            updateGoadProvisioningUI({
                status: 'running',
                jumpbox_ip: data.jumpbox_ip,
                remote_pid: data.remote_pid,
                lab_name: labName
            }, true, '');
            pollProvisionStatusFromPanel();
        } else {
            addDeploymentLog(`AD provisioning failed to start: ${data.error}`, 'error');
            updateGoadProvisioningUI({
                status: 'failed',
                error: data.error || 'Failed to start'
            }, false, '');
        }
    } catch (err) {
        addDeploymentLog(`AD provisioning error: ${err.message}`, 'error');
        updateGoadProvisioningUI({
            status: 'failed',
            error: err.message
        }, false, '');
    }
}

/**
 * Poll provision status from the GOAD panel (every 30 seconds).
 */
async function pollProvisionStatusFromPanel() {
    try {
        const response = await fetch(`${API_BASE}/goad/provision-status`);
        const data = await response.json();

        if (data.success && !data.provisioning) {
            const status = data.data?.status || 'unknown';
            const logTail = data.log_tail || data.data?.log_tail || '';

            if (status === 'completed') {
                addDeploymentLog('AD provisioning completed successfully', 'success');
            } else {
                const exitCode = data.data?.exit_code || 'unknown';
                addDeploymentLog(`AD provisioning failed (exit code: ${exitCode})`, 'error', logTail);
            }

            updateGoadProvisioningUI(data.data, false, logTail);
            return;
        }

        // Still running — update log tail and poll again
        if (data.success && data.provisioning) {
            updateGoadProvisioningUI(data.data, true, data.log_tail || '');
        }

        setTimeout(() => pollProvisionStatusFromPanel(), 30000);
    } catch (err) {
        // Network error — retry polling
        setTimeout(() => pollProvisionStatusFromPanel(), 30000);
    }
}

/**
 * Verify AD health by calling the verify endpoint.
 * Shows per-VM WinRM connectivity results.
 */
async function verifyGoadAD() {
    // Find or create results container
    let resultsDiv = document.getElementById('goad-verify-results');
    const panel = document.getElementById('goad-provision-status-panel');

    if (!resultsDiv && panel) {
        const div = document.createElement('div');
        div.id = 'goad-verify-results';
        panel.appendChild(div);
        resultsDiv = div;
    }

    if (resultsDiv) {
        resultsDiv.innerHTML = `
            <div style="margin-top: 12px; display: flex; align-items: center; gap: 10px;">
                <div class="spinner" style="width: 16px; height: 16px; border: 2px solid var(--border); border-top: 2px solid var(--info); border-radius: 50%; animation: spin 1s linear infinite;"></div>
                <span style="color: var(--info-text); font-size: 0.9em;">Verifying AD health (your machine → SSH → jumpbox → WinRM → AD VMs)...</span>
            </div>
        `;
    }

    try {
        const response = await fetch(`${API_BASE}/goad/verify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();

        if (data.success) {
            const vms = data.vms || {};
            const vmRows = Object.entries(vms).map(([name, info]) => {
                const statusIcon = info.status === 'healthy' ? '&#x2705;' : (info.status === 'unreachable' ? '&#x274C;' : '&#x26A0;&#xFE0F;');
                const statusColor = info.status === 'healthy' ? 'var(--success-text)' : 'var(--danger-text)';
                return `<tr>
                    <td style="padding: 6px 12px; font-weight: 500;">${name}</td>
                    <td style="padding: 6px 12px; color: var(--text-secondary);">${info.ip}</td>
                    <td style="padding: 6px 12px; color: ${statusColor};">${statusIcon} ${info.status}</td>
                </tr>`;
            }).join('');

            const level = data.all_healthy ? 'success' : 'warning';
            addDeploymentLog(`AD verification: ${data.healthy}/${data.total} VMs healthy`, level);

            if (resultsDiv) {
                resultsDiv.innerHTML = `
                    <div style="margin-top: 12px; background: var(--bg-card); border-radius: 6px; padding: 12px; border: 1px solid ${data.all_healthy ? 'var(--success-border)' : 'var(--danger-border)'};">
                        <div style="font-weight: 600; margin-bottom: 8px; color: ${data.all_healthy ? 'var(--success-text)' : 'var(--danger-text)'};">
                            ${data.all_healthy ? 'All VMs healthy' : `${data.healthy}/${data.total} VMs healthy`} (${data.lab_name})
                        </div>
                        <table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                            <thead><tr style="border-bottom: 1px solid var(--border);">
                                <th style="padding: 6px 12px; text-align: left;">VM</th>
                                <th style="padding: 6px 12px; text-align: left;">IP</th>
                                <th style="padding: 6px 12px; text-align: left;">Status</th>
                            </tr></thead>
                            <tbody>${vmRows}</tbody>
                        </table>
                    </div>
                `;
            }
        } else {
            addDeploymentLog(`AD verification failed: ${data.error}`, 'error');
            if (resultsDiv) {
                resultsDiv.innerHTML = `
                    <div style="margin-top: 12px; color: var(--danger-text); background: var(--danger-bg); padding: 12px; border-radius: 6px;">
                        Verification failed: ${escapeHtml(data.error || 'Unknown error')}
                        ${data.details ? `<div style="margin-top: 6px; font-size: 0.88em; color: var(--text-secondary);">${escapeHtml(data.details)}</div>` : ''}
                    </div>
                `;
            }
        }
    } catch (err) {
        addDeploymentLog(`AD verification error: ${err.message}`, 'error');
        if (resultsDiv) {
            resultsDiv.innerHTML = `
                <div style="margin-top: 12px; color: var(--danger-text); background: var(--danger-bg); padding: 12px; border-radius: 6px;">
                    Error connecting to API: ${escapeHtml(err.message)}
                </div>
            `;
        }
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

// Flag to suppress per-section toasts during bulk refresh
let _suppressSectionToasts = false;

/**
 * Refresh ALL deployment page sections in parallel.
 * Single entry point for the "Refresh All" button.
 * Uses force-fetch for resources (bypasses cache) since the user explicitly asked to refresh.
 */
async function refreshAll() {
    const lastUpdatedSpan = document.getElementById('deployments-last-updated');
    if (lastUpdatedSpan) {
        lastUpdatedSpan.textContent = 'Refreshing all sections...';
    }

    const refreshBtn = document.getElementById('refresh-all-btn');
    if (refreshBtn) {
        refreshBtn.disabled = true;
        refreshBtn.textContent = 'Refreshing...';
    }

    _suppressSectionToasts = true;
    try {
        await Promise.all([
            refreshDeployments(),
            refreshResourceList(),
            loadDeploymentHistory()
        ]);
        showMessage('All sections refreshed', 'success');
        if (lastUpdatedSpan) {
            lastUpdatedSpan.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
        }
    } catch (error) {
        console.error('Error during refresh all:', error);
    } finally {
        _suppressSectionToasts = false;
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.textContent = 'Refresh All';
        }
    }
}

/**
 * Refresh resources and timeline after a lifecycle action (stop/start/purge).
 * Does NOT refresh the overview section — the caller has already populated it
 * with the action result display (e.g., "Infrastructure Paused").
 */
function refreshAfterAction() {
    loadResourceList();
    renderDeploymentTimeline();
}

/**
 * Refresh deployment information from backend
 */
async function refreshDeployments() {
    const overviewDiv = document.getElementById('deployments-overview');
    const lastUpdatedSpan = document.getElementById('deployments-last-updated');
    const noDeploymentDiv = document.getElementById('no-deployment-message');
    
    // Show loading state inline (no flashing box)
    if (lastUpdatedSpan) {
        lastUpdatedSpan.textContent = 'Loading...';
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
                    <div style="text-align: center; padding: 15px; background: var(--bg-card); border-radius: 8px;">
                        <div style="font-size: 2em; font-weight: bold; color: var(--danger-text);">${summary.c2_server_count || 0}</div>
                        <div style="color: var(--text-secondary); font-size: 0.9em;">C2 Servers</div>
                    </div>
                    <div style="text-align: center; padding: 15px; background: var(--bg-card); border-radius: 8px;">
                        <div style="font-size: 2em; font-weight: bold; color: var(--success-text);">${summary.redirector_count || 0}</div>
                        <div style="color: var(--text-secondary); font-size: 0.9em;">Redirectors</div>
                    </div>
                    <div style="text-align: center; padding: 15px; background: var(--bg-card); border-radius: 8px;">
                        <div style="font-size: 2em; font-weight: bold; color: var(--info-text);">${summary.has_bastion ? '1' : '0'}</div>
                        <div style="color: var(--text-secondary); font-size: 0.9em;">Bastion Host</div>
                    </div>
            `;
        }
        
        if (hasGoadDeployment && goadInfo) {
            overviewHtml += `
                    <div style="text-align: center; padding: 15px; background: var(--bg-card); border-radius: 8px; border: 2px solid var(--warning);">
                        <div style="font-size: 2em; font-weight: bold; color: var(--warning-text);">${goadInfo.vms || 0}</div>
                        <div style="color: var(--text-secondary); font-size: 0.9em;">GOAD VMs</div>
                    </div>
            `;
        }
        
        overviewHtml += `
                </div>
        `;
        
        if (hasC2Deployment) {
            overviewHtml += `<p style="margin-top: 15px; color: var(--text-secondary);"><strong>C2 Deployment Mode:</strong> ${data.deployment_mode || 'N/A'}</p>`;
        }
        if (hasGoadDeployment) {
            overviewHtml += `<p style="margin-top: 5px; color: var(--text-secondary);"><strong>GOAD Lab:</strong> ${goadData.deployed_lab || 'N/A'}</p>`;
        }
        
        overviewHtml += `</div>`;
        overviewDiv.innerHTML = overviewHtml;

        // Check for stopped instances and show warning banner
        checkInstanceStates(data.project_name || '');

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
 * Check instance states and show a stopped-instances banner if any are stopped.
 * Calls the /deploy/instance-status endpoint.
 */
async function checkInstanceStates(projectName) {
    try {
        const response = await fetch(`${API_BASE}/deploy/instance-status`);
        const data = await response.json();

        if (!data.success || !data.instances || data.instances.length === 0) return;

        const counts = data.status_counts || {};
        const stoppedCount = counts.stopped || 0;
        const runningCount = counts.running || 0;
        const totalActive = stoppedCount + runningCount;

        if (stoppedCount === 0) return; // All running, no banner needed

        const stoppedInstances = data.instances.filter(i => i.state === 'stopped');
        const instanceNames = stoppedInstances.map(i => i.name).join(', ');

        const bannerDiv = document.createElement('div');
        bannerDiv.id = 'stopped-instances-banner';
        bannerDiv.style.cssText = 'margin-top: 12px; padding: 12px 16px; background: rgba(143, 164, 100, 0.1); border: 1px solid var(--warning); border-radius: 8px;';
        bannerDiv.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                <div>
                    <strong style="color: var(--warning-text);">&#9724; ${stoppedCount} of ${totalActive} instance${totalActive !== 1 ? 's' : ''} stopped</strong>
                    <span style="color: var(--text-muted); font-size: 0.88em; margin-left: 8px;">${instanceNames}</span>
                </div>
                <button class="btn" onclick="startInfrastructure()" style="background: var(--success); color: var(--text-primary); font-size: 0.88em; padding: 6px 14px;">
                    Start All Instances
                </button>
            </div>
        `;

        // Change the overview header to reflect partial state
        const overviewDiv = document.getElementById('deployments-overview');
        if (overviewDiv) {
            // Replace "Infrastructure Active" with "Infrastructure Paused" if ALL stopped
            const statusP = overviewDiv.querySelector('.status-display p strong');
            if (statusP && stoppedCount === totalActive) {
                statusP.innerHTML = '&#9724; Infrastructure Paused';
                const statusBox = overviewDiv.querySelector('.status-display');
                if (statusBox) {
                    statusBox.classList.remove('success');
                    statusBox.classList.add('warning');
                }
            } else if (statusP && stoppedCount > 0) {
                statusP.innerHTML = '&#9888; Infrastructure Partially Active';
            }

            // Append banner inside the status-display div
            const statusDisplay = overviewDiv.querySelector('.status-display');
            if (statusDisplay) {
                statusDisplay.appendChild(bannerDiv);
            }
        }
    } catch (err) {
        // Silent fail — instance status check is supplementary
        console.warn('Could not check instance states:', err.message);
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
const RESOURCES_CACHE_KEY = 'red_team_resources_cache';

/**
 * Format a timestamp for display (e.g. "18:44:33" or "2 min ago")
 */
function formatResourceTimestamp(ts) {
    if (!ts) return 'never';
    const diff = Math.floor((Date.now() - ts) / 1000);
    if (diff < 10) return 'just now';
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
    return new Date(ts).toLocaleTimeString();
}

/**
 * Update the scope info bar with account, region count, and cache/live status
 */
function updateResourceScopeInfo(data, isCached) {
    const scopeDiv = document.getElementById('resource-scope-info');
    if (!scopeDiv) return;
    const acct = data.account_id || 'unknown';
    const maskedAcct = acct.length > 4 ? '****' + acct.slice(-4) : acct;
    const timeStr = formatResourceTimestamp(data.timestamp);

    if (isCached) {
        scopeDiv.innerHTML = `<span style="background: var(--warning); color: var(--text-inverse); padding: 2px 8px; border-radius: 4px; font-size: 0.88em; font-weight: 600;">CACHED</span> Account <strong>${maskedAcct}</strong> &middot; eu-central-1 &middot; Last checked <strong>${timeStr}</strong> &middot; <span style="color: var(--text-muted);">Refreshing...</span>`;
    } else {
        scopeDiv.innerHTML = `<span style="background: var(--success); color: var(--text-inverse); padding: 2px 8px; border-radius: 4px; font-size: 0.88em; font-weight: 600;">LIVE</span> Account <strong>${maskedAcct}</strong> &middot; eu-central-1 &middot; Updated <strong>${timeStr}</strong>`;
    }
}

// Region filter removed — locked to eu-central-1

/**
 * Render resource data (table + filters + scope info)
 */
function applyResourceData(data, isCached) {
    const section = document.getElementById('resource-list-section');
    const tableBody = document.getElementById('resource-table-body');
    const countDiv = document.getElementById('resource-count');
    if (!section || !tableBody) return;

    allResources = data.resources || [];
    updateResourceScopeInfo(data, isCached);

    if (allResources.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="6" style="padding: 20px; text-align: center; color: var(--text-secondary);">No deployed resources</td></tr>`;
        if (countDiv) countDiv.textContent = '0 resources';
        return;
    }

    section.style.display = 'block';
    renderResourceTable(allResources);
}

/**
 * Save resource data to localStorage cache
 */
function saveResourceCache(data) {
    try {
        const cacheEntry = {
            resources: data.resources || [],
            regions_queried: data.regions_queried || [],
            regions_with_resources: data.regions_with_resources || [],
            account_id: data.account_id || '',
            user_arn: data.user_arn || '',
            timestamp: Date.now()
        };
        localStorage.setItem(RESOURCES_CACHE_KEY, JSON.stringify(cacheEntry));
    } catch (e) {
        console.warn('Failed to cache resources:', e);
    }
}

/**
 * Load resource data from localStorage cache
 */
function loadResourceCache() {
    try {
        const raw = localStorage.getItem(RESOURCES_CACHE_KEY);
        if (!raw) return null;
        return JSON.parse(raw);
    } catch (e) {
        return null;
    }
}

/**
 * Load and display all deployed resources (with cache-first strategy)
 */
async function loadResourceList() {
    const section = document.getElementById('resource-list-section');
    const tableBody = document.getElementById('resource-table-body');
    if (!section || !tableBody) return;

    // 1. Show cached data immediately if available
    const cached = loadResourceCache();
    if (cached) {
        applyResourceData(cached, true);
    } else {
        tableBody.innerHTML = `<tr><td colspan="7" style="padding: 20px; text-align: center; color: var(--text-muted);"><div class="spinner" style="display: inline-block; margin-right: 8px;"></div>Loading resources (eu-central-1)...</td></tr>`;
    }

    // 2. Fetch fresh data in background
    try {
        const response = await fetch(`${API_BASE}/deploy/resources`);
        const data = await response.json();

        if (!data.success) {
            // If we have cache, keep showing it with a warning
            if (cached) {
                updateResourceScopeInfo(cached, false);
                const scopeDiv = document.getElementById('resource-scope-info');
                if (scopeDiv) scopeDiv.innerHTML += ` <span style="color: var(--danger-text);">&middot; Refresh failed</span>`;
            } else {
                tableBody.innerHTML = `<tr><td colspan="7" style="padding: 20px; text-align: center; color: var(--text-secondary);">No resources found or error loading resources</td></tr>`;
            }
            return;
        }

        // 3. Save to cache and render live data
        saveResourceCache(data);
        data.timestamp = Date.now();
        applyResourceData(data, false);

    } catch (error) {
        console.error('Error loading resources:', error);
        // If we have cache, keep showing it with error note
        if (cached) {
            updateResourceScopeInfo(cached, false);
            const scopeDiv = document.getElementById('resource-scope-info');
            if (scopeDiv) scopeDiv.innerHTML += ` <span style="color: var(--danger-text);">&middot; Refresh failed: ${error.message}</span>`;
        } else {
            tableBody.innerHTML = `<tr><td colspan="7" style="padding: 20px; text-align: center; color: var(--danger-text);">Error loading resources: ${error.message}</td></tr>`;
        }
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
    
    // Group resources by project for the purge buttons
    const projectGroups = {};
    activeResources.forEach(r => {
        const project = r.project || 'unknown';
        if (!projectGroups[project]) {
            projectGroups[project] = [];
        }
        projectGroups[project].push(r);
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
        'running': 'var(--success-text)',
        'available': 'var(--success-text)',
        'active': 'var(--success-text)',
        'stopped': 'var(--warning-text)',
        'pending': 'var(--info-text)',
        'terminated': 'var(--danger-text)',
        'deleted': 'var(--danger-text)'
    };
    
    if (activeResources.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="6" style="padding: 20px; text-align: center; color: var(--text-secondary);">No active resources</td></tr>`;
        countDiv.textContent = '0 resources';
        return;
    }

    tableBody.innerHTML = activeResources.map((r, idx) => `
        <tr style="background: ${idx % 2 === 0 ? 'var(--bg-card)' : 'var(--bg-section)'};">
            <td style="padding: 10px; border-bottom: 1px solid var(--border);">
                <span style="font-size: 1.2em;">${typeIcons[r.type] || '📄'}</span>
                <span style="margin-left: 5px; text-transform: uppercase; font-size: 0.88em; color: var(--text-secondary);">${r.type}</span>
            </td>
            <td style="padding: 10px; border-bottom: 1px solid var(--border); font-weight: 500;">${r.name || '-'}</td>
            <td style="padding: 10px; border-bottom: 1px solid var(--border);">
                <code style="background: var(--bg-terminal); padding: 3px 8px; border-radius: 3px; font-size: 0.88em;">${r.id || '-'}</code>
            </td>
            <td style="padding: 10px; border-bottom: 1px solid var(--border);">
                <span style="background: ${stateColors[r.state?.toLowerCase()] || 'var(--text-muted)'}; color: var(--text-primary); padding: 3px 10px; border-radius: 12px; font-size: 0.88em; text-transform: uppercase;">${r.state || 'unknown'}</span>
            </td>
            <td style="padding: 10px; border-bottom: 1px solid var(--border); font-size: 0.88em; color: var(--info-text);">
                ${r.project ? `<a href="#" onclick="event.preventDefault(); purgeFailedDeployment('${r.project}')" style="background: var(--info-bg); padding: 3px 8px; border-radius: 4px; text-decoration: none; cursor: pointer;" title="Click to purge this project">${r.project}</a>` : '-'}
            </td>
            <td style="padding: 10px; border-bottom: 1px solid var(--border); font-size: 0.88em; color: var(--text-secondary);">${r.details || '-'}</td>
        </tr>
    `).join('');

    countDiv.textContent = `${activeResources.length} resource${activeResources.length !== 1 ? 's' : ''} found`;
}

/**
 * Filter resources based on type, region, and search
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
 * Refresh resource list (force fresh fetch, no cache-first)
 */
async function refreshResourceList() {
    const tableBody = document.getElementById('resource-table-body');
    const scopeDiv = document.getElementById('resource-scope-info');
    if (tableBody) tableBody.innerHTML = `<tr><td colspan="7" style="padding: 20px; text-align: center; color: var(--text-muted);"><div class="spinner" style="display: inline-block; margin-right: 8px;"></div>Loading resources (eu-central-1)...</td></tr>`;
    if (scopeDiv) scopeDiv.innerHTML = '<span style="color: var(--text-muted);">Refreshing...</span>';

    try {
        const response = await fetch(`${API_BASE}/deploy/resources`);
        const data = await response.json();
        if (data.success) {
            saveResourceCache(data);
            data.timestamp = Date.now();
            applyResourceData(data, false);
            if (!_suppressSectionToasts) showMessage('Resource list refreshed', 'success');
        } else {
            // Fall back to cache if available
            const cached = loadResourceCache();
            if (cached) {
                applyResourceData(cached, false);
                showMessage('Refresh failed — showing cached data', 'warning');
            }
        }
    } catch (error) {
        const cached = loadResourceCache();
        if (cached) {
            applyResourceData(cached, false);
            showMessage(`Refresh failed: ${error.message} — showing cached data`, 'warning');
        }
    }
}

/**
 * Export resource list to CSV
 */
function exportResourceList() {
    if (allResources.length === 0) {
        showMessage('No resources to export', 'warning');
        return;
    }
    
    const headers = ['Type', 'Name', 'Resource ID', 'State', 'Project', 'Details'];
    const rows = allResources.map(r => [
        r.type || '',
        r.name || '',
        r.id || '',
        r.state || '',
        r.project || '',
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
function addDeploymentLog(message, level = 'info', details = null, projectName = null) {
    const entry = {
        timestamp: new Date().toISOString(),
        level: level,
        message: message,
        details: details
    };

    // Attach project name if provided, or try to extract from [project_name] in message
    if (projectName) {
        entry.project_name = projectName;
    } else {
        const match = message.match(/\[([^\]]+)\]\s*[:.]?\s*$/);
        if (match) entry.project_name = match[1];
    }
    
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
            // Respect the "cleared at" timestamp — don't re-merge entries older than it
            const clearedAt = localStorage.getItem('red_team_logs_cleared_at');
            const clearedTime = clearedAt ? new Date(clearedAt).getTime() : 0;

            // Merge server history with local logs AND archive
            data.history.forEach(h => {
                const entryTime = new Date(h.timestamp).getTime();

                // Skip entries older than the clear point (they were intentionally cleared)
                // But always add to archive
                if (entryTime > clearedTime) {
                    const existsInLogs = deploymentLogs.some(l =>
                        l.timestamp === h.timestamp && l.message === h.message
                    );
                    if (!existsInLogs) {
                        deploymentLogs.push(h);
                    }
                }

                // Always add to archive if not exists
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
    
    // Filter out plan-only logs from the deployment timeline
    // Plan logs should only appear in the archived logs section
    const deploymentOnlyLogs = deploymentLogs.filter(log => log.entry_type !== 'plan');
    
    // Get unique deployment sessions (group by date + project_name)
    // This allows multiple deployments on the same day to be shown separately
    const sessions = {};
    deploymentOnlyLogs.forEach(log => {
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
                hasWarning: false,
                projectName: projectName,
                deploymentType: null,
                firstTime: null,
                lastTime: null
            };
        }
        sessions[sessionKey].logs.push(log);
        if (log.level === 'error') sessions[sessionKey].hasError = true;
        if (log.level === 'success') sessions[sessionKey].hasSuccess = true;
        if (log.level === 'warning') sessions[sessionKey].hasWarning = true;
        
        // Extract deployment type from log messages like "Starting deployment: goad-mini"
        if (log.message && log.message.includes('Starting deployment:')) {
            const match = log.message.match(/Starting deployment:\s*(\S+)/);
            if (match) {
                sessions[sessionKey].deploymentType = match[1];
            }
        }
        
        // If project_name wasn't in log, try to extract from message
        if (!sessions[sessionKey].projectName && log.message) {
            // Pattern 1: "project: name" or "(project: name)"
            const projectColonMatch = log.message.match(/\(?\s*project[:\s]+([a-z0-9_]+(?:_[a-z0-9_]+)+)\s*\)?/i);
            if (projectColonMatch) {
                sessions[sessionKey].projectName = projectColonMatch[1];
            }
            
            // Pattern 2: project_name-component (e.g., "goad_mini_dev_001-goadmini-vpc")
            if (!sessions[sessionKey].projectName) {
                const projectMatch = log.message.match(/([a-z0-9]+_[a-z0-9]+_[a-z0-9_]+)-/i);
                if (projectMatch) {
                    sessions[sessionKey].projectName = projectMatch[1];
                }
            }
            
            // Pattern 3: "for project 'name'" or "project 'name'"
            if (!sessions[sessionKey].projectName) {
                const quotedProjectMatch = log.message.match(/project\s+['"]([^'"]+)['"]/i);
                if (quotedProjectMatch) {
                    sessions[sessionKey].projectName = quotedProjectMatch[1];
                }
            }
            
            // Pattern 4: workspace name pattern (e.g., "Using workspace: goad_mini_dev_001")
            if (!sessions[sessionKey].projectName) {
                const workspaceMatch = log.message.match(/workspace[:\s]+([a-z0-9_]+(?:_[a-z0-9_]+)+)/i);
                if (workspaceMatch) {
                    sessions[sessionKey].projectName = workspaceMatch[1];
                }
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
        timelineContent.innerHTML = '<div style="color: var(--text-muted); text-align: center;">No deployment history yet</div>';
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
                log.message.includes('no tagged resources remain') ||
                log.message.includes('Purge completed') && log.level === 'success' ||
                log.message.includes('terraform destroy') && log.level === 'success'
            ))
        );
        
        // Determine status - destroyed takes precedence over success
        let statusIcon, statusColor, statusText;
        if (wasDestroyed) {
            statusIcon = '🗑️';
            statusColor = 'var(--text-muted)';
            statusText = 'Destroyed';
        } else if (s.hasError) {
            statusIcon = '❌';
            statusColor = 'var(--danger-text)';
            statusText = 'Failed';
        } else if (s.hasSuccess) {
            statusIcon = '✅';
            statusColor = 'var(--success-text)';
            statusText = 'Success';
        } else if (s.hasWarning) {
            statusIcon = '&#9888;';
            statusColor = 'var(--warning-text)';
            statusText = 'Completed';
        } else {
            statusIcon = '&#128260;';
            statusColor = 'var(--info-text)';
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
        const hasValidProjectName = s.projectName && s.projectName !== 'Unknown Project';
        
        // Get resource count for this project from allResources
        const projectResourceCount = hasValidProjectName ? 
            allResources.filter(r => r.project === projectName).length : 0;
        const resourceCountLabel = projectResourceCount > 0 ? ` (${projectResourceCount})` : '';
        
        // Deployment type badge (e.g., goad-mini, c2-full)
        const deploymentTypeBadge = s.deploymentType ? `<span style="background: var(--info-bg); color: var(--info-text); padding: 3px 8px; border-radius: 4px; font-size: 0.75em; font-weight: 500;">${s.deploymentType}</span>` : '';
        
        // Show purge button for failed deployments (but not if already destroyed or unknown project)
        const purgeButton = (s.hasError && !wasDestroyed && hasValidProjectName) ? `
            <button onclick="event.stopPropagation(); purgeFailedDeployment('${projectName}')" class="btn" style="background: var(--danger); color: white; font-size: 0.75em; padding: 6px 12px; margin-left: 10px;" title="Clean up ${projectResourceCount} resources from this failed deployment">
                🧹 Purge${resourceCountLabel}
            </button>
        ` : (s.hasError && !wasDestroyed && !hasValidProjectName) ? `
            <span style="color: var(--text-muted); font-size: 0.75em; margin-left: 10px;" title="Cannot purge: project name unknown. Use the Resources section to manually delete.">
                ⚠️ Manual cleanup required
            </span>
        ` : '';
        
        // Build expanded content
        const expandedContent = isExpanded ? buildSessionDetails(s, sessionId) : '';
        
        // Last log message - show more characters
        const lastLogMessage = lastLog.message.replace(/\x1b\[[0-9;]*m/g, ''); // Clean ANSI codes
        const truncatedMessage = lastLogMessage.length > 80 ? lastLogMessage.substring(0, 80) + '...' : lastLogMessage;
        
        return `
            <div style="margin-bottom: 16px;">
                <!-- Clickable Header -->
                <div onclick="toggleSessionExpand('${sessionId}')" style="display: flex; align-items: center; gap: 15px; padding: 16px 20px; background: var(--bg-card); border-radius: ${isExpanded ? '8px 8px 0 0' : '8px'}; border-left: 5px solid ${statusColor}; cursor: pointer; transition: all 0.2s; box-shadow: 0 2px 4px rgba(0,0,0,0.05);" onmouseover="this.style.background='var(--bg-elevated)'; this.style.boxShadow='0 4px 8px rgba(0,0,0,0.2)'" onmouseout="this.style.background='var(--bg-card)'; this.style.boxShadow='0 2px 4px rgba(0,0,0,0.1)'">
                    <span style="font-size: 1em; transition: transform 0.2s; transform: rotate(${isExpanded ? '90deg' : '0deg'}); color: var(--text-secondary);">▶</span>
                    <span style="font-size: 1.8em;">${statusIcon}</span>
                    <div style="flex: 1; min-width: 0;">
                        <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 6px;">
                            <span style="font-weight: 700; color: var(--text-primary); font-size: 1.1em;">${projectName}</span>
                            ${deploymentTypeBadge}
                            <span style="background: ${statusColor}15; color: ${statusColor}; padding: 3px 10px; border-radius: 4px; font-size: 0.75em; font-weight: 600; text-transform: uppercase;">${statusText}</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 12px; color: var(--text-secondary); font-size: 0.88em;">
                            <span>📅 ${formatDate(s.date)}</span>
                            <span>🕐 ${timeRange}</span>
                            <span>⏱️ ${duration || 'N/A'}</span>
                            <span>📊 ${logCount} events</span>
                        </div>
                        <div style="font-size: 0.88em; color: var(--text-muted); margin-top: 8px; font-style: italic;">
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
        const msg = log.message || '';

        // Detect phase changes — deployment phases
        const isNewPhase = msg.includes('Started:') || msg.includes('Starting');

        // Detect destroy/purge phases
        const isDestroyPhase = msg.includes('Destroying') || msg.includes('terraform destroy') ||
            msg.match(/^Phase \d+\/\d+:.*Destroy/i);
        const isPurgePhase = msg.includes('Purging') || msg.includes('purge') && !msg.includes('purged');
        const isStopPhase = msg.includes('Stopping EC2') || msg.includes('Stop All');
        const isStartPhase = msg.includes('Starting EC2') || msg.includes('Start All');

        if (isNewPhase || isDestroyPhase || isPurgePhase || isStopPhase || isStartPhase) {
            if (currentPhase.logs.length > 0) {
                phases.push(currentPhase);
            }
            let phaseName;
            if (isDestroyPhase) {
                phaseName = msg.match(/^Phase \d+\/\d+:\s*(.+)/) ? msg : 'Destroying Infrastructure';
            } else if (isPurgePhase) {
                phaseName = 'Purging Resources';
            } else if (isStopPhase) {
                phaseName = 'Stopping EC2 Instances';
            } else if (isStartPhase) {
                phaseName = 'Starting EC2 Instances';
            } else {
                phaseName = msg.replace('Started:', '').replace('Starting', '').trim() || 'Processing';
            }
            currentPhase = { name: phaseName, logs: [], status: 'info' };
        }

        currentPhase.logs.push(log);

        // Mark phase status — also detect purge/destroy success
        if (log.level === 'error') {
            currentPhase.status = 'error';
        } else if (log.level === 'success' && currentPhase.status !== 'error') {
            currentPhase.status = 'success';
        } else if (msg.includes('purged successfully') || msg.includes('Infrastructure destroyed')) {
            if (currentPhase.status !== 'error') currentPhase.status = 'success';
        }
    });
    
    if (currentPhase.logs.length > 0) {
        phases.push(currentPhase);
    }
    
    // Build phase timeline
    const phaseHtml = phases.map((phase, idx) => {
        const isDestroy = phase.name.includes('Destroy') || phase.name.includes('Purging');
        const isStop = phase.name.includes('Stopping');
        const isStart = phase.name.includes('Starting EC2');
        let phaseIcon, phaseColor;
        if (phase.status === 'error') {
            phaseIcon = '❌'; phaseColor = 'var(--danger-text)';
        } else if (isDestroy && phase.status === 'success') {
            phaseIcon = '🗑️'; phaseColor = 'var(--text-muted)';
        } else if (isStop && phase.status === 'success') {
            phaseIcon = '⏸️'; phaseColor = 'var(--warning-text)';
        } else if (isStart && phase.status === 'success') {
            phaseIcon = '▶️'; phaseColor = 'var(--success-text)';
        } else if (phase.status === 'success') {
            phaseIcon = '✅'; phaseColor = 'var(--success-text)';
        } else {
            phaseIcon = '🔄'; phaseColor = 'var(--info-text)';
        }
        
        return `
            <div style="display: flex; align-items: flex-start; gap: 10px; padding: 8px 0; ${idx < phases.length - 1 ? 'border-bottom: 1px solid var(--border);' : ''}">
                <span style="font-size: 1em;">${phaseIcon}</span>
                <div style="flex: 1;">
                    <div style="font-weight: 500; color: var(--text-primary); font-size: 0.9em;">${phase.name}</div>
                    <div style="font-size: 0.8em; color: var(--text-secondary); margin-top: 2px;">${phase.logs.length} log entries</div>
                </div>
                <span style="font-size: 0.75em; color: ${phaseColor}; text-transform: uppercase; font-weight: 500;">${phase.status}</span>
            </div>
        `;
    }).join('');
    
    // Get error logs for display
    const errorLogs = session.logs.filter(l => l.level === 'error');
    const errorSection = errorLogs.length > 0 ? `
        <div style="margin-top: 15px;">
            <div style="font-weight: 600; color: var(--danger-text); margin-bottom: 8px; font-size: 0.9em;">⚠️ Errors (${errorLogs.length})</div>
            <div style="background: var(--bg-terminal); color: var(--danger-text); padding: 12px; border-radius: 6px; font-family: monospace; font-size: 0.8em; max-height: 150px; overflow-y: auto;">
                ${errorLogs.map(log => {
                    const time = new Date(log.timestamp).toLocaleTimeString();
                    // Clean ANSI codes from message
                    const cleanMsg = log.message.replace(/\x1b\[[0-9;]*m/g, '').substring(0, 200);
                    return `<div style="margin-bottom: 6px;"><span style="color: var(--text-muted);">[${time}]</span> ${cleanMsg}</div>`;
                }).join('')}
            </div>
        </div>
    ` : '';
    
    // Summary stats
    const successCount = session.logs.filter(l => l.level === 'success').length;
    const warningCount = session.logs.filter(l => l.level === 'warning').length;
    const infoCount = session.logs.filter(l => l.level === 'info').length;
    
    // Build deployed resources section (from logs - fallback)
    const deployedSection = buildResourcesSection(deployedResources, 'Deployed Resources (from logs)', '🚀', 'var(--success-text)', 'created');
    
    // Build purged resources section
    const purgedSection = buildResourcesSection(purgedResources, 'Purged Resources', '🗑️', 'var(--danger-text)', 'destroyed');
    
    // Project name for fetching actual resources
    const projectName = session.projectName || '';
    
    // Only show management buttons for successful deployments
    const isSuccess = session.hasSuccess && !session.hasError;
    const managementButtons = isSuccess ? `
        <div style="background: var(--bg-card); padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid var(--border);">
            <div style="font-weight: 600; color: var(--text-primary); margin-bottom: 12px; font-size: 0.95em;">⚙️ Deployment Management</div>
            <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <button onclick="stopDeploymentResources('${projectName}')" class="btn" style="background: var(--warning); color: var(--text-primary); font-size: 0.88em; padding: 8px 16px;">
                    ⏸️ Stop EC2 Instances
                </button>
                <button onclick="startDeploymentResources('${projectName}')" class="btn" style="background: var(--success); color: var(--text-primary); font-size: 0.88em; padding: 8px 16px;">
                    ▶️ Start EC2 Instances
                </button>
                <button onclick="destroyDeployment('${projectName}')" class="btn" style="background: var(--danger); color: var(--text-primary); font-size: 0.88em; padding: 8px 16px;">
                    🗑️ Destroy Infrastructure
                </button>
            </div>
            <div style="margin-top: 10px; font-size: 0.8em; color: var(--text-secondary); background: var(--warning-bg); padding: 8px 12px; border-radius: 4px; border-left: 3px solid var(--warning);">
                ⚠️ <strong>Note:</strong> Stop/Start only affects EC2 instances. Other resources (VPC, S3, NAT Gateway, etc.) remain active and may still incur charges.
            </div>
        </div>
    ` : '';
    
    // Connection info section for successful deployments
    const connectionSection = isSuccess ? `
        <div id="${sessionId}-connection" style="background: var(--bg-card); padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid var(--border);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <div style="font-weight: 600; color: var(--text-primary); font-size: 0.95em;">🔗 Connection Info</div>
                <button onclick="loadConnectionInfo('${projectName}', '${sessionId}')" class="btn btn-secondary" style="font-size: 0.75em; padding: 4px 10px;">
                    🔄 Load Connection Details
                </button>
            </div>
            <div id="${sessionId}-connection-content" style="color: var(--text-secondary); font-size: 0.9em;">
                Click "Load Connection Details" to fetch SSH commands and access information
            </div>
        </div>
    ` : '';
    
    // Credentials section for successful deployments
    const credentialsSection = isSuccess ? `
        <div id="${sessionId}-credentials" style="background: var(--bg-card); padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid var(--border);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <div style="font-weight: 600; color: var(--text-primary); font-size: 0.95em;">🔐 Credentials</div>
                <button onclick="loadCredentials('${projectName}', '${sessionId}')" class="btn btn-secondary" style="font-size: 0.75em; padding: 4px 10px;">
                    🔄 Load Credentials
                </button>
            </div>
            <div id="${sessionId}-credentials-content" style="color: var(--text-secondary); font-size: 0.9em;">
                Click "Load Credentials" to fetch GOAD lab credentials and access details
            </div>
        </div>
    ` : '';
    
    // GOAD Provisioning Instructions (for GOAD deployments)
    // Use deployment type from session data for reliable detection
    const sessionDeployType = session?.deploymentType || '';
    const isGoadDeployment = sessionDeployType.startsWith('goad-') ||
                             sessionDeployType.startsWith('combined-') ||
                             sessionDeployType.includes('goad') ||
                             sessionDeployType.includes('sccm') ||
                             sessionDeployType.includes('nha');
    
    const goadProvisioningSection = (isSuccess && isGoadDeployment) ? `
        <div style="background: var(--warning-bg); padding: 20px; border-radius: 8px; margin-bottom: 15px; border: 2px solid var(--warning);">
            <div style="font-weight: 700; color: var(--warning-text); margin-bottom: 15px; font-size: 1.1em; display: flex; align-items: center; gap: 8px;">
                ⚠️ IMPORTANT: Active Directory Not Yet Configured!
            </div>

            <div style="background: var(--bg-card); padding: 15px; border-radius: 6px; margin-bottom: 15px;">
                <p style="margin: 0 0 10px 0; color: var(--text-primary); font-size: 0.9em;">
                    <strong>What's deployed:</strong> AWS infrastructure (VMs, networking, Jumpbox, Team Server, Windows Attack Box) is ready.<br>
                    <strong>What's NOT deployed:</strong> Active Directory configuration, domain controllers, users, groups, GPOs, and vulnerabilities.
                </p>
                <p style="margin: 0; color: var(--text-secondary); font-size: 0.88em;">
                    The jumpbox has <strong>Ansible and the GOAD repo pre-installed</strong>. Click the button below to start AD provisioning remotely, or SSH to the jumpbox and run it manually.
                </p>
            </div>

            <!-- Provision AD Button -->
            <div style="text-align: center; margin-bottom: 15px;">
                <button id="${sessionId}-provision-btn" onclick="startGoadProvisioning('${sessionId}')" style="
                    background: var(--warning);
                    color: white;
                    border: none;
                    padding: 15px 40px;
                    border-radius: 8px;
                    cursor: pointer;
                    font-size: 1.1em;
                    font-weight: 700;
                    box-shadow: 0 4px 12px rgba(230, 81, 0, 0.3);
                    transition: all 0.3s;
                " onmouseover="this.style.transform='translateY(-2px)'" onmouseout="this.style.transform='translateY(0)'">
                    🚀 Provision Active Directory
                </button>
                <div style="margin-top: 8px; color: var(--text-secondary); font-size: 0.8em;">
                    Estimated time: <strong>30-60 minutes</strong> depending on lab type
                </div>
            </div>

            <!-- Provisioning Status Area (hidden initially) -->
            <div id="${sessionId}-provision-status" style="display: none; margin-bottom: 15px;">
                <div style="background: var(--bg-terminal); border-radius: 6px; padding: 15px;">
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                        <div class="spinner" style="width: 18px; height: 18px; border: 2px solid var(--border); border-top: 2px solid var(--warning); border-radius: 50%; animation: spin 1s linear infinite;"></div>
                        <span id="${sessionId}-provision-msg" style="color: var(--warning-text); font-weight: 600;">Starting AD provisioning...</span>
                    </div>
                    <div id="${sessionId}-provision-log" style="color: var(--text-muted); font-family: monospace; font-size: 0.8em; max-height: 200px; overflow-y: auto;">
                    </div>
                </div>
            </div>

            <!-- Manual Alternative (collapsible) -->
            <details style="margin-bottom: 15px;">
                <summary style="cursor: pointer; color: var(--text-secondary); font-size: 0.88em; font-weight: 500;">📋 Manual Alternative: Run Ansible from Jumpbox</summary>
                <div style="background: var(--bg-terminal); border-radius: 6px; overflow: hidden; margin-top: 10px;">
                    <div style="padding: 12px; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 0.88em; color: var(--text-secondary); line-height: 1.6;">
                        <div style="color: var(--text-muted);"># SSH to jumpbox</div>
                        <div style="color: var(--accent-muted);">ssh -i ~/.ssh/goad_key ubuntu@&lt;JUMPBOX_IP&gt;</div>
                        <div style="color: var(--text-muted); margin-top: 8px;"># Run GOAD Ansible provisioning (pre-installed on jumpbox)</div>
                        <div style="color: var(--accent-muted);">cd /home/ubuntu/GOAD</div>
                        <div style="color: var(--accent-muted);">ansible-playbook -i ad/&lt;LAB_TYPE&gt;/data/inventory -i ad/&lt;LAB_TYPE&gt;/providers/aws/inventory ansible/main.yml</div>
                    </div>
                </div>
            </details>

            <div style="background: var(--success-bg); padding: 12px; border-radius: 6px; border-left: 4px solid var(--success);">
                <div style="font-weight: 600; color: var(--success-text); margin-bottom: 5px; font-size: 0.88em;">✅ After Ansible Completes:</div>
                <ul style="margin: 0; padding-left: 20px; color: var(--text-primary); font-size: 0.88em; line-height: 1.6;">
                    <li>Active Directory domains will be configured</li>
                    <li>Domain controllers will be promoted</li>
                    <li>Users, groups, and GPOs will be created</li>
                    <li>Vulnerabilities will be configured for attack practice</li>
                    <li>RDP to Windows Attack Box and use PowerSploit to attack!</li>
                </ul>
            </div>

            <div style="margin-top: 15px; padding: 10px; background: var(--info-bg); border-radius: 6px; font-size: 0.8em; color: var(--info-text);">
                💡 <strong>Tip:</strong> See the official <a href="https://orange-cyberdefense.github.io/GOAD/providers/aws/" target="_blank" style="color: var(--info-text);">GOAD AWS Documentation</a> for detailed provisioning instructions.
            </div>
        </div>
    ` : '';

    return `
        <div id="${sessionId}-details" style="background: var(--bg-container); border: 1px solid var(--border); border-top: none; border-radius: 0 0 8px 8px; padding: 20px;">
            <!-- Summary Stats -->
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px;">
                <div style="background: var(--bg-card); padding: 12px; border-radius: 8px; text-align: center; border: 1px solid var(--border);">
                    <div style="font-size: 1.5em; font-weight: bold; color: var(--info-text);">${infoCount}</div>
                    <div style="font-size: 0.75em; color: var(--text-secondary);">Info</div>
                </div>
                <div style="background: var(--bg-card); padding: 12px; border-radius: 8px; text-align: center; border: 1px solid var(--border);">
                    <div style="font-size: 1.5em; font-weight: bold; color: var(--success-text);">${successCount}</div>
                    <div style="font-size: 0.75em; color: var(--text-secondary);">Success</div>
                </div>
                <div style="background: var(--bg-card); padding: 12px; border-radius: 8px; text-align: center; border: 1px solid var(--border);">
                    <div style="font-size: 1.5em; font-weight: bold; color: var(--warning-text);">${warningCount}</div>
                    <div style="font-size: 0.75em; color: var(--text-secondary);">Warnings</div>
                </div>
                <div style="background: var(--bg-card); padding: 12px; border-radius: 8px; text-align: center; border: 1px solid var(--border);">
                    <div style="font-size: 1.5em; font-weight: bold; color: var(--danger-text);">${errorLogs.length}</div>
                    <div style="font-size: 0.75em; color: var(--text-secondary);">Errors</div>
                </div>
            </div>
            
            <!-- Management Buttons (for successful deployments) -->
            ${managementButtons}
            
            <!-- Deployment Info -->
            <div style="background: var(--bg-card); padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid var(--border);">
                <div style="font-weight: 600; color: var(--text-primary); margin-bottom: 12px; font-size: 0.95em;">📋 Deployment Details</div>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; font-size: 0.88em;">
                    <div><span style="color: var(--text-secondary);">Project:</span> <strong>${session.projectName || 'Unknown'}</strong></div>
                    <div><span style="color: var(--text-secondary);">Date:</span> <strong>${formatDate(session.date)}</strong></div>
                    <div><span style="color: var(--text-secondary);">Started:</span> <strong>${session.firstTime ? session.firstTime.toLocaleTimeString() : 'N/A'}</strong></div>
                    <div><span style="color: var(--text-secondary);">Ended:</span> <strong>${session.lastTime ? session.lastTime.toLocaleTimeString() : 'N/A'}</strong></div>
                </div>
            </div>
            
            <!-- Connection Info (for successful deployments) -->
            ${connectionSection}
            
            <!-- Credentials (for successful deployments) -->
            ${credentialsSection}
            
            <!-- GOAD Provisioning Instructions (for GOAD deployments) -->
            ${goadProvisioningSection}
            
            <!-- AWS Resources Section (loaded dynamically) -->
            <div id="${sessionId}-resources" style="background: var(--bg-card); padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid var(--border);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <div style="font-weight: 600; color: var(--text-primary); font-size: 0.95em;">☁️ AWS Resources</div>
                    <button onclick="loadProjectResources('${projectName}', '${sessionId}')" class="btn btn-secondary" style="font-size: 0.75em; padding: 4px 10px;">
                        🔄 Load Resources
                    </button>
                </div>
                <div id="${sessionId}-resources-content" style="color: var(--text-secondary); font-size: 0.9em;">
                    Click "Load Resources" to fetch live resource status from AWS
                </div>
            </div>
            
            <!-- Purged Resources -->
            ${purgedSection}
            
            <!-- Phase Timeline -->
            <div style="background: var(--bg-card); padding: 15px; border-radius: 8px; border: 1px solid var(--border); margin-bottom: 15px;">
                <div style="font-weight: 600; color: var(--text-primary); margin-bottom: 12px; font-size: 0.95em;">📊 Deployment Phases</div>
                ${phaseHtml}
            </div>
            
            ${errorSection}
            
            <!-- View Full Logs Button -->
            <div style="margin-top: 20px; text-align: center;">
                <button onclick="showSessionLogs('${session.sessionKey}')" class="btn btn-secondary" style="font-size: 0.88em;">
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
        contentDiv.innerHTML = '<span style="color: var(--danger-text);">❌ No project name available</span>';
        return;
    }
    
    contentDiv.innerHTML = '<div style="display: flex; align-items: center; gap: 10px;"><div class="spinner" style="width: 20px; height: 20px;"></div> Loading resources from AWS...</div>';
    
    try {
        const response = await fetch(`${API_BASE}/deploy/resources/project/${encodeURIComponent(projectName)}?refresh=true`);
        const data = await response.json();
        
        if (!data.success) {
            contentDiv.innerHTML = `<span style="color: var(--danger-text);">❌ ${data.error || 'Failed to load resources'}</span>`;
            return;
        }
        
        if (!data.resources || data.resources.length === 0) {
            contentDiv.innerHTML = '<span style="color: var(--text-secondary);">No resources found for this project</span>';
            return;
        }
        
        // Build resources display
        contentDiv.innerHTML = buildProjectResourcesHTML(data);
        
    } catch (error) {
        contentDiv.innerHTML = `<span style="color: var(--danger-text);">❌ Error: ${error.message}</span>`;
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
        'running': 'var(--success-text)',
        'stopped': 'var(--warning-text)',
        'terminated': 'var(--danger-text)',
        'available': 'var(--success-text)',
        'active': 'var(--success-text)',
        'associated': 'var(--success-text)',
        'pending': 'var(--info-text)',
        'deleted': 'var(--text-muted)',
        'deleting': 'var(--warning-text)'
    };
    
    let html = `
        <div style="margin-bottom: 10px; font-size: 0.88em; color: var(--text-secondary);">
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
                <div style="font-weight: 500; color: var(--text-primary); margin-bottom: 8px; font-size: 0.9em;">
                    ${config.icon} ${config.label} (${typeResources.length})
                </div>
                <div style="display: flex; flex-direction: column; gap: 6px;">
        `;
        
        for (const resource of typeResources) {
            const stateColor = stateColors[resource.state] || 'var(--text-muted)';
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
                <div style="display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: var(--bg-container); border-radius: 6px; font-size: 0.88em;">
                    <span>${stateIcon}</span>
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-weight: 500; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                            ${resource.name || resource.id}
                        </div>
                        <div style="font-size: 0.88em; color: var(--text-muted); font-family: monospace;">
                            ${resource.id}
                        </div>
                        ${details.length > 0 ? `
                            <div style="font-size: 0.8em; color: var(--text-secondary); margin-top: 2px;">
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
                <div style="font-weight: 500; color: var(--text-primary); margin-bottom: 8px; font-size: 0.9em;">
                    ${config.icon} ${config.label} (${typeResources.length})
                </div>
                <div style="font-size: 0.88em; color: var(--text-secondary);">
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
            <div style="display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: ${action === 'created' ? 'var(--success-bg)' : 'var(--danger-bg)'}; border-radius: 6px; margin-bottom: 6px;">
                <span style="font-size: 1.1em;">${typeIcon}</span>
                <div style="flex: 1; min-width: 0;">
                    <div style="font-weight: 500; color: var(--text-primary); font-size: 0.88em; text-transform: capitalize;">${type.replace(/_/g, ' ')}</div>
                    <div style="font-size: 0.8em; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${item.name || item.id || 'Unknown'}</div>
                </div>
                <span style="background: ${action === 'created' ? 'var(--success)' : 'var(--danger)'}; color: var(--text-primary); padding: 2px 8px; border-radius: 4px; font-size: 0.7em; text-transform: uppercase;">${item.status}</span>
            </div>
        `).join('');
    }).join('');
    
    return `
        <div style="background: var(--bg-card); padding: 15px; border-radius: 8px; border: 1px solid var(--border); margin-bottom: 15px;">
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
        'info': 'var(--accent-muted)',
        'success': 'var(--success-text)',
        'warning': 'var(--warning-text)',
        'error': 'var(--danger-text)'
    };
    
    modal.innerHTML = `
        <div style="background: var(--bg-terminal); border-radius: 12px; max-width: 900px; width: 100%; max-height: 80vh; overflow: hidden; display: flex; flex-direction: column;">
            <div style="padding: 20px; border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between; align-items: center;">
                <h2 style="margin: 0; color: white;">📜 Full Deployment Logs - ${formatDate(date)}</h2>
                <button onclick="closeSessionLogsModal()" style="background: none; border: none; color: white; font-size: 24px; cursor: pointer;">&times;</button>
            </div>
            <div style="flex: 1; overflow-y: auto; padding: 15px; font-family: 'SF Mono', Monaco, monospace; font-size: 0.88em; line-height: 1.6;">
                ${sessionLogs.map(log => {
                    const time = new Date(log.timestamp).toLocaleTimeString();
                    const color = levelColors[log.level] || 'var(--text-secondary)';
                    // Clean ANSI codes
                    const cleanMsg = log.message.replace(/\x1b\[[0-9;]*m/g, '');
                    return `<div style="margin-bottom: 6px; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                        <span style="color: var(--text-muted);">[${time}]</span>
                        <span style="color: ${color}; background: ${color}20; padding: 1px 6px; border-radius: 3px; font-size: 0.8em; margin: 0 8px;">${log.level.toUpperCase()}</span>
                        <span style="color: var(--text-secondary);">${cleanMsg}</span>
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
        logsDiv.innerHTML = '<div style="color: var(--text-muted);">No logs match the current filter</div>';
        return;
    }
    
    const levelColors = {
        'info': 'var(--info-text)',
        'success': 'var(--success-text)',
        'warning': 'var(--warning-text)',
        'error': 'var(--danger-text)'
    };
    
    logsDiv.innerHTML = filtered.slice(-100).reverse().map(log => {
        const time = formatTimestamp(log.timestamp);
        const color = levelColors[log.level] || 'var(--text-muted)';
        const levelBadge = `<span style="color: ${color}; font-weight: bold;">[${log.level.toUpperCase()}]</span>`;
        
        let html = `<div style="margin-bottom: 8px;"><span style="color: var(--text-muted);">${time}</span> ${levelBadge} <span style="color: var(--text-primary);">${escapeHtml(log.message)}</span></div>`;
        
        if (log.details) {
            html += `<div style="margin-left: 20px; margin-bottom: 12px; padding: 8px; background: var(--bg-container); border-radius: 4px; color: var(--text-muted); font-size: 0.9em; white-space: pre-wrap;">${escapeHtml(log.details)}</span></div>`;
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
    if (!_suppressSectionToasts) showMessage('Deployment history refreshed', 'success');
}

/**
 * Clear deployment logs (current view only - archive is preserved)
 */
function clearDeploymentLogs() {
    // Identify active projects: sessions with successful deployment but no destroy/purge completion
    const destroyPatterns = [
        'Resources purged successfully',
        'Resources force-purged successfully',
        'All resources have been purged',
        'Infrastructure destroyed',
        'no tagged resources remain',
        'Purge completed'
    ];

    // Group logs by project to find active ones
    const projectLogs = {};
    deploymentLogs.forEach(log => {
        const pn = log.project_name || null;
        if (!pn) return;
        if (!projectLogs[pn]) projectLogs[pn] = { hasSuccess: false, wasDestroyed: false, logs: [] };
        projectLogs[pn].logs.push(log);
        if (log.level === 'success') projectLogs[pn].hasSuccess = true;
        if (log.message && destroyPatterns.some(p => log.message.includes(p))) projectLogs[pn].wasDestroyed = true;
        if (log.message && log.message.includes('terraform destroy') && log.level === 'success') projectLogs[pn].wasDestroyed = true;
    });

    const activeProjects = Object.entries(projectLogs)
        .filter(([_, p]) => p.hasSuccess && !p.wasDestroyed)
        .map(([name]) => name);

    if (activeProjects.length > 0) {
        const kept = activeProjects.join(', ');
        if (!confirm(
            `Clear deployment logs?\n\n` +
            `${activeProjects.length} active project${activeProjects.length !== 1 ? 's' : ''} will be preserved:\n` +
            `${kept}\n\n` +
            `These logs are needed for Stop/Start/Destroy controls.\n` +
            `Only inactive and orphaned logs will be cleared.\n\n` +
            `Archive is always preserved.`
        )) {
            return;
        }

        // Keep logs belonging to active projects, clear everything else
        const activeSet = new Set(activeProjects);
        deploymentLogs = deploymentLogs.filter(log => log.project_name && activeSet.has(log.project_name));
        saveDeploymentLogs();
        // Set cleared-at timestamp so server merge doesn't re-add old entries
        localStorage.setItem('red_team_logs_cleared_at', new Date().toISOString());
    } else {
        if (!confirm('Clear all deployment logs?\n\nNo active deployments found. All logs will be cleared.\nArchive is always preserved via "Archived Logs".')) {
            return;
        }
        deploymentLogs = [];
        localStorage.removeItem(LOGS_STORAGE_KEY);
        // Set cleared-at timestamp so server merge doesn't re-add old entries
        localStorage.setItem('red_team_logs_cleared_at', new Date().toISOString());
    }

    renderDeploymentTimeline();
    renderDeploymentLogs();
    const msg = activeProjects.length > 0
        ? `Logs cleared (${activeProjects.length} active project${activeProjects.length !== 1 ? 's' : ''} preserved)`
        : 'All logs cleared (archive preserved)';
    showMessage(msg, 'success');
}

/**
 * Extract structured facts from a session's log entries
 */
function extractSessionFacts(logs) {
    const facts = {
        deploymentType: null,
        workspace: null,
        deployDuration: null,
        resourcesCreated: 0,
        resourcesDestroyed: 0,
        resourcesRemaining: 0,
        destroyedResources: [],
        s3Uploads: [],
        instancesStopped: 0,
        instancesStarted: 0,
        stoppedNames: [],
        startedNames: [],
        errors: []
    };

    logs.forEach(log => {
        const msg = log.message || '';

        // Deployment type
        const deployMatch = msg.match(/Starting deployment:\s*(\S+)/);
        if (deployMatch) facts.deploymentType = deployMatch[1];

        // Workspace
        const wsMatch = msg.match(/Using workspace:\s*(\S+)/);
        if (wsMatch) facts.workspace = wsMatch[1];

        // Deploy duration
        const durMatch = msg.match(/Deployment completed successfully in (.+)/);
        if (durMatch) facts.deployDuration = durMatch[1];

        // Resources created (from "Saved X resources for project")
        const createdMatch = msg.match(/Saved (\d+) resources? for project/);
        if (createdMatch) facts.resourcesCreated = parseInt(createdMatch[1]);

        // Individual resource destroyed
        const destroyedMatch = msg.match(/^Destroyed:\s*(.+)/);
        if (destroyedMatch) facts.destroyedResources.push(destroyedMatch[1]);

        // Total resources destroyed
        const totalDestroyMatch = msg.match(/(\d+) resources? destroyed/);
        if (totalDestroyMatch) facts.resourcesDestroyed = Math.max(facts.resourcesDestroyed, parseInt(totalDestroyMatch[1]));

        // Resources remaining
        const remainMatch = msg.match(/(\d+) resources? still remain/);
        if (remainMatch) facts.resourcesRemaining = parseInt(remainMatch[1]);

        // S3 uploads
        const s3Match = msg.match(/Uploaded .+ to (s3:\/\/\S+)/);
        if (s3Match) facts.s3Uploads.push(s3Match[1]);

        // Instances stopped
        const stopMatch = msg.match(/Stopped (\d+) EC2 instance\(s\):\s*(.+)/);
        if (stopMatch) {
            facts.instancesStopped = parseInt(stopMatch[1]);
            facts.stoppedNames = stopMatch[2].split(',').map(n => n.trim()).filter(Boolean);
        }

        // Instances started
        const startMatch = msg.match(/Started (\d+) EC2 instance\(s\):\s*(.+)/);
        if (startMatch) {
            facts.instancesStarted = parseInt(startMatch[1]);
            facts.startedNames = startMatch[2].split(',').map(n => n.trim()).filter(Boolean);
        }

        // Errors
        if (log.level === 'error') {
            facts.errors.push(msg.length > 150 ? msg.substring(0, 150) + '...' : msg);
        }
    });

    // If no total count but we have individual destroyed entries, use that count
    if (facts.resourcesDestroyed === 0 && facts.destroyedResources.length > 0) {
        facts.resourcesDestroyed = facts.destroyedResources.length;
    }

    return facts;
}

/**
 * View archived logs in a modal — timeline-style session cards
 */
// Track expanded sessions in the archived modal separately
let expandedArchivedSessions = new Set();

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

    function buildArchivedSessions() {
        // Group archived logs into sessions (same logic as renderDeploymentTimeline)
        const sessions = {};
        archivedLogs.forEach(log => {
            const date = log.timestamp.split('T')[0];
            const projectName = log.project_name || null;
            const sessionKey = projectName ? `${date}-${projectName}` : date;

            if (!sessions[sessionKey]) {
                sessions[sessionKey] = {
                    date,
                    sessionKey,
                    logs: [],
                    hasError: false,
                    hasSuccess: false,
                    hasWarning: false,
                    projectName: projectName,
                    deploymentType: null,
                    firstTime: null,
                    lastTime: null
                };
            }
            sessions[sessionKey].logs.push(log);
            if (log.level === 'error') sessions[sessionKey].hasError = true;
            if (log.level === 'success') sessions[sessionKey].hasSuccess = true;
            if (log.level === 'warning') sessions[sessionKey].hasWarning = true;

            // Extract deployment type
            if (log.message && log.message.includes('Starting deployment:')) {
                const match = log.message.match(/Starting deployment:\s*(\S+)/);
                if (match) sessions[sessionKey].deploymentType = match[1];
            }

            // Extract project name from message if not in log
            if (!sessions[sessionKey].projectName && log.message) {
                const projectColonMatch = log.message.match(/\(?\s*project[:\s]+([a-z0-9_]+(?:_[a-z0-9_]+)+)\s*\)?/i);
                if (projectColonMatch) {
                    sessions[sessionKey].projectName = projectColonMatch[1];
                } else {
                    const projectMatch = log.message.match(/([a-z0-9]+_[a-z0-9]+_[a-z0-9_]+)-/i);
                    if (projectMatch) sessions[sessionKey].projectName = projectMatch[1];
                }
                if (!sessions[sessionKey].projectName) {
                    const quotedMatch = log.message.match(/project\s+['"]([^'"]+)['"]/i);
                    if (quotedMatch) sessions[sessionKey].projectName = quotedMatch[1];
                }
                if (!sessions[sessionKey].projectName) {
                    const wsMatch = log.message.match(/workspace[:\s]+([a-z0-9_]+(?:_[a-z0-9_]+)+)/i);
                    if (wsMatch) sessions[sessionKey].projectName = wsMatch[1];
                }
            }

            // Track time range
            const logTime = new Date(log.timestamp);
            if (!sessions[sessionKey].firstTime || logTime < sessions[sessionKey].firstTime) {
                sessions[sessionKey].firstTime = logTime;
            }
            if (!sessions[sessionKey].lastTime || logTime > sessions[sessionKey].lastTime) {
                sessions[sessionKey].lastTime = logTime;
            }
        });

        return Object.values(sessions).reverse();
    }

    function renderArchivedContent() {
        const sessionList = buildArchivedSessions();

        const sessionCards = sessionList.length === 0 ? `
            <p style="text-align: center; color: var(--text-muted);">No archived sessions.</p>
        ` : sessionList.map(s => {
            const archSessionId = `arch-${s.sessionKey}`;
            const isExpanded = expandedArchivedSessions.has(archSessionId);

            // Determine status
            const wasDestroyed = s.logs.some(log =>
                (log.message && (
                    log.message.includes('Resources purged successfully') ||
                    log.message.includes('Resources force-purged successfully') ||
                    log.message.includes('All resources have been purged') ||
                    log.message.includes('Infrastructure destroyed') ||
                    log.message.includes('no tagged resources remain') ||
                    log.message.includes('Purge completed') && log.level === 'success' ||
                    log.message.includes('terraform destroy') && log.level === 'success'
                ))
            );

            let statusIcon, statusColor, statusText;
            if (wasDestroyed) {
                statusIcon = '&#128465;'; statusColor = 'var(--text-muted)'; statusText = 'Destroyed';
            } else if (s.hasError) {
                statusIcon = '&#10060;'; statusColor = 'var(--danger-text)'; statusText = 'Failed';
            } else if (s.hasSuccess) {
                statusIcon = '&#9989;'; statusColor = 'var(--success-text)'; statusText = 'Success';
            } else if (s.hasWarning) {
                statusIcon = '&#9888;'; statusColor = 'var(--warning-text)'; statusText = 'Completed';
            } else {
                statusIcon = '&#128260;'; statusColor = 'var(--info-text)'; statusText = 'Info';
            }

            const logCount = s.logs.length;
            const lastLog = s.logs[s.logs.length - 1];
            const projectName = s.projectName || 'Unknown Project';

            // Time range & duration
            const startTime = s.firstTime ? s.firstTime.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '';
            const endTime = s.lastTime ? s.lastTime.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '';
            const timeRange = startTime === endTime ? startTime : `${startTime} - ${endTime}`;
            let duration = '';
            if (s.firstTime && s.lastTime) {
                const durationMs = s.lastTime - s.firstTime;
                const durationMin = Math.floor(durationMs / 60000);
                const durationSec = Math.floor((durationMs % 60000) / 1000);
                duration = durationMin > 0 ? `${durationMin}m ${durationSec}s` : `${durationSec}s`;
            }

            const deploymentTypeBadge = s.deploymentType ? `<span style="background: var(--info-bg); color: var(--info-text); padding: 3px 8px; border-radius: 4px; font-size: 0.75em; font-weight: 500;">${s.deploymentType}</span>` : '';

            const lastLogMessage = (lastLog.message || '').replace(/\x1b\[[0-9;]*m/g, '');
            const truncatedMessage = lastLogMessage.length > 80 ? lastLogMessage.substring(0, 80) + '...' : lastLogMessage;

            // Extract facts for both header summary and expanded view
            const facts = extractSessionFacts(s.logs);

            // Build compact summary tags for the card header
            let headerTags = [];
            if (facts.resourcesCreated > 0) {
                headerTags.push(`<span style="background: rgba(126,207,140,0.15); color: var(--success-text); padding: 2px 7px; border-radius: 3px; font-size: 0.72em;">+${facts.resourcesCreated} created</span>`);
            }
            if (facts.resourcesDestroyed > 0) {
                headerTags.push(`<span style="background: rgba(122,132,158,0.15); color: var(--text-muted); padding: 2px 7px; border-radius: 3px; font-size: 0.72em;">-${facts.resourcesDestroyed} destroyed</span>`);
            }
            if (facts.instancesStopped > 0) {
                headerTags.push(`<span style="background: rgba(143,164,100,0.15); color: var(--warning-text); padding: 2px 7px; border-radius: 3px; font-size: 0.72em;">${facts.instancesStopped} stopped</span>`);
            }
            if (facts.instancesStarted > 0) {
                headerTags.push(`<span style="background: rgba(126,207,140,0.15); color: var(--success-text); padding: 2px 7px; border-radius: 3px; font-size: 0.72em;">${facts.instancesStarted} started</span>`);
            }
            if (facts.errors.length > 0) {
                headerTags.push(`<span style="background: rgba(240,138,132,0.15); color: var(--danger-text); padding: 2px 7px; border-radius: 3px; font-size: 0.72em;">${facts.errors.length} error${facts.errors.length !== 1 ? 's' : ''}</span>`);
            }
            const headerTagsHtml = headerTags.length > 0 ? headerTags.join(' ') : '';

            // Build expanded content with structured summary
            let expandedContent = '';
            if (isExpanded) {
                const levelColors = { info: 'var(--info-text)', success: 'var(--success-text)', error: 'var(--danger-text)', warning: 'var(--warning-text)' };
                const levelIcons = { info: 'ℹ️', success: '✅', error: '❌', warning: '⚠️' };

                // Build summary section
                let summaryItems = [];
                if (facts.deploymentType) {
                    summaryItems.push(`<span style="color: var(--info-text);">Deployment Type:</span> ${escapeHtml(facts.deploymentType)}`);
                }
                if (facts.workspace) {
                    summaryItems.push(`<span style="color: var(--info-text);">Workspace:</span> ${escapeHtml(facts.workspace)}`);
                }
                if (facts.deployDuration) {
                    summaryItems.push(`<span style="color: var(--success-text);">Deploy Duration:</span> ${escapeHtml(facts.deployDuration)}`);
                }
                if (facts.resourcesCreated > 0) {
                    summaryItems.push(`<span style="color: var(--success-text);">Resources Created:</span> ${facts.resourcesCreated}`);
                }
                if (facts.s3Uploads.length > 0) {
                    summaryItems.push(`<span style="color: var(--success-text);">S3 Uploads:</span> ${facts.s3Uploads.map(u => escapeHtml(u)).join(', ')}`);
                }
                if (facts.resourcesDestroyed > 0) {
                    summaryItems.push(`<span style="color: var(--text-muted);">Resources Destroyed:</span> ${facts.resourcesDestroyed}`);
                }
                if (facts.resourcesRemaining > 0) {
                    summaryItems.push(`<span style="color: var(--warning-text);">Resources Remaining:</span> ${facts.resourcesRemaining}`);
                }
                if (facts.instancesStopped > 0) {
                    summaryItems.push(`<span style="color: var(--warning-text);">Instances Stopped:</span> ${facts.instancesStopped}${facts.stoppedNames.length ? ' (' + facts.stoppedNames.map(n => escapeHtml(n)).join(', ') + ')' : ''}`);
                }
                if (facts.instancesStarted > 0) {
                    summaryItems.push(`<span style="color: var(--success-text);">Instances Started:</span> ${facts.instancesStarted}${facts.startedNames.length ? ' (' + facts.startedNames.map(n => escapeHtml(n)).join(', ') + ')' : ''}`);
                }
                if (facts.errors.length > 0) {
                    summaryItems.push(`<span style="color: var(--danger-text);">Errors:</span> ${facts.errors.length}`);
                }

                const summaryHtml = summaryItems.length > 0 ? `
                    <div style="background: rgba(255,255,255,0.04); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;">
                        <div style="font-weight: 600; color: var(--text-secondary); font-size: 0.82em; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">Session Summary</div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px 20px;">
                            ${summaryItems.map(item => `<div style="font-size: 0.82em; color: var(--text-primary);">${item}</div>`).join('')}
                        </div>
                    </div>
                ` : '';

                // Destroyed resources list
                const destroyedListHtml = facts.destroyedResources.length > 0 ? `
                    <div style="background: rgba(255,255,255,0.04); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;">
                        <div style="font-weight: 600; color: var(--text-muted); font-size: 0.82em; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">Destroyed Resources (${facts.destroyedResources.length})</div>
                        <div style="font-family: monospace; font-size: 0.78em; color: var(--text-secondary); max-height: 120px; overflow-y: auto;">
                            ${facts.destroyedResources.map(r => `<div style="padding: 2px 0;">&#8226; ${escapeHtml(r)}</div>`).join('')}
                        </div>
                    </div>
                ` : '';

                // Error details
                const errorListHtml = facts.errors.length > 0 ? `
                    <div style="background: rgba(240,138,132,0.08); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;">
                        <div style="font-weight: 600; color: var(--danger-text); font-size: 0.82em; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">Errors (${facts.errors.length})</div>
                        <div style="font-size: 0.8em; color: var(--danger-text); max-height: 100px; overflow-y: auto;">
                            ${facts.errors.map(e => `<div style="padding: 3px 0; border-bottom: 1px solid rgba(240,138,132,0.1);">${escapeHtml(e)}</div>`).join('')}
                        </div>
                    </div>
                ` : '';

                // Raw log entries (collapsible)
                const rawLogsHtml = s.logs.map(log => {
                    const time = new Date(log.timestamp).toLocaleTimeString();
                    return `
                        <div style="padding: 6px 10px; margin-bottom: 4px; background: rgba(255,255,255,0.02); border-radius: 4px; border-left: 2px solid ${levelColors[log.level] || 'var(--text-muted)'};">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
                                <span style="color: ${levelColors[log.level] || 'var(--text-primary)'}; font-weight: 500; font-size: 0.78em;">
                                    ${levelIcons[log.level] || ''} ${log.level.toUpperCase()}
                                </span>
                                <span style="color: var(--text-muted); font-size: 0.75em;">${time}</span>
                            </div>
                            <div style="color: var(--text-primary); font-size: 0.8em;">${escapeHtml(log.message)}</div>
                            ${log.details ? `<div style="color: var(--text-muted); font-size: 0.72em; margin-top: 3px; font-family: monospace;">${escapeHtml(log.details)}</div>` : ''}
                        </div>
                    `;
                }).join('');

                expandedContent = `
                    <div style="background: var(--bg-terminal); border-radius: 0 0 8px 8px; padding: 16px; border-left: 5px solid ${statusColor}; max-height: 400px; overflow-y: auto;">
                        ${summaryHtml}
                        ${destroyedListHtml}
                        ${errorListHtml}
                        <div style="font-weight: 600; color: var(--text-secondary); font-size: 0.78em; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px;">Event Log (${s.logs.length})</div>
                        ${rawLogsHtml}
                    </div>
                `;
            }

            return `
                <div style="margin-bottom: 12px;">
                    <div onclick="toggleArchivedSession('${archSessionId}')" style="display: flex; align-items: center; gap: 12px; padding: 14px 18px; background: var(--bg-card); border-radius: ${isExpanded ? '8px 8px 0 0' : '8px'}; border-left: 5px solid ${statusColor}; cursor: pointer; transition: all 0.2s;" onmouseover="this.style.background='var(--bg-elevated)'" onmouseout="this.style.background='var(--bg-card)'">
                        <span style="font-size: 0.9em; transition: transform 0.2s; transform: rotate(${isExpanded ? '90deg' : '0deg'}); color: var(--text-secondary);">&#9654;</span>
                        <span style="font-size: 1.5em;">${statusIcon}</span>
                        <div style="flex: 1; min-width: 0;">
                            <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 4px;">
                                <span style="font-weight: 700; color: var(--text-primary); font-size: 1em;">${escapeHtml(projectName)}</span>
                                ${deploymentTypeBadge}
                                <span style="background: ${statusColor}15; color: ${statusColor}; padding: 2px 8px; border-radius: 4px; font-size: 0.72em; font-weight: 600; text-transform: uppercase;">${statusText}</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 10px; color: var(--text-secondary); font-size: 0.82em;">
                                <span>&#128197; ${formatDate(s.date)}</span>
                                <span>&#128336; ${timeRange}</span>
                                <span>&#9201; ${duration || 'N/A'}</span>
                                <span>&#128202; ${logCount} events</span>
                            </div>
                            ${headerTagsHtml ? `
                            <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 6px;">
                                ${headerTagsHtml}
                            </div>
                            ` : `
                            <div style="font-size: 0.82em; color: var(--text-muted); margin-top: 6px; font-style: italic;">
                                Last: ${escapeHtml(truncatedMessage)}
                            </div>
                            `}
                        </div>
                    </div>
                    ${expandedContent}
                </div>
            `;
        }).join('');

        return `
            <div style="background: var(--bg-container); border-radius: 12px; max-width: 900px; width: 100%; max-height: 80vh; overflow: hidden; display: flex; flex-direction: column;">
                <div style="padding: 20px; border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between; align-items: center;">
                    <h2 style="margin: 0; color: white;">Archived Logs <span style="color: var(--text-muted); font-size: 0.6em; font-weight: 400;">${sessionList.length} sessions &middot; ${archivedLogs.length} events</span></h2>
                    <button onclick="closeArchivedLogsModal()" style="background: none; border: none; color: white; font-size: 24px; cursor: pointer;">&times;</button>
                </div>

                <div id="archived-logs-content" style="flex: 1; overflow-y: auto; padding: 20px;">
                    ${sessionCards}
                </div>

                <div style="padding: 15px 20px; border-top: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between; align-items: center;">
                    <button onclick="clearArchivedLogs()" style="padding: 8px 16px; background: transparent; border: 1px solid var(--danger); border-radius: 6px; color: var(--danger); cursor: pointer; font-size: 0.9em;">
                        Clear Archive
                    </button>
                    <button onclick="downloadArchivedLogs()" style="padding: 8px 16px; background: var(--brand); border: none; border-radius: 6px; color: white; cursor: pointer; font-size: 0.9em;">
                        Download All
                    </button>
                </div>
            </div>
        `;
    }

    modal.innerHTML = renderArchivedContent();
    document.body.appendChild(modal);

    // Toggle expand/collapse for archived sessions
    window.toggleArchivedSession = (sessionId) => {
        if (expandedArchivedSessions.has(sessionId)) {
            expandedArchivedSessions.delete(sessionId);
        } else {
            expandedArchivedSessions.add(sessionId);
        }
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
    if (!text) return '';
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
            <div style="background: var(--bg-card); padding: 15px; border-radius: 5px;">
                <strong>Public IP:</strong><br>
                <code style="background: var(--bg-terminal); padding: 5px 10px; border-radius: 3px; display: inline-block; margin-top: 5px;">${bastion.public_ip || 'N/A'}</code>
            </div>
            <div style="background: var(--bg-card); padding: 15px; border-radius: 5px;">
                <strong>Private IP:</strong><br>
                <code style="background: var(--bg-terminal); padding: 5px 10px; border-radius: 3px; display: inline-block; margin-top: 5px;">${bastion.private_ip || 'N/A'}</code>
            </div>
        </div>
        ${bastion.rdp_connection ? `
        <div style="margin-top: 15px; background: var(--bg-card); padding: 15px; border-radius: 5px;">
            <strong>RDP Connection:</strong><br>
            <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 10px; border-radius: 3px; display: block; margin-top: 5px; overflow-x: auto;">${bastion.rdp_connection}</code>
        </div>
        ` : ''}
        ${bastion.wsl2_info ? `
        <div style="margin-top: 15px; background: var(--warning-bg); padding: 15px; border-radius: 5px; border-left: 4px solid var(--warning);">
            <strong>WSL2 Info:</strong><br>
            <p style="margin-top: 5px; color: var(--text-secondary);">${bastion.wsl2_info}</p>
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
                <div style="background: var(--bg-card); padding: 15px; border-radius: 5px; border-left: 4px solid var(--danger);">
                    <h4 style="margin: 0 0 10px 0; color: var(--danger-text);">${name}</h4>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px;">
                        <div>
                            <strong>Instance ID:</strong><br>
                            <code style="font-size: 0.88em;">${server.instance_id || 'N/A'}</code>
                        </div>
                        <div>
                            <strong>Private IP:</strong><br>
                            <code style="background: var(--bg-terminal); padding: 3px 8px; border-radius: 3px;">${server.private_ip || 'N/A'}</code>
                        </div>
                        ${server.phase ? `
                        <div>
                            <strong>Phase:</strong><br>
                            <span style="background: var(--danger-bg); padding: 3px 8px; border-radius: 3px;">${server.phase}</span>
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
                <div style="background: var(--bg-card); padding: 15px; border-radius: 5px; border-left: 4px solid var(--danger);">
                    <h4 style="margin: 0 0 10px 0; color: var(--danger-text);">C2 Server ${idx + 1}</h4>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px;">
                        <div>
                            <strong>Instance ID:</strong><br>
                            <code style="font-size: 0.88em;">${id}</code>
                        </div>
                        <div>
                            <strong>Private IP:</strong><br>
                            <code style="background: var(--bg-terminal); padding: 3px 8px; border-radius: 3px;">${privateIps[idx] || 'N/A'}</code>
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
            <div style="background: var(--bg-card); padding: 15px; border-radius: 5px; border-left: 4px solid var(--success);">
                <h4 style="margin: 0 0 10px 0; color: var(--success-text);">Redirector ${idx + 1}</h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px;">
                    <div>
                        <strong>Instance ID:</strong><br>
                        <code style="font-size: 0.88em;">${id}</code>
                    </div>
                    <div>
                        <strong>Public IP:</strong><br>
                        <code style="background: var(--success-bg); padding: 3px 8px; border-radius: 3px; color: var(--success-text);">${publicIps[idx] || 'N/A'}</code>
                    </div>
                    <div>
                        <strong>Private IP:</strong><br>
                        <code style="background: var(--bg-terminal); padding: 3px 8px; border-radius: 3px;">${privateIps[idx] || 'N/A'}</code>
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
        sslContent.innerHTML = '<p style="color: var(--text-secondary);">No redirectors deployed</p>';
        return;
    }
    
    // For now, show status based on config (actual status would require SSM or API call to redirector)
    try {
        const configResponse = await fetch(`${API_BASE}/config/`);
        const configData = await configResponse.json();
        
        if (!configData.success) {
            sslContent.innerHTML = '<p style="color: var(--text-secondary);">Unable to load SSL configuration</p>';
            return;
        }
        
        const config = configData.config || {};
        const sslProvider = config.ssl_provider || 'letsencrypt';
        const adminEmail = config.admin_email || '';
        const sslAutoRetry = config.ssl_auto_retry !== false;
        const enableSsl = config.enable_ssl_certificate !== false;
        
        if (!enableSsl) {
            sslContent.innerHTML = `
                <div style="display: flex; align-items: center; gap: 10px; padding: 10px; background: var(--warning-bg); border-radius: 6px;">
                    <span style="font-size: 1.5em;">⚠️</span>
                    <div>
                        <strong style="color: var(--warning-text);">SSL Disabled</strong>
                        <p style="margin: 5px 0 0 0; font-size: 0.9em; color: var(--text-secondary);">HTTPS is not configured on redirectors</p>
                    </div>
                </div>
            `;
            return;
        }
        
        let statusHtml = '';
        
        if (sslProvider === 'letsencrypt') {
            statusHtml = `
                <div style="display: grid; gap: 15px;">
                    <div style="display: flex; align-items: center; gap: 10px; padding: 12px; background: var(--info-bg); border-radius: 6px;">
                        <span style="font-size: 1.5em;">🔒</span>
                        <div>
                            <strong style="color: var(--info-text);">Let's Encrypt</strong>
                            <p style="margin: 5px 0 0 0; font-size: 0.9em; color: var(--text-secondary);">
                                Auto-renewal enabled • Notifications to: ${adminEmail || 'Not set'}
                            </p>
                        </div>
                    </div>
                    
                    <div style="font-size: 0.9em;">
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px;">
                            <div style="padding: 10px; background: var(--bg-container); border-radius: 4px;">
                                <strong>Auto-Retry:</strong> ${sslAutoRetry ? '✅ Enabled' : '❌ Disabled'}
                            </div>
                            <div style="padding: 10px; background: var(--bg-container); border-radius: 4px;">
                                <strong>Certificate Validity:</strong> 90 days
                            </div>
                        </div>
                    </div>
                    
                    <div style="padding: 12px; background: var(--warning-bg); border-radius: 6px; font-size: 0.88em;">
                        <strong>📋 Certificate Status Check:</strong>
                        <p style="margin: 8px 0 0 0; color: var(--text-secondary);">
                            SSH into a redirector and run: <code style="background: var(--bg-terminal); padding: 2px 6px; border-radius: 3px;">cat /opt/ssl-status.json</code>
                        </p>
                        <p style="margin: 5px 0 0 0; color: var(--text-secondary);">
                            Or check logs: <code style="background: var(--bg-terminal); padding: 2px 6px; border-radius: 3px;">tail -f /var/log/ssl-auto-request.log</code>
                        </p>
                    </div>
                </div>
            `;
        } else {
            statusHtml = `
                <div style="display: flex; align-items: center; gap: 10px; padding: 12px; background: var(--warning-bg); border-radius: 6px;">
                    <span style="font-size: 1.5em;">⚠️</span>
                    <div>
                        <strong style="color: var(--warning-text);">Self-Signed Certificate</strong>
                        <p style="margin: 5px 0 0 0; font-size: 0.9em; color: var(--text-secondary);">
                            Browsers will show security warnings. Consider switching to Let's Encrypt.
                        </p>
                    </div>
                </div>
            `;
        }
        
        sslContent.innerHTML = statusHtml;
        
    } catch (error) {
        console.error('Error loading SSL status:', error);
        sslContent.innerHTML = '<p style="color: var(--danger-text);">Error loading SSL status</p>';
    }
}

/**
 * Refresh SSL status
 */
async function refreshSSLStatus() {
    const sslContent = document.getElementById('ssl-status-content');
    if (sslContent) {
        sslContent.innerHTML = '<p style="color: var(--text-secondary); font-style: italic;">Refreshing...</p>';
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
            <div style="background: var(--bg-card); padding: 15px; border-radius: 5px;">
                <strong>VPC ID:</strong><br>
                <code style="font-size: 0.88em;">${network.vpc_id}</code>
            </div>
            <div style="background: var(--bg-card); padding: 15px; border-radius: 5px;">
                <strong>VPC CIDR:</strong><br>
                <code style="background: var(--bg-terminal); padding: 3px 8px; border-radius: 3px;">${network.vpc_cidr || 'N/A'}</code>
            </div>
        </div>
        
        <div style="margin-top: 15px; display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px;">
            <div style="background: var(--bg-card); padding: 15px; border-radius: 5px;">
                <strong>Public Subnets (${(network.public_subnets || []).length}):</strong>
                <ul style="margin: 10px 0 0 20px; padding: 0;">
                    ${(network.public_subnets || []).map(s => `<li><code style="font-size: 0.88em;">${s}</code></li>`).join('') || '<li>None</li>'}
                </ul>
            </div>
            <div style="background: var(--bg-card); padding: 15px; border-radius: 5px;">
                <strong>Private Subnets (${(network.private_subnets || []).length}):</strong>
                <ul style="margin: 10px 0 0 20px; padding: 0;">
                    ${(network.private_subnets || []).map(s => `<li><code style="font-size: 0.88em;">${s}</code></li>`).join('') || '<li>None</li>'}
                </ul>
            </div>
        </div>
        
        ${securityGroups ? `
        <div style="margin-top: 15px; background: var(--bg-card); padding: 15px; border-radius: 5px;">
            <strong>Security Groups:</strong>
            <div style="margin-top: 10px; display: grid; gap: 5px;">
                ${securityGroups.c2_server_sg ? `<div>C2 Server SG: <code style="font-size: 0.88em;">${securityGroups.c2_server_sg}</code></div>` : ''}
                ${securityGroups.redirector_sg ? `<div>Redirector SG: <code style="font-size: 0.88em;">${securityGroups.redirector_sg}</code></div>` : ''}
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
                <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 10px 15px; border-radius: 5px; display: block; overflow-x: auto;">
                    mstsc /v:${data.bastion.public_ip}
                </code>
                <p style="color: var(--text-secondary); font-size: 0.88em; margin-top: 8px;">
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
                <p style="color: var(--text-secondary); font-size: 0.9em; margin-bottom: 10px;">
                    Connect through the Windows Bastion's WSL2 environment.
                </p>
                ${c2Ips.map((ip, idx) => `
                    <div style="margin-bottom: 10px;">
                        <span style="color: var(--text-secondary);">C2 Server ${idx + 1}:</span>
                        <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 10px 15px; border-radius: 5px; display: block; margin-top: 5px; overflow-x: auto;">
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
                <p style="color: var(--text-secondary); font-size: 0.9em; margin-bottom: 10px;">
                    Direct SSH access. Redirectors run Ubuntu.
                </p>
                ${redirectorIps.map((ip, idx) => `
                    <div style="margin-bottom: 10px;">
                        <span style="color: var(--text-secondary);">Redirector ${idx + 1}:</span>
                        <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 10px 15px; border-radius: 5px; display: block; margin-top: 5px; overflow-x: auto;">
                            ssh -i ~/.ssh/${keyPairName}.pem ubuntu@${ip}
                        </code>
                    </div>
                `).join('')}
                
                <details style="margin-top: 15px;">
                    <summary style="cursor: pointer; color: var(--info-text); font-weight: 500;">
                        📋 Common Redirector Commands
                    </summary>
                    <div style="margin-top: 10px; padding: 15px; background: var(--bg-container); border-radius: 5px; font-size: 0.9em;">
                        <p style="margin: 0 0 10px 0;"><strong>Check SSL Status:</strong></p>
                        <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 8px 12px; border-radius: 4px; display: block;">cat /opt/ssl-status.json</code>
                        
                        <p style="margin: 15px 0 10px 0;"><strong>View Nginx Config:</strong></p>
                        <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 8px 12px; border-radius: 4px; display: block;">sudo cat /etc/nginx/sites-enabled/default</code>
                        
                        <p style="margin: 15px 0 10px 0;"><strong>Edit Nginx (for URI changes):</strong></p>
                        <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 8px 12px; border-radius: 4px; display: block;">sudo nano /etc/nginx/sites-enabled/default</code>
                        
                        <p style="margin: 15px 0 10px 0;"><strong>Reload Nginx After Changes:</strong></p>
                        <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 8px 12px; border-radius: 4px; display: block;">sudo nginx -t && sudo systemctl reload nginx</code>
                        
                        <p style="margin: 15px 0 10px 0;"><strong>View Access Logs:</strong></p>
                        <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 8px 12px; border-radius: 4px; display: block;">sudo tail -f /var/log/nginx/access.log</code>
                        
                        <p style="margin: 15px 0 10px 0;"><strong>Manual Let's Encrypt Request:</strong></p>
                        <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 8px 12px; border-radius: 4px; display: block;">sudo certbot --nginx -d yourdomain.com</code>
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
                            <summary style="cursor: pointer; color: var(--danger-text); font-weight: 500;">
                                🔑 GOAD Default Credentials
                            </summary>
                            <div style="margin-top: 10px; padding: 15px; background: var(--danger-bg); border-radius: 5px; font-size: 0.9em;">
                                <p style="margin: 0 0 15px 0; color: var(--danger-text);">
                                    <strong>⚠️ Intentionally Vulnerable:</strong> These are default GOAD credentials for the <strong>${creds.lab_display_name || creds.lab_name}</strong> lab.
                                </p>
                                
                                <div style="background: var(--bg-card); padding: 12px; border-radius: 5px; margin-bottom: 10px;">
                                    <p style="margin: 0 0 8px 0;"><strong>Default Password (All Users):</strong></p>
                                    <code style="background: var(--bg-terminal); color: var(--danger-text); padding: 8px 15px; border-radius: 4px; display: inline-block; font-size: 1.1em;">
                                        ${creds.default_password || 'vagrant'}
                                    </code>
                                </div>
                                
                                ${creds.domains && creds.domains.length > 0 ? `
                                    <p style="margin: 15px 0 10px 0;"><strong>Domains in this Lab:</strong></p>
                                    <table style="width: 100%; border-collapse: collapse; font-size: 0.9em; margin-bottom: 15px;">
                                        <thead>
                                            <tr style="background: var(--info-bg);">
                                                <th style="padding: 8px; text-align: left; border: 1px solid var(--border);">Domain</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid var(--border);">FQDN</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid var(--border);">DC</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            ${creds.domains.map(d => `
                                                <tr>
                                                    <td style="padding: 8px; border: 1px solid var(--border);"><strong>${d.name}</strong></td>
                                                    <td style="padding: 8px; border: 1px solid var(--border);"><code>${d.fqdn}</code></td>
                                                    <td style="padding: 8px; border: 1px solid var(--border);">${d.dc}</td>
                                                </tr>
                                            `).join('')}
                                        </tbody>
                                    </table>
                                ` : ''}
                                
                                ${creds.domain_admins && creds.domain_admins.length > 0 ? `
                                    <p style="margin: 15px 0 10px 0;"><strong>Domain Administrators:</strong></p>
                                    <table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                                        <thead>
                                            <tr style="background: var(--bg-container);">
                                                <th style="padding: 8px; text-align: left; border: 1px solid var(--border);">Domain</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid var(--border);">Username</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid var(--border);">Password</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            ${creds.domain_admins.map(admin => `
                                                <tr>
                                                    <td style="padding: 8px; border: 1px solid var(--border);">${admin.domain}</td>
                                                    <td style="padding: 8px; border: 1px solid var(--border);"><code>${admin.username}</code></td>
                                                    <td style="padding: 8px; border: 1px solid var(--border);"><code style="color: var(--danger-text);">${admin.password}</code></td>
                                                </tr>
                                            `).join('')}
                                        </tbody>
                                    </table>
                                ` : ''}
                                
                                ${creds.key_users && creds.key_users.length > 0 ? `
                                    <p style="margin: 15px 0 10px 0;"><strong>Key Domain Users:</strong></p>
                                    <table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                                        <thead>
                                            <tr style="background: var(--warning-bg);">
                                                <th style="padding: 8px; text-align: left; border: 1px solid var(--border);">Domain</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid var(--border);">Username</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid var(--border);">Password</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid var(--border);">Role</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            ${creds.key_users.map(user => `
                                                <tr>
                                                    <td style="padding: 8px; border: 1px solid var(--border);">${user.domain}</td>
                                                    <td style="padding: 8px; border: 1px solid var(--border);"><code>${user.username}</code></td>
                                                    <td style="padding: 8px; border: 1px solid var(--border);"><code style="color: var(--danger-text);">${user.password}</code></td>
                                                    <td style="padding: 8px; border: 1px solid var(--border); font-size: 0.88em;">${user.role}</td>
                                                </tr>
                                            `).join('')}
                                        </tbody>
                                    </table>
                                ` : ''}
                                
                                ${creds.trusts && creds.trusts.length > 0 ? `
                                    <p style="margin: 15px 0 10px 0;"><strong>Domain Trusts:</strong></p>
                                    <table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                                        <thead>
                                            <tr style="background: var(--bg-section);">
                                                <th style="padding: 8px; text-align: left; border: 1px solid var(--border);">From</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid var(--border);">To</th>
                                                <th style="padding: 8px; text-align: left; border: 1px solid var(--border);">Type</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            ${creds.trusts.map(trust => `
                                                <tr>
                                                    <td style="padding: 8px; border: 1px solid var(--border);">${trust.from}</td>
                                                    <td style="padding: 8px; border: 1px solid var(--border);">${trust.to}</td>
                                                    <td style="padding: 8px; border: 1px solid var(--border);">${trust.type}</td>
                                                </tr>
                                            `).join('')}
                                        </tbody>
                                    </table>
                                ` : ''}
                                
                                ${creds.special_accounts && creds.special_accounts.length > 0 ? `
                                    <p style="margin: 15px 0 10px 0;"><strong>Special Accounts (Lab-Specific):</strong></p>
                                    <div style="background: var(--warning-bg); padding: 10px; border-radius: 5px;">
                                        ${creds.special_accounts.map(acc => `
                                            <p style="margin: 5px 0;"><strong>${acc.name}:</strong> ${acc.note}</p>
                                        `).join('')}
                                    </div>
                                ` : ''}
                                
                                <p style="margin: 15px 0 10px 0;"><strong>Local Accounts (All VMs):</strong></p>
                                <table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                                    <thead>
                                        <tr style="background: var(--bg-container);">
                                            <th style="padding: 8px; text-align: left; border: 1px solid var(--border);">Account</th>
                                            <th style="padding: 8px; text-align: left; border: 1px solid var(--border);">Username</th>
                                            <th style="padding: 8px; text-align: left; border: 1px solid var(--border);">Password</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        <tr>
                                            <td style="padding: 8px; border: 1px solid var(--border);">Local Admin</td>
                                            <td style="padding: 8px; border: 1px solid var(--border);"><code>Administrator</code></td>
                                            <td style="padding: 8px; border: 1px solid var(--border);"><code style="color: var(--danger-text);">vagrant</code></td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 8px; border: 1px solid var(--border);">Vagrant User</td>
                                            <td style="padding: 8px; border: 1px solid var(--border);"><code>vagrant</code></td>
                                            <td style="padding: 8px; border: 1px solid var(--border);"><code style="color: var(--danger-text);">vagrant</code></td>
                                        </tr>
                                    </tbody>
                                </table>
                                
                                <p style="margin: 15px 0 0 0; font-size: 0.88em; color: var(--text-secondary);">
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
                    <p style="color: var(--text-secondary); font-size: 0.9em; margin-bottom: 10px;">
                        Access the GOAD lab management server. Lab: <strong>${jb.lab_name || 'GOAD'}</strong>
                    </p>
                    
                    ${jb.public_ip ? `
                        <div style="margin-bottom: 10px;">
                            <span style="color: var(--text-secondary);">SSH Access (use your own private key):</span>
                            <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 10px 15px; border-radius: 5px; display: block; margin-top: 5px; overflow-x: auto;">
                                ${jb.commands?.ssh || `ssh -i ~/.ssh/your_key ubuntu@${jb.public_ip}`}
                            </code>
                        </div>
                        
                        <div style="margin-bottom: 10px;">
                            <span style="color: var(--text-secondary);">SOCKS Proxy (for accessing AD network):</span>
                            <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 10px 15px; border-radius: 5px; display: block; margin-top: 5px; overflow-x: auto;">
                                ${jb.commands?.socks_proxy || `ssh -D 1080 -i ~/.ssh/your_key ubuntu@${jb.public_ip}`}
                            </code>
                        </div>
                        
                        <div style="margin-top: 8px; padding: 8px; background: var(--success-bg); border-radius: 4px; font-size: 0.88em; color: var(--success-text);">
                            💡 Replace <code>your_key</code> with your private key path (e.g., <code>~/.ssh/id_ed25519</code>)
                        </div>
                    ` : `
                        <p style="color: var(--warning-text);">⚠️ Jumpbox IP not available yet. The lab may still be deploying.</p>
                    `}
                    
                    ${credsHtml}
                    
                    <details style="margin-top: 15px;">
                        <summary style="cursor: pointer; color: var(--info-text); font-weight: 500;">
                            📋 Common GOAD Commands
                        </summary>
                        <div style="margin-top: 10px; padding: 15px; background: var(--bg-container); border-radius: 5px; font-size: 0.9em;">
                            <p style="margin: 0 0 10px 0;"><strong>Check Lab Status:</strong></p>
                            <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 8px 12px; border-radius: 4px; display: block;">cd /opt/goad && ./goad.sh -t check -l GOAD -p aws</code>
                            
                            <p style="margin: 15px 0 10px 0;"><strong>Run Ansible Provisioning:</strong></p>
                            <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 8px 12px; border-radius: 4px; display: block;">cd /opt/goad && ./goad.sh -t install -l GOAD -p aws</code>
                            
                            <p style="margin: 15px 0 10px 0;"><strong>View Ansible Inventory:</strong></p>
                            <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 8px 12px; border-radius: 4px; display: block;">cat /opt/goad/ad/GOAD/providers/aws/inventory</code>
                            
                            <p style="margin: 15px 0 10px 0;"><strong>Test WinRM to DC:</strong></p>
                            <code style="background: var(--bg-terminal); color: var(--accent-muted); padding: 8px 12px; border-radius: 4px; display: block;">evil-winrm -i DC_IP -u Administrator -p 'vagrant'</code>
                        </div>
                    </details>
                </div>
            `;
        }
    } catch (e) {
        console.log('No GOAD jumpbox info available');
    }
    
    if (!html) {
        html = '<p style="color: var(--text-muted);">No connection information available.</p>';
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
            <div style="display: flex; align-items: center; gap: 15px; padding: 15px; background: var(--success-bg); border-radius: 8px;">
                <span style="font-size: 2em;">🎯</span>
                <div>
                    <strong>Direct Connection</strong>
                    <p style="margin: 5px 0 0 0; color: var(--success-text);">
                        Connect CS client directly to <code>${data.cobalt_strike.host || 'jumpbox_ip'}:${data.cobalt_strike.port}</code>
                    </p>
                </div>
            </div>
        `;
    } else if (arch === 'combined') {
        html = `
            <div style="display: flex; align-items: center; gap: 15px; padding: 15px; background: var(--warning-bg); border-radius: 8px;">
                <span style="font-size: 2em;">🔗</span>
                <div>
                    <strong>SSH Tunnel Required</strong>
                    <p style="margin: 5px 0 0 0; color: var(--warning-text);">
                        RDP to bastion, then SSH tunnel to C2 server. GOAD accessible via VPC peering.
                    </p>
                </div>
            </div>
        `;
    } else {
        html = `
            <div style="display: flex; align-items: center; gap: 15px; padding: 15px; background: var(--info-bg); border-radius: 8px;">
                <span style="font-size: 2em;">🔒</span>
                <div>
                    <strong>SSH Tunnel Required</strong>
                    <p style="margin: 5px 0 0 0; color: var(--info-text);">
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
                    <td colspan="4" style="text-align: center; color: var(--text-secondary);">
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
        element.style.background = 'var(--success-bg)';
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
