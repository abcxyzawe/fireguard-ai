/* FireGuard Shared Layout Renderer
   Renders sidebar + topbar into DOM. Each page sets data-active="<key>" on body. */

// Mark that shell will be rendered — prevents app.js from double-initing handlers
window.__fgShellWillRender = true;

(function () {
  function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (k === 'class') el.className = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
      else if (v === true) el.setAttribute(k, '');
      else if (v !== false && v != null) el.setAttribute(k, v);
    });
    children.flat().forEach(c => {
      if (c == null || c === false) return;
      el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return el;
  }
  function icon(cls) { return h('i', { class: cls }); }

  function navLink(href, iconCls, label, key, badge) {
    const active = document.body.dataset.active === key;
    const a = h('a', {
      href,
      class: `nav-link flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium text-slate-300 hover:bg-white/5 transition ${active ? 'active' : ''}`,
    });
    a.appendChild(icon(`nav-icon ${iconCls} text-lg`));
    a.appendChild(h('span', {}, label));
    if (badge) a.appendChild(h('span', { class: 'ml-auto text-[10px] px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 font-semibold' }, badge));
    return a;
  }

  function renderSidebar() {
    const bg = h('div', { id: 'sidebarBackdrop', class: 'hidden lg:hidden fixed inset-0 bg-black/50 backdrop-blur-sm z-40' });

    const aside = h('aside', {
      id: 'sidebar',
      class: 'fixed inset-y-0 left-0 w-64 bg-bg-soft border-r border-white/5 -translate-x-full lg:translate-x-0 transition-transform duration-300 z-50 flex flex-col',
    });

    const logoBlock = h('div', { class: 'h-16 px-5 flex items-center gap-2.5 border-b border-white/5' });
    const logoWrap = h('div', { class: 'w-9 h-9 rounded-xl overflow-hidden ring-1 ring-flame-500/20' });
    logoWrap.appendChild(h('img', { src: 'assets/images/logo.jpg', alt: '', class: 'w-full h-full object-cover' }));
    const logoText = h('span', { class: 'font-display font-bold tracking-tight' });
    logoText.appendChild(document.createTextNode('Fire'));
    logoText.appendChild(h('span', { class: 'text-flame-400' }, 'Guard'));
    logoBlock.appendChild(logoWrap);
    logoBlock.appendChild(logoText);

    const nav = h('nav', { class: 'flex-1 py-5 px-3 space-y-0.5' });
    nav.appendChild(h('div', { class: 'px-3 pb-2 text-[10px] font-bold text-slate-500 tracking-widest uppercase' }, 'Menu chính'));
    nav.appendChild(navLink('dashboard.html', 'ph-fill ph-squares-four', 'Tổng quan', 'dashboard'));
    nav.appendChild(navLink('cameras.html', 'ph-bold ph-video-camera', 'Camera', 'cameras', '3/4'));
    nav.appendChild(navLink('history.html', 'ph-bold ph-clock-counter-clockwise', 'Lịch sử', 'history'));
    nav.appendChild(navLink('settings.html', 'ph-bold ph-gear-six', 'Cài đặt', 'settings'));
    nav.appendChild(h('div', { class: 'px-3 pt-6 pb-2 text-[10px] font-bold text-slate-500 tracking-widest uppercase' }, 'Hỗ trợ'));
    nav.appendChild(navLink('#', 'ph-bold ph-book-open', 'Tài liệu', 'docs'));
    nav.appendChild(navLink('#', 'ph-bold ph-lifebuoy', 'Liên hệ hỗ trợ', 'support'));

    const bottom = h('div', { class: 'p-4 border-t border-white/5' });
    const bottomCard = h('div', { class: 'p-3 rounded-xl bg-gradient-to-br from-flame-500/10 to-flame-700/5 border border-flame-500/20' });
    const topRow = h('div', { class: 'flex items-center gap-2 mb-2' });
    topRow.appendChild(h('span', { class: 'status-dot status-online' }));
    topRow.appendChild(h('span', { class: 'text-xs font-semibold text-white' }, 'Hệ thống ổn định'));
    bottomCard.appendChild(topRow);
    const uptimeTxt = h('div', { class: 'text-[11px] text-slate-400' });
    uptimeTxt.appendChild(document.createTextNode('Uptime: '));
    uptimeTxt.appendChild(h('span', { class: 'text-flame-400 font-mono font-bold' }, '99.8%'));
    bottomCard.appendChild(uptimeTxt);
    bottom.appendChild(bottomCard);

    aside.appendChild(logoBlock);
    aside.appendChild(nav);
    aside.appendChild(bottom);
    return [bg, aside];
  }

  function renderTopbar(pageTitle, breadcrumb) {
    const header = h('header', { class: 'sticky top-0 z-30 h-16 glass border-b border-white/5 flex items-center px-5 gap-3' });

    const toggle = h('button', { id: 'sidebarToggle', class: 'lg:hidden w-10 h-10 rounded-lg grid place-items-center hover:bg-white/5', 'aria-label': 'Menu' });
    toggle.appendChild(icon('ph-bold ph-list text-xl'));
    header.appendChild(toggle);

    const titleWrap = h('div', { class: 'hidden sm:block' });
    titleWrap.appendChild(h('div', { class: 'text-xs text-slate-500' }, breadcrumb));
    titleWrap.appendChild(h('h1', { class: 'font-display font-bold text-lg leading-none mt-0.5' }, pageTitle));
    header.appendChild(titleWrap);

    const searchWrap = h('div', { class: 'flex-1 max-w-md mx-auto relative hide-mobile' });
    searchWrap.appendChild(icon('ph-bold ph-magnifying-glass absolute left-4 top-1/2 -translate-y-1/2 text-slate-500'));
    searchWrap.appendChild(h('input', { type: 'text', placeholder: 'Tìm camera, sự kiện...', class: 'input-base w-full pl-10 pr-4 py-2 rounded-lg text-sm' }));
    searchWrap.appendChild(h('kbd', { class: 'absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-mono text-slate-500 bg-white/5 px-1.5 py-0.5 rounded' }, '⌘K'));
    header.appendChild(searchWrap);

    header.appendChild(h('div', { class: 'flex-1 sm:hidden' }));

    const actions = h('div', { class: 'flex items-center gap-2' });

    // Notification dropdown
    const notifWrap = h('div', { class: 'relative' });
    const bellBtn = h('button', { id: 'notifBtn', class: 'relative w-10 h-10 rounded-lg grid place-items-center hover:bg-white/5 transition', 'aria-label': 'Thông báo' });
    bellBtn.appendChild(icon('ph-bold ph-bell text-xl text-slate-300'));
    // Badge
    const badge = h('span', { class: 'absolute top-1.5 right-2 min-w-[16px] h-4 rounded-full bg-flame-500 text-[9px] font-bold text-white grid place-items-center px-1' }, '3');
    bellBtn.appendChild(badge);
    notifWrap.appendChild(bellBtn);

    const notifPanel = h('div', { id: 'notifPanel', class: 'hidden fixed sm:absolute left-2 right-2 sm:left-auto sm:right-0 top-16 sm:top-full sm:mt-2 sm:w-96 rounded-2xl glass shadow-2xl z-50 overflow-hidden' });
    const notifHeader = h('div', { class: 'flex items-center justify-between px-4 py-3 border-b border-white/5' });
    notifHeader.appendChild(h('div', { class: 'font-display font-bold text-sm' }, 'Thông báo'));
    notifHeader.appendChild(h('button', { class: 'text-[11px] text-flame-400 hover:text-flame-300 font-semibold' }, 'Đánh dấu đã đọc'));
    notifPanel.appendChild(notifHeader);

    const notifList = h('div', { class: 'max-h-80 overflow-y-auto' });
    const notifs = [
      { type: 'alert', title: 'Phát hiện lửa nhỏ — đã dập tắt', time: 'Vừa xong', cam: 'CAM2', unread: true, iconCls: 'ph-fill ph-fire', color: 'text-red-400', bg: 'bg-red-500/15' },
      { type: 'warn', title: 'CAM4 mất kết nối', time: '2 phút trước', cam: 'CAM4', unread: true, iconCls: 'ph-fill ph-warning', color: 'text-yellow-400', bg: 'bg-yellow-500/15' },
      { type: 'blocked', title: 'AI chặn cảnh báo sai (đèn LED)', time: '15 phút trước', cam: 'CAM2', unread: true, iconCls: 'ph-fill ph-shield-check', color: 'text-purple-400', bg: 'bg-purple-500/15' },
      { type: 'info', title: 'Hệ thống tự kiểm tra hoàn tất', time: '1 giờ trước', cam: null, unread: false, iconCls: 'ph-fill ph-check-circle', color: 'text-cyan-glow', bg: 'bg-cyan-glow/15' },
      { type: 'info', title: 'Cập nhật model AI thành công', time: 'Hôm qua', cam: null, unread: false, iconCls: 'ph-fill ph-download', color: 'text-cyan-glow', bg: 'bg-cyan-glow/15' },
    ];
    notifs.forEach(n => {
      const row = h('a', { href: 'history.html', class: `flex items-start gap-3 px-4 py-3 hover:bg-white/5 transition border-b border-white/5 last:border-b-0 ${n.unread ? 'bg-flame-500/[0.03]' : ''}` });
      const iconBox = h('div', { class: `flex-shrink-0 w-9 h-9 rounded-lg grid place-items-center ${n.bg}` });
      iconBox.appendChild(icon(`${n.iconCls} ${n.color}`));
      row.appendChild(iconBox);

      const body = h('div', { class: 'flex-1 min-w-0' });
      const titleRow = h('div', { class: 'flex items-start justify-between gap-2' });
      titleRow.appendChild(h('div', { class: 'text-sm font-semibold text-slate-100' }, n.title));
      if (n.unread) titleRow.appendChild(h('span', { class: 'flex-shrink-0 w-2 h-2 rounded-full bg-flame-500 mt-1.5' }));
      body.appendChild(titleRow);
      const metaRow = h('div', { class: 'mt-0.5 flex items-center gap-2 text-[11px] text-slate-500' });
      metaRow.appendChild(h('span', {}, n.time));
      if (n.cam) {
        metaRow.appendChild(h('span', { class: 'w-1 h-1 rounded-full bg-slate-700' }));
        metaRow.appendChild(h('span', { class: 'font-mono font-semibold text-slate-400' }, n.cam));
      }
      body.appendChild(metaRow);
      row.appendChild(body);
      notifList.appendChild(row);
    });
    notifPanel.appendChild(notifList);

    const notifFooter = h('a', { href: 'history.html', class: 'block text-center py-3 text-xs font-semibold text-flame-400 hover:bg-white/5 border-t border-white/5' }, 'Xem tất cả thông báo →');
    notifPanel.appendChild(notifFooter);
    notifWrap.appendChild(notifPanel);
    actions.appendChild(notifWrap);

    const userWrap = h('div', { class: 'relative' });
    const userBtn = h('button', { id: 'userMenuBtn', class: 'flex items-center gap-2 pl-2 pr-3 py-1.5 rounded-lg hover:bg-white/5 transition' });
    userBtn.appendChild(h('img', { 'data-user-avatar': '', src: 'assets/images/avatar_2.jpg', alt: '', class: 'w-8 h-8 rounded-lg object-cover ring-1 ring-white/10' }));
    const userInfo = h('div', { class: 'hidden sm:block text-left' });
    userInfo.appendChild(h('div', { 'data-user-name': '', class: 'text-xs font-semibold leading-none' }, 'Quốc Anh'));
    userInfo.appendChild(h('div', { 'data-user-role': '', class: 'text-[10px] text-slate-500 mt-0.5 leading-none' }, 'Chủ hộ'));
    userBtn.appendChild(userInfo);
    userBtn.appendChild(icon('ph-bold ph-caret-down text-xs text-slate-500 hidden sm:inline'));

    const userMenu = h('div', { id: 'userMenu', class: 'hidden absolute right-0 top-full mt-2 w-60 rounded-xl glass p-2 shadow-2xl z-50' });
    const infoHeader = h('div', { class: 'px-3 py-3 border-b border-white/5 mb-2' });
    infoHeader.appendChild(h('div', { 'data-user-name': '', class: 'text-sm font-semibold' }, 'Quốc Anh'));
    infoHeader.appendChild(h('div', { 'data-user-email': '', class: 'text-xs text-slate-500 mt-0.5 truncate' }, 'admin@fireguard.ai'));
    userMenu.appendChild(infoHeader);
    const mkItem = (href, iconCls, label, extra) => {
      const a = h('a', { href, class: `flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/5 text-sm ${extra || ''}` });
      a.appendChild(icon(iconCls));
      a.appendChild(document.createTextNode(label));
      return a;
    };
    userMenu.appendChild(mkItem('settings.html', 'ph-bold ph-user', ' Tài khoản'));
    userMenu.appendChild(mkItem('settings.html', 'ph-bold ph-gear-six', ' Cài đặt'));
    userMenu.appendChild(h('div', { class: 'h-px bg-white/5 my-1' }));
    const logout = mkItem('#', 'ph-bold ph-sign-out', ' Đăng xuất', 'hover:bg-red-500/10 text-red-400');
    logout.id = 'logoutBtn';
    userMenu.appendChild(logout);

    userWrap.appendChild(userBtn);
    userWrap.appendChild(userMenu);
    actions.appendChild(userWrap);
    header.appendChild(actions);

    return header;
  }

  window.FG = window.FG || {};
  window.FG.renderShell = function (opts) {
    const pageTitle = opts.pageTitle || 'Trang';
    const breadcrumb = opts.breadcrumb || 'Trang chủ';

    const [backdrop, sidebar] = renderSidebar();
    document.body.prepend(backdrop);
    document.body.prepend(sidebar);

    const contentWrap = h('div', { class: 'lg:pl-64' });
    const main = document.getElementById('pageMain');
    if (main) {
      main.parentNode.removeChild(main);
      contentWrap.appendChild(renderTopbar(pageTitle, breadcrumb));
      contentWrap.appendChild(main);
    }
    document.body.appendChild(contentWrap);

    // Wire up interactions
    const toggleBtn = document.getElementById('sidebarToggle');
    const sidebarEl = document.getElementById('sidebar');
    const bd = document.getElementById('sidebarBackdrop');
    if (toggleBtn && sidebarEl) {
      const open = () => { sidebarEl.classList.add('translate-x-0'); sidebarEl.classList.remove('-translate-x-full'); if (bd) bd.classList.remove('hidden'); };
      const close = () => { sidebarEl.classList.remove('translate-x-0'); sidebarEl.classList.add('-translate-x-full'); if (bd) bd.classList.add('hidden'); };
      toggleBtn.addEventListener('click', () => {
        sidebarEl.classList.contains('-translate-x-full') ? open() : close();
      });
      if (bd) bd.addEventListener('click', close);
    }
    const umBtn = document.getElementById('userMenuBtn');
    const umMenu = document.getElementById('userMenu');
    const notifBtn = document.getElementById('notifBtn');
    const notifPanel = document.getElementById('notifPanel');

    if (umBtn && umMenu) {
      umBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        umMenu.classList.toggle('hidden');
        if (notifPanel) notifPanel.classList.add('hidden');
      });
    }
    if (notifBtn && notifPanel) {
      notifBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        notifPanel.classList.toggle('hidden');
        if (umMenu) umMenu.classList.add('hidden');
      });
      notifPanel.addEventListener('click', (e) => e.stopPropagation());
    }
    document.addEventListener('click', () => {
      if (umMenu) umMenu.classList.add('hidden');
      if (notifPanel) notifPanel.classList.add('hidden');
    });
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) logoutBtn.addEventListener('click', (e) => { e.preventDefault(); Auth.logout(); });

    const u = Auth.user();
    if (u) {
      document.querySelectorAll('[data-user-name]').forEach(el => { el.textContent = u.name; });
      document.querySelectorAll('[data-user-email]').forEach(el => { el.textContent = u.email; });
      document.querySelectorAll('[data-user-avatar]').forEach(el => { el.src = u.avatar; });
      document.querySelectorAll('[data-user-role]').forEach(el => { el.textContent = u.role; });
    }
  };
})();
