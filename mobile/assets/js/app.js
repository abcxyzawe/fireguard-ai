/* FireGuard Mobile — shared JS */

// Tailwind config
if (typeof tailwind !== 'undefined') {
  tailwind.config = {
    theme: {
      extend: {
        fontFamily: {
          display: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
          sans: ['Inter', 'system-ui', 'sans-serif'],
          mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
        },
        colors: {
          bg: { base: '#05070B', soft: '#0B0E14', card: '#12161F', hover: '#1A1F2B' },
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
}

// Mock session
const Auth = {
  KEY: 'fireguard_mobile_session',
  login(user) {
    localStorage.setItem(this.KEY, JSON.stringify({
      name: user.name || 'Quốc Anh',
      email: user.email || 'admin@fireguard.ai',
      avatar: user.avatar || 'assets/images/avatar.jpg',
      loggedAt: Date.now(),
    }));
  },
  logout() { localStorage.removeItem(this.KEY); location.href = 'login.html'; },
  user() { try { return JSON.parse(localStorage.getItem(this.KEY)); } catch { return null; } },
  isLoggedIn() { return !!this.user(); },
  requireAuth() {
    if (!this.isLoggedIn()) { location.href = 'login.html'; return false; }
    return true;
  },
};
window.Auth = Auth;

// Mock data (shared with web client style)
const MockData = {
  cameras: [
    { id: 'cam1', name: 'Phòng khách', status: 'online', location: 'Tầng 1', fps: 15, lastSeen: 'Vừa xong', img: 'assets/images/cam_living.jpg' },
    { id: 'cam2', name: 'Phòng bếp',   status: 'online', location: 'Tầng 1', fps: 15, lastSeen: 'Vừa xong', img: 'assets/images/cam_kitchen.jpg' },
    { id: 'cam3', name: 'Phòng ngủ',   status: 'online', location: 'Tầng 2', fps: 14, lastSeen: '2s trước', img: 'assets/images/hero.jpg' },
    { id: 'cam4', name: 'Gara xe',     status: 'offline', location: 'Tầng hầm', fps: 0, lastSeen: '1 giờ trước', img: null },
  ],
  events: [
    { type: 'alert',   title: 'Phát hiện lửa — đã dập',     time: '2 ngày trước',      cam: 'cam2', conf: 96.3 },
    { type: 'blocked', title: 'Chặn cảnh báo sai (LED)',    time: 'Hôm nay 12:47',     cam: 'cam2', conf: 42.1 },
    { type: 'blocked', title: 'Chặn cảnh báo sai (nắng)',   time: 'Hôm qua 16:32',     cam: 'cam1', conf: 38.4 },
    { type: 'warn',    title: 'CAM4 mất kết nối',           time: 'Hôm nay 10:23',     cam: 'cam4' },
    { type: 'info',    title: 'Hệ thống khởi động',         time: 'Hôm nay 08:00',     cam: null  },
    { type: 'info',    title: 'Phát hiện chuyển động',       time: 'Hôm nay 11:15',     cam: 'cam1' },
    { type: 'info',    title: 'Tự kiểm tra hoàn tất',        time: 'Hôm nay 14:00',     cam: null  },
  ],
  notifications: [
    { type: 'alert', title: 'Phát hiện lửa nhỏ — đã dập tắt', body: 'Hệ thống đã kích hoạt vòi phun trong 2.3 giây', time: 'Vừa xong', cam: 'CAM2', unread: true },
    { type: 'warn',  title: 'CAM4 mất kết nối',               body: 'Không nhận được ảnh trong 60 giây',               time: '2 phút trước', cam: 'CAM4', unread: true },
    { type: 'blocked', title: 'AI chặn cảnh báo sai',         body: 'Đèn LED gây nhiễu — không phải lửa',              time: '15 phút trước', cam: 'CAM2', unread: true },
    { type: 'info',  title: 'Tự kiểm tra hệ thống',           body: 'Tất cả thiết bị hoạt động bình thường',           time: '1 giờ trước', cam: null, unread: false },
    { type: 'info',  title: 'Cập nhật model AI',              body: 'YOLOv8s v4 — mAP 88.2%',                           time: 'Hôm qua', cam: null, unread: false },
  ],
};
window.MockData = MockData;

// Haptic-like feedback for supported devices
function haptic(ms = 10) {
  try { navigator.vibrate && navigator.vibrate(ms); } catch (_) {}
}
window.haptic = haptic;

// Toast
function toast(msg, type = 'info', duration = 2500) {
  let c = document.getElementById('toastContainer');
  if (!c) {
    c = document.createElement('div');
    c.id = 'toastContainer';
    c.className = 'fixed top-4 left-4 right-4 z-[100] space-y-2 pointer-events-none';
    c.style.maxWidth = '440px';
    c.style.margin = '0 auto';
    document.body.appendChild(c);
  }
  const tints = {
    info: 'border-cyan-glow/30 bg-cyan-glow/10 text-cyan-glow',
    success: 'border-green-500/30 bg-green-500/10 text-green-400',
    warn: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-400',
    error: 'border-red-500/30 bg-red-500/10 text-red-400',
  };
  const icons = { info: 'ph-info', success: 'ph-check-circle', warn: 'ph-warning', error: 'ph-x-circle' };
  const el = document.createElement('div');
  el.className = 'flex items-center gap-2.5 px-4 py-3 rounded-2xl border backdrop-blur-md shadow-xl fade-up ' + tints[type];
  const i = document.createElement('i'); i.className = 'ph-bold ' + icons[type];
  const s = document.createElement('span'); s.className = 'text-sm font-medium'; s.textContent = msg;
  el.appendChild(i); el.appendChild(s);
  c.appendChild(el);
  setTimeout(() => { el.style.transition = 'opacity .25s'; el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, duration);
}
window.toast = toast;

// Populate user placeholders
document.addEventListener('DOMContentLoaded', () => {
  const u = Auth.user();
  if (u) {
    document.querySelectorAll('[data-user-name]').forEach(el => { el.textContent = u.name; });
    document.querySelectorAll('[data-user-email]').forEach(el => { el.textContent = u.email; });
    document.querySelectorAll('[data-user-avatar]').forEach(el => { el.src = u.avatar; });
  }
});
