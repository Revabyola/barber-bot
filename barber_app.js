// ===== CONFIG =====
// TODO: замени на URL своего бэкенда на Render/Railway
const API_URL = 'https://YOUR-BACKEND.onrender.com';

const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

const userId = tg.initDataUnsafe?.user?.id || 0;
const userName = tg.initDataUnsafe?.user?.first_name || '';

// ===== STATE =====
const state = {
    isAdmin: false,
    services: [],
    slots: [],     // free slots only
    allSlots: [],  // admin: all slots with booking info
    portfolio: [],
    reviews: [],
    appointments: [],
    booking: { step: 1, service: null, date: null, slotId: null, name: userName, phone: '', comment: '' },
    selectedRating: 5,
};

// ===== INIT =====
async function init() {
    try {
        const me = await api('/api/barber/me?user_id=' + userId);
        state.isAdmin = me.is_admin;
        if (state.isAdmin) addAdminNavBtn();
    } catch (e) { /* offline/preview mode */ }
    setupNav();
    navigate('home');
}

function setupNav() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => navigate(btn.dataset.page));
    });
}

function addAdminNavBtn() {
    const nav = document.getElementById('nav');
    const btn = document.createElement('button');
    btn.className = 'nav-btn';
    btn.dataset.page = 'admin';
    btn.innerHTML = '<span class="nav-icon">⚙️</span><span>Панель</span>';
    btn.addEventListener('click', () => navigate('admin'));
    nav.appendChild(btn);
}

function navigate(page) {
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.page === page));
    renderPage(page);
}

async function renderPage(page) {
    setContent('<div class="loading-full"></div>');
    switch (page) {
        case 'home':      await renderHome(); break;
        case 'book':      await renderBook(); break;
        case 'portfolio': await renderPortfolio(); break;
        case 'prices':    await renderPrices(); break;
        case 'reviews':   await renderReviews(); break;
        case 'mybookings': await renderMyBookings(); break;
        case 'admin':     await renderAdmin(); break;
    }
}

// ===== HOME =====
async function renderHome() {
    setContent(`
        <div class="hero">
            <span class="hero-scissors">✂️</span>
            <div class="hero-name">Барбершоп</div>
            <div class="hero-sub">Твой мастер стиля</div>
        </div>
        <div class="home-grid">
            <button class="home-card" onclick="navigate('book')">
                <span class="home-card-icon">📅</span>
                <div class="home-card-title">Записаться</div>
                <div class="home-card-desc">Выбери удобное время</div>
            </button>
            <button class="home-card" onclick="navigate('portfolio')">
                <span class="home-card-icon">📸</span>
                <div class="home-card-title">Портфолио</div>
                <div class="home-card-desc">Примеры работ</div>
            </button>
            <button class="home-card" onclick="navigate('prices')">
                <span class="home-card-icon">💰</span>
                <div class="home-card-title">Цены</div>
                <div class="home-card-desc">Услуги и стоимость</div>
            </button>
            <button class="home-card" onclick="navigate('reviews')">
                <span class="home-card-icon">⭐</span>
                <div class="home-card-title">Отзывы</div>
                <div class="home-card-desc">Что говорят клиенты</div>
            </button>
        </div>
        <button class="btn btn-outline" onclick="navigate('mybookings')">👤 Мои записи</button>
        ${state.isAdmin ? '<button class="btn btn-gold mt-8" onclick="navigate(\'admin\')">⚙️ Панель управления</button>' : ''}
    `);
}

// ===== BOOK =====
async function renderBook() {
    state.booking = { step: 1, service: null, date: null, slotId: null, name: userName, phone: '', comment: '' };
    const [svcData, slotData] = await Promise.all([
        api('/api/barber/services'),
        api('/api/barber/slots'),
    ]);
    state.services = svcData.services || [];
    state.slots = slotData.slots || [];
    renderBookStep();
}

