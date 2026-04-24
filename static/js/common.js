/* ======================================
   محلات الحبيشي - JavaScript المشترك
   ====================================== */

const STORE_PHONE = '771217771';
const STORE_EMAIL = 'yamenameen97@gmail.com';
let __memberSession = null;
let __adminAuthInitialized = false;

// ======================================
// إدارة التوست
// ======================================
function ensureToastContainer() {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }
  return container;
}

function showToast(message, type = 'info', duration = 4000) {
  const container = ensureToastContainer();
  const icons = {
    success: '✅',
    error: '❌',
    warning: '⚠️',
    info: 'ℹ️'
  };

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || icons.info}</span>
    <span class="toast-message">${message}</span>
    <button class="toast-close" onclick="this.parentElement.remove()">✕</button>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s ease forwards';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ======================================
// API Helpers
// ======================================
async function requestJSON(url, options = {}) {
  const res = await fetch(url, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    },
    ...options
  });

  let data = null;
  try {
    data = await res.json();
  } catch (_) {}

  if (!res.ok) {
    const err = new Error(data?.error || `HTTP ${res.status}`);
    err.status = res.status;
    err.payload = data;
    if (res.status === 401 && window.location.pathname.endsWith('admin.html')) {
      createAdminAuthOverlay();
    }
    throw err;
  }
  return data;
}

async function apiGet(table, params = {}) {
  const qs = new URLSearchParams(params).toString();
  return requestJSON(`tables/${table}${qs ? '?' + qs : ''}`, { method: 'GET' });
}

async function apiGetById(table, id) {
  return requestJSON(`tables/${table}/${id}`, { method: 'GET' });
}

async function apiCreate(table, data) {
  return requestJSON(`tables/${table}`, {
    method: 'POST',
    body: JSON.stringify(data)
  });
}

async function apiUpdate(table, id, data) {
  return requestJSON(`tables/${table}/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data)
  });
}

async function apiPatch(table, id, data) {
  return requestJSON(`tables/${table}/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data)
  });
}

async function apiDelete(table, id) {
  await requestJSON(`tables/${table}/${id}`, { method: 'DELETE' });
  return true;
}

let __storeSettings = null;

async function applyStoreDescriptionTargets() {
  try {
    const data = await requestJSON('/api/store/settings', { method: 'GET' });
    __storeSettings = data || {};

    const description = String(data?.store_description || '').trim();
    const phone = String(data?.phone || STORE_PHONE).trim();
    const email = String(data?.email || STORE_EMAIL).trim();
    const location = String(data?.location || 'إب - المجمعة، اليمن').trim();
    const workingHours = String(data?.working_hours || '8 صباحاً - 9 مساءً').trim();
    const externalLink = String(data?.external_link || 'alhabeshi-stores.html').trim();
    const footerNote = String(data?.footer_note || '').trim();
    const tickerItems = Array.isArray(data?.ticker_items)
      ? data.ticker_items.filter(Boolean)
      : [];

    if (description) {
      document.querySelectorAll('.store-description-target').forEach(el => {
        el.textContent = description;
      });
    }

    document.querySelectorAll('a[href^="tel:"]').forEach(el => {
      el.href = `tel:+967${phone.replace(/^0+/, '')}`;
      el.textContent = phone;
    });

    document.querySelectorAll('a[href^="mailto:"]').forEach(el => {
      el.href = `mailto:${email}`;
      el.textContent = email;
    });

    const topbar = document.querySelector('.topbar');
    if (topbar) {
      const infoBlocks = topbar.querySelectorAll('.topbar-info');
      if (infoBlocks[0]) {
        infoBlocks[0].innerHTML = `
          <span><i class="fas fa-map-marker-alt"></i> ${location}</span>
          <span><i class="fas fa-phone"></i> <a href="tel:+967${phone.replace(/^0+/, '')}" style="color:inherit;text-decoration:none">${phone}</a></span>
          <span><i class="fas fa-envelope"></i> <a href="mailto:${email}" style="color:inherit;text-decoration:none">${email}</a></span>
          <span><i class="fas fa-clock"></i> ساعات العمل: ${workingHours}</span>
        `;
      }
    }

    const ticker = document.getElementById('tickerContent');
    if (ticker && tickerItems.length) {
      const doubled = [...tickerItems, ...tickerItems];
      ticker.innerHTML = doubled.map(item => `<span>${item}</span>`).join('');
    }

    const footerLink = document.querySelector('a[href="alhabeshi-stores.html"]');
    if (footerLink && externalLink) {
      footerLink.href = externalLink;
      footerLink.textContent = externalLink;
    }

    document.querySelectorAll('.footer-bottom p:first-child').forEach(el => {
      if (footerNote) el.textContent = footerNote;
    });
  } catch (_) {}
}

