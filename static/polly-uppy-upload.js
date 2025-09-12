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
        this.initialized = false;
    }

    /**
     * Initialize Uppy instance
     * @param {Object} options - Configuration options
     */
    async init(options = {}) {
        try {
            console.log('🔧 Initializing Uppy...');
            
            // Check if dashboard container exists
            const dashboardContainer = document.querySelector(this.dashboardTarget);
            if (!dashboardContainer) {
                console.log('❌ Dashboard container not found');
                return null;
            }

            // Load Uppy from CDN if not already loaded
            if (!window.Uppy) {
                console.log('📦 Loading Uppy from CDN...');
                await this.loadUppyFromCDN();
            }

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
                console.log('🧹 Cleaning up existing Uppy instance');
                this.uppyInstance.destroy();
            }

            // Create new Uppy instance
            console.log('🚀 Creating new Uppy instance');
            this.uppyInstance = new window.Uppy.Uppy({
                debug: false,
                autoProceed: false,
                restrictions: {
                    maxFileSize: config.maxFileSize,
                    allowedFileTypes: config.allowedFileTypes,
                    maxNumberOfFiles: 1
                }
            })
            .use(window.Uppy.Dashboard, {
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
            .use(window.Uppy.XHRUpload, {
                endpoint: config.uploadEndpoint,
                fieldName: 'image',
                formData: true,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            // Set up event handlers
            this.setupEventHandlers(config);
            this.initialized = true;
            
            console.log('✅ Uppy initialized successfully');
            return this.uppyInstance;

        } catch (error) {
            console.error('❌ Failed to initialize Uppy:', error);
            
            // Fallback to simple file input
            this.createFallbackUpload();
            return null;
        }
    }

    /**
     * Load Uppy from CDN using script tags
     */
    async loadUppyFromCDN() {
        return new Promise((resolve, reject) => {
            // Check if already loaded
            if (window.Uppy) {
                resolve();
                return;
            }

            // Create script element
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/uppy@3.24.0/dist/uppy.min.js';
            script.onload = () => {
                console.log('📦 Uppy loaded from CDN');
                resolve();
            };
            script.onerror = (error) => {
                console.error('❌ Failed to load Uppy from CDN:', error);
                reject(error);
            };
            
            document.head.appendChild(script);
        });
    }

    /**
     * Create fallback file upload if Uppy fails
     */
    createFallbackUpload() {
        console.log('🔄 Creating fallback file upload');
        
        const dashboardContainer = document.querySelector(this.dashboardTarget);
        if (!dashboardContainer) return;

        dashboardContainer.innerHTML = `
            <div class="fallback-upload">
                <div class="upload-area" style="
                    border: 2px dashed #dee2e6;
                    border-radius: 0.375rem;
                    padding: 2rem;
                    text-align: center;
                    background-color: #f8f9fa;
                    cursor: pointer;
                ">
                    <i class="fas fa-cloud-upload-alt fa-2x text-primary mb-2"></i>
                    <p class="mb-2">Click to select an image</p>
                    <small class="text-muted">Max 8MB • JPEG, PNG, GIF, WebP</small>
                    <input type="file" 
                           id="fallback-file-input"
                           accept="image/jpeg,image/png,image/gif,image/webp"
                           style="display: none;">
                </div>
                <div id="fallback-preview" style="display: none; margin-top: 1rem;">
                    <div class="card" style="max-width: 300px;">
                        <img id="fallback-preview-img" class="card-img-top" style="max-height: 200px; object-fit: cover;" alt="Preview">
                        <div class="card-body p-2 d-flex justify-content-between align-items-center">
                            <small class="text-muted" id="fallback-file-info">Preview</small>
                            <button type="button" class="btn btn-sm btn-outline-danger" id="fallback-remove">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Set up fallback event handlers
        this.setupFallbackHandlers();
    }

    /**
     * Set up fallback upload handlers
     */
    setupFallbackHandlers() {
        const uploadArea = document.querySelector('.upload-area');
        const fileInput = document.getElementById('fallback-file-input');
        const preview = document.getElementById('fallback-preview');
        const previewImg = document.getElementById('fallback-preview-img');
        const fileInfo = document.getElementById('fallback-file-info');
        const removeBtn = document.getElementById('fallback-remove');

        if (!uploadArea || !fileInput) return;

        // Click to select file
        uploadArea.addEventListener('click', () => {
            fileInput.click();
        });

        // Handle file selection
        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                this.handleFallbackFile(file);
            }
        });

        // Handle drag and drop
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.style.borderColor = '#0d6efd';
            uploadArea.style.backgroundColor = '#e7f3ff';
        });

        uploadArea.addEventListener('dragleave', (e) => {
            e.preventDefault();
            uploadArea.style.borderColor = '#dee2e6';
            uploadArea.style.backgroundColor = '#f8f9fa';
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.style.borderColor = '#dee2e6';
            uploadArea.style.backgroundColor = '#f8f9fa';
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.handleFallbackFile(files[0]);
            }
        });

        // Remove file
        if (removeBtn) {
            removeBtn.addEventListener('click', () => {
                fileInput.value = '';
                preview.style.display = 'none';
                
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
            });
        }
    }

    /**
     * Handle fallback file selection
     */
    async handleFallbackFile(file) {
        // Validate file
        if (!this.validateFile(file)) {
            return;
        }

        // Show preview
        const preview = document.getElementById('fallback-preview');
        const previewImg = document.getElementById('fallback-preview-img');
        const fileInfo = document.getElementById('fallback-file-info');

        if (preview && previewImg && fileInfo) {
            const reader = new FileReader();
            reader.onload = (e) => {
                previewImg.src = e.target.result;
                fileInfo.textContent = `${file.name} (${this.formatFileSize(file.size)})`;
                preview.style.display = 'block';
            };
            reader.readAsDataURL(file);
        }

        // Upload file
        await this.uploadFile(file);
    }

    /**
     * Validate file
     */
    validateFile(file) {
        const maxSize = 8 * 1024 * 1024; // 8MB
        const allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];

        if (!allowedTypes.includes(file.type)) {
            this.showMessage('error', 'Please select a valid image file (JPEG, PNG, GIF, or WebP)');
            return false;
        }

        if (file.size > maxSize) {
            this.showMessage('error', 'File size must be less than 8MB');
            return false;
        }

        return true;
    }

    /**
     * Upload file using fetch
     */
    async uploadFile(file) {
        try {
            const formData = new FormData();
            formData.append('image', file);

            const response = await fetch(this.uploadEndpoint, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            const result = await response.json();

            if (result.success) {
                // Store the uploaded image path
                const hiddenInput = document.getElementById(this.hiddenInputId);
                if (hiddenInput) {
                    hiddenInput.value = result.image_path;
                }
                
                // Show image message section
                const imageMessageSection = document.getElementById(this.imageMessageSectionId);
                if (imageMessageSection) {
                    imageMessageSection.style.display = 'block';
                }

                this.showMessage('success', 'Image uploaded successfully!');
            } else {
                this.showMessage('error', result.error || 'Upload failed');
            }

        } catch (error) {
            console.error('Upload error:', error);
            this.showMessage('error', 'Upload failed. Please try again.');
        }
    }

    /**
     * Set up Uppy event handlers
     * @param {Object} config - Configuration options
     */
    setupEventHandlers(config) {
        if (!this.uppyInstance) return;

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
     * Format file size
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    /**
     * Destroy the Uppy instance
     */
    destroy() {
        if (this.uppyInstance) {
            this.uppyInstance.destroy();
            this.uppyInstance = null;
        }
        this.initialized = false;
    }

    /**
     * Check if Uppy is initialized
     * @returns {boolean} True if initialized
     */
    isInitialized() {
        return this.initialized;
    }
}

// Create global instance
window.PollyUppyUpload = new PollyUppyUpload();

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Check if uppy dashboard container exists
    const dashboardContainer = document.querySelector('#uppy-dashboard');
    if (dashboardContainer) {
        console.log('🔧 Found dashboard container, initializing Uppy...');
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
        console.log('🔧 HTMX swap detected, re-initializing Uppy...');
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
