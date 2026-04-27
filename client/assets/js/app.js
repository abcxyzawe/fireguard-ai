/* FireGuard Client App - Shared JS */

// ============================================================
// TAILWIND CONFIG (inline so each page can extend)
// ============================================================
window.applyTailwindConfig = () => {
  if (typeof tailwind === 'undefined') return;
  tailwind.config = {
    theme: {
      extend: {
        fontFamily: {
          display: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
          sans: ['Inter', 'system-ui', 'sans-serif'],
          mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
        },
        colors: {
          bg: {
            base: '#05070B',
            soft: '#0B0E14',
            card: '#12161F',
            hover: '#1A1F2B',
          },
          flame: {
            50: '#FFF4ED', 100: '#FFE3D0', 200: '#FFC4A0', 300: '#FF9B66',
            400: '#FF6F2C', 500: '#F04E17', 600: '#D13904', 700: '#A82A03',
            800: '#7A1F02', 900: '#541503',
          },
          cyan: { glow: '#7FDBFF' },
        },
      },
    },
  };
};
window.applyTailwindConfig();

// ============================================================
// MOCK AUTH (for demo)
// ============================================================
const Auth = {
  KEY: 'fireguard_session',
  login(user) {
    localStorage.setItem(this.KEY, JSON.stringify({
      name: user.name || 'Quốc Anh',
      email: user.email || 'admin@fireguard.ai',
      avatar: user.avatar || 'assets/images/avatar_2.jpg',
      role: user.role || 'Chủ hộ',
      loggedAt: Date.now(),
    }));
  },
  logout() { localStorage.removeItem(this.KEY); location.href = 'login.html'; },
  user() {
    try { return JSON.parse(localStorage.getItem(this.KEY)); }
    catch { return null; }
  },
  isLoggedIn() { return !!this.user(); },
  requireAuth() {
    if (!this.isLoggedIn()) { location.href = 'login.html'; return false; }
    return true;
  },
};
window.Auth = Auth;

// ============================================================
// MOCK DATA (for demo)
// ============================================================
const MockData = {
  cameras: [
    { id: 'cam1', name: 'Phòng khách', status: 'online', location: 'Tầng 1', fps: 15, resolution: '800×600', lastSeen: 'Vừa xong' },
    { id: 'cam2', name: 'Phòng bếp', status: 'online', location: 'Tầng 1', fps: 15, resolution: '800×600', lastSeen: 'Vừa xong' },
    { id: 'cam3', name: 'Phòng ngủ chính', status: 'online', location: 'Tầng 2', fps: 14, resolution: '800×600', lastSeen: '2 giây' },
    { id: 'cam4', name: 'Gara xe', status: 'offline', location: 'Tầng hầm', fps: 0, resolution: '-', lastSeen: '1 giờ trước' },
  ],
  stats: {
    systemUptime: 99.8,
    camerasOnline: 3,
    camerasTotal: 4,
    detectionsToday: 0,
    falsePositivesBlocked: 12,
    lastCheck: 'Vừa xong',
  },
  events: [
    { id: 1, type: 'info', title: 'Hệ thống khởi động', time: 'Hôm nay, 08:00', cam: null, icon: 'ph-power' },
    { id: 2, type: 'warn', title: 'CAM4 mất kết nối', time: 'Hôm nay, 10:23', cam: 'cam4', icon: 'ph-warning' },
    { id: 3, type: 'info', title: 'Phát hiện chuyển động', time: 'Hôm nay, 11:15', cam: 'cam1', icon: 'ph-person' },
    { id: 4, type: 'blocked', title: 'Chặn cảnh báo sai (đèn LED)', time: 'Hôm nay, 12:47', cam: 'cam2', icon: 'ph-shield-check' },
    { id: 5, type: 'info', title: 'Hệ thống tự kiểm tra', time: 'Hôm nay, 14:00', cam: null, icon: 'ph-check-circle' },
    { id: 6, type: 'blocked', title: 'Chặn cảnh báo sai (ánh nắng)', time: 'Hôm qua, 16:32', cam: 'cam1', icon: 'ph-shield-check' },
    { id: 7, type: 'alert', title: 'Phát hiện lửa — đã dập tắt', time: '2 ngày trước, 19:45', cam: 'cam2', icon: 'ph-fire' },
  ],
};
window.MockData = MockData;

// ============================================================
// UI HELPERS
// ============================================================
function $(sel, root = document) { return root.querySelector(sel); }
function $$(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }
window.$ = $; window.$$ = $$;

// Sidebar mobile toggle
function initSidebar() {
  const toggleBtn = $('#sidebarToggle');
  const sidebar = $('#sidebar');
  const backdrop = $('#sidebarBackdrop');
  if (!toggleBtn || !sidebar) return;

  const open = () => {
    sidebar.classList.add('translate-x-0');
    sidebar.classList.remove('-translate-x-full');
    if (backdrop) backdrop.classList.remove('hidden');
  };
  const close = () => {
    sidebar.classList.remove('translate-x-0');
    sidebar.classList.add('-translate-x-full');
    if (backdrop) backdrop.classList.add('hidden');
  };

  toggleBtn.addEventListener('click', () => {
    const closed = sidebar.classList.contains('-translate-x-full');
    closed ? open() : close();
  });
  if (backdrop) backdrop.addEventListener('click', close);
}

// User dropdown toggle
function initUserMenu() {
  const btn = $('#userMenuBtn');
  const menu = $('#userMenu');
  if (!btn || !menu) return;
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    menu.classList.toggle('hidden');
  });
  document.addEventListener('click', () => menu.classList.add('hidden'));
  const logoutBtn = $('#logoutBtn');
  if (logoutBtn) logoutBtn.addEventListener('click', (e) => {
    e.preventDefault();
    Auth.logout();
  });
}

// Populate user info
function populateUser() {
  const u = Auth.user();
  if (!u) return;
  $$('[data-user-name]').forEach(el => { el.textContent = u.name; });
  $$('[data-user-email]').forEach(el => { el.textContent = u.email; });
  $$('[data-user-avatar]').forEach(el => { el.src = u.avatar; });
  $$('[data-user-role]').forEach(el => { el.textContent = u.role; });
}

// Toast notification (XSS-safe: uses textContent)
function toast(msg, type = 'info', duration = 3500) {
  let container = $('#toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'fixed top-5 right-5 z-[100] space-y-2';
    document.body.appendChild(container);
  }
  const colors = {
    info: 'border-cyan-glow/30 bg-cyan-glow/10 text-cyan-glow',
    success: 'border-green-500/30 bg-green-500/10 text-green-400',
    warn: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-400',
    error: 'border-red-500/30 bg-red-500/10 text-red-400',
  };
  const icons = { info: 'ph-info', success: 'ph-check-circle', warn: 'ph-warning', error: 'ph-x-circle' };
  const el = document.createElement('div');
  el.className = `flex items-center gap-2.5 px-4 py-3 rounded-xl border backdrop-blur-md ${colors[type]} fade-in-up shadow-lg min-w-[280px]`;
  const icon = document.createElement('i');
  icon.className = `ph-bold ${icons[type]}`;
  const span = document.createElement('span');
  span.className = 'text-sm font-medium';
  span.textContent = msg;
  el.appendChild(icon);
  el.appendChild(span);
  container.appendChild(el);
  setTimeout(() => {
    el.style.transition = 'opacity 0.3s';
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 300);
  }, duration);
}
window.toast = toast;

// Sidebar + user menu + user data wiring is done inside FG.renderShell (layout.js)
// on every authed page. Login/signup pages don't need these. So nothing to run here.