async function loadPublicNotifications() {
  try {
    if (window.location.pathname.endsWith('admin.html')) return;
    const result = await requestJSON('/api/public/notifications', { method: 'GET' });
    const items = result?.data || [];
    const nextItem = items.find(item => !sessionStorage.getItem(`site_notice_${item.id}`));
    if (!nextItem) return;
    sessionStorage.setItem(`site_notice_${nextItem.id}`, '1');
    showToast(`🔔 ${nextItem.title}\n${nextItem.message}`, 'info', 7000);
  } catch (_) {}
}

// ======================================
// تنسيق الأرقام والتواريخ
// ======================================
function formatPrice(price) {
  return new Intl.NumberFormat('ar-YE').format(price || 0) + ' ريال';
}

function formatDate(timestamp) {
  if (!timestamp) return '-';
  const date = new Date(timestamp);
  return date.toLocaleDateString('ar-YE', {
    year: 'numeric', month: 'long', day: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}

function formatDateShort(timestamp) {
  if (!timestamp) return '-';
  return new Date(timestamp).toLocaleDateString('ar-YE');
}

// ======================================
// حالة الطلب
// ======================================
const orderStatuses = {
  'جديد': { class: 'badge-info', icon: '🆕' },
  'قيد المعالجة': { class: 'badge-warning', icon: '⚙️' },
  'جاهز': { class: 'badge-success', icon: '✅' },
  'تم التسليم': { class: 'badge-dark', icon: '📦' },
  'ملغي': { class: 'badge-danger', icon: '❌' }
};

function getStatusBadge(status) {
  const info = orderStatuses[status] || { class: 'badge-dark', icon: '❓' };
  return `<span class="badge ${info.class}">${info.icon} ${status}</span>`;
}

// ======================================
// Modal Helpers
// ======================================
function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
  }
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.style.display = 'none';
    document.body.style.overflow = '';
  }
}

document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.style.display = 'none';
    document.body.style.overflow = '';
  }
});

// ======================================
// الشريط العلوي
// ======================================
function rebuildNavbarMenu() {
  const list = document.querySelector('.navbar-links');
  if (!list) return;
  list.innerHTML = `
    <li><a href="index.html"><i class="fas fa-home"></i> الرئيسية</a></li>
    <li><a href="chat.html"><i class="fas fa-comments"></i> مراسلة الإدارة</a></li>
    <li><a href="new-products.html"><i class="fas fa-star"></i> الأصناف الجديدة</a></li>
    <li><a href="offers.html"><i class="fas fa-tags"></i> العروض</a></li>
    <li><a href="offers.html#competitions"><i class="fas fa-trophy"></i> المسابقات</a></li>
    <li><a href="subscribe.html"><i class="fas fa-bell"></i> صفحة الاشتراك</a></li>
    <li><a href="#" data-member-menu-link><i class="fas fa-user-circle"></i> حساب الزائر</a></li>
    <li><a href="about.html"><i class="fas fa-info-circle"></i> معلومات عن المحل</a></li>
    <li><a href="#" data-logout-menu-link><i class="fas fa-sign-out-alt"></i> تسجيل الخروج من الصفحة</a></li>
    <li><a href="order.html"><i class="fas fa-shopping-cart"></i> اطلب الآن</a></li>
    <li><a href="admin.html" style="background: rgba(243,156,18,0.2); border-radius: 8px;">
      <i class="fas fa-cog"></i> الإدارة
      <span class="nav-badge" id="orders-badge" style="display:none">0</span>
    </a></li>
  `;

  list.querySelector('[data-member-menu-link]')?.addEventListener('click', (e) => {
    e.preventDefault();
    openMemberAuthModal(__memberSession ? 'login' : 'register');
  });

  list.querySelector('[data-logout-menu-link]')?.addEventListener('click', async (e) => {
    e.preventDefault();
    await logoutCurrentPageMember();
  });
}

function initNavbar() {
  const toggle = document.querySelector('.navbar-toggle');
  const links = document.querySelector('.navbar-links');
  if (toggle && links && !toggle.dataset.bound) {
    toggle.dataset.bound = '1';
    toggle.addEventListener('click', () => links.classList.toggle('open'));
  }
  if (links) {
    links.querySelectorAll('a').forEach(a => {
      if (a.dataset.bound === '1') return;
      a.dataset.bound = '1';
      a.addEventListener('click', () => links.classList.remove('open'));
    });
  }

  const currentPage = window.location.pathname.split('/').pop() || 'index.html';
  const currentHash = window.location.hash || '';
  document.querySelectorAll('.navbar-links a').forEach(a => {
    a.classList.remove('active');
    const href = a.getAttribute('href') || '';
    if (href === '#') return;
    if (href === currentPage || href === window.location.pathname || (currentPage === '' && href === 'index.html')) {
      a.classList.add('active');
    }
    if (currentPage === 'offers.html' && href === `offers.html${currentHash}`) {
      a.classList.add('active');
    }
  });
}

