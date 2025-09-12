/**
 * Enhanced Polly Image Upload with Drag & Drop and Preview
 * Modern, condensed interface with immediate preview functionality
 */

// Only declare the class if it doesn't already exist
if (typeof window.PollyImageUpload === 'undefined') {
    class PollyImageUpload {
    constructor() {
        this.uploadEndpoint = '/htmx/upload-image';
        this.maxFileSize = 8 * 1024 * 1024; // 8MB
        this.allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
        this.currentFile = null;
        this.uploadedImagePath = null;
    }

    /**
     * Initialize the enhanced image upload
     * @param {string} containerId - ID of the container element
     * @param {Object} options - Configuration options
     */
    init(containerId, options = {}) {
        const container = document.getElementById(containerId);
        if (!container) {
            console.error(`Container ${containerId} not found`);
            return;
        }

        this.options = {
            showImageMessage: true,
            currentImagePath: null,
            currentImageText: '',
            ...options
        };

        this.createUploadInterface(container);
        this.setupEventHandlers(container);
        
        console.log('✅ Enhanced image upload initialized');
    }

    /**
     * Create the upload interface HTML
     */
    createUploadInterface(container) {
        const currentImageHtml = this.options.currentImagePath ? `
            <div class="current-image-preview mb-3" id="current-image-preview">
                <div class="image-card">
                    <img src="/${this.options.currentImagePath}" alt="Current image" class="current-image">
                    <div class="image-overlay">
                        <button type="button" class="btn btn-sm btn-outline-light" id="remove-current-image">
                            <i class="fas fa-trash"></i> Remove
                        </button>
                    </div>
                </div>
            </div>
        ` : '';

        container.innerHTML = `
            ${currentImageHtml}
            
            <div class="upload-zone" id="upload-zone">
                <div class="upload-content">
                    <i class="fas fa-cloud-upload-alt upload-icon"></i>
                    <div class="upload-text">
                        <strong>Drop image here or click to browse</strong>
                        <small>JPEG, PNG, GIF, WebP • Max 8MB</small>
                    </div>
                </div>
                <input type="file" id="file-input" name="image" accept="image/jpeg,image/png,image/gif,image/webp" style="display: none;">
            </div>

            <div class="upload-preview" id="upload-preview" style="display: none;">
                <div class="preview-card">
                    <img id="preview-image" alt="Preview" class="preview-img">
                    <div class="preview-overlay">
                        <div class="preview-info">
                            <span id="preview-filename"></span>
                            <span id="preview-filesize"></span>
                        </div>
                        <div class="preview-actions">
                            <button type="button" class="btn btn-sm btn-outline-light" id="cancel-btn">
                                <i class="fas fa-times"></i> Remove
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            ${this.options.showImageMessage ? `
                <div class="image-message-section" id="image-message-section" style="display: ${this.options.currentImagePath || this.currentFile ? 'block' : 'none'};">
                    <label for="image-message-text" class="form-label">
                        <i class="fas fa-comment me-1"></i>Message with Image (Optional)
                    </label>
                    <textarea class="form-control" 
                              id="image-message-text" 
                              name="image_message_text" 
                              rows="2" 
                              placeholder="Add a message to display with your image...">${this.options.currentImageText}</textarea>
                    <small class="text-muted">This text will appear with the image before the poll</small>
                </div>
            ` : ''}

            <!-- Hidden inputs for form submission -->
            <input type="hidden" id="remove-current-image-flag" name="remove_current_image" value="false">
        `;
    }

    /**
     * Set up all event handlers
     */
    setupEventHandlers(container) {
        const uploadZone = container.querySelector('#upload-zone');
        const fileInput = container.querySelector('#file-input');
        const cancelBtn = container.querySelector('#cancel-btn');
        const removeCurrentBtn = container.querySelector('#remove-current-image');

        // Click to browse
        uploadZone.addEventListener('click', () => {
            fileInput.click();
        });

        // File selection
        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                this.handleFileSelection(file, container);
            }
        });

        // Drag and drop
        uploadZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadZone.classList.add('drag-over');
        });

        uploadZone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            uploadZone.classList.remove('drag-over');
        });

        uploadZone.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadZone.classList.remove('drag-over');
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                // Set the file to the input element for form submission
                const dt = new DataTransfer();
                dt.items.add(files[0]);
                fileInput.files = dt.files;
                
                this.handleFileSelection(files[0], container);
            }
        });

        // Cancel button
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => {
                this.cancelUpload(container);
            });
        }

        // Remove current image
        if (removeCurrentBtn) {
            removeCurrentBtn.addEventListener('click', () => {
                this.removeCurrentImage(container);
            });
        }
    }

    /**
     * Handle file selection
     */
    handleFileSelection(file, container) {
        if (!this.validateFile(file)) {
            return;
        }

        this.currentFile = file;
        this.showPreview(file, container);
    }

    /**
     * Validate selected file
     */
    validateFile(file) {
        if (!this.allowedTypes.includes(file.type)) {
            this.showAlert('error', 'Please select a valid image file (JPEG, PNG, GIF, or WebP)');
            return false;
        }

        if (file.size > this.maxFileSize) {
            this.showAlert('error', 'File size must be less than 8MB');
            return false;
        }

        return true;
    }

    /**
     * Show file preview
     */
    showPreview(file, container) {
        const uploadZone = container.querySelector('#upload-zone');
        const uploadPreview = container.querySelector('#upload-preview');
        const previewImage = container.querySelector('#preview-image');
        const previewFilename = container.querySelector('#preview-filename');
        const previewFilesize = container.querySelector('#preview-filesize');
        const imageMessageSection = container.querySelector('#image-message-section');

        const reader = new FileReader();
        reader.onload = (e) => {
            previewImage.src = e.target.result;
            previewFilename.textContent = file.name;
            previewFilesize.textContent = this.formatFileSize(file.size);
            
            uploadZone.style.display = 'none';
            uploadPreview.style.display = 'block';
            
            // Show image message section when file is selected
            if (imageMessageSection) {
                imageMessageSection.style.display = 'block';
            }
        };
        reader.readAsDataURL(file);
    }

    /**
     * Cancel preview and return to upload zone
     */
    cancelUpload(container) {
        const uploadZone = container.querySelector('#upload-zone');
        const uploadPreview = container.querySelector('#upload-preview');
        const fileInput = container.querySelector('#file-input');
        const imageMessageSection = container.querySelector('#image-message-section');

        uploadPreview.style.display = 'none';
        uploadZone.style.display = 'block';
        fileInput.value = '';
        this.currentFile = null;

        // Show image message section and show it if current image exists
        if (imageMessageSection) {
            if (this.options.currentImagePath) {
                imageMessageSection.style.display = 'block';
            } else {
                imageMessageSection.style.display = 'none';
            }
        }
    }

    /**
     * Remove current image
     */
    removeCurrentImage(container) {
        const currentImagePreview = container.querySelector('#current-image-preview');
        const removeCurrentFlag = container.querySelector('#remove-current-image-flag');
        const imageMessageSection = container.querySelector('#image-message-section');

        // Hide current image
        if (currentImagePreview) {
            currentImagePreview.style.display = 'none';
        }

        // Set removal flag
        if (removeCurrentFlag) {
            removeCurrentFlag.value = 'true';
        }

        // Hide image message section if no uploaded image
        if (imageMessageSection && !this.uploadedImagePath) {
            imageMessageSection.style.display = 'none';
        }

        this.options.currentImagePath = null;
    }

    /**
     * Show alert message
     */
    showAlert(type, message) {
        const alertClass = type === 'success' ? 'alert-success' : 'alert-danger';
        const iconClass = type === 'success' ? 'fa-check-circle' : 'fa-exclamation-triangle';
        
        // Remove existing alerts
        document.querySelectorAll('.upload-alert').forEach(alert => alert.remove());
        
        // Create new alert
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert ${alertClass} alert-dismissible fade show upload-alert mt-2`;
        alertDiv.innerHTML = `
            <i class="fas ${iconClass} me-2"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        // Insert alert
        const container = document.querySelector('.upload-zone').parentNode;
        container.insertBefore(alertDiv, container.firstChild);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 5000);
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
    }

    // Create global instance
    window.PollyImageUpload = PollyImageUpload;

    // Export for module usage
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = PollyImageUpload;
    }
}
