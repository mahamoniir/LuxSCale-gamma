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
    initializeChatPageHandoff();
    initializeStudySteps();
    initializeUploadModals();
    initializeRoomDrawing();
  });

  // Room Drawing (Box Studio Mini) Functionality
  function initializeRoomDrawing() {
    const inputs = ['dimA', 'dimB', 'dimC', 'dimD', 'dimHeight'];
    const colors = ['colorWallA', 'colorWallB', 'colorWallC', 'colorWallD', 'colorFloor'];
    
    const elements = {
      dimA: document.getElementById('dimA'),
      dimB: document.getElementById('dimB'),
      dimC: document.getElementById('dimC'),
      dimD: document.getElementById('dimD'),
      dimHeight: document.getElementById('dimHeight'),
      wallA: document.getElementById('wallAMini'),
      wallB: document.getElementById('wallBMini'),
      wallC: document.getElementById('wallCMini'),
      wallD: document.getElementById('wallDMini'),
      floor: document.getElementById('floorMini'),
      colorWallA: document.getElementById('colorWallA'),
      colorWallB: document.getElementById('colorWallB'),
      colorWallC: document.getElementById('colorWallC'),
      colorWallD: document.getElementById('colorWallD'),
      colorFloor: document.getElementById('colorFloor'),
      widthLine: document.getElementById('widthLineMini'),
      lengthLine: document.getElementById('lengthLineMini'),
      wrap: document.getElementById('projection-wrap-mini')
    };

    if (!elements.dimA || !elements.floor) return;

    function updateVisualization() {
      // Get values in meters, convert to px for visualization (1m = 40px)
      const scale = 40;
      const w1 = parseFloat(elements.dimA.value) || 0;
      const l1 = parseFloat(elements.dimB.value) || 0;
      const w2 = parseFloat(elements.dimC.value) || w1; // Default to w1 if empty
      const l2 = parseFloat(elements.dimD.value) || l1; // Default to l1 if empty
      const h = parseFloat(elements.dimHeight.value) || 0;

      const visW1 = w1 * scale;
      const visL1 = l1 * scale;
      const visW2 = w2 * scale;
      const visL2 = l2 * scale;
      const visH = h * scale;

      // Base visual constraints
      if (visW1 === 0 || visL1 === 0) {
        elements.wrap.style.opacity = '0.3';
        return;
      }
      elements.wrap.style.opacity = '1';

      // Floor (Base rectangle using Side 1 and Side 2)
      elements.floor.style.width = visW1 + 'px';
      elements.floor.style.height = visL1 + 'px';
      elements.floor.style.background = elements.colorFloor.value;
      elements.floor.querySelector('.wall-dims').textContent = `${w1}x${l1}m`;

      // Wall A (Top) - Side 1 x Height
      elements.wallA.style.width = visW1 + 'px';
      elements.wallA.style.height = visH + 'px';
      elements.wallA.style.background = elements.colorWallA.value;
      elements.wallA.querySelector('.wall-dims').textContent = `${w1}x${h}m`;

      // Wall B (Bottom) - Side 3 x Height
      elements.wallB.style.width = visW2 + 'px';
      elements.wallB.style.height = visH + 'px';
      elements.wallB.style.background = elements.colorWallB.value;
      elements.wallB.querySelector('.wall-dims').textContent = `${w2}x${h}m`;

      // Wall C (Left) - Height x Side 2
      elements.wallC.style.width = visH + 'px';
      elements.wallC.style.height = visL1 + 'px';
      elements.wallC.style.background = elements.colorWallC.value;
      elements.wallC.querySelector('.wall-dims').textContent = `${h}x${l1}m`;

      // Wall D (Right) - Height x Side 4
      elements.wallD.style.width = visH + 'px';
      elements.wallD.style.height = visL2 + 'px';
      elements.wallD.style.background = elements.colorWallD.value;
      elements.wallD.querySelector('.wall-dims').textContent = `${h}x${l2}m`;

      // Dimension labels
      elements.widthLine.querySelector('span').textContent = `W: ${w1}m`;
      elements.widthLine.querySelector('.dim-line').style.width = visW1 + 'px';
      
      elements.lengthLine.querySelector('span').textContent = `L: ${l1}m`;
      elements.lengthLine.querySelector('.dim-line').style.height = visL1 + 'px';

      // Auto-scale to fit container
      const container = document.getElementById('canvasScrollMini');
      if (container) {
        const padding = 140; // Extra padding for labels
        const totalW = visW1 + (visH * 2) + padding;
        const totalL = visL1 + (visH * 2) + padding;
        const scaleFit = Math.min(
          container.offsetWidth / totalW,
          container.offsetHeight / totalL,
          0.8 // Max scale 80% to keep it neat
        );
        elements.wrap.style.transform = `scale(${scaleFit})`;
      }
    }

    // Bind events
    inputs.forEach(id => {
      document.getElementById(id).addEventListener('input', updateVisualization);
    });
    colors.forEach(id => {
      document.getElementById(id).addEventListener('input', updateVisualization);
    });

    // Initial run
    updateVisualization();
  }

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

  function initializeChatPageHandoff() {
    const input = document.getElementById('typewriterInput');
    const sendBtn = document.getElementById('chatGoUpBtn')
      || document.querySelector('#chatInterface .btn-sc-circle');
    if (!input || !sendBtn) return;

    const CHAT_PREFILL_KEY = 'luxscale_chat_prefill_message';
    const targetUrl = 'chat-with-luxSCale.html';

    function forwardToChatPage() {
      const text = String(input.value || '').trim();
      if (!text) return;
      try {
        sessionStorage.setItem(CHAT_PREFILL_KEY, text);
      } catch (_err) {
        // Ignore storage failures and continue with redirect.
      }
      window.location.href = targetUrl;
    }

    sendBtn.addEventListener('click', function (e) {
      e.preventDefault();
      forwardToChatPage();
    });

    input.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      forwardToChatPage();
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
    const createStudyBtn = document.getElementById('createStudyBtn');
    const defineAreaStep = document.getElementById('defineAreaStep');
    const chooseApplicationStep = document.getElementById('chooseApplicationStep');
    const stdCategory = document.getElementById('stdCategory');
    const stdTask = document.getElementById('stdTask');

    if (!continueToApplication || !backToArea || !createStudyBtn || 
        !defineAreaStep || !chooseApplicationStep || !stdCategory || !stdTask) {
      console.warn('Some study step elements not found - this is expected if using standard selection');
      return;
    }

    // Show define area step by default
    defineAreaStep.classList.add('active');

    // Continue to application step
    continueToApplication.addEventListener('click', function() {
      // Validate that dimA and dimHeight are entered (minimum requirement)
      const dimA = document.getElementById('dimA');
      const dimHeight = document.getElementById('dimHeight');
      
      if (dimA && dimA.value && dimHeight && dimHeight.value) {
        toggleStudySteps(chooseApplicationStep, defineAreaStep);
      } else {
        alert('Please enter at least Side 1 and Height before continuing.');
      }
    });

    // Back to area step
    backToArea.addEventListener('click', function() {
      toggleStudySteps(defineAreaStep, chooseApplicationStep);
    });

    // Add visual feedback for inputs
    [stdCategory, stdTask].forEach(input => {
      input.addEventListener('input', function() {
        if (this.value) {
          this.style.borderColor = 'var(--primary-color)';
        } else {
          this.style.borderColor = 'rgba(255, 255, 255, 0.2)';
        }
      });
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