function renderBookStep() {
    switch (state.booking.step) {
        case 1: renderStep1(); break;
        case 2: renderStep2(); break;
        case 3: renderStep3(); break;
        case 4: renderStep4(); break;
        case 5: renderStep5(); break;
    }
}

function stepsHtml(active) {
    return `
        <div class="steps">
            ${[1,2,3,4].map((n, i) => `
                ${i > 0 ? `<div class="step-line ${n <= active ? 'done' : ''}"></div>` : ''}
                <div class="step-dot ${n < active ? 'done' : n === active ? 'active' : ''}">
                    ${n < active ? '✓' : n}
                </div>
            `).join('')}
        </div>
    `;
}

function renderStep1() {
    let svcsHtml = '';
    if (state.services.length === 0) {
        svcsHtml = '<div class="empty">Услуги пока не добавлены</div>';
    } else {
        svcsHtml = '<div class="services-list">' + state.services.map(s => `
            <div class="svc-card ${state.booking.service?.id === s.id ? 'selected' : ''}"
                 onclick="selectService(${s.id})">
                <div>
                    <div class="svc-name">${s.name}</div>
                    ${s.description ? `<div class="svc-desc">${esc(s.description)}</div>` : ''}
                    <div class="svc-dur">⏱ ${s.duration} мин</div>
                </div>
                <div class="svc-price">${s.price} ₽</div>
            </div>
        `).join('') + '</div>';
    }

    setContent(`
        <div class="page-hdr">
            <h2>Выбери услугу</h2>
            <span class="page-hint">Шаг 1/4</span>
        </div>
        ${stepsHtml(1)}
        ${svcsHtml}
        <button class="btn btn-outline" onclick="selectService(null)">Пропустить →</button>
    `);
}

function selectService(id) {
    state.booking.service = id ? state.services.find(s => s.id === id) : null;
    state.booking.step = 2;
    renderBookStep();
}

function renderStep2() {
    const dateMap = {};
    state.slots.forEach(s => {
        if (!dateMap[s.date]) dateMap[s.date] = 0;
        dateMap[s.date]++;
    });
    const dates = Object.keys(dateMap).sort();

    const dayNames = ['Вс','Пн','Вт','Ср','Чт','Пт','Сб'];
    const monthNames = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'];

    let datesHtml = '';
    if (dates.length === 0) {
        datesHtml = '<div class="empty-book">😔 Свободных слотов пока нет.<br>Загляни позже!</div>';
    } else {
        datesHtml = '<div class="dates-grid">' + dates.map(date => {
            const d = new Date(date + 'T00:00:00');
            const cnt = dateMap[date];
            const slots_word = cnt === 1 ? 'слот' : cnt < 5 ? 'слота' : 'слотов';
            return `
                <button class="date-card ${state.booking.date === date ? 'selected' : ''}"
                        onclick="selectDate('${date}')">
                    <div class="date-dname">${dayNames[d.getDay()]}</div>
                    <div class="date-dnum">${d.getDate()}</div>
                    <div class="date-month">${monthNames[d.getMonth()]}</div>
                    <div class="date-count">${cnt} ${slots_word}</div>
                </button>
            `;
        }).join('') + '</div>';
    }

    setContent(`
        <div class="page-hdr">
            <button class="back-btn" onclick="goStep(1)">←</button>
            <h2>Выбери дату</h2>
            <span class="page-hint">Шаг 2/4</span>
        </div>
        ${stepsHtml(2)}
        ${datesHtml}
    `);
}

function selectDate(date) {
    state.booking.date = date;
    state.booking.step = 3;
    renderBookStep();
}

