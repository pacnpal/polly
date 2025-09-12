/**
 * Polly Uppy Image Upload Handler
 * Shared functionality for image uploads using Uppy in both create and edit forms
 */

class PollyUppyUpload {
    constructor() {
        this.uppyInstance = null;
        this.dashboardTarget = '#uppy-dashboard';
        this.uploadEndpoint = '/htmx/upload-image';
        this.hiddenInputId = 'uploaded-image-path';
        this.imageMessageSectionId = 'image-message-section';
    }

    /**
     * Initialize Uppy instance
     * @param {Object} options - Configuration options
     */
    async init(options = {}) {
        // Import Uppy modules dynamically
        const { Uppy } = await import('https://cdn.jsdelivr.net/npm/@uppy/core@3.8.0/+esm');
        const { Dashboard } = await import('https://cdn.jsdelivr.net/npm/@uppy/dashboard@3.7.4/+esm');
        const { XHRUpload } = await import('https://cdn.jsdelivr.net/npm/@uppy/xhr-upload@3.6.6/+esm');
        
        // Merge default options with provided options
        const config = {
            dashboardTarget: this.dashboardTarget,
            uploadEndpoint: this.uploadEndpoint,
            hiddenInputId: this.hiddenInputId,
            imageMessageSectionId: this.imageMessageSectionId,
            maxFileSize: 8 * 1024 * 1024, // 8MB
            allowedFileTypes: ['image/jpeg', 'image/png', 'image/gif', 'image/webp'],
            ...options
        };

        // Clean up existing instance
        if (this.uppyInstance) {
            this.uppyInstance.destroy();
        }

        // Create new Uppy instance
        this.uppyInstance = new Uppy({
            debug: false,
            autoProceed: false,
            restrictions: {
                maxFileSize: config.maxFileSize,
                allowedFileTypes: config.allowedFileTypes,
                maxNumberOfFiles: 1
            }
        })
        .use(Dashboard, {
            target: config.dashboardTarget,
            inline: true,
            height: 300,
            showProgressDetails: true,
            hideUploadButton: false,
            hideRetryButton: false,
            hidePauseResumeButton: false,
            hideCancelButton: false,
            showRemoveButtonAfterComplete: true,
            note: 'Images only, up to 8MB',
            proudlyDisplayPoweredByUppy: false,
            locale: {
                strings: {
                    dropPasteFiles: 'Drop image here or %{browseFiles}',
                    browseFiles: 'browse',
                    uploadComplete: 'Upload complete',
                    uploadFailed: 'Upload failed',
                    retry: 'Retry',
                    cancel: 'Cancel',
                    remove: 'Remove',
                    addMore: 'Add more',
                    uploadingXFiles: {
                        0: 'Uploading %{smart_count} file',
                        1: 'Uploading %{smart_count} files'
                    }
                }
            }
        })
        .use(XHRUpload, {
            endpoint: config.uploadEndpoint,
            fieldName: 'image',
            formData: true,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        // Set up event handlers
        this.setupEventHandlers(config);

        return this.uppyInstance;
    }

    /**
     * Set up Uppy event handlers
     * @param {Object} config - Configuration options
     */
    setupEventHandlers(config) {
        // Handle successful uploads
        this.uppyInstance.on('upload-success', (file, response) => {
            console.log('Upload successful:', file.name, response);
            
            if (response.body && response.body.success) {
                // Store the uploaded image path
                const hiddenInput = document.getElementById(config.hiddenInputId);
                if (hiddenInput) {
                    hiddenInput.value = response.body.image_path;
                }
                
                // Show image message section
                const imageMessageSection = document.getElementById(config.imageMessageSectionId);
                if (imageMessageSection) {
                    imageMessageSection.style.display = 'block';
                }

                // Show success message
                this.showMessage('success', 'Image uploaded successfully!');
            }
        });

        // Handle upload errors
        this.uppyInstance.on('upload-error', (file, error, response) => {
            console.error('Upload failed:', file.name, error);
            
            let errorMessage = 'Upload failed. Please try again.';
            if (response && response.body && response.body.error) {
                errorMessage = response.body.error;
            } else if (error && error.message) {
                errorMessage = error.message;
            }
            
            this.showMessage('error', errorMessage);
        });

        // Handle file removal
        this.uppyInstance.on('file-removed', (file, reason) => {
            console.log('File removed:', file.name, reason);
            
            // Clear the hidden input
            const hiddenInput = document.getElementById(config.hiddenInputId);
            if (hiddenInput) {
                hiddenInput.value = '';
            }
            
            // Hide image message section
            const imageMessageSection = document.getElementById(config.imageMessageSectionId);
            if (imageMessageSection) {
                imageMessageSection.style.display = 'none';
            }

            // Clear image message text
            const imageMessageText = document.getElementById('image-message-text');
            if (imageMessageText) {
                imageMessageText.value = '';
            }
        });

        // Handle upload completion (all files)
        this.uppyInstance.on('complete', (result) => {
            console.log('Upload complete:', result);
            
            if (result.failed.length > 0) {
                this.showMessage('error', `${result.failed.length} file(s) failed to upload.`);
            }
        });

        // Handle restriction failures
        this.uppyInstance.on('restriction-failed', (file, error) => {
            console.error('Restriction failed:', file.name, error);
            
            let errorMessage = 'File does not meet requirements.';
            if (error.message) {
                errorMessage = error.message;
            }
            
            this.showMessage('error', errorMessage);
        });
    }

    /**
     * Show success or error message
     * @param {string} type - 'success' or 'error'
     * @param {string} message - Message to display
     */
    showMessage(type, message) {
        const alertClass = type === 'success' ? 'alert-success' : 'alert-danger';
        const iconClass = type === 'success' ? 'fa-check-circle' : 'fa-exclamation-triangle';
        
        // Create alert element
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert ${alertClass} alert-dismissible fade show mt-2`;
        alertDiv.innerHTML = `
            <i class="fas ${iconClass} me-2"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        // Find dashboard container and insert alert
        const dashboardContainer = document.querySelector(this.dashboardTarget);
        if (dashboardContainer) {
            // Remove any existing alerts
            const existingAlerts = dashboardContainer.parentNode.querySelectorAll('.alert');
            existingAlerts.forEach(alert => {
                if (alert.parentNode === dashboardContainer.parentNode) {
                    alert.remove();
                }
            });
            
            // Insert new alert
            dashboardContainer.parentNode.insertBefore(alertDiv, dashboardContainer.nextSibling);
            
            // Auto-remove after 5 seconds
            setTimeout(() => {
                if (alertDiv.parentNode) {
                    alertDiv.remove();
                }
            }, 5000);
        }
    }

    /**
     * Destroy the Uppy instance
     */
    destroy() {
        if (this.uppyInstance) {
            this.uppyInstance.destroy();
            this.uppyInstance = null;
        }
    }

    /**
     * Get the current Uppy instance
     * @returns {Object|null} Uppy instance
     */
    getInstance() {
        return this.uppyInstance;
    }

    /**
     * Check if Uppy is initialized
     * @returns {boolean} True if initialized
     */
    isInitialized() {
        return this.uppyInstance !== null;
    }

    /**
     * Add files programmatically
     * @param {Array} files - Array of file objects
     */
    addFiles(files) {
        if (this.uppyInstance && files && files.length > 0) {
            files.forEach(file => {
                try {
                    this.uppyInstance.addFile({
                        name: file.name,
                        type: file.type,
                        data: file,
                        source: 'Local',
                        isRemote: false
                    });
                } catch (error) {
                    console.error('Error adding file:', error);
                    this.showMessage('error', `Failed to add file: ${file.name}`);
                }
            });
        }
    }

    /**
     * Clear all files
     */
    clearFiles() {
        if (this.uppyInstance) {
            this.uppyInstance.cancelAll();
            
            // Clear hidden input
            const hiddenInput = document.getElementById(this.hiddenInputId);
            if (hiddenInput) {
                hiddenInput.value = '';
            }
            
            // Hide image message section
            const imageMessageSection = document.getElementById(this.imageMessageSectionId);
            if (imageMessageSection) {
                imageMessageSection.style.display = 'none';
            }
        }
    }

    /**
     * Get upload status
     * @returns {Object} Status information
     */
    getStatus() {
        if (!this.uppyInstance) {
            return { initialized: false };
        }

        const files = this.uppyInstance.getFiles();
        const state = this.uppyInstance.getState();
        
        return {
            initialized: true,
            fileCount: files.length,
            isUploading: state.isUploading,
            hasUploadedFiles: files.some(file => file.progress && file.progress.uploadComplete),
            hasFailedFiles: files.some(file => file.error)
        };
    }
}

// Create global instance
window.PollyUppyUpload = new PollyUppyUpload();

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Check if uppy dashboard container exists
    const dashboardContainer = document.querySelector('#uppy-dashboard');
    if (dashboardContainer) {
        window.PollyUppyUpload.init().catch(error => {
            console.error('Failed to initialize Uppy:', error);
        });
    }
});

// Re-initialize on HTMX content swaps
document.addEventListener('htmx:afterSwap', function(event) {
    // Check if the swapped content contains uppy dashboard
    const dashboardContainer = event.detail.target.querySelector('#uppy-dashboard') || 
                              document.querySelector('#uppy-dashboard');
    
    if (dashboardContainer) {
        // Small delay to ensure DOM is ready
        setTimeout(() => {
            window.PollyUppyUpload.init().catch(error => {
                console.error('Failed to re-initialize Uppy after HTMX swap:', error);
            });
        }, 100);
    }
});

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PollyUppyUpload;
}