function enhanceNavbarLinks() {
  rebuildNavbarMenu();
}

// ======================================
// عداد الطلبات
// ======================================
async function updateOrdersBadge() {
  try {
    const isAdminPage = window.location.pathname.endsWith('admin.html');
    if (!isAdminPage) return;
    const data = await apiGet('orders', { limit: 200 });
    const newOrders = data.data ? data.data.filter(o => o.status === 'جديد').length : 0;
    const badge = document.getElementById('orders-badge');
    if (badge) {
      badge.textContent = newOrders;
      badge.style.display = newOrders > 0 ? 'inline-flex' : 'none';
    }
  } catch(_) {}
}

// ======================================
// أدوات واجهة مشتركة
// ======================================
function validateYemenPhone(phone) {
  const digits = String(phone || '').replace(/\D/g, '');
  return /^(?:967|0)?7\d{8}$/.test(digits);
}

function shareCurrentPage(title = document.title) {
  const data = { title, text: 'محلات الحبيشي | ' + title, url: window.location.href };
  if (navigator.share) {
    navigator.share(data).catch(() => {});
  } else {
    navigator.clipboard.writeText(window.location.href).then(() => showToast('تم نسخ رابط الصفحة', 'success'));
  }
}

function injectFloatingShareButton() {
  if (document.getElementById('floatingShareBtn')) return;
  const btn = document.createElement('button');
  btn.id = 'floatingShareBtn';
  btn.type = 'button';
  btn.innerHTML = '<i class="fas fa-share-alt"></i>';
  btn.title = 'مشاركة الصفحة';
  btn.setAttribute('aria-label', 'مشاركة الصفحة');
  btn.style.cssText = 'position:fixed;left:18px;bottom:18px;z-index:2500;width:54px;height:54px;border:none;border-radius:50%;background:linear-gradient(135deg,#1a5276,#2e86c1);color:#fff;box-shadow:0 10px 25px rgba(26,82,118,.28);cursor:pointer;font-size:1.1rem;display:flex;align-items:center;justify-content:center;';
  btn.onclick = () => shareCurrentPage();
  document.body.appendChild(btn);
}

function injectAdminShortcut() {
  if (document.getElementById('adminQuickShortcut')) return;
  const a = document.createElement('a');
  a.id = 'adminQuickShortcut';
  a.href = 'admin.html';
  a.title = 'لوحة الإدارة';
  a.innerHTML = '<i class="fas fa-user-shield"></i>';
  a.style.cssText = 'position:fixed;top:82px;left:18px;z-index:2400;width:48px;height:48px;border-radius:14px;background:linear-gradient(135deg,#f39c12,#e67e22);color:#fff;text-decoration:none;display:flex;align-items:center;justify-content:center;font-size:1.15rem;box-shadow:0 10px 25px rgba(230,126,34,.28);';
  document.body.appendChild(a);
}

function injectFaqHelpers() {
  document.querySelectorAll('.faq-question').forEach(btn => {
    if (btn.dataset.bound === '1') return;
    btn.dataset.bound = '1';
    btn.addEventListener('click', () => {
      const item = btn.closest('.faq-item');
      if (!item) return;
      const answer = item.querySelector('.faq-answer');
      const isOpen = item.classList.contains('open');
      item.parentElement?.querySelectorAll('.faq-item').forEach(other => {
        other.classList.remove('open');
        const otherAnswer = other.querySelector('.faq-answer');
        if (otherAnswer) otherAnswer.style.maxHeight = null;
      });
      if (!isOpen) {
        item.classList.add('open');
        if (answer) answer.style.maxHeight = answer.scrollHeight + 'px';
      }
    });
  });
}

// ======================================
// عضوية الزوار
// ======================================
function injectMemberNavButton() {
  const nav = document.querySelector('.navbar-links');
  if (!nav || nav.querySelector('[data-member-auth-link]')) return;
  const li = document.createElement('li');
  li.innerHTML = `<a href="#" data-member-auth-link style="background:rgba(39,174,96,.12);border-radius:8px"><i class="fas fa-user-plus"></i> <span id="memberNavText">تسجيل / دخول</span></a>`;
  nav.appendChild(li);
  li.querySelector('a').addEventListener('click', (e) => {
    e.preventDefault();
    openMemberAuthModal();
  });
}

