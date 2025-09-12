/**
 * Polly Debug JavaScript Utilities
 * Provides consistent debug logging that respects the backend DEBUG mode setting
 */

// Global debug logger object
window.PollyDebug = (function() {
    // Get debug mode from template context (injected by backend)
    const serverDebugMode = typeof POLLY_DEBUG !== 'undefined' ? POLLY_DEBUG : false;
    
    // Check for client-side debug override (for development)
    const clientDebugOverride = (() => {
        // Check localStorage for debug override
        try {
            const stored = localStorage.getItem('polly_debug_override');
            if (stored !== null) {
                return stored === 'true';
            }
        } catch (e) {
            // localStorage may not be available in some environments
        }
        
        // Check URL parameter for debug override
        try {
            const urlParams = new URLSearchParams(window.location.search);
            const debugParam = urlParams.get('debug');
            if (debugParam !== null) {
                const enabled = debugParam === 'true' || debugParam === '1';
                // Store the preference for this session
                try {
                    localStorage.setItem('polly_debug_override', enabled.toString());
                } catch (e) {
                    // Ignore localStorage errors
                }
                return enabled;
            }
        } catch (e) {
            // URL API may not be available in some environments
        }
        
        return null; // No override
    })();
    
    // Final debug mode: client override takes precedence over server setting
    const debugMode = clientDebugOverride !== null ? clientDebugOverride : serverDebugMode;
    
    // Create styled console methods
    const createStyledLogger = (level, color, emoji) => {
        return function(message, ...args) {
            if (!debugMode) return;
            
            const timestamp = new Date().toLocaleTimeString();
            const styled = `%c[${timestamp}] ${emoji} POLLY ${level.toUpperCase()}`;
            const styles = `color: ${color}; font-weight: bold;`;
            
            console[level](styled, styles, message, ...args);
        };
    };
    
    // Public API
    return {
        // Properties
        enabled: debugMode,
        serverDebugMode: serverDebugMode,
        clientOverride: clientDebugOverride,
        isDebugMode: () => debugMode,
        
        // Client-side debug control
        enableClientDebug: function() {
            try {
                localStorage.setItem('polly_debug_override', 'true');
                console.info('%c🐛 POLLY CLIENT DEBUG ENABLED', 'color: #dc3545; font-weight: bold; font-size: 14px; background: #fff3cd; padding: 2px 6px; border-radius: 3px;');
                console.info('🔄 Refresh the page to activate debug logging.');
                return true;
            } catch (e) {
                console.warn('Failed to enable client debug mode:', e);
                return false;
            }
        },
        
        disableClientDebug: function() {
            try {
                localStorage.removeItem('polly_debug_override');
                console.info('%c📊 POLLY CLIENT DEBUG DISABLED', 'color: #198754; font-weight: bold; font-size: 14px; background: #d1e7dd; padding: 2px 6px; border-radius: 3px;');
                console.info('🔄 Refresh the page to deactivate debug logging.');
                return true;
            } catch (e) {
                console.warn('Failed to disable client debug mode:', e);
                return false;
            }
        },
        
        getDebugStatus: function() {
            return {
                serverDebugMode: serverDebugMode,
                clientOverride: clientDebugOverride,
                effectiveMode: debugMode,
                canOverride: typeof localStorage !== 'undefined'
            };
        },
        
        // Styled logging methods
        debug: createStyledLogger('debug', '#6c757d', '🐛'),
        info: createStyledLogger('info', '#0dcaf0', 'ℹ️'),
        warn: createStyledLogger('warn', '#ffc107', '⚠️'),
        error: createStyledLogger('error', '#dc3545', '❌'),
        success: createStyledLogger('info', '#198754', '✅'),
        
        // Special logging methods
        htmx: function(message, ...args) {
            if (!debugMode) return;
            const timestamp = new Date().toLocaleTimeString();
            const styled = `%c[${timestamp}] 🔄 POLLY HTMX`;
            const styles = 'color: #8b5cf6; font-weight: bold;';
            console.debug(styled, styles, message, ...args);
        },
        
        api: function(message, ...args) {
            if (!debugMode) return;
            const timestamp = new Date().toLocaleTimeString();
            const styled = `%c[${timestamp}] 🌐 POLLY API`;
            const styles = 'color: #06b6d4; font-weight: bold;';
            console.debug(styled, styles, message, ...args);
        },
        
        user: function(message, ...args) {
            if (!debugMode) return;
            const timestamp = new Date().toLocaleTimeString();
            const styled = `%c[${timestamp}] 👤 POLLY USER`;
            const styles = 'color: #10b981; font-weight: bold;';
            console.debug(styled, styles, message, ...args);
        },
        
        poll: function(message, ...args) {
            if (!debugMode) return;
            const timestamp = new Date().toLocaleTimeString();
            const styled = `%c[${timestamp}] 📊 POLLY POLL`;
            const styles = 'color: #f59e0b; font-weight: bold;';
            console.debug(styled, styles, message, ...args);
        },
        
        // Utility methods
        group: function(label) {
            if (!debugMode) return { end: () => {} };
            const timestamp = new Date().toLocaleTimeString();
            const styled = `%c[${timestamp}] 📁 ${label}`;
            const styles = 'color: #8b5cf6; font-weight: bold;';
            console.groupCollapsed(styled, styles);
            return {
                end: () => console.groupEnd()
            };
        },
        
        table: function(data, label = null) {
            if (!debugMode) return;
            if (label) {
                this.debug(label);
            }
            console.table(data);
        },
        
        time: function(label) {
            if (!debugMode) return { end: () => {} };
            const fullLabel = `🕒 POLLY TIMER: ${label}`;
            console.time(fullLabel);
            return {
                end: () => console.timeEnd(fullLabel)
            };
        },
        
        // Browser console notification on load
        init: function() {
            if (debugMode) {
                const styled = '%c🐛 POLLY DEBUG MODE ENABLED';
                const styles = 'color: #dc3545; font-weight: bold; font-size: 16px; background: #fff3cd; padding: 4px 8px; border-radius: 4px;';
                console.info(styled, styles);
                
                // Show debug source information
                if (clientDebugOverride !== null) {
                    const overrideType = clientDebugOverride ? 'enabled' : 'disabled';
                    console.info(`🎛️  Client override: Debug ${overrideType} (server: ${serverDebugMode})`);
                } else {
                    console.info(`🖥️  Server debug mode: ${serverDebugMode}`);
                }
                
                console.info('🔍 Debug logging is active. Use PollyDebug.* methods for consistent logging.');
                console.info('💡 Client controls: PollyDebug.enableClientDebug() / PollyDebug.disableClientDebug()');
            } else {
                // Silent when debug is off, but provide help for developers
                if (typeof console !== 'undefined' && console.info) {
                    console.info('💡 Polly Debug: Use PollyDebug.enableClientDebug() to enable debug logging, or add ?debug=true to URL');
                }
            }
        }
    };
})();

