// Architecture Documentation - Dynamically loads markdown files
// Uses marked.js for rendering

// Configure marked options
marked.setOptions({
    breaks: true,
    gfm: true,
    headerIds: true,
    mangle: false,
    tables: true,
    sanitize: false
});

// Architecture content definitions with file paths
const architectures = {
    // C2 Infrastructure
    'c2-adhoc': {
        diagram: '/api/architecture/diagram/c2-adhoc-architecture.png',
        markdownFile: 'c2-adhoc.md',
        title: 'C2 Ad-Hoc - Single Team Server'
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
    
    // GOAD Training Labs - Each with specific diagram
    'goad-mini': {
        diagram: '/api/architecture/diagram/goad-mini-correct.png',
        markdownFile: 'goad-mini.md',
        title: 'GOAD Mini - 1 VM, 1 Domain'
    },
    'goad-minilab': {
        diagram: '/api/architecture/diagram/goad-minilab-correct.png',
        markdownFile: 'goad-mini.md',
        title: 'GOAD MiniLab - 2 VMs, 1 Domain'
    },
    'goad-light': {
        diagram: '/api/architecture/diagram/goad-light-correct.png',
        markdownFile: 'goad-light.md',
        title: 'GOAD Light - 3 VMs, 2 Domains'
    },
    'goad-full': {
        diagram: '/api/architecture/diagram/goad-full-correct.png',
        markdownFile: 'goad-light.md',
        title: 'GOAD Full - 5 VMs, 3 Domains, 2 Forests'
    },
    'goad-sccm': {
        diagram: '/api/architecture/diagram/goad-sccm-correct.png',
        markdownFile: 'goad-light.md',
        title: 'GOAD SCCM - 4 VMs, SCCM Lab'
    },
    'goad-nha': {
        diagram: '/api/architecture/diagram/goad-nha-correct.png',
        markdownFile: 'goad-light.md',
        title: 'GOAD NHA - 5 VMs, Challenge Lab'
    },
    
    // Combined Deployments - Specific combined diagrams
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
        markdownFile: 'goad-mini.md',
        title: 'Windows Attack Box - Detailed Architecture'
    },
    'iam-security': {
        diagram: '/api/architecture/diagram/iam-security-architecture.png',
        markdownFile: 'README.md',
        title: 'IAM Security - Roles & Permissions'
    },
    'ssh-key-management': {
        diagram: '/api/architecture/diagram/ssh-key-architecture.png',
        markdownFile: 'README.md',
        title: 'SSH Key Management - Automation'
    }
};

// Function to load markdown from Flask API
async function loadMarkdownFile(filename) {
    try {
        console.log(`Loading markdown file: ${filename}`);
        const response = await fetch(`/api/architecture/docs/${filename}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Response data:', data);
        
        if (data.status === 'success') {
            return data.content;
        } else {
            throw new Error(data.error || 'Unknown error loading documentation');
        }
    } catch (error) {
        console.error('Error loading markdown file:', error);
        return `# Error Loading Documentation

Unable to load documentation file: ${filename}

Error: ${error.message}

## Troubleshooting

The documentation could not be loaded. This might be because:
- The file doesn't exist yet
- The web server needs to be restarted
- There's a network connectivity issue

## Quick Fix

Try refreshing the page or check the browser console (F12) for more details.

## Available Architectures

You can try selecting a different architecture type from the dropdown menu above.
`;
    }
}

// Function to render architecture
async function renderArchitecture(selectedArch) {
    const contentDiv = document.getElementById('markdown-content');
    const arch = architectures[selectedArch];
    
    if (!arch) {
        contentDiv.innerHTML = '<p style="color: #f44336;">Architecture not found</p>';
        return;
    }
    
    console.log(`Rendering architecture: ${selectedArch}`);
    
    // Show loading state
    contentDiv.innerHTML = '<div class="loading">Loading architecture documentation</div>';
    
    let html = '';
    
    // Add diagram if available
    if (arch.diagram) {
        html += `
            <div style="
                background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                padding: 30px;
                border-radius: 12px;
                margin-bottom: 30px;
                box-shadow: 0 8px 16px rgba(0,0,0,0.1);
            ">
                <h2 style="margin-top: 0; color: #1e3c72; display: flex; align-items: center; gap: 10px;">
                    <span>📐</span>
                    <span>AWS Architecture Diagram</span>
                </h2>
                <div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
                    <img src="${arch.diagram}" 
                         alt="${arch.title || selectedArch} architecture diagram"
                         style="
                            max-width: 100%; 
                            height: auto;
                            border-radius: 8px;
                            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                            cursor: pointer;
                            transition: transform 0.3s;
                         "
                         onmouseover="this.style.transform='scale(1.02)'"
                         onmouseout="this.style.transform='scale(1)'"
                         onclick="window.open(this.src, '_blank')"
                         title="Click to open in new tab"
                         onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%27800%27 height=%27400%27%3E%3Crect fill=%27%23f0f0f0%27 width=%27800%27 height=%27400%27/%3E%3Ctext x=%2750%25%27 y=%2750%25%27 font-size=%2720%27 text-anchor=%27middle%27 dy=%27.3em%27 fill=%27%23999%27%3EDiagram not available%3C/text%3E%3C/svg%3E'">
                </div>
                <div style="
                    margin-top: 15px; 
                    text-align: center; 
                    color: #666; 
                    font-size: 0.9em;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    gap: 15px;
                    flex-wrap: wrap;
                ">
                    <span>✨ Generated using AWS MCP Diagram Server</span>
                    <span>|</span>
                    <span>📚 Following <a href="https://aws.amazon.com/blogs/machine-learning/build-aws-architecture-diagrams-using-amazon-q-cli-and-mcp/" target="_blank" style="color: #2a5298;">AWS Best Practices</a></span>
                    <span>|</span>
                    <span style="cursor: pointer; color: #2a5298; font-weight: 500;" onclick="window.open('${arch.diagram}', '_blank')">
                        🔍 View Full Size
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
        
        console.log('Architecture rendered successfully');
    } catch (error) {
        console.error('Error rendering architecture:', error);
        contentDiv.innerHTML = html + `
            <div style="background: #fff3e0; border-left: 4px solid #ff9800; padding: 15px; margin: 20px 0; border-radius: 4px;">
                <h3 style="margin-top: 0; color: #f57c00;">⚠️ Error Loading Documentation</h3>
                <p>Unable to load the documentation content. Please try refreshing the page.</p>
                <p style="color: #666; font-size: 0.9em;">Error: ${error.message}</p>
                <p style="margin-top: 15px;">
                    <button onclick="location.reload()" style="
                        background: #2a5298;
                        color: white;
                        border: none;
                        padding: 10px 20px;
                        border-radius: 4px;
                        cursor: pointer;
                        font-size: 1em;
                    ">
                        🔄 Refresh Page
                    </button>
                </p>
            </div>
        `;
    }
}

// Handle dropdown change
document.getElementById('architecture-select').addEventListener('change', function(e) {
    console.log('Architecture selection changed to:', e.target.value);
    renderArchitecture(e.target.value).catch(error => {
        console.error('Failed to render architecture:', error);
    });
});

// Load default architecture on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, rendering default architecture');
    renderArchitecture('goad-mini').catch(error => {
        console.error('Failed to load default architecture:', error);
    });
});
