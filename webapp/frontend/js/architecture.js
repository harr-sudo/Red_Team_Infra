// Architecture Documentation - Embedded tab in main SPA
// Uses marked.js for markdown rendering

// Architecture content definitions with file paths
const architectures = {
    // C2 Infrastructure
    'c2-adhoc': {
        diagram: '/api/architecture/diagram/c2-adhoc-architecture.png',
        markdownFile: 'c2-adhoc.md',
        title: 'C2 Ad-Hoc - Single Team Server'
    },
    'c2-adhoc-domain-fronting': {
        diagram: '/api/architecture/diagram/c2-adhoc-domain-fronting.png',
        markdownFile: 'c2-adhoc.md',
        title: 'C2 Ad-Hoc - Domain Fronting Mode'
    },
    'ssl-options': {
        diagram: '/api/architecture/diagram/ssl-options-comparison.png',
        markdownFile: 'c2-adhoc.md',
        title: 'SSL/TLS Options Comparison'
    },
    'c2-purple': {
        diagram: '/api/architecture/diagram/c2-purple-architecture.png',
        markdownFile: 'c2-adhoc.md',
        title: 'C2 Purple Team - Redundant Servers'
    },
    'c2-full': {
        diagram: '/api/architecture/diagram/c2-full-architecture.png',
        markdownFile: 'c2-adhoc.md',
        title: 'C2 Full Red Team - Phase-Based'
    },

    // GOAD Training Labs
    'goad-mini': {
        diagram: '/api/architecture/diagram/goad-mini-architecture.png',
        markdownFile: 'goad-mini.md',
        title: 'GOAD Mini - 1 DC, 1 Domain'
    },
    'goad-light': {
        diagram: '/api/architecture/diagram/goad-light-architecture.png',
        markdownFile: 'goad-light.md',
        title: 'GOAD Light - 3 VMs, 2 Domains'
    },
    'goad-full': {
        diagram: '/api/architecture/diagram/goad-full-architecture.png',
        markdownFile: 'goad-light.md',
        title: 'GOAD Full - 5 VMs, 3 Domains, 2 Forests'
    },
    'goad-sccm': {
        diagram: '/api/architecture/diagram/goad-sccm-architecture.png',
        markdownFile: 'goad-light.md',
        title: 'GOAD SCCM - 4 VMs, SCCM Lab'
    },
    'goad-nha': {
        diagram: '/api/architecture/diagram/goad-nha-architecture.png',
        markdownFile: 'goad-light.md',
        title: 'GOAD NHA - 5 VMs, Challenge Lab'
    },

    // Combined Deployments
    'combined-mini': {
        diagram: '/api/architecture/diagram/combined-c2-goad-mini.png',
        markdownFile: 'goad-mini.md',
        title: 'Combined: C2 Ad-Hoc + GOAD Mini'
    },
    'combined-light': {
        diagram: '/api/architecture/diagram/combined-full-c2-goad-light.png',
        markdownFile: 'goad-light.md',
        title: 'Combined: C2 Ad-Hoc + GOAD Light'
    },
    'combined-full': {
        diagram: '/api/architecture/diagram/combined-full-c2-goad-full.png',
        markdownFile: 'goad-light.md',
        title: 'Combined: Full C2 + GOAD Full'
    },

    // Component Architecture
    'attack-box': {
        diagram: '/api/architecture/diagram/attackbox-architecture.png',
        markdownFile: 'attackbox.md',
        title: 'Windows Attack Box - Standalone Module'
    },
    's3-storage': {
        diagram: '/api/architecture/diagram/s3-storage-security-architecture.png',
        markdownFile: 's3-storage.md',
        title: 'S3 Deployment Storage - Security Architecture'
    },
    'iam-security': {
        diagram: '/api/architecture/diagram/iam-security-architecture.png',
        markdownFile: 'iam-security.md',
        title: 'IAM Security - Roles & Permissions'
    },
    'ssh-key-management': {
        diagram: '/api/architecture/diagram/ssh-key-architecture.png',
        markdownFile: 'ssh-key-management.md',
        title: 'SSH Key Management - Automation'
    }
};

let architectureInitialized = false;

// Load markdown from Flask API
async function loadMarkdownFile(filename) {
    try {
        const response = await fetch(`/api/architecture/docs/${filename}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        if (data.status === 'success') {
            return data.content;
        } else {
            throw new Error(data.error || 'Unknown error loading documentation');
        }
    } catch (error) {
        console.error('Error loading markdown file:', error);
        return `# Error Loading Documentation\n\nUnable to load: ${filename}\n\nError: ${error.message}\n\nTry refreshing the page or selecting a different architecture.`;
    }
}

// Render architecture content
async function renderArchitecture(selectedArch) {
    const contentDiv = document.getElementById('markdown-content');
    const arch = architectures[selectedArch];

    if (!arch) {
        contentDiv.innerHTML = '<p style="color: var(--danger-text);">Architecture not found</p>';
        return;
    }

    // Show loading state
    contentDiv.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 40px 0;">Loading architecture documentation...</p>';

    let html = '';

    // Add diagram section — uses CSS classes for theme support
    if (arch.diagram) {
        html += `
            <div class="arch-diagram-wrapper">
                <div class="arch-diagram-frame">
                    <img src="${arch.diagram}"
                         alt="${arch.title || selectedArch} architecture diagram"
                         class="arch-diagram-img"
                         onclick="window.open(this.src, '_blank')"
                         title="Click to open in new tab"
                         onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%27800%27 height=%27400%27%3E%3Crect fill=%27%23f0f0f0%27 width=%27800%27 height=%27400%27/%3E%3Ctext x=%2750%25%27 y=%2750%25%27 font-size=%2720%27 text-anchor=%27middle%27 dy=%27.3em%27 fill=%27%23999%27%3EDiagram not available%3C/text%3E%3C/svg%3E'">
                </div>
                <div class="arch-diagram-caption">
                    <span style="cursor: pointer; font-weight: 500;" onclick="window.open('${arch.diagram}', '_blank')">
                        View Full Size
                    </span>
                </div>
            </div>
        `;
    }

    // Load and render markdown content
    try {
        let markdownContent;
        if (arch.markdownFile) {
            markdownContent = await loadMarkdownFile(arch.markdownFile);
        } else {
            markdownContent = `# ${arch.title || selectedArch}\n\nDocumentation coming soon...`;
        }

        html += marked.parse(markdownContent);
        contentDiv.innerHTML = html;
    } catch (error) {
        console.error('Error rendering architecture:', error);
        contentDiv.innerHTML = html + `
            <div class="callout callout--warning">
                <strong>Error Loading Documentation</strong>
                <p>Unable to load the documentation content. ${error.message}</p>
            </div>
        `;
    }
}

// Called by APP.loadPageContent when architecture tab is activated
function initArchitecturePage() {
    // Configure marked on first use
    if (typeof marked !== 'undefined' && !architectureInitialized) {
        marked.setOptions({
            breaks: true,
            gfm: true,
            headerIds: true,
            mangle: false,
            tables: true,
            sanitize: false
        });
    }

    const select = document.getElementById('architecture-select');
    if (!select) return;

    // Attach change listener once
    if (!architectureInitialized) {
        select.addEventListener('change', function(e) {
            renderArchitecture(e.target.value).catch(error => {
                console.error('Failed to render architecture:', error);
            });
        });
        architectureInitialized = true;
    }

    // Load default on first visit, or reload current selection
    const current = select.value;
    if (current) {
        renderArchitecture(current).catch(error => {
            console.error('Failed to load architecture:', error);
        });
    }
}
