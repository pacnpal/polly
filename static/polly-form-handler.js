/**
 * Polly Form Handler
 * Handles form functionality including emoji selection, Discord emojis, validation, 
 * channel loading, role management, and HTMX integration
 */

window.PollyFormHandler = (function() {
    'use strict';
    
    // Global state
    let currentEmojiButton = null;
    let isInitialLoad = true;
    let initialized = false;
    
    // Configuration
    const config = {
        emojiPickerWidth: 350,
        emojiPickerHeight: 300,
        channelCheckMaxAttempts: 50,
        channelCheckInterval: 100
    };
    
    function debugLog(message, ...args) {
        if (window.PollyDebug && window.PollyDebug.enabled) {
            console.log(`🔍 FORM HANDLER DEBUG - ${message}`, ...args);
        }
    }
    
    // Emoji picker functionality
    const EmojiPicker = {
        init: function() {
            const emojiPickerContainer = document.getElementById('emoji-picker-container');
            if (!emojiPickerContainer) {
                debugLog('Emoji picker container not found');
                return;
            }
            
            // Wait for emoji-picker element to be defined
            this.waitForEmojiPicker(() => {
                this.setupEmojiPicker();
            });
        },
        
        waitForEmojiPicker: function(callback) {
            if (customElements.get('emoji-picker')) {
                callback();
            } else {
                customElements.whenDefined('emoji-picker').then(callback);
            }
        },
        
        setupEmojiPicker: function() {
            const emojiPicker = document.querySelector('emoji-picker');
            const emojiPickerContainer = document.getElementById('emoji-picker-container');
            
            if (!emojiPicker) {
                console.warn('Emoji picker element not found');
                return;
            }

            // Handle emoji picker button clicks
            document.addEventListener('click', (e) => {
                if (e.target.classList.contains('emoji-picker-btn')) {
                    e.preventDefault();
                    currentEmojiButton = e.target;
                    this.positionEmojiPicker(e.target, emojiPickerContainer);
                }
            });

            // Handle emoji selection
            emojiPicker.addEventListener('emoji-click', (event) => {
                if (currentEmojiButton) {
                    const emoji = event.detail.emoji.unicode;
                    const optionNumber = currentEmojiButton.dataset.option;
                    
                    // Update button text and hidden input
                    currentEmojiButton.textContent = emoji;
                    const hiddenInput = currentEmojiButton.closest('.input-group').querySelector(`input[name="emoji${optionNumber}"]`);
                    if (hiddenInput) {
                        hiddenInput.value = emoji;
                    }
                    
                    // Hide the picker
                    emojiPickerContainer.style.display = 'none';
                    currentEmojiButton = null;
                }
            });

            // Hide emoji picker when clicking outside
            document.addEventListener('click', (e) => {
                if (emojiPickerContainer && !emojiPickerContainer.contains(e.target) && !e.target.classList.contains('emoji-picker-btn')) {
                    emojiPickerContainer.style.display = 'none';
                    currentEmojiButton = null;
                }
            });
        },
        
        positionEmojiPicker: function(button, container) {
            const rect = button.getBoundingClientRect();
            const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
            const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
            
            // Calculate position, but ensure it stays within viewport
            let left = rect.left + scrollLeft;
            let top = rect.bottom + scrollTop + 5;
            
            // Adjust if picker would go off-screen
            const viewportWidth = window.innerWidth;
            const viewportHeight = window.innerHeight;
            
            // Adjust horizontal position if needed
            if (left + config.emojiPickerWidth > viewportWidth) {
                left = rect.right + scrollLeft - config.emojiPickerWidth;
            }
            
            // Adjust vertical position if needed (show above button if no space below)
            if (top + config.emojiPickerHeight > viewportHeight + scrollTop) {
                top = rect.top + scrollTop - config.emojiPickerHeight - 5;
            }
            
            container.style.display = 'block';
            container.style.left = left + 'px';
            container.style.top = top + 'px';
        }
    };
    
    // Discord emoji functionality
    const DiscordEmoji = {
        init: function() {
            const serverSelectElement = document.getElementById('server-select');
            if (serverSelectElement) {
                serverSelectElement.addEventListener('change', () => {
                    // Clear custom Discord emojis when changing servers
                    this.resetEmojiButtonsToDefault();
                    // Then load new server's emojis
                    this.loadDiscordEmojis();
                });
                
                // Load emojis on initial page load if server is already selected
                if (serverSelectElement.value) {
                    this.loadDiscordEmojis();
                }
            }

            // Also load Discord emojis when HTMX updates the server selection
            document.addEventListener('htmx:afterSwap', (event) => {
                if (event.detail.target.id === 'channel-select') {
                    // Server was changed, reload Discord emojis
                    this.loadDiscordEmojis();
                }
            });
        },
        
        loadDiscordEmojis: function() {
            const serverSelectElement = document.getElementById('server-select');
            const serverId = serverSelectElement ? serverSelectElement.value : null;
            
            if (!serverId) {
                // Clear all Discord emoji dropdowns if no server selected
                document.querySelectorAll('.discord-emoji-dropdown').forEach(dropdown => {
                    dropdown.innerHTML = '<li><h6 class="dropdown-header">Select a server first</h6></li>';
                });
                // Reset all emoji buttons to default when no server selected
                this.resetEmojiButtonsToDefault();
                return;
            }

            // Load Discord emojis for the selected server
            fetch(`/htmx/guild-emojis/${serverId}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success && data.emojis) {
                        this.updateDiscordEmojiDropdowns(data.emojis);
                    } else {
                        this.updateDiscordEmojiDropdowns([]);
                    }
                })
                .catch(error => {
                    console.error('Error loading Discord emojis:', error);
                    this.updateDiscordEmojiDropdowns([]);
                });
        },
        
        resetEmojiButtonsToDefault: function() {
            // Get default emojis from global variable (set by backend)
            const defaultEmojis = window.POLLY_DEFAULT_EMOJIS || ['🇦', '🇧', '🇨', '🇩', '🇪', '🇫', '🇬', '🇭', '🇮', '🇯'];
            
            document.querySelectorAll('.emoji-picker-btn').forEach((button, index) => {
                const optionNumber = button.dataset.option;
                const hiddenInput = document.querySelector(`input[name="emoji${optionNumber}"]`);
                
                // Only reset if it's currently a custom Discord emoji (contains < and >)
                if (hiddenInput && hiddenInput.value.includes('<') && hiddenInput.value.includes('>')) {
                    const defaultEmoji = defaultEmojis[index] || defaultEmojis[0];
                    // Reset button display back to text emoji
                    button.innerHTML = defaultEmoji;
                    button.title = ''; // Clear the title
                    hiddenInput.value = defaultEmoji;
                }
            });
        },
        
        updateDiscordEmojiDropdowns: function(emojis) {
            document.querySelectorAll('.discord-emoji-dropdown').forEach(dropdown => {
                if (emojis.length === 0) {
                    dropdown.innerHTML = '<li><h6 class="dropdown-header">No custom emojis found</h6></li>';
                    return;
                }

                let html = '<li><h6 class="dropdown-header">Discord Custom Emojis</h6></li>';
                html += '<li><hr class="dropdown-divider"></li>';
                html += '<li class="px-3 py-2">';
                html += '<div class="discord-emoji-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(40px, 1fr)); gap: 8px; max-height: 200px; overflow-y: auto; padding: 8px;">';
                
                emojis.forEach(emoji => {
                    const emojiFormat = emoji.format;
                    const displayUrl = emoji.url;
                    
                    html += `
                        <div class="discord-emoji-item" 
                             style="cursor: pointer; padding: 4px; border-radius: 4px; transition: background-color 0.2s; display: flex; align-items: center; justify-content: center;"
                             data-emoji="${emojiFormat}" 
                             data-option="${dropdown.dataset.option}" 
                             data-emoji-url="${displayUrl}" 
                             data-emoji-name="${emoji.name}"
                             title=":${emoji.name}:"
                             onmouseover="this.style.backgroundColor='#f8f9fa'"
                             onmouseout="this.style.backgroundColor='transparent'">
                            <img src="${displayUrl}?size=32" 
                                 alt="${emoji.name}" 
                                 style="width: 32px; height: 32px; object-fit: contain;" 
                                 onerror="this.style.display='none';">
                        </div>
                    `;
                });

                html += '</div>';
                html += '</li>';
                dropdown.innerHTML = html;
            });

            // Add click handlers for Discord emoji items
            this.setupDiscordEmojiClickHandlers();
        },
        
        setupDiscordEmojiClickHandlers: function() {
            document.querySelectorAll('.discord-emoji-item').forEach(item => {
                item.addEventListener('click', function(e) {
                    e.preventDefault();
                    const emoji = this.dataset.emoji;
                    const emojiUrl = this.dataset.emojiUrl;
                    const emojiName = this.dataset.emojiName;
                    const optionNumber = this.dataset.option;
                    
                    // Find the corresponding emoji button and hidden input
                    const emojiButton = document.querySelector(`.emoji-picker-btn[data-option="${optionNumber}"]`);
                    const hiddenInput = document.querySelector(`input[name="emoji${optionNumber}"]`);
                    
                    if (emojiButton && hiddenInput) {
                        // Display the custom emoji using an img element in the button
                        emojiButton.innerHTML = `<img src="${emojiUrl}?size=24" alt="${emojiName}" style="width: 20px; height: 20px; object-fit: contain;" title=":${emojiName}:">`;
                        emojiButton.title = emoji;
                        hiddenInput.value = emoji;
                        
                        // Close the dropdown
                        const dropdown = this.closest('.dropdown-menu');
                        if (dropdown) {
                            const bsDropdown = bootstrap.Dropdown.getInstance(dropdown.previousElementSibling);
                            if (bsDropdown) {
                                bsDropdown.hide();
                            }
                        }
                    }
                });
            });
        }
    };
    
    // Channel loading functionality
    const ChannelLoader = {
        init: function() {
            const serverSelectElement = document.getElementById('server-select');
            if (!serverSelectElement) return;
            
            // Intercept HTMX requests to add the preselect_last_channel parameter
            document.addEventListener('htmx:configRequest', (event) => {
                if (event.detail.elt === serverSelectElement) {
                    const url = new URL(event.detail.path, window.location.origin);
                    url.searchParams.set('preselect_last_channel', isInitialLoad ? 'true' : 'false');
                    event.detail.path = url.pathname + url.search;
                    
                    // After the first request, all subsequent requests are server switches
                    isInitialLoad = false;
                }
            });
            
            // Load channels immediately if server is already selected
            this.loadChannelsIfServerSelected();
        },
        
        loadChannelsIfServerSelected: function() {
            const serverSelect = document.getElementById('server-select');
            const channelSelect = document.getElementById('channel-select');
            
            debugLog('Checking if channels need to be loaded');
            debugLog('Server select exists:', !!serverSelect);
            debugLog('Channel select exists:', !!channelSelect);
            
            if (!serverSelect || !channelSelect) {
                debugLog('Form elements not found, skipping channel load');
                return;
            }
            
            const currentServerId = serverSelect.value;
            debugLog('Current server ID:', currentServerId);
            debugLog('Channel select children count:', channelSelect.children.length);
            
            if (currentServerId && channelSelect.children.length <= 1) {
                debugLog('Server selected but no channels loaded, triggering load');
                
                // Use HTMX to load channels
                if (typeof htmx !== 'undefined') {
                    debugLog('Using HTMX to load channels');
                    htmx.ajax('GET', `/htmx/channels?server_id=${currentServerId}&preselect_last_channel=true`, {
                        target: '#channel-select',
                        swap: 'innerHTML'
                    });
                } else {
                    debugLog('HTMX not available, using fetch fallback');
                    // Fallback to fetch if HTMX is not available
                    fetch(`/htmx/channels?server_id=${currentServerId}&preselect_last_channel=true`)
                        .then(response => response.text())
                        .then(html => {
                            if (channelSelect) {
                                channelSelect.innerHTML = html;
                                debugLog('Channels loaded via fetch');
                            }
                        })
                        .catch(error => {
                            console.error('Error loading channels via fetch:', error);
                        });
                }
            } else if (currentServerId && channelSelect.children.length > 1) {
                debugLog('Server selected and channels already loaded');
            } else {
                debugLog('No server selected or elements not ready');
            }
        }
    };
    
    // Form validation
    const FormValidation = {
        init: function() {
            const openTimeInput = document.getElementById('open-time');
            const closeTimeInput = document.getElementById('close-time');
            const form = openTimeInput ? openTimeInput.closest('form') : null;
            
            if (!openTimeInput || !closeTimeInput) return;
            
            // Validate on input change
            openTimeInput.addEventListener('change', this.validateTimes);
            closeTimeInput.addEventListener('change', this.validateTimes);

            // Validate on form submission
            if (form) {
                form.addEventListener('submit', (e) => {
                    if (!this.validateTimes()) {
                        e.preventDefault();
                        e.stopPropagation();
                    }
                });
            }
        },
        
        validateTimes: function() {
            const openTimeInput = document.getElementById('open-time');
            const closeTimeInput = document.getElementById('close-time');
            const openTimeError = document.getElementById('open-time-error');
            const closeTimeError = document.getElementById('close-time-error');
            
            if (!openTimeInput || !closeTimeInput) return true;
            
            let isValid = true;

            // Clear previous errors
            openTimeInput.classList.remove('is-invalid');
            closeTimeInput.classList.remove('is-invalid');
            if (openTimeError) openTimeError.textContent = '';
            if (closeTimeError) closeTimeError.textContent = '';

            if (openTimeInput.value && closeTimeInput.value) {
                const openTime = new Date(openTimeInput.value);
                const closeTime = new Date(closeTimeInput.value);
                
                // Check if close time is after open time
                if (closeTime <= openTime) {
                    closeTimeInput.classList.add('is-invalid');
                    if (closeTimeError) closeTimeError.textContent = 'Close time must be after open time';
                    isValid = false;
                }
            }

            return isValid;
        }
    };
    
    // Checkbox functionality
    const CheckboxHandlers = {
        init: function() {
            this.initRolePingCheckbox();
            this.initOpenImmediatelyCheckbox();
            this.initMultipleChoiceCheckbox();
        },
        
        initRolePingCheckbox: function() {
            const pingRoleCheckbox = document.getElementById('ping-role-enabled');
            const roleSelectionContainer = document.getElementById('role-selection-container');
            
            if (!pingRoleCheckbox || !roleSelectionContainer) return;
            
            pingRoleCheckbox.addEventListener('change', function() {
                if (this.checked) {
                    roleSelectionContainer.style.display = 'block';
                } else {
                    roleSelectionContainer.style.display = 'none';
                    const roleSelect = document.getElementById('role-select');
                    if (roleSelect) {
                        roleSelect.value = '';
                    }
                }
            });
            
            // Initialize visibility based on current checkbox state
            if (pingRoleCheckbox.checked) {
                roleSelectionContainer.style.display = 'block';
            } else {
                roleSelectionContainer.style.display = 'none';
            }
        },
        
        initOpenImmediatelyCheckbox: function() {
            const openImmediatelyCheckbox = document.getElementById('open-immediately');
            const openTimeContainer = document.getElementById('open-time-container');
            const openTimeInput = document.getElementById('open-time');
            
            if (!openImmediatelyCheckbox || !openTimeContainer || !openTimeInput) return;
            
            openImmediatelyCheckbox.addEventListener('change', function() {
                if (this.checked) {
                    openTimeContainer.style.display = 'none';
                    openTimeInput.removeAttribute('required');
                    openTimeInput.value = '';
                } else {
                    openTimeContainer.style.display = 'block';
                    openTimeInput.setAttribute('required', 'required');
                }
            });
            
            // Initialize visibility based on current checkbox state
            if (openImmediatelyCheckbox.checked) {
                openTimeContainer.style.display = 'none';
                openTimeInput.removeAttribute('required');
            } else {
                openTimeContainer.style.display = 'block';
                openTimeInput.setAttribute('required', 'required');
            }
        },
        
        initMultipleChoiceCheckbox: function() {
            const multipleChoiceCheckbox = document.getElementById('multiple-choice-poll');
            const choiceLimitContainer = document.getElementById('choice-limit-container');
            
            if (!multipleChoiceCheckbox || !choiceLimitContainer) return;
            
            multipleChoiceCheckbox.addEventListener('change', function() {
                if (this.checked) {
                    choiceLimitContainer.style.display = 'block';
                } else {
                    choiceLimitContainer.style.display = 'none';
                    const maxChoicesSelect = document.getElementById('max-choices');
                    if (maxChoicesSelect) {
                        maxChoicesSelect.value = '';
                    }
                }
            });
            
            // Initialize visibility based on current checkbox state
            if (multipleChoiceCheckbox.checked) {
                choiceLimitContainer.style.display = 'block';
            } else {
                choiceLimitContainer.style.display = 'none';
            }
        }
    };
    
    // HTMX integration
    const HTMXIntegration = {
        init: function() {
            const form = document.querySelector('form[hx-post]');
            if (!form) return;
            
            const submitBtn = document.getElementById('submit-btn');
            const submitText = submitBtn?.querySelector('.submit-text');
            const loadingText = submitBtn?.querySelector('.loading-text');

            // HTMX event handlers for loading states
            document.addEventListener('htmx:beforeRequest', (event) => {
                if (event.detail.elt === form) {
                    // Show loading state
                    if (submitText && loadingText) {
                        submitText.classList.add('d-none');
                        loadingText.classList.remove('d-none');
                    }
                    
                    // Disable form elements to prevent multiple submissions
                    const formElements = form.querySelectorAll('input, select, textarea, button');
                    formElements.forEach(el => {
                        if (el.type !== 'submit') {
                            el.disabled = true;
                        }
                    });
                }
            });

            document.addEventListener('htmx:afterRequest', (event) => {
                if (event.detail.elt === form) {
                    // Hide loading state
                    if (submitText && loadingText) {
                        submitText.classList.remove('d-none');
                        loadingText.classList.add('d-none');
                    }
                    
                    // Re-enable form elements
                    const formElements = form.querySelectorAll('input, select, textarea, button');
                    formElements.forEach(el => {
                        el.disabled = false;
                    });
                }
            });

            // Handle validation errors
            document.addEventListener('htmx:responseError', (event) => {
                if (event.detail.elt === form) {
                    // Hide loading state on error
                    if (submitText && loadingText) {
                        submitText.classList.remove('d-none');
                        loadingText.classList.add('d-none');
                    }
                    
                    // Re-enable form elements
                    const formElements = form.querySelectorAll('input, select, textarea, button');
                    formElements.forEach(el => {
                        el.disabled = false;
                    });
                }
            });
        }
    };
    
    // Template data pre-filling
    const TemplateDataHandler = {
        init: function(templateData) {
            if (!templateData) {
                debugLog('No template data available');
                return;
            }
            
            debugLog('Pre-filling template data:', templateData);
            
            // Pre-fill server selection
            if (templateData.server_id) {
                this.preFillServer(templateData.server_id);
            }
            
            // Pre-fill options and emojis
            if (templateData.options && templateData.emojis) {
                this.preFillOptions(templateData.options, templateData.emojis);
            }
            
            // Pre-fill checkboxes
            this.preFillCheckboxes(templateData);
            
            // Pre-fill channel (with delay to allow server selection to load channels)
            if (templateData.channel_id) {
                this.preFillChannel(templateData.channel_id);
            }
            
            // Pre-fill role (with delay)
            if (templateData.ping_role_id) {
                this.preFillRole(templateData.ping_role_id);
            }
        },
        
        preFillServer: function(serverId) {
            const serverSelect = document.getElementById('server-select');
            if (serverSelect) {
                debugLog('Setting server value to:', serverId);
                serverSelect.value = serverId;
                
                // Trigger HTMX change event to load channels
                if (typeof htmx !== 'undefined') {
                    htmx.trigger(serverSelect, 'change');
                } else {
                    serverSelect.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
        },
        
        preFillOptions: function(options, emojis) {
            const optionsContainer = document.getElementById('options-container');
            if (!optionsContainer) return;
            
            // Clear existing options first
            optionsContainer.innerHTML = '';
            
            // Add options from template
            options.forEach((option, index) => {
                const optionNum = index + 1;
                const emoji = emojis[index] || '🇦';
                
                const optionHtml = `
                    <div class="input-group mb-2">
                        <div class="btn-group">
                            <button type="button" class="btn btn-outline-secondary emoji-picker-btn" data-option="${optionNum}">${emoji}</button>
                            <button type="button" class="btn btn-outline-secondary dropdown-toggle dropdown-toggle-split discord-emoji-btn" 
                                    data-bs-toggle="dropdown" data-option="${optionNum}" aria-expanded="false">
                                <span class="visually-hidden">Discord Emojis</span>
                            </button>
                            <ul class="dropdown-menu discord-emoji-dropdown" data-option="${optionNum}">
                                <li><h6 class="dropdown-header">Loading Discord emojis...</h6></li>
                            </ul>
                        </div>
                        <input type="text" class="form-control" name="option${optionNum}" placeholder="Option ${optionNum}" required value="${option}">
                        <input type="hidden" name="emoji${optionNum}" value="${emoji}">
                    </div>
                `;
                optionsContainer.insertAdjacentHTML('beforeend', optionHtml);
            });
        },
        
        preFillCheckboxes: function(templateData) {
            if (templateData.anonymous) {
                const anonymousCheckbox = document.getElementById('anonymous-poll');
                if (anonymousCheckbox) {
                    anonymousCheckbox.checked = true;
                }
            }

            if (templateData.multiple_choice) {
                const multipleChoiceCheckbox = document.getElementById('multiple-choice-poll');
                if (multipleChoiceCheckbox) {
                    multipleChoiceCheckbox.checked = true;
                }
            }

            if (templateData.ping_role_enabled) {
                const pingRoleCheckbox = document.getElementById('ping-role-enabled');
                const roleSelectionContainer = document.getElementById('role-selection-container');
                if (pingRoleCheckbox) {
                    pingRoleCheckbox.checked = true;
                    if (roleSelectionContainer) {
                        roleSelectionContainer.style.display = 'block';
                    }
                }
            }
        },
        
        preFillChannel: function(channelId) {
            debugLog('Setting up channel pre-selection for channel_id:', channelId);
            
            let channelCheckAttempts = 0;
            const maxChannelCheckAttempts = config.channelCheckMaxAttempts;
            
            const checkChannelLoad = setInterval(() => {
                channelCheckAttempts++;
                const channelSelect = document.getElementById('channel-select');
                
                debugLog(`Channel check attempt ${channelCheckAttempts}: channelSelect exists=${!!channelSelect}, children count=${channelSelect ? channelSelect.children.length : 0}`);
                
                if (channelSelect && channelSelect.children.length > 1) {
                    const targetOption = channelSelect.querySelector(`option[value="${channelId}"]`);
                    
                    if (targetOption) {
                        channelSelect.value = channelId;
                        debugLog('Successfully pre-selected channel:', channelId);
                        clearInterval(checkChannelLoad);
                    } else {
                        debugLog('Target channel not found in options, continuing to wait...');
                        
                        if (channelCheckAttempts >= maxChannelCheckAttempts) {
                            debugLog('Channel pre-selection timeout - target channel not available');
                            clearInterval(checkChannelLoad);
                        }
                    }
                } else if (channelCheckAttempts >= maxChannelCheckAttempts) {
                    debugLog('Channel pre-selection timeout - channels not loaded');
                    clearInterval(checkChannelLoad);
                }
            }, config.channelCheckInterval);
        },
        
        preFillRole: function(roleId) {
            const checkRoleLoad = setInterval(() => {
                const roleSelect = document.getElementById('role-select');
                if (roleSelect && roleSelect.children.length > 1) {
                    roleSelect.value = roleId;
                    clearInterval(checkRoleLoad);
                }
            }, 100);
            
            // Clear interval after 5 seconds to prevent infinite loop
            setTimeout(() => clearInterval(checkRoleLoad), 5000);
        }
    };
    
    // Public API
    return {
        init: function(options = {}) {
            if (initialized) {
                debugLog('Form handler already initialized, skipping');
                return;
            }
            
            debugLog('Initializing form handler');
            
            // Initialize all components
            EmojiPicker.init();
            DiscordEmoji.init();
            ChannelLoader.init();
            FormValidation.init();
            CheckboxHandlers.init();
            HTMXIntegration.init();
            
            // Handle template data if provided
            if (options.templateData) {
                // Delay template data handling to ensure DOM is ready
                setTimeout(() => {
                    TemplateDataHandler.init(options.templateData);
                }, 100);
            }
            
            // Use longer delays to ensure DOM is fully loaded for channel loading
            setTimeout(() => ChannelLoader.loadChannelsIfServerSelected(), 200);
            setTimeout(() => ChannelLoader.loadChannelsIfServerSelected(), 500);
            setTimeout(() => ChannelLoader.loadChannelsIfServerSelected(), 1000);
            
            initialized = true;
            debugLog('Form handler initialization complete');
        },
        
        // Expose individual components for external use
        EmojiPicker,
        DiscordEmoji,
        ChannelLoader,
        FormValidation,
        CheckboxHandlers,
        HTMXIntegration,
        TemplateDataHandler
    };
})();