function renderStep3() {
    const daySlots = state.slots.filter(s => s.date === state.booking.date);
    const timesHtml = '<div class="times-grid">' + daySlots.map(s => `
        <button class="time-card ${state.booking.slotId === s.id ? 'selected' : ''}"
                onclick="selectSlot(${s.id})">${s.time}</button>
    `).join('') + '</div>';

    setContent(`
        <div class="page-hdr">
            <button class="back-btn" onclick="goStep(2)">←</button>
            <h2>Выбери время</h2>
            <span class="page-hint">Шаг 3/4</span>
        </div>
        ${stepsHtml(3)}
        ${timesHtml}
    `);
}

function selectSlot(id) {
    state.booking.slotId = id;
    state.booking.step = 4;
    renderBookStep();
}

function renderStep4() {
    setContent(`
        <div class="page-hdr">
            <button class="back-btn" onclick="goStep(3)">←</button>
            <h2>Твои данные</h2>
            <span class="page-hint">Шаг 4/4</span>
        </div>
        ${stepsHtml(4)}
        <div class="form-group">
            <label>Имя *</label>
            <input class="input" id="book-name" type="text" value="${esc(state.booking.name)}" placeholder="Как тебя зовут?" maxlength="60">
        </div>
        <div class="form-group">
            <label>Телефон</label>
            <input class="input" id="book-phone" type="tel" value="${esc(state.booking.phone)}" placeholder="+7 (999) 000-00-00">
        </div>
        <div class="form-group">
            <label>Пожелания</label>
            <textarea class="input" id="book-comment" rows="3" placeholder="Особые пожелания к стрижке...">${esc(state.booking.comment)}</textarea>
        </div>
        <button class="btn btn-gold" onclick="proceedConfirm()">Далее →</button>
    `);
}

function proceedConfirm() {
    const name = document.getElementById('book-name').value.trim();
    if (!name) { alert('Введи своё имя'); return; }
    state.booking.name = name;
    state.booking.phone = document.getElementById('book-phone').value.trim();
    state.booking.comment = document.getElementById('book-comment').value.trim();
    state.booking.step = 5;
    renderBookStep();
}

function renderStep5() {
    const { service, date, slotId, name, phone, comment } = state.booking;
    const slot = state.slots.find(s => s.id === slotId);
    const d = new Date(date + 'T00:00:00');
    const months = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];
    const dateStr = `${d.getDate()} ${months[d.getMonth()]}`;

    setContent(`
        <div class="page-hdr">
            <button class="back-btn" onclick="goStep(4)">←</button>
            <h2>Подтверждение</h2>
        </div>
        <div class="confirm-card">
            <div class="confirm-row">
                <span class="confirm-icon">📅</span>
                <div>
                    <div class="confirm-label">Дата и время</div>
                    <div class="confirm-value">${dateStr} в ${slot?.time || ''}</div>
                </div>
            </div>
            ${service ? `
            <div class="confirm-row">
                <span class="confirm-icon">✂️</span>
                <div>
                    <div class="confirm-label">Услуга</div>
                    <div class="confirm-value">${esc(service.name)} — ${service.price} ₽</div>
                </div>
            </div>` : ''}
            <div class="confirm-row">
                <span class="confirm-icon">👤</span>
                <div>
                    <div class="confirm-label">Имя</div>
                    <div class="confirm-value">${esc(name)}</div>
                </div>
            </div>
            ${phone ? `
            <div class="confirm-row">
                <span class="confirm-icon">📱</span>
                <div>
                    <div class="confirm-label">Телефон</div>
                    <div class="confirm-value">${esc(phone)}</div>
                </div>
            </div>` : ''}
            ${comment ? `
            <div class="confirm-row">
                <span class="confirm-icon">💬</span>
                <div>
                    <div class="confirm-label">Пожелания</div>
                    <div class="confirm-value">${esc(comment)}</div>
                </div>
            </div>` : ''}
        </div>
        <button class="btn btn-gold" id="submit-btn" onclick="submitBooking()">✅ Записаться</button>
        <button class="btn btn-outline" onclick="navigate('book')">Изменить</button>
    `);
}

