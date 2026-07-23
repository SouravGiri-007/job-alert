/* ============================================
   Smart Job Alert - Main JavaScript
   ============================================ */

// Dark Mode Toggle
function initThemeToggle() {
    const toggle = document.getElementById('themeToggle');
    if (!toggle) return;

    const html = document.documentElement;
    const icon = toggle.querySelector('i');

    // Load saved preference
    const saved = localStorage.getItem('theme');
    if (saved === 'dark') {
        html.setAttribute('data-bs-theme', 'dark');
        if (icon) icon.className = 'bi bi-sun-fill';
    }

    toggle.addEventListener('click', () => {
        const isDark = html.getAttribute('data-bs-theme') === 'dark';
        if (isDark) {
            html.setAttribute('data-bs-theme', 'light');
            if (icon) icon.className = 'bi bi-moon-stars-fill';
            localStorage.setItem('theme', 'light');
        } else {
            html.setAttribute('data-bs-theme', 'dark');
            if (icon) icon.className = 'bi bi-sun-fill';
            localStorage.setItem('theme', 'dark');
        }
    });
}

// Auto-dismiss toasts
function initToasts() {
    const toasts = document.querySelectorAll('.toast.show');
    toasts.forEach((toast, index) => {
        const duration = parseInt(toast.getAttribute('data-duration')) || 4000;
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100px)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, duration + (index * 500));
    });
}

// Smooth scroll for anchor links
function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            const href = this.getAttribute('href');
            if (href === '#') return;
            const target = document.querySelector(href);
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            // If target doesn't exist on this page, let the browser handle it naturally
        });
    });
}

// Form validation enhancement
function initFormValidation() {
    const form = document.getElementById('subscribeForm');
    if (!form) return;

    form.addEventListener('submit', function (e) {
        const email = this.querySelector('input[name="email"]');
        if (email && email.value) {
            // Disable button to prevent double submit
            const btn = this.querySelector('button[type="submit"]');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Subscribing...';
            }
        }
    });
}

// Navbar scroll effect — add shadow class when scrolled
function initNavbarScroll() {
    const navbar = document.querySelector('.navbar');
    if (!navbar) return;

    const checkScroll = () => {
        if (window.scrollY > 20) {
            navbar.classList.add('navbar-scrolled');
        } else {
            navbar.classList.remove('navbar-scrolled');
        }
    };

    window.addEventListener('scroll', checkScroll, { passive: true });
    checkScroll();
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    initThemeToggle();
    initToasts();
    initSmoothScroll();
    initFormValidation();
    initNavbarScroll();
});