// Enhanced HTMX event logging when in debug mode
if (PollyDebug.enabled && typeof htmx !== 'undefined') {
    // Wait for DOM to be ready before adding event listeners
    function addHTMXEventListeners() {
        try {
            // Ensure document and body are available
            if (!document || !document.body) {
                setTimeout(addHTMXEventListeners, 100);
                return;
            }
            
            const targetElement = document.body;
            
            // Log HTMX requests
            targetElement.addEventListener('htmx:beforeRequest', function(evt) {
            PollyDebug.htmx('Request starting:', {
                method: evt.detail.xhr.method || 'GET',
                url: evt.detail.requestConfig.path,
                element: evt.detail.elt.tagName.toLowerCase() + (evt.detail.elt.id ? '#' + evt.detail.elt.id : ''),
                target: evt.detail.target ? evt.detail.target.tagName.toLowerCase() + (evt.detail.target.id ? '#' + evt.detail.target.id : '') : null
            });
        });
        
        targetElement.addEventListener('htmx:afterRequest', function(evt) {
            const status = evt.detail.xhr.status;
            const isSuccess = status >= 200 && status < 300;
            
            if (isSuccess) {
                PollyDebug.htmx('Request completed:', {
                    status: status,
                    url: evt.detail.requestConfig.path,
                    responseSize: evt.detail.xhr.responseText.length + ' chars'
                });
            } else {
                PollyDebug.warn('HTMX request failed:', {
                    status: status,
                    url: evt.detail.requestConfig.path,
                    response: evt.detail.xhr.responseText.substring(0, 200) + (evt.detail.xhr.responseText.length > 200 ? '...' : '')
                });
            }
        });
        
        // Log HTMX errors
        targetElement.addEventListener('htmx:responseError', function(evt) {
            PollyDebug.error('HTMX response error:', {
                status: evt.detail.xhr.status,
                url: evt.detail.requestConfig.path,
                error: evt.detail.xhr.statusText
            });
        });
        
        // Log HTMX swaps
        targetElement.addEventListener('htmx:beforeSwap', function(evt) {
            PollyDebug.htmx('Content swapping:', {
                target: evt.detail.target.tagName.toLowerCase() + (evt.detail.target.id ? '#' + evt.detail.target.id : ''),
                swapStyle: evt.detail.swapStyle || 'innerHTML',
                contentLength: evt.detail.serverResponse.length + ' chars'
            });
        });
        } catch (error) {
            console.warn('PollyDebug: Error setting up HTMX event listeners:', error);
            // Retry after a longer delay if there was an error
            setTimeout(addHTMXEventListeners, 500);
        }
    }
    
    // Add event listeners when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', addHTMXEventListeners);
    } else {
        addHTMXEventListeners();
    }
}

// Initialize debug logging on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', PollyDebug.init);
} else {
    PollyDebug.init();
}
