/**
 * Enhanced Log Viewer JavaScript
 * Advanced functionality for the super admin logging system
 */

class EnhancedLogViewer {
    constructor() {
        this.groupingEnabled = false;
        this.timestampsVisible = true;
        this.metadataVisible = true;
        this.autoRefresh = false;
        this.refreshInterval = null;
        this.currentFilters = {};
        
        this.init();
    }
    
    init() {
        // Initialize event listeners
        this.setupEventListeners();
        
        // Load saved preferences
        this.loadPreferences();
        
        // Setup keyboard shortcuts
        this.setupKeyboardShortcuts();
    }
    
    setupEventListeners() {
        // Filter change events
        document.addEventListener('change', (e) => {
            if (e.target.matches('#log-level-filter, #log-category-filter, #log-severity-filter, #log-search, #log-time-filter')) {
                this.debounce(() => this.applyLogFilters(), 300)();
            }
        });
        
        // Auto-refresh toggle
        const autoRefreshBtn = document.getElementById('auto-refresh-btn');
        if (autoRefreshBtn) {
            autoRefreshBtn.addEventListener('click', () => this.toggleAutoRefresh());
        }
        
        // Export functionality
        const exportBtn = document.getElementById('export-logs-btn');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => this.exportLogs());
        }
    }
    
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + R: Refresh logs
            if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
                e.preventDefault();
                this.refreshLogs();
            }
            
            // Ctrl/Cmd + F: Focus search
            if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
                e.preventDefault();
                document.getElementById('log-search')?.focus();
            }
            
            // Escape: Clear filters
            if (e.key === 'Escape') {
                this.clearLogFilters();
            }
        });
    }
    
    toggleGrouping() {
        this.groupingEnabled = !this.groupingEnabled;
        const viewer = document.getElementById('log-viewer');
        const btn = document.getElementById('grouping-btn');
        
        if (this.groupingEnabled) {
            viewer?.classList.add('show-grouping');
            btn?.classList.add('active');
            if (btn) btn.innerHTML = '<i class="fas fa-layer-group me-1"></i>Ungroup';
        } else {
            viewer?.classList.remove('show-grouping');
            btn?.classList.remove('active');
            if (btn) btn.innerHTML = '<i class="fas fa-layer-group me-1"></i>Group by Category';
        }
        
        this.savePreferences();
    }
    
    toggleTimestamps() {
        this.timestampsVisible = !this.timestampsVisible;
        const viewer = document.getElementById('log-viewer');
        const btn = document.getElementById('timestamps-btn');
        
        if (this.timestampsVisible) {
            viewer?.classList.remove('hide-timestamps');
            btn?.classList.remove('active');
            if (btn) btn.innerHTML = '<i class="fas fa-clock me-1"></i>Hide Timestamps';
        } else {
            viewer?.classList.add('hide-timestamps');
            btn?.classList.add('active');
            if (btn) btn.innerHTML = '<i class="fas fa-clock me-1"></i>Show Timestamps';
        }
        
        this.savePreferences();
    }
    
    toggleMetadata() {
        this.metadataVisible = !this.metadataVisible;
        const viewer = document.getElementById('log-viewer');
        const btn = document.getElementById('metadata-btn');
        
        if (this.metadataVisible) {
            viewer?.classList.remove('hide-metadata');
            btn?.classList.remove('active');
            if (btn) btn.innerHTML = '<i class="fas fa-tags me-1"></i>Hide Metadata';
        } else {
            viewer?.classList.add('hide-metadata');
            btn?.classList.add('active');
            if (btn) btn.innerHTML = '<i class="fas fa-tags me-1"></i>Show Metadata';
        }
        
        this.savePreferences();
    }
    
    toggleAutoRefresh() {
        this.autoRefresh = !this.autoRefresh;
        const btn = document.getElementById('auto-refresh-btn');
        
        if (this.autoRefresh) {
            this.refreshInterval = setInterval(() => this.refreshLogs(), 30000); // 30 seconds
            btn?.classList.add('active');
            if (btn) btn.innerHTML = '<i class="fas fa-pause me-1"></i>Stop Auto-Refresh';
            this.showToast('Auto-refresh enabled (30s intervals)', 'success');
        } else {
            if (this.refreshInterval) {
                clearInterval(this.refreshInterval);
                this.refreshInterval = null;
            }
            btn?.classList.remove('active');
            if (btn) btn.innerHTML = '<i class="fas fa-sync me-1"></i>Auto-Refresh';
            this.showToast('Auto-refresh disabled', 'info');
        }
        
        this.savePreferences();
    }
    
    quickFilter(type) {
        // Clear existing filters first
        this.clearLogFilters();
        
        switch(type) {
            case 'errors':
                this.setFilter('log-level-filter', 'ERROR');
                break;
            case 'warnings':
                this.setFilter('log-level-filter', 'WARNING');
                break;
            case 'polls':
                this.setFilter('log-category-filter', 'poll_operations');
                break;
            case 'performance':
                this.setFilter('log-search', 'response_time');
                break;
            case 'recent':
                this.setFilter('log-time-filter', '1h');
                break;
            case 'high-severity':
                this.setFilter('log-severity-filter', 'high');
                break;
            case 'critical':
                this.setFilter('log-level-filter', 'CRITICAL');
                break;
            case 'api':
                this.setFilter('log-category-filter', 'api_operations');
                break;
            case 'discord':
                this.setFilter('log-category-filter', 'discord_operations');
                break;
        }
        
        this.applyLogFilters();
    }
    
    setFilter(filterId, value) {
        const element = document.getElementById(filterId);
        if (element) {
            element.value = value;
        }
    }
    
    clearLogFilters() {
        const filters = ['log-level-filter', 'log-category-filter', 'log-severity-filter', 'log-search'];
        filters.forEach(filterId => {
            const element = document.getElementById(filterId);
            if (element) {
                element.value = '';
            }
        });
        
        // Reset time filter to default
        this.setFilter('log-time-filter', '24h');
        
        this.applyLogFilters();
    }
    
    applyLogFilters() {
        const filters = {
            level: document.getElementById('log-level-filter')?.value || '',
            category: document.getElementById('log-category-filter')?.value || '',
            severity: document.getElementById('log-severity-filter')?.value || '',
            search: document.getElementById('log-search')?.value || '',
            time_range: document.getElementById('log-time-filter')?.value || '24h'
        };
        
        this.currentFilters = filters;
        
        // Build query string
        const params = new URLSearchParams();
        Object.entries(filters).forEach(([key, value]) => {
            if (value) {
                params.append(key, value);
            }
        });
        
        // Show loading indicator
        this.showLoadingIndicator();
        
        // Make HTMX request
        htmx.ajax('GET', `/super-admin/htmx/logs/enhanced?${params.toString()}`, {
            target: '#log-content',
            swap: 'innerHTML'
        }).then(() => {
            this.hideLoadingIndicator();
            this.showToast('Logs filtered successfully', 'success');
        }).catch(() => {
            this.hideLoadingIndicator();
            this.showToast('Error filtering logs', 'error');
        });
    }
    
    refreshLogs() {
        this.showLoadingIndicator();
        this.applyLogFilters();
    }
    
    exportLogs() {
        const params = new URLSearchParams(this.currentFilters);
        const url = `/super-admin/api/logs/download/enhanced?${params.toString()}`;
        
        // Create temporary download link
        const link = document.createElement('a');
        link.href = url;
        link.download = `polly_logs_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.txt`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        this.showToast('Log export started', 'info');
    }
    
    showLoadingIndicator() {
        const indicator = document.getElementById('loading-indicator');
        if (indicator) {
            indicator.style.display = 'block';
        }
    }
    
    hideLoadingIndicator() {
        const indicator = document.getElementById('loading-indicator');
        if (indicator) {
            indicator.style.display = 'none';
        }
    }
    
    showToast(message, type = 'info') {
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast align-items-center text-white bg-${type === 'error' ? 'danger' : type === 'success' ? 'success' : 'primary'} border-0`;
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    <i class="fas fa-${type === 'error' ? 'exclamation-triangle' : type === 'success' ? 'check' : 'info-circle'} me-2"></i>
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;
        
        // Add to toast container
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container position-fixed top-0 end-0 p-3';
            container.style.zIndex = '9999';
            document.body.appendChild(container);
        }
        
        container.appendChild(toast);
        
        // Initialize and show toast
        const bsToast = new bootstrap.Toast(toast, { delay: 3000 });
        bsToast.show();
        
        // Remove toast element after it's hidden
        toast.addEventListener('hidden.bs.toast', () => {
            toast.remove();
        });
    }
    
    savePreferences() {
        const preferences = {
            groupingEnabled: this.groupingEnabled,
            timestampsVisible: this.timestampsVisible,
            metadataVisible: this.metadataVisible,
            autoRefresh: this.autoRefresh
        };
        
        localStorage.setItem('polly-log-viewer-preferences', JSON.stringify(preferences));
    }
    
    loadPreferences() {
        try {
            const saved = localStorage.getItem('polly-log-viewer-preferences');
            if (saved) {
                const preferences = JSON.parse(saved);
                
                if (preferences.groupingEnabled !== this.groupingEnabled) {
                    this.toggleGrouping();
                }
                
                if (preferences.timestampsVisible !== this.timestampsVisible) {
                    this.toggleTimestamps();
                }
                
                if (preferences.metadataVisible !== this.metadataVisible) {
                    this.toggleMetadata();
                }
                
                // Don't auto-enable auto-refresh on load for performance
                this.autoRefresh = false;
            }
        } catch (e) {
            console.warn('Failed to load log viewer preferences:', e);
        }
    }
    
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
}

// Global functions for template compatibility
function toggleGrouping() {
    window.logViewer?.toggleGrouping();
}

function toggleTimestamps() {
    window.logViewer?.toggleTimestamps();
}

function toggleMetadata() {
    window.logViewer?.toggleMetadata();
}

function quickFilter(type) {
    window.logViewer?.quickFilter(type);
}

function clearLogFilters() {
    window.logViewer?.clearLogFilters();
}

function applyLogFilters() {
    window.logViewer?.applyLogFilters();
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.logViewer = new EnhancedLogViewer();
});