function createMemberAuthModal() {
  if (document.getElementById('memberAuthModal')) return;
  const modal = document.createElement('div');
  modal.id = 'memberAuthModal';
  modal.className = 'modal-overlay';
  modal.style.display = 'none';
  modal.innerHTML = `
    <div class="modal" style="max-width:520px">
      <div class="modal-header">
        <span><i class="fas fa-user-plus"></i> حساب الزوار والعملاء</span>
        <button class="modal-close" onclick="closeModal('memberAuthModal')">✕</button>
      </div>
      <div class="modal-body">
        <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;">
          <button class="btn btn-primary btn-sm" type="button" onclick="switchMemberTab('register')">إنشاء حساب</button>
          <button class="btn btn-outline btn-sm" type="button" onclick="switchMemberTab('login')">تسجيل الدخول</button>
          <button class="btn btn-warning btn-sm" type="button" id="memberLogoutBtn" onclick="logoutMember()" style="display:none">تسجيل الخروج</button>
        </div>
        <div id="memberLoggedBox" class="alert alert-success" style="display:none"></div>
        <div id="memberRegisterTab">
          <div class="form-group"><label class="form-label">الاسم الكامل</label><input id="memberFullName" class="form-control" placeholder="اسم الزائر أو العميل"></div>
          <div class="form-group"><label class="form-label">رقم الجوال</label><input id="memberPhone" class="form-control" placeholder="771234567"></div>
          <div class="form-group"><label class="form-label">البريد الإلكتروني</label><input id="memberEmail" class="form-control" type="email" placeholder="name@example.com"></div>
          <div class="form-group"><label class="form-label">كلمة المرور</label><input id="memberPassword" class="form-control" type="password" placeholder="6 أحرف أو أكثر"></div>
          <label class="form-check" style="display:flex;gap:10px;align-items:center;margin-bottom:14px;background:#f8fbfd;padding:12px;border-radius:12px;border:1px solid #dce8f2">
            <input type="checkbox" id="memberWantsNotifications" checked>
            <span>أرغب في استلام إشعارات المنتجات الجديدة والعروض عبر البريد الإلكتروني</span>
          </label>
          <button class="btn btn-success w-100" type="button" onclick="registerMember()"><i class="fas fa-user-check"></i> إنشاء الحساب</button>
        </div>
        <div id="memberLoginTab" style="display:none">
          <div class="form-group"><label class="form-label">البريد الإلكتروني</label><input id="memberLoginEmail" class="form-control" type="email"></div>
          <div class="form-group"><label class="form-label">كلمة المرور</label><input id="memberLoginPassword" class="form-control" type="password"></div>
          <button class="btn btn-primary w-100" type="button" onclick="loginMember()"><i class="fas fa-sign-in-alt"></i> دخول</button>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
}

function switchMemberTab(tab) {
  document.getElementById('memberRegisterTab').style.display = tab === 'register' ? 'block' : 'none';
  document.getElementById('memberLoginTab').style.display = tab === 'login' ? 'block' : 'none';
}

async function openMemberAuthModal(defaultTab = 'register') {
  createMemberAuthModal();
  await refreshMemberSession();
  switchMemberTab(__memberSession ? 'login' : defaultTab);
  openModal('memberAuthModal');
}

async function refreshMemberSession() {
  try {
    const data = await requestJSON('/api/members/me', { method: 'GET' });
    __memberSession = data.member;
  } catch {
    __memberSession = null;
  }
  window.__memberSession = __memberSession;
  updateMemberUI();
  return __memberSession;
}

function updateMemberUI() {
  const navText = document.getElementById('memberNavText');
  if (navText) navText.textContent = __memberSession ? (__memberSession.full_name || 'حسابي') : 'تسجيل / دخول';
  const box = document.getElementById('memberLoggedBox');
  const logoutBtn = document.getElementById('memberLogoutBtn');
  if (box) {
    if (__memberSession) {
      box.style.display = 'block';
      box.innerHTML = `<strong>مرحباً ${__memberSession.full_name}</strong><br><small>${__memberSession.email}</small><br><small>${__memberSession.wants_notifications ? '🔔 الإشعارات البريدية مفعلة' : '🔕 الإشعارات البريدية غير مفعلة'}</small>`;
    } else {
      box.style.display = 'none';
      box.innerHTML = '';
    }
  }
  if (logoutBtn) logoutBtn.style.display = __memberSession ? 'inline-flex' : 'none';

  const nameInput = document.getElementById('customerName');
  const phoneInput = document.getElementById('customerPhone');
  const memberToggle = document.getElementById('isMember');
  const memberId = document.getElementById('memberId');
  const memberIdSection = document.getElementById('memberIdSection');
  if (__memberSession && nameInput && !nameInput.value) nameInput.value = __memberSession.full_name || '';
  if (__memberSession && phoneInput && !phoneInput.value) phoneInput.value = __memberSession.phone || '';
  if (__memberSession && memberToggle) {
    memberToggle.checked = true;
    if (memberId) memberId.value = __memberSession.id || '';
    if (memberIdSection) memberIdSection.style.display = 'block';
  }
}

async function registerMember() {
  const payload = {
    full_name: document.getElementById('memberFullName').value.trim(),
    phone: document.getElementById('memberPhone').value.trim(),
    email: document.getElementById('memberEmail').value.trim(),
    password: document.getElementById('memberPassword').value,
    wants_notifications: document.getElementById('memberWantsNotifications')?.checked
  };
  if (!payload.full_name || !payload.email || !payload.password) {
    showToast('يرجى تعبئة بيانات التسجيل', 'warning');
    return;
  }
  try {
    await requestJSON('/api/members/register', { method: 'POST', body: JSON.stringify(payload) });
    await refreshMemberSession();
    showToast('تم إنشاء الحساب بنجاح', 'success');
  } catch (e) {
    showToast(e.message || 'تعذر إنشاء الحساب', 'error');
  }
}

async function loginMember() {
  const payload = {
    email: document.getElementById('memberLoginEmail').value.trim(),
    password: document.getElementById('memberLoginPassword').value
  };
  try {
    await requestJSON('/api/members/login', { method: 'POST', body: JSON.stringify(payload) });
    await refreshMemberSession();
    showToast('تم تسجيل الدخول', 'success');
  } catch (e) {
    showToast(e.message || 'فشل تسجيل الدخول', 'error');
  }
}

async function logoutMember() {
  await requestJSON('/api/members/logout', { method: 'POST' });
  __memberSession = null;
  window.__memberSession = null;
  updateMemberUI();
  showToast('تم تسجيل الخروج', 'info');
}

async function logoutCurrentPageMember() {
  if (!__memberSession) {
    showToast('لا يوجد مستخدم مسجل حالياً', 'info');
    return;
  }
  await logoutMember();
}

// ======================================
// حماية لوحة الإدارة
// ======================================
function createAdminAuthOverlay() {
  if (__adminAuthInitialized || !window.location.pathname.endsWith('admin.html')) return;
  __adminAuthInitialized = true;
  const shell = document.createElement('div');
  shell.id = 'adminAuthShell';
  shell.style.cssText = 'position:fixed;inset:0;z-index:5000;background:rgba(10,22,34,.78);backdrop-filter:blur(5px);display:flex;align-items:center;justify-content:center;padding:20px;';
  shell.innerHTML = `
    <div style="width:min(560px,100%);background:#fff;border-radius:22px;box-shadow:0 30px 80px rgba(0,0,0,.25);overflow:hidden">
      <div style="padding:26px 26px 14px;background:linear-gradient(135deg,#1a5276,#2e86c1);color:#fff">
        <div style="font-size:1.4rem;font-weight:900;margin-bottom:6px">🔐 دخول لوحة الإدارة</div>
        <div style="opacity:.95;font-size:.92rem">أنشئ حساب الإدارة أول مرة ثم ادخل بالبريد وكلمة المرور المحفوظة في القاعدة</div>
      </div>
      <div style="padding:24px">
        <div id="adminSetupBox" style="display:none">
          <h3 style="margin-bottom:12px;color:#1a5276">إعداد المدير لأول مرة</h3>
          <div class="form-group"><label class="form-label">اسم المدير</label><input id="adminSetupName" class="form-control" placeholder="مثال: مدير محلات الحبيشي"></div>
          <div class="form-group"><label class="form-label">البريد الإلكتروني</label><input id="adminSetupEmail" class="form-control" type="email" placeholder="you@example.com"></div>
          <div class="form-group"><label class="form-label">كلمة المرور</label><input id="adminSetupPassword" class="form-control" type="password" placeholder="6 أحرف أو أكثر"></div>
          <button class="btn btn-success w-100" type="button" onclick="setupAdminAccount()"><i class="fas fa-shield-alt"></i> إنشاء حساب الإدارة</button>
        </div>
        <div id="adminLoginBox" style="display:none">
          <h3 style="margin-bottom:12px;color:#1a5276">تسجيل الدخول</h3>
          <div class="form-group"><label class="form-label">البريد الإلكتروني</label><input id="adminLoginEmail" class="form-control" type="email"></div>
          <div class="form-group"><label class="form-label">كلمة المرور</label><input id="adminLoginPassword" class="form-control" type="password"></div>
          <button class="btn btn-primary w-100" type="button" onclick="loginAdminAccount()"><i class="fas fa-sign-in-alt"></i> دخول الإدارة</button>
        </div>
        <div id="adminAuthHint" class="alert alert-info" style="margin-top:14px">جاري فحص حالة الحساب...</div>
      </div>
    </div>
  `;
  document.body.appendChild(shell);
  loadAdminAuthState();
}

async function loadAdminAuthState() {
  try {
    const status = await requestJSON('/api/health', { method: 'GET' });
    document.getElementById('adminSetupBox').style.display = status.adminExists ? 'none' : 'block';
    document.getElementById('adminLoginBox').style.display = status.adminExists ? 'block' : 'none';
    document.getElementById('adminAuthHint').innerHTML = status.adminExists
      ? `البريد المستلم للإشعارات: <strong>${status.ownerEmail}</strong> ${status.emailReady ? '✅' : '⚠️ فعّل SMTP من Render'}`
      : 'هذه أول زيارة للوحة الإدارة، أنشئ الحساب الرئيسي الآن.';
  } catch {
    document.getElementById('adminAuthHint').textContent = 'تعذر التحقق من حالة الخادم.';
  }
}

async function verifyAdminSession() {
  if (!window.location.pathname.endsWith('admin.html')) return true;
  try {
    const data = await requestJSON('/api/auth/admin/me', { method: 'GET' });
    removeAdminAuthOverlay();
    injectAdminTopTools(data.user);
    return true;
  } catch {
    createAdminAuthOverlay();
    return false;
  }
}

function removeAdminAuthOverlay() {
  const shell = document.getElementById('adminAuthShell');
  if (shell) shell.remove();
  __adminAuthInitialized = false;
}

async function setupAdminAccount() {
  const payload = {
    display_name: document.getElementById('adminSetupName').value.trim(),
    email: document.getElementById('adminSetupEmail').value.trim(),
    password: document.getElementById('adminSetupPassword').value
  };
  try {
    await requestJSON('/api/auth/admin/setup', { method: 'POST', body: JSON.stringify(payload) });
    removeAdminAuthOverlay();
    showToast('تم إنشاء حساب الإدارة بنجاح', 'success');
    location.reload();
  } catch (e) {
    showToast(e.message || 'تعذر إنشاء الحساب', 'error');
  }
}

async function loginAdminAccount() {
  const payload = {
    email: document.getElementById('adminLoginEmail').value.trim(),
    password: document.getElementById('adminLoginPassword').value
  };
  try {
    await requestJSON('/api/auth/admin/login', { method: 'POST', body: JSON.stringify(payload) });
    removeAdminAuthOverlay();
    showToast('تم تسجيل الدخول بنجاح', 'success');
    location.reload();
  } catch (e) {
    showToast(e.message || 'فشل تسجيل الدخول', 'error');
  }
}

async function logoutAdminAccount() {
  await requestJSON('/api/auth/admin/logout', { method: 'POST' });
  showToast('تم تسجيل الخروج', 'info');
  location.reload();
}

function injectAdminTopTools(user) {
  if (!window.location.pathname.endsWith('admin.html')) return;
  const dashboard = document.getElementById('tab-dashboard');
  if (dashboard && !document.getElementById('adminQuickToolsCard')) {
    const box = document.createElement('div');
    box.id = 'adminQuickToolsCard';
    box.className = 'card mb-20';
    box.innerHTML = `
      <div class="card-header"><i class="fas fa-link"></i> أدوات إدارة الموقع</div>
      <div class="card-body" style="display:grid;grid-template-columns:1.5fr 1fr;gap:18px;align-items:center;">
        <div>
          <div style="font-weight:800;color:#1a5276;margin-bottom:6px">رابط الموقع</div>
          <div id="siteLinkValue" style="background:#f8f9fa;border:1px solid #e9ecef;padding:12px;border-radius:12px;font-size:.92rem;word-break:break-all">${window.location.origin || window.location.href.replace(/\/admin\.html.*$/, '')}</div>
          <div style="margin-top:8px;color:#6c757d;font-size:.82rem">المدير الحالي: ${user?.display_name || user?.email || 'مدير الموقع'}</div>
        </div>
        <div style="display:grid;gap:10px;">
          <button class="btn btn-primary btn-sm" onclick="copySiteLink()"><i class="fas fa-copy"></i> نسخ الرابط</button>
          <button class="btn btn-success btn-sm" onclick="shareSiteFromAdmin()"><i class="fas fa-share-alt"></i> مشاركة الرابط</button>
          <button class="btn btn-warning btn-sm" onclick="logoutAdminAccount()"><i class="fas fa-sign-out-alt"></i> خروج الإدارة</button>
        </div>
      </div>
    `;
    dashboard.insertBefore(box, dashboard.children[1] || null);
  }
  injectSportsAdminTab();
}

function copySiteLink() {
  const link = window.location.origin;
  navigator.clipboard.writeText(link).then(() => showToast('تم نسخ رابط الموقع', 'success'));
}

function shareSiteFromAdmin() {
  const title = 'محلات الحبيشي';
  const url = window.location.origin;
  if (navigator.share) {
    navigator.share({ title, text: title, url }).catch(() => {});
  } else {
    navigator.clipboard.writeText(url).then(() => showToast('تم نسخ رابط الموقع للمشاركة', 'success'));
  }
}

// ======================================
// تبويب الرياضة داخل الإدارة
// ======================================
function injectSportsAdminTab() {
  if (!window.location.pathname.endsWith('admin.html')) return;
  const sidebar = document.querySelector('.sidebar-menu');
  if (sidebar && !sidebar.querySelector('[data-sports-admin]')) {
    const li = document.createElement('li');
    li.innerHTML = `<a href="#" data-sports-admin onclick="loadSportsAdminPanel(); switchTab('sports-admin', this)"><i class="fas fa-futbol"></i> الرياضة</a>`;
    sidebar.appendChild(li);
  }
  const main = document.querySelector('.admin-content');
  if (main && !document.getElementById('tab-sports-admin')) {
    const tab = document.createElement('div');
    tab.className = 'tab-content';
    tab.id = 'tab-sports-admin';
    tab.innerHTML = `
      <h2 class="section-title"><i class="fas fa-futbol" style="color:#1a5276"></i> إدارة الأخبار الرياضية</h2>
      <div class="alert alert-info mb-20"><i class="fas fa-rss"></i> أضف روابط RSS للمواقع الرياضية، وكل جديد يظهر في صفحة الأخبار الرياضية.</div>
      <div class="card mb-20">
        <div class="card-header"><i class="fas fa-plus-circle"></i> إضافة مصدر رياضي</div>
        <div class="card-body" style="display:grid;grid-template-columns:1fr 1.4fr auto;gap:10px;align-items:end;">
          <div class="form-group" style="margin:0"><label class="form-label">اسم المصدر</label><input id="sportsSourceName" class="form-control" placeholder="مثال: BBC Arabic Sport"></div>
          <div class="form-group" style="margin:0"><label class="form-label">رابط RSS</label><input id="sportsSourceUrl" class="form-control" placeholder="https://example.com/rss.xml"></div>
          <button class="btn btn-success" onclick="saveSportsSource()"><i class="fas fa-save"></i> حفظ</button>
        </div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px;">
        <button class="btn btn-primary btn-sm" onclick="syncSportsNow()"><i class="fas fa-sync"></i> تحديث الأخبار الآن</button>
        <a class="btn btn-outline btn-sm" href="sports.html" target="_blank"><i class="fas fa-external-link-alt"></i> فتح صفحة الرياضة</a>
      </div>
      <div id="sportsSourcesList"></div>
      <div class="card" style="margin-top:20px">
        <div class="card-header"><i class="fas fa-newspaper"></i> آخر الأخبار المنشورة</div>
        <div class="card-body" id="sportsArticlesPreview">جاري التحميل...</div>
      </div>
    `;
    main.appendChild(tab);
  }
}

async function loadSportsAdminPanel() {
  injectSportsAdminTab();
  try {
    const [sources, articles] = await Promise.all([
      requestJSON('/api/sports/sources', { method: 'GET' }),
      requestJSON('/api/sports/articles?limit=8', { method: 'GET' })
    ]);
    const wrap = document.getElementById('sportsSourcesList');
    wrap.innerHTML = (sources.data || []).length ? (sources.data || []).map(src => `
      <div class="product-list-item">
        <div class="product-list-icon" style="background:${src.is_active ? 'rgba(39,174,96,.12)' : 'rgba(108,117,125,.12)'}"><i class="fas fa-rss"></i></div>
        <div class="product-list-info">
          <div class="pname">${src.name}</div>
          <div class="pmeta" style="direction:ltr;text-align:left">${src.url}</div>
        </div>
        <span class="badge ${src.is_active ? 'badge-success' : 'badge-dark'}">${src.is_active ? 'نشط' : 'متوقف'}</span>
        <div style="display:flex;gap:6px;">
          <button class="btn-action btn-edit-status" onclick="toggleSportsSource('${src.id}', ${src.is_active ? 'false' : 'true'})"><i class="fas fa-power-off"></i></button>
          <button class="btn-action btn-del" onclick="deleteSportsSource('${src.id}')"><i class="fas fa-trash"></i></button>
        </div>
      </div>
    `).join('') : '<div class="alert alert-warning">لا توجد مصادر مضافة بعد.</div>';

    const preview = document.getElementById('sportsArticlesPreview');
    preview.innerHTML = (articles.data || []).length ? (articles.data || []).map(article => `
      <div style="padding:12px;border-bottom:1px solid #eee;">
        <div style="font-weight:800;color:#1a5276;margin-bottom:4px">${article.title}</div>
        <div style="font-size:.82rem;color:#6c757d;margin-bottom:6px">${article.source_name || 'مصدر رياضي'} • ${formatDate(article.published_at || article.created_at)}</div>
        <div style="font-size:.88rem;line-height:1.8">${article.summary || ''}</div>
      </div>
    `).join('') : '<div style="color:#6c757d">لا توجد أخبار حالياً.</div>';
  } catch (e) {
    showToast(e.message || 'تعذر تحميل إدارة الرياضة', 'error');
  }
}

async function saveSportsSource() {
  const name = document.getElementById('sportsSourceName').value.trim();
  const url = document.getElementById('sportsSourceUrl').value.trim();
  if (!name || !url) return showToast('أدخل اسم المصدر ورابط RSS', 'warning');
  try {
    await requestJSON('/api/sports/sources', { method: 'POST', body: JSON.stringify({ name, url, is_active: true }) });
    document.getElementById('sportsSourceName').value = '';
    document.getElementById('sportsSourceUrl').value = '';
    showToast('تم حفظ المصدر الرياضي', 'success');
    loadSportsAdminPanel();
  } catch (e) {
    showToast(e.message || 'تعذر حفظ المصدر', 'error');
  }
}

async function toggleSportsSource(id, is_active) {
  await requestJSON(`/api/sports/sources/${id}`, { method: 'PATCH', body: JSON.stringify({ is_active }) });
  showToast('تم تحديث حالة المصدر', 'success');
  loadSportsAdminPanel();
}

async function deleteSportsSource(id) {
  if (!confirm('هل تريد حذف هذا المصدر الرياضي؟')) return;
  await requestJSON(`/api/sports/sources/${id}`, { method: 'DELETE' });
  showToast('تم حذف المصدر', 'success');
  loadSportsAdminPanel();
}

async function syncSportsNow() {
  await requestJSON('/api/sports/sync', { method: 'POST' });
  showToast('تم تحديث الأخبار الرياضية', 'success');
  loadSportsAdminPanel();
}

// ======================================
// تهيئة الصفحة
// ======================================
document.addEventListener('DOMContentLoaded', async () => {
  enhanceNavbarLinks();
  initNavbar();
  injectFaqHelpers();
  injectFloatingShareButton();
  injectAdminShortcut();
  createMemberAuthModal();
  await refreshMemberSession();
  await applyStoreDescriptionTargets();
  await loadPublicNotifications();
  if (window.location.pathname.endsWith('admin.html')) {
    createAdminAuthOverlay();
    await verifyAdminSession();
    updateOrdersBadge();
    setInterval(updateOrdersBadge, 60000);
  }
});

// ======================================
// مساعد طباعة الطلب
// ======================================
function printOrder(order) {
  const items = JSON.parse(order.items || '[]');
  const win = window.open('', '_blank', 'width=600,height=800');
  win.document.write(`
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
      <meta charset="UTF-8">
      <title>طلب رقم ${order.id?.substr(0,8)}</title>
      <style>
        body { font-family: 'Cairo', sans-serif; padding: 20px; direction: rtl; }
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap');
        h2 { color: #1a5276; }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; }
        th { background: #1a5276; color: white; padding: 10px; text-align: right; }
        td { padding: 8px 10px; border-bottom: 1px solid #eee; }
        .total { font-size: 1.2rem; font-weight: 900; color: #27ae60; }
        .header { display: flex; justify-content: space-between; align-items: center; }
        .logo { font-size: 1.5rem; font-weight: 900; color: #1a5276; }
      </style>
    </head>
    <body>
      <div class="header">
        <div class="logo">🏪 محلات الحبيشي</div>
        <div>تاريخ: ${formatDate(order.created_at)}</div>
      </div>
      <hr>
      <h2>طلب رقم: ${order.id?.substr(0,8)}...</h2>
      <p>العميل: <strong>${order.customer_name}</strong></p>
      <p>الجوال: <strong>${order.phone}</strong></p>
      ${order.is_member ? '<p>🏅 عميل مشترك</p>' : ''}
      <table>
        <thead><tr><th>#</th><th>الصنف</th><th>الكمية</th><th>الوحدة</th><th>السعر</th><th>الإجمالي</th></tr></thead>
        <tbody>
          ${items.map((item, i) => `
            <tr>
              <td>${i+1}</td>
              <td>${item.name}</td>
              <td>${item.quantity}</td>
              <td>${item.unit || ''}</td>
              <td>${item.price?.toLocaleString('ar-YE')} ريال</td>
              <td>${(item.price * item.quantity)?.toLocaleString('ar-YE')} ريال</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
      <p class="total">الإجمالي: ${order.total?.toLocaleString('ar-YE')} ريال</p>
      ${order.notes ? `<p>ملاحظات: ${order.notes}</p>` : ''}
      <hr>
      <p style="text-align:center; color: #666;">محلات الحبيشي لمواد البناء والسباكة والكهرباء - إب - المجمعة</p>
    </body>
    </html>
  `);
  win.document.close();
  win.print();
}