async function submitBooking() {
    const btn = document.getElementById('submit-btn');
    btn.disabled = true;
    btn.textContent = '⏳ Отправка...';

    try {
        const result = await api('/api/barber/appointments', 'POST', {
            slot_id: state.booking.slotId,
            client_name: state.booking.name,
            client_phone: state.booking.phone,
            client_telegram_id: userId,
            service_id: state.booking.service?.id || null,
            comment: state.booking.comment,
        });

        if (result.success) {
            showSuccess();
        } else {
            alert('Ошибка: ' + (result.error || 'попробуй снова'));
            btn.disabled = false;
            btn.textContent = '✅ Записаться';
        }
    } catch (e) {
        alert('Ошибка сети. Попробуй снова.');
        btn.disabled = false;
        btn.textContent = '✅ Записаться';
    }
}

function showSuccess() {
    const slot = state.slots.find(s => s.id === state.booking.slotId);
    const d = new Date(state.booking.date + 'T00:00:00');
    const months = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];

    tg.HapticFeedback?.notificationOccurred('success');
    setContent(`
        <div class="success-page">
            <span class="success-icon">🎉</span>
            <h2>Запись оформлена!</h2>
            <p>Ты записан(а) на <strong>${d.getDate()} ${months[d.getMonth()]}</strong> в <strong>${slot?.time || ''}</strong></p>
            <p class="success-hint">Мастер получил уведомление о твоей записи</p>
            <button class="btn btn-gold mt-24" onclick="navigate('home')">На главную</button>
            <button class="btn btn-outline" onclick="navigate('mybookings')">👤 Мои записи</button>
        </div>
    `);
}

function goStep(n) {
    state.booking.step = n;
    renderBookStep();
}

// ===== PORTFOLIO =====
async function renderPortfolio() {
    const { portfolio } = await api('/api/barber/portfolio');
    state.portfolio = portfolio || [];

    let gridHtml = '';
    if (state.portfolio.length === 0) {
        gridHtml = '<div class="empty">Фотографии скоро появятся ✨</div>';
    } else {
        gridHtml = '<div class="portfolio-grid">' + state.portfolio.map(item => `
            <div class="portfolio-item">
                <img src="${esc(item.image_url)}" alt="${esc(item.description)}" loading="lazy"
                     onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22300%22 height=%22300%22><rect fill=%22%23222%22 width=%22300%22 height=%22300%22/></svg>'">
                ${item.description ? `<div class="portfolio-desc">${esc(item.description)}</div>` : ''}
                ${state.isAdmin ? `<button class="portfolio-del" onclick="deletePortfolioItem(${item.id})">✕</button>` : ''}
            </div>
        `).join('') + '</div>';
    }

    const adminAddHtml = state.isAdmin ? `
        <div class="add-box">
            <h3>Добавить фото</h3>
            <input class="input mb-10" id="p-url" type="url" placeholder="Ссылка на фото (imgur, etc)">
            <input class="input mb-10" id="p-desc" type="text" placeholder="Описание (необязательно)" maxlength="80">
            <button class="btn btn-gold" onclick="addPortfolioItem()">Добавить</button>
        </div>
    ` : '';

    setContent(`
        <div class="page-hdr"><h2>📸 Портфолио</h2></div>
        ${gridHtml}
        ${adminAddHtml}
    `);
}

async function addPortfolioItem() {
    const url = document.getElementById('p-url').value.trim();
    if (!url) { alert('Введи ссылку на фото'); return; }
    await api('/api/barber/portfolio', 'POST', {
        image_url: url,
        description: document.getElementById('p-desc').value.trim(),
        user_id: userId,
    });
    renderPortfolio();
}

async function deletePortfolioItem(id) {
    if (!confirm('Удалить фото?')) return;
    await api(`/api/barber/portfolio/${id}?user_id=${userId}`, 'DELETE');
    renderPortfolio();
}

