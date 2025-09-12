/**
 * Enhanced Polly Image Upload with Drag & Drop and Preview
 * Modern, condensed interface with immediate preview functionality
 */

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
                <input type="file" id="file-input" accept="image/jpeg,image/png,image/gif,image/webp" style="display: none;">
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
                            <button type="button" class="btn btn-sm btn-success" id="upload-btn">
                                <i class="fas fa-upload"></i> Upload
                            </button>
                            <button type="button" class="btn btn-sm btn-outline-light" id="cancel-btn">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    </div>
                    <div class="upload-progress" id="upload-progress" style="display: none;">
                        <div class="progress">
                            <div class="progress-bar" id="progress-bar"></div>
                        </div>
                        <small id="progress-text">Uploading...</small>
                    </div>
                </div>
            </div>

            <div class="uploaded-preview" id="uploaded-preview" style="display: none;">
                <div class="success-card">
                    <img id="uploaded-image" alt="Uploaded image" class="uploaded-img">
                    <div class="success-overlay">
                        <div class="success-info">
                            <i class="fas fa-check-circle text-success"></i>
                            <span>Image uploaded successfully</span>
                        </div>
                        <button type="button" class="btn btn-sm btn-outline-light" id="remove-uploaded">
                            <i class="fas fa-trash"></i> Remove
                        </button>
                    </div>
                </div>
            </div>

            ${this.options.showImageMessage ? `
                <div class="image-message-section" id="image-message-section" style="display: ${this.options.currentImagePath || this.uploadedImagePath ? 'block' : 'none'};">
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
            <input type="hidden" id="uploaded-image-path" name="uploaded_image_path" value="${this.uploadedImagePath || ''}">
            <input type="hidden" id="remove-current-image-flag" name="remove_current_image" value="false">
        `;
    }

    /**
     * Set up all event handlers
     */
    setupEventHandlers(container) {
        const uploadZone = container.querySelector('#upload-zone');
        const fileInput = container.querySelector('#file-input');
        const uploadBtn = container.querySelector('#upload-btn');
        const cancelBtn = container.querySelector('#cancel-btn');
        const removeUploadedBtn = container.querySelector('#remove-uploaded');
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
                this.handleFileSelection(files[0], container);
            }
        });

        // Upload button
        if (uploadBtn) {
            uploadBtn.addEventListener('click', () => {
                this.uploadFile(container);
            });
        }

        // Cancel button
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => {
                this.cancelUpload(container);
            });
        }

        // Remove uploaded image
        if (removeUploadedBtn) {
            removeUploadedBtn.addEventListener('click', () => {
                this.removeUploadedImage(container);
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

        const reader = new FileReader();
        reader.onload = (e) => {
            previewImage.src = e.target.result;
            previewFilename.textContent = file.name;
            previewFilesize.textContent = this.formatFileSize(file.size);
            
            uploadZone.style.display = 'none';
            uploadPreview.style.display = 'block';
        };
        reader.readAsDataURL(file);
    }

    /**
     * Upload the selected file
     */
    async uploadFile(container) {
        if (!this.currentFile) return;

        const uploadBtn = container.querySelector('#upload-btn');
        const cancelBtn = container.querySelector('#cancel-btn');
        const uploadProgress = container.querySelector('#upload-progress');
        const progressBar = container.querySelector('#progress-bar');
        const progressText = container.querySelector('#progress-text');

        try {
            // Show progress
            uploadBtn.style.display = 'none';
            cancelBtn.style.display = 'none';
            uploadProgress.style.display = 'block';

            const formData = new FormData();
            formData.append('image', this.currentFile);

            const xhr = new XMLHttpRequest();
            
            // Progress tracking
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percentComplete = (e.loaded / e.total) * 100;
                    progressBar.style.width = percentComplete + '%';
                    progressText.textContent = `Uploading... ${Math.round(percentComplete)}%`;
                }
            });

            // Upload completion
            xhr.addEventListener('load', () => {
                if (xhr.status === 200) {
                    const response = JSON.parse(xhr.responseText);
                    if (response.success) {
                        this.handleUploadSuccess(response.image_path, container);
                    } else {
                        this.handleUploadError(response.error || 'Upload failed', container);
                    }
                } else {
                    this.handleUploadError('Upload failed', container);
                }
            });

            xhr.addEventListener('error', () => {
                this.handleUploadError('Upload failed', container);
            });

            xhr.open('POST', this.uploadEndpoint);
            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
            xhr.send(formData);

        } catch (error) {
            console.error('Upload error:', error);
            this.handleUploadError('Upload failed', container);
        }
    }

    /**
     * Handle successful upload
     */
    handleUploadSuccess(imagePath, container) {
        this.uploadedImagePath = imagePath;
        
        const uploadPreview = container.querySelector('#upload-preview');
        const uploadedPreview = container.querySelector('#uploaded-preview');
        const uploadedImage = container.querySelector('#uploaded-image');
        const hiddenInput = container.querySelector('#uploaded-image-path');
        const imageMessageSection = container.querySelector('#image-message-section');

        // Update UI
        uploadedImage.src = `/${imagePath}`;
        uploadPreview.style.display = 'none';
        uploadedPreview.style.display = 'block';

        // Update hidden input
        if (hiddenInput) {
            hiddenInput.value = imagePath;
        }

        // Show image message section
        if (imageMessageSection) {
            imageMessageSection.style.display = 'block';
        }

        this.showAlert('success', 'Image uploaded successfully!');
    }

    /**
     * Handle upload error
     */
    handleUploadError(errorMessage, container) {
        const uploadBtn = container.querySelector('#upload-btn');
        const cancelBtn = container.querySelector('#cancel-btn');
        const uploadProgress = container.querySelector('#upload-progress');

        // Reset UI
        uploadBtn.style.display = 'inline-block';
        cancelBtn.style.display = 'inline-block';
        uploadProgress.style.display = 'none';

        this.showAlert('error', errorMessage);
    }

    /**
     * Cancel upload and return to upload zone
     */
    cancelUpload(container) {
        const uploadZone = container.querySelector('#upload-zone');
        const uploadPreview = container.querySelector('#upload-preview');
        const fileInput = container.querySelector('#file-input');

        uploadPreview.style.display = 'none';
        uploadZone.style.display = 'block';
        fileInput.value = '';
        this.currentFile = null;
    }

    /**
     * Remove uploaded image
     */
    removeUploadedImage(container) {
        const uploadZone = container.querySelector('#upload-zone');
        const uploadedPreview = container.querySelector('#uploaded-preview');
        const hiddenInput = container.querySelector('#uploaded-image-path');
        const imageMessageSection = container.querySelector('#image-message-section');
        const imageMessageText = container.querySelector('#image-message-text');

        // Reset UI
        uploadedPreview.style.display = 'none';
        uploadZone.style.display = 'block';

        // Clear data
        this.uploadedImagePath = null;
        if (hiddenInput) {
            hiddenInput.value = '';
        }

        // Hide image message section if no current image
        if (imageMessageSection && !this.options.currentImagePath) {
            imageMessageSection.style.display = 'none';
            if (imageMessageText) {
                imageMessageText.value = '';
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
