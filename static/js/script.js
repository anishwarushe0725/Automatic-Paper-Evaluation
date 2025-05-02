/**
 * Semantic Grader - Main JavaScript File
 * This file contains all the custom JavaScript functionality for the Semantic Grader application
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function(popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Close alerts automatically after 5 seconds
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert:not(.alert-persistent)');
        alerts.forEach(function(alert) {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);

    // File input enhancement
    const fileInputs = document.querySelectorAll('input[type="file"]');
    fileInputs.forEach(function(input) {
        input.addEventListener('change', function(e) {
            // Get the file name
            let fileName = '';
            if (this.files && this.files.length > 1) {
                fileName = (this.getAttribute('data-multiple-caption') || '{count} files selected').replace('{count}', this.files.length);
            } else {
                fileName = e.target.value.split('\\').pop();
            }
            
            // Show the file name next to the input if one exists
            if (fileName) {
                // If there's a label element that follows the input
                const label = this.nextElementSibling;
                if (label && label.tagName === 'LABEL') {
                    label.innerHTML = fileName;
                } else {
                    // Create a span to show the filename
                    let fileNameDisplay = this.parentElement.querySelector('.file-name');
                    if (!fileNameDisplay) {
                        fileNameDisplay = document.createElement('span');
                        fileNameDisplay.className = 'file-name ml-2';
                        this.parentElement.appendChild(fileNameDisplay);
                    }
                    fileNameDisplay.textContent = fileName;
                }
            }
        });
    });

    // Form validation
    const forms = document.querySelectorAll('.needs-validation');
    Array.from(forms).forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        }, false);
    });

    // Copy to clipboard functionality
    const copyButtons = document.querySelectorAll('.btn-copy');
    copyButtons.forEach(function(button) {
        button.addEventListener('click', function() {
            const textToCopy = this.getAttribute('data-copy');
            const textarea = document.createElement('textarea');
            textarea.value = textToCopy;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            
            // Show tooltip
            const tooltip = bootstrap.Tooltip.getInstance(this);
            if (tooltip) {
                this.setAttribute('data-bs-original-title', 'Copied!');
                tooltip.show();
                
                // Reset tooltip text
                setTimeout(() => {
                    this.setAttribute('data-bs-original-title', 'Copy to clipboard');
                }, 1000);
            }
        });
    });

    // Toggle password visibility
    const togglePasswordButtons = document.querySelectorAll('.toggle-password');
    togglePasswordButtons.forEach(function(button) {
        button.addEventListener('click', function() {
            const passwordInput = document.getElementById(this.getAttribute('data-target'));
            const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
            passwordInput.setAttribute('type', type);
            
            // Toggle icon
            this.querySelector('i').classList.toggle('fa-eye');
            this.querySelector('i').classList.toggle('fa-eye-slash');
        });
    });

    // Handle file upload previews
    const pdfFileInputs = document.querySelectorAll('input[type="file"][accept=".pdf"]');
    pdfFileInputs.forEach(function(input) {
        input.addEventListener('change', function() {
            const previewContainerId = this.getAttribute('data-preview');
            if (!previewContainerId) return;
            
            const previewContainer = document.getElementById(previewContainerId);
            if (!previewContainer) return;
            
            if (this.files && this.files[0]) {
                const reader = new FileReader();
                
                reader.onload = function(e) {
                    // Create preview element
                    previewContainer.innerHTML = `
                        <div class="pdf-preview-card">
                            <div class="pdf-preview-icon">
                                <i class="fas fa-file-pdf fa-3x text-danger"></i>
                            </div>
                            <div class="pdf-preview-info">
                                <p class="pdf-filename">${input.files[0].name}</p>
                                <p class="pdf-filesize">${(input.files[0].size / 1024 / 1024).toFixed(2)} MB</p>
                            </div>
                        </div>
                    `;
                };
                
                reader.readAsDataURL(this.files[0]);
            }
        });
    });

    // Confirmation dialogs
    const confirmButtons = document.querySelectorAll('[data-confirm]');
    confirmButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            if (!confirm(this.getAttribute('data-confirm'))) {
                e.preventDefault();
            }
        });
    });

    // Search functionality for tables
    const tableSearchInputs = document.querySelectorAll('.table-search');
    tableSearchInputs.forEach(function(input) {
        input.addEventListener('keyup', function() {
            const tableId = this.getAttribute('data-table');
            const table = document.getElementById(tableId);
            if (!table) return;
            
            const searchText = this.value.toLowerCase();
            const rows = table.querySelectorAll('tbody tr');
            
            rows.forEach(function(row) {
                const cells = row.querySelectorAll('td');
                let found = false;
                
                cells.forEach(function(cell) {
                    if (cell.textContent.toLowerCase().includes(searchText)) {
                        found = true;
                    }
                });
                
                row.style.display = found ? '' : 'none';
            });
        });
    });

    // Dashboard chart animation
    const charts = document.querySelectorAll('.chart-animate');
    if (charts.length) {
        charts.forEach(function(chart) {
            chart.style.opacity = '0';
            chart.style.transform = 'translateY(20px)';
            chart.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
        });
        
        // Animate charts when they come into view
        const observerOptions = {
            threshold: 0.1
        };
        
        const observer = new IntersectionObserver(function(entries) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    setTimeout(function() {
                        entry.target.style.opacity = '1';
                        entry.target.style.transform = 'translateY(0)';
                    }, 200);
                    observer.unobserve(entry.target);
                }
            });
        }, observerOptions);
        
        charts.forEach(function(chart) {
            observer.observe(chart);
        });
    }

    // Back to top button
    const backToTopButton = document.getElementById('back-to-top');
    if (backToTopButton) {
        window.addEventListener('scroll', function() {
            if (window.pageYOffset > 300) {
                backToTopButton.classList.add('show');
            } else {
                backToTopButton.classList.remove('show');
            }
        });
        
        backToTopButton.addEventListener('click', function() {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    }

    // Add scroll animation for anchor links
    const anchorLinks = document.querySelectorAll('a[href^="#"]:not([href="#"])');
    anchorLinks.forEach(function(link) {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.getAttribute('href');
            const targetElement = document.querySelector(targetId);
            
            if (targetElement) {
                const offset = targetElement.getBoundingClientRect().top + window.pageYOffset - 80;
                window.scrollTo({
                    top: offset,
                    behavior: 'smooth'
                });
            }
        });
    });

    // Handle batch upload functionality
    const batchUploadBtn = document.getElementById('batchUploadBtn');
    if (batchUploadBtn) {
        batchUploadBtn.addEventListener('click', function() {
            const fileCount = document.querySelector('input[name="answer_files"]').files.length;
            if (fileCount > 0) {
                this.innerHTML = `<i class="fas fa-spinner fa-spin me-2"></i>Processing ${fileCount} files...`;
                this.disabled = true;
            }
        });
    }

    // Initialize datepickers if available
    if (typeof flatpickr !== 'undefined') {
        flatpickr('.datepicker', {
            dateFormat: 'Y-m-d',
            allowInput: true
        });
    }

    // Add animation to dashboard cards
    const dashboardCards = document.querySelectorAll('.dashboard-card');
    dashboardCards.forEach(function(card, index) {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        
        setTimeout(function() {
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, 100 * index);
    });

    // Handle sidebar toggle if available
    const sidebarToggle = document.getElementById('sidebar-toggle');
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function() {
            document.body.classList.toggle('sidebar-collapsed');
            
            // Store the state in localStorage
            const isSidebarCollapsed = document.body.classList.contains('sidebar-collapsed');
            localStorage.setItem('sidebar-collapsed', isSidebarCollapsed);
        });
        
        // Check localStorage and apply sidebar state
        const isSidebarCollapsed = localStorage.getItem('sidebar-collapsed') === 'true';
        if (isSidebarCollapsed) {
            document.body.classList.add('sidebar-collapsed');
        }
    }
});
