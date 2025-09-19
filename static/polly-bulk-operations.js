/**
 * Polly Bulk Operations Manager
 * Handles client-side bulk operations, progress tracking, and user interactions
 */

class BulkOperationManager {
    constructor() {
        this.selectedPollIds = new Set();
        this.currentOperation = null;
        this.progressInterval = null;
        this.apiBase = '/super-admin/api/bulk';
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.loadCurrentSelection();
        this.updateUI();
    }
    
    setupEventListeners() {
        // Selection events
        document.addEventListener('change', (e) => {
            if (e.target.classList.contains('poll-checkbox')) {
                this.handlePollSelection(e);
            } else if (e.target.id === 'select-all') {
                this.handleSelectAll(e);
            }
        });
        
        // Bulk action buttons
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('bulk-action-btn')) {
                this.handleBulkAction(e);
            } else if (e.target.id === 'clear-selection') {
                this.clearSelection();
            } else if (e.target.id === 'cancel-operation') {
                this.cancelCurrentOperation();
            }
        });
        
        // Filter selection
        const filterButton = document.getElementById('select-by-filter');
        if (filterButton) {
            filterButton.addEventListener('click', () => this.selectByFilter());
        }
    }
    
    async loadCurrentSelection() {
        try {
            const response = await fetch(`${this.apiBase}/selection`);
            const data = await response.json();
            
            if (data.success) {
                this.selectedPollIds = new Set(data.data.selected_poll_ids);
                this.updateUI();
            }
        } catch (error) {
            console.error('Failed to load current selection:', error);
        }
    }
    
    handlePollSelection(event) {
        const checkbox = event.target;
        const pollId = parseInt(checkbox.value);
        
        if (checkbox.checked) {
            this.selectedPollIds.add(pollId);
        } else {
            this.selectedPollIds.delete(pollId);
        }
        
        this.updateSelection('add', checkbox.checked ? [pollId] : null);
        this.updateUI();
    }
    
    handleSelectAll(event) {
        const selectAll = event.target;
        const pollCheckboxes = document.querySelectorAll('.poll-checkbox');
        
        if (selectAll.checked) {
            // Select all visible polls
            const visiblePollIds = [];
            pollCheckboxes.forEach(checkbox => {
                checkbox.checked = true;
                const pollId = parseInt(checkbox.value);
                this.selectedPollIds.add(pollId);
                visiblePollIds.push(pollId);
            });
            this.updateSelection('add', visiblePollIds);
        } else {
            // Deselect all visible polls
            const visiblePollIds = [];
            pollCheckboxes.forEach(checkbox => {
                checkbox.checked = false;
                const pollId = parseInt(checkbox.value);
                this.selectedPollIds.delete(pollId);
                visiblePollIds.push(pollId);
            });
            this.updateSelection('remove', visiblePollIds);
        }
        
        this.updateUI();
    }
    
    async updateSelection(action, pollIds = null) {
        try {
            const response = await fetch(`${this.apiBase}/selection`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    action: action,
                    poll_ids: pollIds
                })
            });
            
            const data = await response.json();
            if (!data.success) {
                this.showAlert('Failed to update selection', 'error');
            }
        } catch (error) {
            console.error('Failed to update selection:', error);
            this.showAlert('Failed to update selection', 'error');
        }
    }
    
    clearSelection() {
        this.selectedPollIds.clear();
        
        // Uncheck all checkboxes
        document.querySelectorAll('.poll-checkbox').forEach(checkbox => {
            checkbox.checked = false;
        });
        document.getElementById('select-all').checked = false;
        
        this.updateSelection('clear');
        this.updateUI();
    }
    
    async selectByFilter() {
        const statusFilter = document.getElementById('status-filter')?.value;
        const serverFilter = document.getElementById('server-filter')?.value;
        const creatorFilter = document.getElementById('creator-filter')?.value;
        
        try {
            const response = await fetch(`${this.apiBase}/selection/filter`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    status: statusFilter || null,
                    server_id: serverFilter || null,
                    creator_id: creatorFilter || null
                })
            });
            
            const data = await response.json();
            if (data.success) {
                this.selectedPollIds = new Set(data.data.selected_poll_ids);
                this.showAlert(`Selected ${data.data.selection_count} polls matching filters`, 'success');
                this.updateUI();
                
                // Refresh the polls table to show selection
                this.refreshPollsTable();
            } else {
                this.showAlert('Failed to select by filter', 'error');
            }
        } catch (error) {
            console.error('Failed to select by filter:', error);
            this.showAlert('Failed to select by filter', 'error');
        }
    }
    
    updateUI() {
        const selectionCount = this.selectedPollIds.size;
        const toolbar = document.getElementById('bulk-operations-toolbar');
        const countElement = document.getElementById('selected-count');
        const bulkActions = document.getElementById('bulk-actions');
        
        if (countElement) {
            countElement.textContent = selectionCount;
        }
        
        if (toolbar) {
            if (selectionCount > 0) {
                toolbar.classList.remove('hidden');
            } else {
                toolbar.classList.add('hidden');
            }
        }
        
        // Update individual checkboxes
        document.querySelectorAll('.poll-checkbox').forEach(checkbox => {
            const pollId = parseInt(checkbox.value);
            checkbox.checked = this.selectedPollIds.has(pollId);
        });
        
        // Update select all checkbox
        const selectAllCheckbox = document.getElementById('select-all');
        if (selectAllCheckbox) {
            const visibleCheckboxes = document.querySelectorAll('.poll-checkbox');
            const visibleCheckedCount = Array.from(visibleCheckboxes).filter(cb => cb.checked).length;
            
            if (visibleCheckedCount === 0) {
                selectAllCheckbox.checked = false;
                selectAllCheckbox.indeterminate = false;
            } else if (visibleCheckedCount === visibleCheckboxes.length) {
                selectAllCheckbox.checked = true;
                selectAllCheckbox.indeterminate = false;
            } else {
                selectAllCheckbox.checked = false;
                selectAllCheckbox.indeterminate = true;
            }
        }
    }
    
    async handleBulkAction(event) {
        const action = event.target.dataset.action;
        const pollIds = Array.from(this.selectedPollIds);
        
        if (pollIds.length === 0) {
            this.showAlert('No polls selected', 'warning');
            return;
        }
        
        // Show confirmation for destructive operations
        if (['delete', 'close'].includes(action)) {
            const confirmed = await this.showConfirmationDialog(
                `Bulk ${action} operation`,
                `Are you sure you want to ${action} ${pollIds.length} polls?`,
                'This action cannot be undone.'
            );
            if (!confirmed) return;
        }
        
        // Get additional parameters based on action
        let parameters = {};
        if (action === 'reopen') {
            parameters = await this.getBulkReopenParameters();
            if (!parameters) return; // User cancelled
        }
        
        this.startBulkOperation(action, pollIds, parameters);
    }
    
    async getBulkReopenParameters() {
        return new Promise((resolve) => {
            const modal = this.createParametersModal('Bulk Reopen Options', [
                {
                    type: 'number',
                    name: 'extend_hours',
                    label: 'Extend by hours (optional)',
                    placeholder: '24'
                },
                {
                    type: 'checkbox',
                    name: 'reset_votes',
                    label: 'Reset all votes'
                }
            ]);
            
            modal.querySelector('.confirm-btn').addEventListener('click', () => {
                const formData = new FormData(modal.querySelector('form'));
                const parameters = {
                    extend_hours: formData.get('extend_hours') ? parseInt(formData.get('extend_hours')) : null,
                    reset_votes: formData.get('reset_votes') === 'on'
                };
                
                document.body.removeChild(modal);
                resolve(parameters);
            });
            
            modal.querySelector('.cancel-btn').addEventListener('click', () => {
                document.body.removeChild(modal);
                resolve(null);
            });
        });
    }
    
    async startBulkOperation(operationType, pollIds, parameters = {}) {
        try {
            // Add confirmation code for destructive operations
            if (operationType === 'delete') {
                parameters.confirmation_code = 'confirmed';
            }
            
            const response = await fetch(`${this.apiBase}/operation`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    operation_type: `${operationType}_polls`,
                    poll_ids: pollIds,
                    parameters: parameters
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.currentOperation = data.data.operation_id;
                this.showProgressModal(data.data);
                this.startProgressTracking();
                
                // Clear selection after starting operation
                this.clearSelection();
            } else {
                this.showAlert(`Failed to start ${operationType} operation: ${data.error.message}`, 'error');
            }
        } catch (error) {
            console.error('Failed to start bulk operation:', error);
            this.showAlert(`Failed to start ${operationType} operation`, 'error');
        }
    }
    
    startProgressTracking() {
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
        }
        
        this.progressInterval = setInterval(async () => {
            await this.updateProgress();
        }, 1000);
    }
    
    async updateProgress() {
        if (!this.currentOperation) return;
        
        try {
            const response = await fetch(`${this.apiBase}/operation/${this.currentOperation}/progress`);
            const data = await response.json();
            
            if (data.success) {
                this.updateProgressUI(data.data);
                
                if (['completed', 'failed', 'cancelled'].includes(data.data.status)) {
                    clearInterval(this.progressInterval);
                    this.progressInterval = null;
                    this.currentOperation = null;
                    this.showOperationResults(data.data);
                }
            }
        } catch (error) {
            console.error('Failed to fetch progress:', error);
        }
    }
    
    async cancelCurrentOperation() {
        if (!this.currentOperation) return;
        
        try {
            const response = await fetch(`${this.apiBase}/operation/${this.currentOperation}/cancel`, {
                method: 'POST'
            });
            
            const data = await response.json();
            if (data.success) {
                this.showAlert('Operation cancelled', 'info');
            } else {
                this.showAlert('Failed to cancel operation', 'error');
            }
        } catch (error) {
            console.error('Failed to cancel operation:', error);
            this.showAlert('Failed to cancel operation', 'error');
        }
    }
    
    showProgressModal(operationData) {
        const modal = document.createElement('div');
        modal.className = 'modal fade show';
        modal.style.display = 'block';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Bulk Operation Progress</h5>
                    </div>
                    <div class="modal-body">
                        <div class="operation-info mb-3">
                            <strong>Operation:</strong> <span id="operation-type">${operationData.operation_type}</span><br>
                            <strong>Total Polls:</strong> <span id="total-polls">${operationData.poll_count}</span>
                        </div>
                        
                        <div class="progress-container mb-3">
                            <div class="progress" style="height: 25px;">
                                <div id="progress-bar" class="progress-bar progress-bar-striped progress-bar-animated" 
                                     style="width: 0%"></div>
                            </div>
                            <div id="progress-text" class="mt-1">0 / ${operationData.poll_count} completed (0%)</div>
                        </div>
                        
                        <div id="current-item" class="mb-3">
                            <small class="text-muted">Preparing operation...</small>
                        </div>
                        
                        <div id="results-summary" class="row mb-3 d-none">
                            <div class="col-md-6">
                                <div class="text-success">
                                    ✅ <span id="success-count">0</span> successful
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="text-danger">
                                    ❌ <span id="error-count">0</span> failed
                                </div>
                            </div>
                        </div>
                        
                        <div id="error-details" class="d-none">
                            <h6>Recent Errors:</h6>
                            <div id="error-list" class="alert alert-danger" style="max-height: 200px; overflow-y: auto;">
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button id="cancel-operation" class="btn btn-secondary">Cancel Operation</button>
                        <button id="close-modal" class="btn btn-primary d-none">Close</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Close modal handlers
        modal.querySelector('#close-modal').addEventListener('click', () => {
            document.body.removeChild(modal);
        });
    }
    
    updateProgressUI(progressData) {
        const progressBar = document.getElementById('progress-bar');
        const progressText = document.getElementById('progress-text');
        const currentItem = document.getElementById('current-item');
        const successCount = document.getElementById('success-count');
        const errorCount = document.getElementById('error-count');
        const resultsSum = document.getElementById('results-summary');
        const errorDetails = document.getElementById('error-details');
        const errorList = document.getElementById('error-list');
        const cancelBtn = document.getElementById('cancel-operation');
        const closeBtn = document.getElementById('close-modal');
        
        // Update progress bar
        const percentage = progressData.progress_percentage;
        if (progressBar) {
            progressBar.style.width = `${percentage}%`;
            progressBar.textContent = `${Math.round(percentage)}%`;
        }
        
        // Update progress text
        if (progressText) {
            progressText.textContent = `${progressData.processed_items} / ${progressData.total_items} completed (${Math.round(percentage)}%)`;
        }
        
        // Update current item
        if (currentItem && progressData.current_item_name) {
            currentItem.innerHTML = `<small class="text-muted">Processing: ${progressData.current_item_name}</small>`;
        }
        
        // Update results
        if (successCount) successCount.textContent = progressData.successful_items;
        if (errorCount) errorCount.textContent = progressData.failed_items;
        
        // Show results summary if operation is running
        if (resultsSum && progressData.processed_items > 0) {
            resultsSum.classList.remove('d-none');
        }
        
        // Show errors if any
        if (errorDetails && progressData.errors && progressData.errors.length > 0) {
            errorDetails.classList.remove('d-none');
            if (errorList) {
                errorList.innerHTML = progressData.errors.map(error => 
                    `<div><strong>Poll ${error.item_id}:</strong> ${error.message}</div>`
                ).join('');
            }
        }
        
        // Update button states based on operation status
        if (progressData.status === 'completed' || progressData.status === 'failed' || progressData.status === 'cancelled') {
            if (cancelBtn) cancelBtn.classList.add('d-none');
            if (closeBtn) closeBtn.classList.remove('d-none');
            
            if (progressBar) {
                progressBar.classList.remove('progress-bar-animated');
                if (progressData.status === 'failed') {
                    progressBar.classList.add('bg-danger');
                } else if (progressData.status === 'cancelled') {
                    progressBar.classList.add('bg-warning');
                } else {
                    progressBar.classList.add('bg-success');
                }
            }
        }
    }
    
    showOperationResults(progressData) {
        const title = progressData.status === 'completed' ? 'Operation Completed' : 
                     progressData.status === 'failed' ? 'Operation Failed' : 'Operation Cancelled';
        
        let message = `Operation ${progressData.status}.\n`;
        message += `Processed: ${progressData.processed_items}/${progressData.total_items}\n`;
        message += `Successful: ${progressData.successful_items}\n`;
        message += `Failed: ${progressData.failed_items}`;
        
        this.showAlert(message, progressData.status === 'completed' ? 'success' : 'warning');
        
        // Refresh polls table to show changes
        this.refreshPollsTable();
    }
    
    refreshPollsTable() {
        // Trigger HTMX refresh of polls table
        const pollsContainer = document.getElementById('polls-container');
        if (pollsContainer && typeof htmx !== 'undefined') {
            htmx.trigger(pollsContainer, 'refresh');
        }
    }
    
    showAlert(message, type = 'info') {
        const alertContainer = document.getElementById('alert-container') || document.body;
        const alert = document.createElement('div');
        alert.className = `alert alert-${type} alert-dismissible fade show`;
        alert.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        alertContainer.appendChild(alert);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (alert.parentNode) {
                alert.parentNode.removeChild(alert);
            }
        }, 5000);
    }
    
    async showConfirmationDialog(title, message, warning = '') {
        return new Promise((resolve) => {
            const modal = document.createElement('div');
            modal.className = 'modal fade show';
            modal.style.display = 'block';
            modal.innerHTML = `
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">${title}</h5>
                        </div>
                        <div class="modal-body">
                            <p>${message}</p>
                            ${warning ? `<div class="alert alert-warning">${warning}</div>` : ''}
                        </div>
                        <div class="modal-footer">
                            <button class="btn btn-secondary cancel-btn">Cancel</button>
                            <button class="btn btn-danger confirm-btn">Confirm</button>
                        </div>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
            
            modal.querySelector('.confirm-btn').addEventListener('click', () => {
                document.body.removeChild(modal);
                resolve(true);
            });
            
            modal.querySelector('.cancel-btn').addEventListener('click', () => {
                document.body.removeChild(modal);
                resolve(false);
            });
        });
    }
    
    createParametersModal(title, fields) {
        const modal = document.createElement('div');
        modal.className = 'modal fade show';
        modal.style.display = 'block';
        
        const fieldsHtml = fields.map(field => {
            if (field.type === 'checkbox') {
                return `
                    <div class="mb-3 form-check">
                        <input type="checkbox" class="form-check-input" name="${field.name}" id="${field.name}">
                        <label class="form-check-label" for="${field.name}">${field.label}</label>
                    </div>
                `;
            } else {
                return `
                    <div class="mb-3">
                        <label for="${field.name}" class="form-label">${field.label}</label>
                        <input type="${field.type}" class="form-control" name="${field.name}" id="${field.name}" 
                               placeholder="${field.placeholder || ''}">
                    </div>
                `;
            }
        }).join('');
        
        modal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">${title}</h5>
                    </div>
                    <div class="modal-body">
                        <form>
                            ${fieldsHtml}
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary cancel-btn">Cancel</button>
                        <button class="btn btn-primary confirm-btn">Confirm</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        return modal;
    }
}

// Initialize bulk operations manager when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('bulk-operations-toolbar')) {
        window.bulkOperationManager = new BulkOperationManager();
    }
});

// Convenience functions for global access
function bulkOperation(action) {
    if (window.bulkOperationManager) {
        const event = { target: { dataset: { action } } };
        window.bulkOperationManager.handleBulkAction(event);
    }
}

function clearSelection() {
    if (window.bulkOperationManager) {
        window.bulkOperationManager.clearSelection();
    }
}

function selectByFilter() {
    if (window.bulkOperationManager) {
        window.bulkOperationManager.selectByFilter();
    }
}