// ===== PRICES =====
async function renderPrices() {
    const { services } = await api('/api/barber/services');
    state.services = services || [];

    let listHtml = '';
    if (state.services.length === 0) {
        listHtml = '<div class="empty">Прайс-лист скоро появится</div>';
    } else {
        listHtml = state.services.map(s => `
            <div class="price-card">
                <div class="price-info">
                    <div class="price-name">✂️ ${esc(s.name)}</div>
                    ${s.description ? `<div class="price-desc">${esc(s.description)}</div>` : ''}
                    <div class="price-dur">⏱ ${s.duration} мин</div>
                </div>
                <div class="price-amount">${s.price} ₽</div>
                ${state.isAdmin ? `<button class="del-btn" onclick="deleteService(${s.id})">✕</button>` : ''}
            </div>
        `).join('');
    }

    const adminAddHtml = state.isAdmin ? `
        <div class="add-box">
            <h3>Добавить услугу</h3>
            <input class="input mb-10" id="svc-name" type="text" placeholder="Название" maxlength="60">
            <input class="input mb-10" id="svc-desc" type="text" placeholder="Описание (необязательно)" maxlength="100">
            <input class="input mb-10" id="svc-price" type="number" placeholder="Цена, ₽" min="0">
            <input class="input mb-10" id="svc-dur" type="number" placeholder="Длительность, мин" value="60" min="15">
            <button class="btn btn-gold" onclick="addService()">Добавить</button>
        </div>
    ` : '';

    setContent(`
        <div class="page-hdr"><h2>💰 Цены</h2></div>
        ${listHtml}
        ${adminAddHtml}
        <button class="btn btn-gold mt-16" onclick="navigate('book')">📅 Записаться</button>
    `);
}

async function addService() {
    const name = document.getElementById('svc-name').value.trim();
    const price = parseInt(document.getElementById('svc-price').value);
    if (!name || !price) { alert('Заполни название и цену'); return; }
    await api('/api/barber/services', 'POST', {
        name, description: document.getElementById('svc-desc').value.trim(),
        price, duration: parseInt(document.getElementById('svc-dur').value) || 60,
        user_id: userId,
    });
    renderPrices();
}

async function deleteService(id) {
    if (!confirm('Удалить услугу?')) return;
    await api(`/api/barber/services/${id}?user_id=${userId}`, 'DELETE');
    renderPrices();
}

// ===== REVIEWS =====
async function renderReviews() {
    const { reviews } = await api('/api/barber/reviews');
    state.reviews = reviews || [];

    const avg = state.reviews.length > 0
        ? (state.reviews.reduce((s, r) => s + r.rating, 0) / state.reviews.length).toFixed(1)
        : null;

    let listHtml = '';
    if (state.reviews.length === 0) {
        listHtml = '<div class="empty">Пока нет отзывов. Будь первым! 🙌</div>';
    } else {
        listHtml = state.reviews.map(r => {
            const stars = '★'.repeat(r.rating) + '☆'.repeat(5 - r.rating);
            return `
                <div class="review-card">
                    <div class="review-hdr">
                        <div class="review-author">${esc(r.client_name)}</div>
                        <div class="review-stars">${stars}</div>
                    </div>
                    <div class="review-text">${esc(r.text)}</div>
                    <div class="review-date">${r.date}</div>
                    ${state.isAdmin ? `<button class="del-btn mt-8" onclick="deleteReview(${r.id})">Удалить</button>` : ''}
                </div>
            `;
        }).join('');
    }

    const starsHtml = [1,2,3,4,5].map(i =>
        `<button class="star-btn ${i <= state.selectedRating ? 'active' : ''}" data-r="${i}" onclick="selectRating(${i})">★</button>`
    ).join('');

    setContent(`
        <div class="page-hdr">
            <h2>⭐ Отзывы</h2>
            ${avg ? `<div class="avg-badge">★ ${avg}</div>` : ''}
        </div>
        ${listHtml}
        <div class="add-review-box">
            <h3>Оставить отзыв</h3>
            <div class="stars-row">${starsHtml}</div>
            <input class="input mb-10" id="r-name" type="text" value="${esc(userName)}" placeholder="Твоё имя" maxlength="60">
            <textarea class="input mb-10" id="r-text" rows="3" placeholder="Расскажи о своём визите..."></textarea>
            <button class="btn btn-gold" onclick="submitReview()">Отправить отзыв</button>
        </div>
    `);
}

