// Typewriter Effect Configuration
const typewriterConfig = {
    texts: [
      "I can tell you about lighting technicalities",
      "I can recommend the perfect lighting options", 
      "I can analyze a Dialux report and remake it with LuxSCale",
      "I can make you a sketch lighting design from an image"
    ],
    typeSpeed: 100,
    deleteSpeed: 50,
    pauseTime: 2000,
    startDelay: 500
  };

  // Typewriter Effect Implementation
  class TypewriterEffect {
    constructor(config) {
      this.config = config;
      this.currentTextIndex = 0;
      this.currentCharIndex = 0;
      this.isDeleting = false;
      this.isActive = true;
      this.input = null;
      this.cursor = null;
      this.init();
    }

    init() {
      this.input = document.getElementById('typewriterInput');
      this.cursor = document.getElementById('typewriterCursor');
      
      if (!this.input || !this.cursor) {
        console.error('Typewriter elements not found');
        return;
      }

      this.setupEventListeners();
      this.start();
    }

    setupEventListeners() {
      this.input.addEventListener('focus', () => this.pause());
      this.input.addEventListener('blur', () => this.resume());
      this.input.addEventListener('input', () => {
        if (this.input.value === '') {
          this.resume();
        } else {
          this.pause();
        }
      });
    }

    start() {
      setTimeout(() => {
        this.isActive = true;
        this.type();
      }, this.config.startDelay);
    }

    pause() {
      this.isActive = false;
      this.cursor.style.display = 'inline-block';
    }

    resume() {
      if (this.input.value === '') {
        this.isActive = true;
        this.currentTextIndex = 0;
        this.currentCharIndex = 0;
        this.isDeleting = false;
        this.type();
      }
    }

    type() {
      if (!this.isActive) return;

      const currentText = this.config.texts[this.currentTextIndex];
      
      if (this.isDeleting) {
        this.input.placeholder = currentText.substring(0, this.currentCharIndex - 1);
        this.currentCharIndex--;
        
        if (this.currentCharIndex === 0) {
          this.isDeleting = false;
          this.currentTextIndex = (this.currentTextIndex + 1) % this.config.texts.length;
          setTimeout(() => this.type(), this.config.typeSpeed);
          return;
        }
      } else {
        this.input.placeholder = currentText.substring(0, this.currentCharIndex + 1);
        this.currentCharIndex++;
        
        if (this.currentCharIndex === currentText.length) {
          setTimeout(() => {
            this.isDeleting = true;
            this.type();
          }, this.config.pauseTime);
          return;
        }
      }
      
      setTimeout(() => this.type(), this.isDeleting ? this.config.deleteSpeed : this.config.typeSpeed);
    }
  }

  // Initialize when DOM is loaded
  document.addEventListener('DOMContentLoaded', function() {
    new TypewriterEffect(typewriterConfig);
    initializeAuthToggle();
    initializeInterfaceToggle();
    initializeStudySteps();
    initializeUploadModals();
  });

  // Auth Form Toggle Functionality
  function initializeAuthToggle() {
    const loginBtn = document.getElementById('loginBtn');
    const signupBtn = document.getElementById('signupBtn');
    const loginForm = document.getElementById('loginForm');
    const signupForm = document.getElementById('signupForm');

    if (!loginBtn || !signupBtn || !loginForm || !signupForm) {
      console.error('Auth toggle elements not found');
      return;
    }

    // Show login form by default
    loginForm.classList.add('active');

    // Login button click handler
    loginBtn.addEventListener('click', function() {
      if (!loginForm.classList.contains('active')) {
        // Update button states
        loginBtn.classList.add('active');
        signupBtn.classList.remove('active');
        
        // Toggle forms with smooth transition
        toggleForms(loginForm, signupForm);
      }
    });

    // Signup button click handler
    signupBtn.addEventListener('click', function() {
      if (!signupForm.classList.contains('active')) {
        // Update button states
        signupBtn.classList.add('active');
        loginBtn.classList.remove('active');
        
        // Toggle forms with smooth transition
        toggleForms(signupForm, loginForm);
      }
    });
  }

  // Smooth form toggle function
  function toggleForms(showForm, hideForm) {
    // Mark the form to hide as previous
    hideForm.classList.add('prev');
    hideForm.classList.remove('active');
    
    // Show the new form
    showForm.classList.remove('prev');
    showForm.classList.add('active');
  }

  // Interface Toggle Functionality
  function initializeInterfaceToggle() {
    const chatBtn = document.getElementById('chatBtn');
    const studyBtn = document.getElementById('studyBtn');
    const chatInterface = document.getElementById('chatInterface');
    const studyInterface = document.getElementById('studyInterface');

    if (!chatBtn || !studyBtn || !chatInterface || !studyInterface) {
      console.error('Interface toggle elements not found');
      return;
    }

    // Show chat interface by default
    chatInterface.classList.add('active');

    // Chat button click handler
    chatBtn.addEventListener('click', function() {
      if (!chatInterface.classList.contains('active')) {
        // Update button states
        chatBtn.classList.add('active');
        studyBtn.classList.remove('active');
        
        // Toggle interfaces with smooth transition
        toggleInterfaces(chatInterface, studyInterface);
      }
    });

    // Study button click handler
    studyBtn.addEventListener('click', function() {
      if (!studyInterface.classList.contains('active')) {
        // Update button states
        studyBtn.classList.add('active');
        chatBtn.classList.remove('active');
        
        // Toggle interfaces with smooth transition
        toggleInterfaces(studyInterface, chatInterface);
      }
    });
  }

  // Smooth interface toggle function
  function toggleInterfaces(showInterface, hideInterface) {
    // Mark the interface to hide as previous
    hideInterface.classList.add('prev');
    hideInterface.classList.remove('active');
    
    // Show the new interface
    showInterface.classList.remove('prev');
    showInterface.classList.add('active');
  }

  // Study Steps Navigation Functionality
  function initializeStudySteps() {
    const continueToApplication = document.getElementById('continueToApplication');
    const backToArea = document.getElementById('backToArea');
    const continueFromApplication = document.getElementById('continueFromApplication');
    const defineAreaStep = document.getElementById('defineAreaStep');
    const chooseApplicationStep = document.getElementById('chooseApplicationStep');
    const applicationSelect = document.getElementById('applicationSelect');

    if (!continueToApplication || !backToArea || !continueFromApplication || 
        !defineAreaStep || !chooseApplicationStep || !applicationSelect) {
      console.error('Study step elements not found');
      return;
    }

    // Show define area step by default
    defineAreaStep.classList.add('active');

    // Continue to application step
    continueToApplication.addEventListener('click', function() {
      // Validate that at least one dimension is entered
      const dimensionInputs = defineAreaStep.querySelectorAll('.dimension-field');
      let hasValue = false;
      
      dimensionInputs.forEach(input => {
        if (input.value && parseFloat(input.value) > 0) {
          hasValue = true;
        }
      });

      if (hasValue) {
        toggleStudySteps(chooseApplicationStep, defineAreaStep);
      } else {
        // Show validation message or highlight empty fields
        alert('Please enter at least one dimension before continuing.');
      }
    });

    // Back to area step
    backToArea.addEventListener('click', function() {
      toggleStudySteps(defineAreaStep, chooseApplicationStep);
    });

    // Continue from application step
    continueFromApplication.addEventListener('click', function() {
      if (applicationSelect.value) {
        // Here you can add logic to proceed to the next step
        // For now, we'll just show an alert with the selected application
        const selectedApp = applicationSelect.options[applicationSelect.selectedIndex].text;
        alert(`Proceeding with ${selectedApp} application...`);
        
        // You can add more steps here or redirect to another page
        // For example: window.location.href = 'lighting-study.html';
      } else {
        alert('Please select an application type before continuing.');
      }
    });

    // Add visual feedback for dropdown selection
    applicationSelect.addEventListener('change', function() {
      if (this.value) {
        this.style.borderColor = 'var(--primary-color)';
        this.style.boxShadow = '0 0 0 2px rgba(235, 27, 38, 0.2)';
      } else {
        this.style.borderColor = 'transparent';
        this.style.boxShadow = 'none';
      }
    });
  }

  // Smooth study step toggle function
  function toggleStudySteps(showStep, hideStep) {
    // Mark the step to hide as previous
    hideStep.classList.add('prev');
    hideStep.classList.remove('active');
    
    // Show the new step
    showStep.classList.remove('prev');
    showStep.classList.add('active');
  }

  // Upload Modals Functionality
  function initializeUploadModals() {
    initializeDialuxModal();
    initializeImageModal();
  }

  // Dialux Modal Functionality
  function initializeDialuxModal() {
    const uploadArea = document.getElementById('dialuxUploadArea');
    const fileInput = document.getElementById('dialuxFileInput');
    const fileInfo = document.getElementById('dialuxFileInfo');
    const submitBtn = document.getElementById('dialuxSubmitBtn');

    if (!uploadArea || !fileInput || !fileInfo || !submitBtn) {
      console.error('Dialux modal elements not found');
      return;
    }

    // Click to upload
    uploadArea.addEventListener('click', () => {
      fileInput.click();
    });

    // File input change
    fileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        handleDialuxFile(e.target.files[0]);
      }
    });

    // Drag and drop
    uploadArea.addEventListener('dragover', (e) => {
      e.preventDefault();
      uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', () => {
      uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
      e.preventDefault();
      uploadArea.classList.remove('dragover');
      
      if (e.dataTransfer.files.length > 0) {
        handleDialuxFile(e.dataTransfer.files[0]);
      }
    });

    // Submit button
    submitBtn.addEventListener('click', () => {
      const file = fileInput.files[0];
      if (file) {
        processDialuxFile(file);
      }
    });
  }

  // Image Modal Functionality
  function initializeImageModal() {
    const uploadArea = document.getElementById('imageUploadArea');
    const fileInput = document.getElementById('imageFileInput');
    const imagePreview = document.getElementById('imagePreview');
    const previewImage = document.getElementById('previewImage');
    const fileInfo = document.getElementById('imageFileInfo');
    const submitBtn = document.getElementById('imageSubmitBtn');

    if (!uploadArea || !fileInput || !imagePreview || !previewImage || !fileInfo || !submitBtn) {
      console.error('Image modal elements not found');
      return;
    }

    // Click to upload
    uploadArea.addEventListener('click', () => {
      fileInput.click();
    });

    // File input change
    fileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        handleImageFile(e.target.files[0]);
      }
    });

    // Drag and drop
    uploadArea.addEventListener('dragover', (e) => {
      e.preventDefault();
      uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', () => {
      uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
      e.preventDefault();
      uploadArea.classList.remove('dragover');
      
      if (e.dataTransfer.files.length > 0) {
        handleImageFile(e.dataTransfer.files[0]);
      }
    });

    // Submit button
    submitBtn.addEventListener('click', () => {
      const file = fileInput.files[0];
      if (file) {
        processImageFile(file);
      }
    });
  }

  // Handle Dialux File
  function handleDialuxFile(file) {
    const uploadArea = document.getElementById('dialuxUploadArea');
    const fileInfo = document.getElementById('dialuxFileInfo');
    const submitBtn = document.getElementById('dialuxSubmitBtn');

    // Show loading state
    uploadArea.classList.add('loading');

    // Simulate brief processing delay
    setTimeout(() => {
      // Update file information
      document.getElementById('dialuxFileName').textContent = file.name;
      document.getElementById('dialuxFileSize').textContent = formatFileSize(file.size);
      document.getElementById('dialuxFileType').textContent = getFileType(file.name);
      document.getElementById('dialuxUploadDate').textContent = new Date().toLocaleDateString();

      // Show results and enable submit
      uploadArea.classList.remove('loading');
      fileInfo.style.display = 'block';
      submitBtn.disabled = false;
    }, 500);
  }

  // Handle Image File
  function handleImageFile(file) {
    const uploadArea = document.getElementById('imageUploadArea');
    const imagePreview = document.getElementById('imagePreview');
    const previewImage = document.getElementById('previewImage');
    const fileInfo = document.getElementById('imageFileInfo');
    const submitBtn = document.getElementById('imageSubmitBtn');

    // Show image preview
    const reader = new FileReader();
    reader.onload = (e) => {
      previewImage.src = e.target.result;
      imagePreview.style.display = 'block';
    };
    reader.readAsDataURL(file);

    // Show loading state
    uploadArea.classList.add('loading');

    // Simulate brief processing delay
    setTimeout(() => {
      // Update file information
      document.getElementById('imageFileName').textContent = file.name;
      document.getElementById('imageFileSize').textContent = formatFileSize(file.size);
      document.getElementById('imageFileType').textContent = getFileType(file.name);
      document.getElementById('imageUploadDate').textContent = new Date().toLocaleDateString();

      // Show results and enable submit
      uploadArea.classList.remove('loading');
      fileInfo.style.display = 'block';
      submitBtn.disabled = false;
    }, 500);
  }

  // Process Dialux File
  function processDialuxFile(file) {
    const submitBtn = document.getElementById('dialuxSubmitBtn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Processing...';

    // Simulate processing
    setTimeout(() => {
      alert('Dialux report processed successfully! The analysis has been completed and results are ready.');
      // Close modal
      const modal = bootstrap.Modal.getInstance(document.getElementById('dialuxModal'));
      modal.hide();
      
      // Reset form
      resetDialuxModal();
    }, 3000);
  }

  // Process Image File
  function processImageFile(file) {
    const submitBtn = document.getElementById('imageSubmitBtn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Processing...';

    // Simulate processing
    setTimeout(() => {
      alert('Image processed successfully! Lighting analysis has been completed.');
      // Close modal
      const modal = bootstrap.Modal.getInstance(document.getElementById('imageModal'));
      modal.hide();
      
      // Reset form
      resetImageModal();
    }, 3000);
  }

  // Reset Dialux Modal
  function resetDialuxModal() {
    const fileInput = document.getElementById('dialuxFileInput');
    const fileInfo = document.getElementById('dialuxFileInfo');
    const submitBtn = document.getElementById('dialuxSubmitBtn');

    fileInput.value = '';
    fileInfo.style.display = 'none';
    submitBtn.disabled = true;
    submitBtn.textContent = 'Process Report';
  }

  // Reset Image Modal
  function resetImageModal() {
    const fileInput = document.getElementById('imageFileInput');
    const imagePreview = document.getElementById('imagePreview');
    const fileInfo = document.getElementById('imageFileInfo');
    const submitBtn = document.getElementById('imageSubmitBtn');

    fileInput.value = '';
    imagePreview.style.display = 'none';
    fileInfo.style.display = 'none';
    submitBtn.disabled = true;
    submitBtn.textContent = 'Process Image';
  }

  // Utility Functions
  function getFileType(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    const types = {
      'pdf': 'PDF Document',
      'ldt': 'DIALux Project',
      'xlsx': 'Excel Spreadsheet',
      'jpg': 'JPEG Image',
      'jpeg': 'JPEG Image',
      'png': 'PNG Image',
      'gif': 'GIF Image',
      'webp': 'WebP Image'
    };
    return types[ext] || 'Unknown File Type';
  }

  function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

// ========================================
// Dynamic container height management
// Prevents absolute-positioned children from collapsing parent height
// ========================================
function syncContainerHeight(containerSelector, activeChildSelector) {
  const container = document.querySelector(containerSelector);
  if (!container) return;
  const active = container.querySelector(activeChildSelector + '.active');
  if (active) {
    container.style.minHeight = active.scrollHeight + 'px';
  }
}

function updateInterfaceHeight() {
  syncContainerHeight('.interface-container', '.interface-content');
}

function updateFormsHeight() {
  syncContainerHeight('.forms-container', '.auth-form');
}

function updateStudyHeight() {
  const studyInterface = document.getElementById('studyInterface');
  if (!studyInterface) return;
  const activeStep = studyInterface.querySelector('.study-step.active');
  if (activeStep) {
    studyInterface.style.minHeight = activeStep.scrollHeight + 'px';
  }
}

// Patch toggle functions to also update heights
const _origToggleInterfaces = toggleInterfaces;
window.toggleInterfaces = function(show, hide) {
  _origToggleInterfaces(show, hide);
  setTimeout(updateInterfaceHeight, 450);
};

const _origToggleForms = toggleForms;
window.toggleForms = function(show, hide) {
  _origToggleForms(show, hide);
  setTimeout(updateFormsHeight, 450);
};

const _origToggleSteps = toggleStudySteps;
window.toggleStudySteps = function(show, hide) {
  _origToggleSteps(show, hide);
  setTimeout(updateStudyHeight, 450);
};

window.addEventListener('load', () => {
  updateInterfaceHeight();
  updateFormsHeight();
  updateStudyHeight();
});

window.addEventListener('resize', () => {
  updateInterfaceHeight();
  updateFormsHeight();
  updateStudyHeight();
});
