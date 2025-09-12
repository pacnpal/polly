/**
 * Polly Image Upload Handler
 * Handles drag & drop image upload, preview, validation, and file management
 */

window.PollyImageUpload = (function() {
    'use strict';
    
    // Configuration
    const config = {
        maxImageSize: 8 * 1024 * 1024, // 8MB
        allowedImageTypes: ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    };
    
    // Utility functions
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    function debugLog(message, ...args) {
        if (window.PollyDebug && window.PollyDebug.enabled) {
            console.log(`🔍 IMAGE UPLOAD DEBUG - ${message}`, ...args);
        }
    }
    
    // DOM element getters
    function getElements() {
        return {
            imageDropZone: document.getElementById('image-drop-zone'),
            imageInput: document.getElementById('poll-image'),
            imagePreview: document.getElementById('image-preview'),
            previewImg: document.getElementById('preview-img'),
            imageInfo: document.getElementById('image-info'),
            removeImageBtn: document.getElementById('remove-image'),
            imageMessageSection: document.getElementById('image-message-section')
        };
    }
    
    // Error and status message handlers
    function clearImageError() {
        const errorDiv = document.getElementById('image-error');
        if (errorDiv) {
            errorDiv.innerHTML = '';
        }
    }
    
    function showImageError(message) {
        const elements = getElements();
        if (!elements.imageDropZone) return;
        
        let errorDiv = document.getElementById('image-error');
        if (!errorDiv) {
            errorDiv = document.createElement('div');
            errorDiv.id = 'image-error';
            errorDiv.className = 'mt-2';
            elements.imageDropZone.parentNode.appendChild(errorDiv);
        }

        errorDiv.innerHTML = `
            <div class="alert alert-danger alert-dismissible fade show" role="alert">
                <i class="fas fa-exclamation-triangle me-2"></i>
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;

        // Auto-hide after 5 seconds
        setTimeout(() => {
            const alert = errorDiv.querySelector('.alert');
            if (alert) {
                alert.classList.remove('show');
                setTimeout(() => errorDiv.innerHTML = '', 150);
            }
        }, 5000);
    }
    
    function showImageUploadProgress(message) {
        const elements = getElements();
        if (!elements.imageDropZone) return;
        
        let progressDiv = document.getElementById('image-upload-progress');
        if (!progressDiv) {
            progressDiv = document.createElement('div');
            progressDiv.id = 'image-upload-progress';
            progressDiv.className = 'mt-2';
            elements.imageDropZone.parentNode.appendChild(progressDiv);
        }

        progressDiv.innerHTML = `
            <div class="alert alert-info d-flex align-items-center" role="alert">
                <div class="spinner-border spinner-border-sm me-2" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <span>${message}</span>
            </div>
        `;
    }
    
    function hideImageUploadProgress() {
        const progressDiv = document.getElementById('image-upload-progress');
        if (progressDiv) {
            progressDiv.innerHTML = '';
        }
    }
    
    function showImageUploadStatus(type, message) {
        const elements = getElements();
        if (!elements.imageDropZone) return;
        
        let statusDiv = document.getElementById('image-upload-status');
        if (!statusDiv) {
            statusDiv = document.createElement('div');
            statusDiv.id = 'image-upload-status';
            statusDiv.className = 'mt-2';
            elements.imageDropZone.parentNode.appendChild(statusDiv);
        }

        const alertClass = type === 'success' ? 'alert-success' : 
                          type === 'error' ? 'alert-danger' : 'alert-info';
        
        statusDiv.innerHTML = `
            <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
                <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-triangle' : 'info-circle'} me-2"></i>
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;

        // Auto-hide after 3 seconds
        setTimeout(() => {
            const alert = statusDiv.querySelector('.alert');
            if (alert) {
                alert.classList.remove('show');
                setTimeout(() => statusDiv.innerHTML = '', 150);
            }
        }, 3000);
    }
    
    // Event handlers
    function handleDropZoneClick(e) {
        e.preventDefault();
        e.stopPropagation();
        debugLog('Drop zone clicked');
        console.log('🔍 IMAGE UPLOAD - Drop zone clicked!'); // Always log this
        
        const elements = getElements();
        console.log('🔍 IMAGE UPLOAD - Elements check:', {
            imageInput: !!elements.imageInput,
            imageInputId: elements.imageInput ? elements.imageInput.id : 'null',
            imageInputType: elements.imageInput ? elements.imageInput.type : 'null',
            imageInputAccept: elements.imageInput ? elements.imageInput.accept : 'null',
            hasClickMethod: elements.imageInput && typeof elements.imageInput.click === 'function',
            isHidden: elements.imageInput ? elements.imageInput.classList.contains('d-none') : 'null',
            style: elements.imageInput ? elements.imageInput.style.cssText : 'null'
        });
        
        try {
            if (elements.imageInput && typeof elements.imageInput.click === 'function') {
                debugLog('Triggering file input click');
                console.log('🔍 IMAGE UPLOAD - Triggering file input click'); // Always log this
                
                // Force focus on the input before clicking
                elements.imageInput.focus();
                elements.imageInput.click();
                
                console.log('🔍 IMAGE UPLOAD - File input click triggered successfully');
            } else {
                console.error('File input not available or no click method');
                console.error('🔍 IMAGE UPLOAD - File input not available:', {
                    imageInput: elements.imageInput,
                    hasClick: elements.imageInput && typeof elements.imageInput.click === 'function'
                });
                showImageError('File upload not available. Please refresh the page and try again.');
            }
        } catch (error) {
            console.error('Error opening file browser:', error);
            console.error('🔍 IMAGE UPLOAD - Error opening file browser:', error);
            showImageError('Error opening file browser. Please try again.');
        }
    }
    
    function handleDragOver(e) {
        e.preventDefault();
        debugLog('Drag over detected');
        e.currentTarget.classList.add('drag-over');
    }
    
    function handleDragLeave(e) {
        e.preventDefault();
        debugLog('Drag leave detected');
        e.currentTarget.classList.remove('drag-over');
    }
    
    function handleDrop(e) {
        e.preventDefault();
        debugLog('File drop detected');
        e.currentTarget.classList.remove('drag-over');
        
        const files = e.dataTransfer.files;
        debugLog('Files dropped:', files.length);
        if (files.length > 0) {
            handleImageFile(files[0]);
        }
    }
    
    function handleFileInputChange(e) {
        debugLog('File input changed, files:', e.target.files.length);
        if (e.target.files.length > 0) {
            debugLog('Processing selected file:', e.target.files[0].name);
            handleImageFile(e.target.files[0]);
        }
    }
    
    function handleImageFile(file) {
        debugLog('Handling file:', file.name, file.type, file.size);
        
        // Clear any previous errors
        clearImageError();
        
        // Validate file type
        if (!config.allowedImageTypes.includes(file.type)) {
            console.error('Invalid file type:', file.type);
            showImageError('Invalid file type. Please select a JPEG, PNG, GIF, or WebP image.');
            return;
        }

        // Validate file size
        if (file.size > config.maxImageSize) {
            console.error('File too large:', file.size);
            showImageError(`File too large. Maximum size is 8MB. Your file is ${formatFileSize(file.size)}.`);
            return;
        }

        debugLog('File validation passed, showing preview');
        
        // Show HTMX upload progress bar
        showHTMXUploadProgress();

        // Show preview
        const reader = new FileReader();
        reader.onload = (e) => {
            debugLog('FileReader loaded successfully');
            // Hide progress and show preview
            hideHTMXUploadProgress();
            showImagePreview(e.target.result, file.name, file.size);
        };
        
        reader.onerror = (e) => {
            console.error('FileReader error:', e);
            hideHTMXUploadProgress();
            showImageError('Failed to read image file. Please try again.');
        };
        
        reader.readAsDataURL(file);
    }
    
    function showImagePreview(src, fileName, fileSize) {
        const elements = getElements();
        if (!elements.previewImg || !elements.imageInfo) return;
        
        elements.previewImg.src = src;
        elements.imageInfo.textContent = `${fileName} (${formatFileSize(fileSize)})`;
        
        // Remove CSS classes that force display:none and show elements
        if (elements.imagePreview) {
            elements.imagePreview.classList.remove('image-preview-hidden');
            elements.imagePreview.style.display = 'block';
            // Force override the !important CSS rule
            elements.imagePreview.style.setProperty('display', 'block', 'important');
        }
        
        if (elements.imageDropZone) {
            elements.imageDropZone.style.display = 'none';
        }
        
        if (elements.imageMessageSection) {
            elements.imageMessageSection.classList.remove('image-message-section-hidden');
            elements.imageMessageSection.style.display = 'block';
            // Force override the !important CSS rule
            elements.imageMessageSection.style.setProperty('display', 'block', 'important');
        }
        
        // Hide progress indicator and show success
        hideImageUploadProgress();
        showImageUploadStatus('success', 'Image loaded successfully! Ready to create poll.');
        debugLog('Image preview setup complete');
    }
    
    function clearImagePreview() {
        debugLog('Clearing image preview');
        const elements = getElements();
        
        if (elements.imageInput) {
            elements.imageInput.value = '';
        }
        
        // Add CSS classes back and hide elements
        if (elements.imagePreview) {
            elements.imagePreview.classList.add('image-preview-hidden');
            elements.imagePreview.style.display = 'none';
            // Force override any inline styles
            elements.imagePreview.style.setProperty('display', 'none', 'important');
        }
        
        if (elements.imageDropZone) {
            elements.imageDropZone.style.display = 'block';
        }
        
        if (elements.imageMessageSection) {
            elements.imageMessageSection.classList.add('image-message-section-hidden');
            elements.imageMessageSection.style.display = 'none';
            // Force override any inline styles
            elements.imageMessageSection.style.setProperty('display', 'none', 'important');
        }
        
        if (elements.previewImg) {
            elements.previewImg.src = '';
        }
        
        if (elements.imageInfo) {
            elements.imageInfo.textContent = '';
        }
        
        const imageMessageText = document.getElementById('image-message-text');
        if (imageMessageText) {
            imageMessageText.value = '';
        }
        
        // Clear any status messages
        const statusDiv = document.getElementById('image-upload-status');
        if (statusDiv) {
            statusDiv.innerHTML = '';
        }
    }
    
    // Public API
    return {
        init: function() {
            debugLog('Initializing image upload functionality');
            console.log('🔍 IMAGE UPLOAD - Starting initialization'); // Always log this
            
            const elements = getElements();
            
            const elementStatus = {
                imageDropZone: !!elements.imageDropZone,
                imageInput: !!elements.imageInput,
                imagePreview: !!elements.imagePreview,
                previewImg: !!elements.previewImg,
                imageInfo: !!elements.imageInfo,
                removeImageBtn: !!elements.removeImageBtn,
                imageMessageSection: !!elements.imageMessageSection
            };
            
            debugLog('Elements found:', elementStatus);
            console.log('🔍 IMAGE UPLOAD - Elements found:', elementStatus); // Always log this

            if (!elements.imageDropZone || !elements.imageInput) {
                debugLog('Image upload elements not found, skipping initialization');
                console.log('🔍 IMAGE UPLOAD - Required elements missing, skipping initialization');
                return false;
            }

            // Check if already initialized to prevent duplicate event listeners
            // But allow re-initialization if the click handler is missing
            const hasClickHandler = elements.imageDropZone._pollyClickHandler;
            if (elements.imageDropZone.dataset.initialized === 'true' && hasClickHandler) {
                debugLog('Drop zone already initialized with handlers, skipping');
                console.log('🔍 IMAGE UPLOAD - Already initialized with handlers, skipping');
                return false;
            }
            
            // Mark as initialized
            elements.imageDropZone.dataset.initialized = 'true';
            
            debugLog('Setting up event listeners');
            console.log('🔍 IMAGE UPLOAD - Setting up event listeners');
            
            // Event listeners with enhanced debugging
            // Store reference to click handler for initialization check
            elements.imageDropZone._pollyClickHandler = handleDropZoneClick;
            elements.imageDropZone.addEventListener('click', handleDropZoneClick);
            elements.imageDropZone.addEventListener('dragover', handleDragOver);
            elements.imageDropZone.addEventListener('dragleave', handleDragLeave);
            elements.imageDropZone.addEventListener('drop', handleDrop);
            elements.imageInput.addEventListener('change', handleFileInputChange);
            
            // Test click handler immediately
            console.log('🔍 IMAGE UPLOAD - Testing drop zone click handler setup');
            console.log('🔍 IMAGE UPLOAD - Drop zone element:', elements.imageDropZone);
            console.log('🔍 IMAGE UPLOAD - Drop zone classes:', elements.imageDropZone.className);
            console.log('🔍 IMAGE UPLOAD - Drop zone style:', elements.imageDropZone.style.cssText);
            
            if (elements.removeImageBtn) {
                elements.removeImageBtn.addEventListener('click', clearImagePreview);
            }
            
            debugLog('Image upload initialization complete');
            console.log('🔍 IMAGE UPLOAD - Initialization complete!');
            return true;
        },
        
        // Expose utility functions for external use
        clearPreview: clearImagePreview,
        showError: showImageError,
        showStatus: showImageUploadStatus
    };
})();