function selectRating(r) {
    state.selectedRating = r;
    document.querySelectorAll('.star-btn').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.r) <= r);
    });
}

async function submitReview() {
    const name = document.getElementById('r-name').value.trim();
    const text = document.getElementById('r-text').value.trim();
    if (!name || !text) { alert('Заполни имя и текст'); return; }

    const result = await api('/api/barber/reviews', 'POST', {
        client_name: name,
        client_telegram_id: userId,
        rating: state.selectedRating,
        text,
    });

    if (result.success) {
        tg.HapticFeedback?.notificationOccurred('success');
        renderReviews();
    }
}

async function deleteReview(id) {
    if (!confirm('Удалить отзыв?')) return;
    await api(`/api/barber/reviews/${id}?user_id=${userId}`, 'DELETE');
    renderReviews();
}

// ===== MY BOOKINGS =====
async function renderMyBookings() {
    const { appointments } = await api(`/api/barber/appointments?user_id=${userId}`);
    state.appointments = appointments || [];

    const months = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'];
    let listHtml = '';
    if (state.appointments.length === 0) {
        listHtml = `
            <div class="empty">У тебя пока нет записей</div>
            <button class="btn btn-gold mt-16" onclick="navigate('book')">📅 Записаться</button>
        `;
    } else {
        listHtml = state.appointments.map(a => {
            const d = new Date(a.date + 'T00:00:00');
            return `
                <div class="appt-card">
                    <div class="appt-date">${d.getDate()} ${months[d.getMonth()]} в ${a.time}</div>
                    ${a.service_name ? `<div class="appt-svc">✂️ ${esc(a.service_name)}${a.price ? ` — ${a.price} ₽` : ''}</div>` : ''}
                    <div class="appt-status-confirmed">✅ Подтверждено</div>
                    <button class="btn btn-outline btn-sm" onclick="cancelMyAppt(${a.id})">Отменить</button>
                </div>
            `;
        }).join('');
    }

    setContent(`
        <div class="page-hdr"><h2>👤 Мои записи</h2></div>
        ${listHtml}
    `);
}

async function cancelMyAppt(id) {
    if (!confirm('Отменить эту запись?')) return;
    await api(`/api/barber/appointments/${id}?user_id=${userId}`, 'DELETE');
    renderMyBookings();
}

