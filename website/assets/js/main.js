/* FireGuard AI - Main JS */

(() => {
  // Navigation scroll effect
  const nav = document.getElementById('nav');
  const menuBtn = document.getElementById('menuBtn');
  const mobileMenu = document.getElementById('mobileMenu');

  const onScroll = () => {
    if (window.scrollY > 20) {
      nav.classList.add('scrolled');
    } else {
      nav.classList.remove('scrolled');
    }
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // Mobile menu toggle
  if (menuBtn && mobileMenu) {
    menuBtn.addEventListener('click', () => {
      const isOpen = !mobileMenu.classList.contains('hidden');
      if (isOpen) {
        mobileMenu.classList.add('hidden');
        nav.classList.remove('menu-open');
      } else {
        mobileMenu.classList.remove('hidden');
        nav.classList.add('menu-open');
      }
      // Toggle icon
      const icon = menuBtn.querySelector('i');
      icon.classList.toggle('ph-list');
      icon.classList.toggle('ph-x');
    });

    // Close on link click
    mobileMenu.querySelectorAll('a').forEach(a => {
      a.addEventListener('click', () => {
        mobileMenu.classList.add('hidden');
        nav.classList.remove('menu-open');
        const icon = menuBtn.querySelector('i');
        icon.classList.add('ph-list');
        icon.classList.remove('ph-x');
      });
    });
  }

  // Reveal on scroll (IntersectionObserver)
  const reveals = document.querySelectorAll('[data-reveal]');
  const io = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const el = entry.target;
        const delay = parseInt(el.dataset.revealDelay || '0', 10);
        setTimeout(() => el.classList.add('revealed'), delay);
        io.unobserve(el);
      }
    });
  }, { rootMargin: '0px 0px -80px 0px', threshold: 0.05 });

  reveals.forEach(el => io.observe(el));

  // Count-up numbers on stats (nice to have)
  const countUps = document.querySelectorAll('[data-count]');
  const countIO = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const el = entry.target;
      const target = parseFloat(el.dataset.count);
      const duration = 1500;
      const start = performance.now();
      const animate = (now) => {
        const progress = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = (target * eased).toFixed(target % 1 === 0 ? 0 : 1);
        if (progress < 1) requestAnimationFrame(animate);
      };
      requestAnimationFrame(animate);
      countIO.unobserve(el);
    });
  }, { threshold: 0.4 });
  countUps.forEach(el => countIO.observe(el));

  // Lazy cursor glow (subtle, desktop only)
  if (window.matchMedia('(pointer: fine)').matches) {
    const cursor = document.createElement('div');
    cursor.style.cssText = `
      position: fixed;
      width: 400px; height: 400px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(240,78,23,0.12), transparent 70%);
      pointer-events: none;
      transform: translate(-50%, -50%);
      z-index: 0;
      opacity: 0;
      transition: opacity 0.3s;
      mix-blend-mode: screen;
    `;
    document.body.appendChild(cursor);
    let active = false;
    document.addEventListener('mousemove', (e) => {
      cursor.style.left = e.clientX + 'px';
      cursor.style.top = e.clientY + 'px';
      if (!active) { cursor.style.opacity = '1'; active = true; }
    });
    document.addEventListener('mouseleave', () => {
      cursor.style.opacity = '0';
      active = false;
    });
  }
})();