// ===== ADMIN =====
async function renderAdmin() {
    if (!state.isAdmin) { navigate('home'); return; }

    const [slotData, apptData] = await Promise.all([
        api(`/api/barber/slots?user_id=${userId}&all=1`),
        api(`/api/barber/appointments?user_id=${userId}`),
    ]);

    const allSlots = slotData.slots || [];
    const appointments = apptData.appointments || [];

    const freeCount = allSlots.filter(s => !s.is_booked).length;
    const months = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'];

    const dateMap = {};
    allSlots.forEach(s => {
        if (!dateMap[s.date]) dateMap[s.date] = [];
        dateMap[s.date].push(s);
    });

    const apptHtml = appointments.length === 0
        ? '<p class="hint">Нет предстоящих записей</p>'
        : appointments.map(a => {
            const d = new Date(a.date + 'T00:00:00');
            return `
                <div class="admin-appt-card">
                    <div class="admin-appt-time">${d.getDate()} ${months[d.getMonth()]} · ${a.time}</div>
                    <div>👤 <strong>${esc(a.client_name)}</strong></div>
                    ${a.client_phone ? `<div>📱 ${esc(a.client_phone)}</div>` : ''}
                    ${a.service_name ? `<div>✂️ ${esc(a.service_name)}${a.price ? ` (${a.price} ₽)` : ''}</div>` : ''}
                    ${a.comment ? `<div>💬 ${esc(a.comment)}</div>` : ''}
                    <button class="btn btn-danger btn-sm mt-8" onclick="adminCancelAppt(${a.id})">Отменить</button>
                </div>
            `;
        }).join('');

    const slotsHtml = Object.keys(dateMap).sort().map(date => {
        const d = new Date(date + 'T00:00:00');
        const chips = dateMap[date].map(s => `
            <div class="slot-chip ${s.is_booked ? 'slot-booked' : 'slot-free'}">
                <span>${s.time}</span>
                ${s.is_booked
                    ? `<span class="slot-client-name">${esc(s.client_name || '')}</span>`
                    : `<button class="slot-del-btn" onclick="deleteSlot(${s.id})">✕</button>`}
            </div>
        `).join('');
        return `
            <div class="slots-group">
                <div class="slots-group-hdr">${d.getDate()} ${months[d.getMonth()]}</div>
                <div class="slots-wrap">${chips}</div>
            </div>
        `;
    }).join('');

    const timesRow = ['09:00','09:30','10:00','10:30','11:00','11:30','12:00','12:30',
                      '13:00','13:30','14:00','14:30','15:00','15:30','16:00','16:30',
                      '17:00','17:30','18:00','18:30','19:00','19:30','20:00'].map(t => `
        <label class="time-chk-label">
            <input type="checkbox" class="time-chk" value="${t}">
            <span>${t}</span>
        </label>
    `).join('');

    const today = new Date().toISOString().split('T')[0];

    setContent(`
        <div class="page-hdr"><h2>⚙️ Панель управления</h2></div>

        <div class="admin-stats">
            <div class="admin-stat">
                <div class="admin-stat-num">${appointments.length}</div>
                <div class="admin-stat-lbl">Записей</div>
            </div>
            <div class="admin-stat">
                <div class="admin-stat-num">${freeCount}</div>
                <div class="admin-stat-lbl">Свободных слотов</div>
            </div>
        </div>

        <div class="section-title">📅 Предстоящие записи</div>
        ${apptHtml}

        <div class="section-title">🕐 Добавить слоты</div>
        <div class="add-box">
            <input class="input mb-10" id="slot-date" type="date" min="${today}">
            <div class="time-checkboxes">${timesRow}</div>
            <button class="btn btn-gold" onclick="addSlots()">Добавить выбранные слоты</button>
        </div>

        <div class="section-title">📋 Все слоты</div>
        ${slotsHtml || '<p class="hint">Нет слотов</p>'}
    `);
}

async function addSlots() {
    const date = document.getElementById('slot-date').value;
    if (!date) { alert('Выбери дату'); return; }
    const checked = Array.from(document.querySelectorAll('.time-chk:checked'));
    if (checked.length === 0) { alert('Выбери хотя бы одно время'); return; }
    await Promise.all(checked.map(c => api('/api/barber/slots', 'POST', { date, time: c.value, user_id: userId })));
    renderAdmin();
}

async function deleteSlot(id) {
    await api(`/api/barber/slots/${id}?user_id=${userId}`, 'DELETE');
    renderAdmin();
}

async function adminCancelAppt(id) {
    if (!confirm('Отменить эту запись?')) return;
    await api(`/api/barber/appointments/${id}?user_id=${userId}`, 'DELETE');
    renderAdmin();
}

// ===== UTILS =====
function setContent(html) {
    const el = document.getElementById('content');
    el.innerHTML = html;
    el.scrollTop = 0;
}

async function api(path, method = 'GET', body = null) {
    const url = path.startsWith('http') ? path : API_URL + path;
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(url, opts);
    return res.json();
}

function esc(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// ===== START =====
init();
