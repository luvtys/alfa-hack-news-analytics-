const USE_REAL_API = true;
const FEED_URL = 'http://127.0.0.1:8000/api/feed';

document.addEventListener("DOMContentLoaded", () => {
    const insightContainer = document.getElementById('insight-container');
    const blockedContainer = document.getElementById('blocked-container');
    const emptyContainer = document.getElementById('empty-container');
    const dashboardScreen = document.getElementById('dashboard-screen');
    const entryScreen = document.getElementById('entry-screen');
    const timeline = document.getElementById('timeline-steps');
    const fogLayer = document.getElementById('fog-layer');
    const parallaxBg = document.getElementById('parallax-bg');

    let currentRole = 'CFO';
    let currentData = null;
    let feedItems = [];
    let currentIndex = 0;

    const ROLE_MAPPING = {
        'CFO': { uid: 'U_26030', toast: 'Фокус: Финансовые риски', label: 'Финансовый директор' },
        'OWNER': { uid: 'U_1941', toast: 'Фокус: Стратегические риски', label: 'Собственник' },
        'CHIEF_ACCOUNTANT': { uid: 'U_106783', toast: 'Фокус: Контрагенты', label: 'Главный бухгалтер' }
    };

    // --- КАСТОМНЫЙ ДРОПДАУН ---
    const selectWrapper = document.getElementById('custom-select');
    if (selectWrapper) {
        const trigger = selectWrapper.querySelector('.custom-select-trigger');
        const options = selectWrapper.querySelectorAll('.custom-option');
        const triggerText = trigger.querySelector('span');

        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            selectWrapper.classList.toggle('open');
        });

        options.forEach(option => {
            option.addEventListener('click', () => {
                const value = option.dataset.value;
                const text = option.innerText;

                triggerText.innerText = text;
                options.forEach(o => o.classList.remove('selected'));
                option.classList.add('selected');
                selectWrapper.classList.remove('open');

                changeRole(value);
            });
        });

        document.addEventListener('click', () => {
            selectWrapper.classList.remove('open');
        });
    }

    // --- ПАРАЛЛАКС ЛЕСА ---
    document.addEventListener('mousemove', (e) => {
        const x = (e.clientX / window.innerWidth - 0.5) * 20;
        const y = (e.clientY / window.innerHeight - 0.5) * 20;
        if (parallaxBg) {
            parallaxBg.style.transform = `translate(${x}px, ${y}px) scale(1.05)`;
        }
    });

    // --- СТАРТ АНАЛИЗА ---
    window.startAnalysis = function () {
        const overlay = document.createElement('div');
        overlay.className = 'fog-reveal-overlay';
        overlay.innerHTML = `
            <div class="fog-reveal-text">хао...</div>
            <div class="fog-reveal-text">хао...</div>
            <div class="fog-reveal-text">хао...</div>
        `;
        document.body.appendChild(overlay);

        setTimeout(() => { overlay.classList.add('active'); }, 50);
        fogLayer.style.animation = 'fogPulse 3s infinite alternate';

        setTimeout(() => {
            overlay.classList.remove('active');
            setTimeout(() => overlay.remove(), 1000);

            entryScreen.style.display = 'none';
            dashboardScreen.style.display = 'grid';

            if (window.effects) {
                window.effects.spawnInsightParticles(window.innerWidth / 2, window.innerHeight / 2);
            }

            loadFeed();
            loadTrace();
        }, 3000);
    };

    // --- ПЕРЕКЛЮЧЕНИЕ ТАБОВ ---
    window.switchTab = function (tabName) {
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

        document.getElementById(`tab-${tabName}`).classList.add('active');
        document.getElementById(`tab-content-${tabName}`).classList.add('active');

        if (tabName === 'trace') {
            document.getElementById('ai-explain-overlay').style.display = 'none';
        }
    };

    // --- РЕЖИМ ОБЪЯСНЕНИЯ ---
    window.openExplainMode = function () {
        document.getElementById('ai-explain-overlay').style.display = 'flex';
    };

    window.closeExplainMode = function () {
        document.getElementById('ai-explain-overlay').style.display = 'none';
    };

    // --- СМЕНА РОЛИ (С ОЧИСТКОЙ ЧАТА И ТАБОВ) ---
    window.changeRole = function (roleValue) {
        currentRole = roleValue;
        currentIndex = 0;

        // Очищаем чат при смене роли
        document.getElementById('chat-history').innerHTML = '<div class="chat-msg assistant">Я проанализировал новость. Задайте вопрос по этой компании.</div>';

        // Сбрасываем табы (пока грузится - скрыты)
        document.getElementById('tab-actions').style.display = 'none';
        document.getElementById('tab-trace').style.display = 'none';

        fogLayer.style.opacity = '1';
        fogLayer.style.background = 'radial-gradient(circle at 50% 50%, rgba(95, 141, 144, 0.6) 0%, rgba(7, 19, 21, 1) 100%)';

        setTimeout(() => {
            loadFeed();
            setTimeout(() => {
                fogLayer.style.opacity = '';
                fogLayer.style.background = '';
            }, 300);
        }, 700);
    };

    // --- МОДАЛКИ ---
    window.openSourceModal = function (label, ref) {
        document.getElementById('modal-body').innerHTML = `
            <p><strong>Документ:</strong> ${label}</p>
            <p><strong>Ссылка:</strong> <code>${ref}</code></p>
        `;
        document.getElementById('source-modal').style.display = 'flex';
    };

    window.openActionModal = function (title, text) {
        document.getElementById('action-modal-body').innerHTML = `
            <p><strong>${title}</strong></p>
            <p>${text}</p>
        `;
        document.getElementById('action-modal').style.display = 'flex';
    };

    window.closeModal = function (modalId) {
        document.getElementById(modalId).style.display = 'none';
    };

    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.style.display = 'none';
        });
    });

    // --- ЗАГРУЗКА ЛЕНТЫ ---
    async function loadFeed() {
        const roleData = ROLE_MAPPING[currentRole];

        insightContainer.innerHTML = '<div style="color: #fff; padding: 20px;">Загрузка ленты...</div>';
        insightContainer.style.display = 'block';
        blockedContainer.style.display = 'none';
        emptyContainer.style.display = 'none';

        document.getElementById('actions-list').innerHTML = '';

        try {
            const response = await fetch(FEED_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    company_id: roleData.uid,
                    role: currentRole
                })
            });

            const result = await response.json();

            if (!result.items || result.items.length === 0) {
                feedItems = [];
                insightContainer.style.display = 'none';
                emptyContainer.style.display = 'block';
                document.getElementById('empty-message-text').innerText = "Нет актуальных инсайтов для этой роли";
                document.getElementById('tab-actions').style.display = 'none';
                document.getElementById('tab-trace').style.display = 'none';
                return;
            }

            feedItems = result.items;
            currentIndex = 0;
            renderCurrentItem();

        } catch (error) {
            console.error("Ошибка загрузки ленты:", error);
            insightContainer.innerHTML = `<div style="color:#EF3124; padding: 20px;">Ошибка загрузки: ${error.message}</div>`;
            document.getElementById('tab-actions').style.display = 'none';
            document.getElementById('tab-trace').style.display = 'none';
        }
    }

    // --- ОТРИСОВКА ТЕКУЩЕЙ НОВОСТИ (С ПРАВИЛЬНЫМ УПРАВЛЕНИЕМ ТАБАМИ) ---
    function renderCurrentItem() {
        if (!feedItems || feedItems.length === 0) return;

        const item = feedItems[currentIndex];

        // 1. Если новость не прошла скоринг (skipped) — скрываем табы
        if (item.status === 'skipped') {
            insightContainer.innerHTML = `
                <div class="blocked-card" style="margin: 20px auto; max-width: 800px;">
                    <h2 class="blocked-title">Пока всё стабильно</h2>
                    <p class="blocked-text">${item.reason || 'Новость нерелевантна для этой компании.'}</p>
                </div>
            `;
            document.getElementById('tab-actions').style.display = 'none';
            document.getElementById('tab-trace').style.display = 'none';
            return;
        }

        const ins = item.insight;
        const ev = ins.event;
        const interp = ins.interpretation;
        const scorePercent = ins.relevance ? (ins.relevance.score * 100).toFixed(0) : '?';
        const bankQuote = interp.bank_view.quote || interp.bank_view.text || "Аналитика банка недоступна.";

        currentData = ins;

        // 2. Проверяем guard (refused)
        let hasRefused = ins.data_quality && ins.data_quality.refused && ins.data_quality.refused.length > 0;

        let refusedBlock = '';
        if (hasRefused) {
            refusedBlock = `
                <div class="blocked-card" style="margin-top: 20px;">
                    <h2 class="blocked-title">Вывод не сделан</h2>
                    <p class="blocked-text">${ins.data_quality.refused[0].message}</p>
                </div>
            `;
            document.getElementById('tab-actions').style.display = 'none';
            document.getElementById('tab-trace').style.display = 'none';
        } else {
            document.getElementById('tab-actions').style.display = 'block';
            document.getElementById('tab-trace').style.display = 'block';

            document.getElementById('actions-list').innerHTML = ins.actions.map(a => `
                <button class="action-btn" onclick="openActionModal('${a.text}', 'Переход в раздел: ${a.product_hint}')">
                    ${a.text}
                </button>
            `).join('');
        }

        const prevDisabled = currentIndex === 0;
        const nextDisabled = currentIndex === feedItems.length - 1;

        // 3. Рисуем карточку с кнопками поверх
        insightContainer.innerHTML = `
            <div style="position: relative; width: 100%; max-width: 100%; margin: 0; padding: 0 40px;">
                
                <!-- Кнопка Назад -->
                <button onclick="prevNews()" ${prevDisabled ? 'disabled' : ''} 
                    style="position: absolute; left: 0; top: 50%; transform: translateY(-50%); z-index: 10; 
                    width: 40px; height: 40px; border-radius: 50%; background: rgba(0,0,0,0.4); 
                    border: 1px solid rgba(255,255,255,0.1); color: #fff; cursor: ${prevDisabled ? 'default' : 'pointer'};
                    display: flex; align-items: center; justify-content: center; font-size: 18px;
                    opacity: ${prevDisabled ? '0.1' : '0.5'}; transition: all 0.2s;"
                    onmouseover="if(!this.disabled) { this.style.opacity='1'; this.style.background='rgba(239,49,36,0.8)'; }"
                    onmouseout="if(!this.disabled) { this.style.opacity='0.5'; this.style.background='rgba(0,0,0,0.4)'; }">
                    ←
                </button>

                <!-- Карточка -->
                <div class="insight-card" style="margin: 0; width: 100%;">
                    <div class="insight-header">
                        <div class="header-tags">
                            <span class="tag-alfa">Alfa Analytics</span>
                            <span class="tag-score">Релевантность ${scorePercent}%</span>
                        </div>
                        <span class="date">${new Date(ev.published_at).toLocaleDateString('ru-RU')}</span>
                    </div>
                    <h1 class="event-headline">${ev.headline}</h1>
                    
                    <div class="why-matters-box">
                        <h3>Скрытый сигнал</h3>
                        <p>${interp.why_it_matters || "Анализ влияния на компанию недоступен."}</p>
                    </div>
                    
                    <div class="consequences">
                        ${interp.consequences.map(c => `
                            <div class="consequence ${c.type}">
                                <span class="badge badge-${c.type}">${c.type === 'risk' ? 'Угроза' : 'Возможность'}</span>
                                <p>${c.text || "Детали не указаны."}</p>
                            </div>
                        `).join('')}
                    </div>
                    
                    <div class="bank-view-box">
                        <div class="bank-view-header">
                            <h4>Мнение Альфа-Банка</h4>
                            <span class="bank-date">${interp.bank_view.as_of_date || 'Архив'}</span>
                        </div>
                        <blockquote>"${bankQuote}"</blockquote>
                        <div class="source-links">
                            ${ins.evidence ? ins.evidence.map(e => `
                                <a href="javascript:void(0)" class="evidence-badge ${e.kind}" onclick="openSourceModal('${e.label}', '${e.ref}')">
                                    ${e.kind === 'verified_fact' ? 'Факт' : e.kind === 'alfa_view' ? 'Аналитика' : 'AI'}
                                </a>
                            `).join('') : ''}
                        </div>
                    </div>
                    ${refusedBlock}
                </div>

                <!-- Кнопка Вперед -->
                <button onclick="nextNews()" ${nextDisabled ? 'disabled' : ''} 
                    style="position: absolute; right: 0; top: 50%; transform: translateY(-50%); z-index: 10; 
                    width: 40px; height: 40px; border-radius: 50%; background: rgba(0,0,0,0.4); 
                    border: 1px solid rgba(255,255,255,0.1); color: #fff; cursor: ${nextDisabled ? 'default' : 'pointer'};
                    display: flex; align-items: center; justify-content: center; font-size: 18px;
                    opacity: ${nextDisabled ? '0.1' : '0.5'}; transition: all 0.2s;"
                    onmouseover="if(!this.disabled) { this.style.opacity='1'; this.style.background='rgba(239,49,36,0.8)'; }"
                    onmouseout="if(!this.disabled) { this.style.opacity='0.5'; this.style.background='rgba(0,0,0,0.4)'; }">
                    →
                </button>
            </div>
        `;
    }

    // --- НАВИГАЦИЯ ПО ЛЕНТЕ ---
    window.prevNews = function () {
        if (currentIndex > 0) {
            currentIndex--;
            renderCurrentItem();
        }
    };

    window.nextNews = function () {
        if (currentIndex < feedItems.length - 1) {
            currentIndex++;
            renderCurrentItem();
        }
    };

    // --- ЗАГРУЗКА ТРАССЫ ---
    async function loadTrace() {
        try {
            const response = await fetch('/static/trace_trc_4c90de.json');
            const data = await response.json();
            timeline.innerHTML = data.steps.map(step => {
                let icon = '✓';
                if (step.status === 'failed') icon = '✗';
                if (step.status === 'retry') icon = '↻';

                return `
                    <div class="step ${step.status}">
                        <div class="step-icon">${icon}</div>
                        <div class="step-content">
                            <strong>Шаг ${step.step_no}: ${step.title}</strong>
                            ${step.note ? `<br><small style="color:#EF3124;">${step.note}</small>` : ''}
                        </div>
                    </div>
                `;
            }).join('');

            // Добавляем кнопку графа, если ее нет
            // if (!document.getElementById('explain-btn')) {
            //     const btn = document.createElement('button');
            //     btn.id = 'explain-btn';
            //     btn.className = 'action-btn';
            //     btn.style.marginTop = '20px';
            //     btn.innerText = 'Как получен вывод? (Граф)';
            //     btn.onclick = openExplainMode; // <-- ВОТ ЭТА СТРОКА
            //     timeline.appendChild(btn);
            // }
        } catch (error) {
            console.error("Ошибка трассы", error);
        }
    }

    // --- ЧАТ ---
    window.sendQuestion = async function () {
        const input = document.getElementById('chat-input');
        const history = document.getElementById('chat-history');
        if (!input.value.trim()) return;

        const userQuestion = input.value;
        history.innerHTML += `<div class="chat-msg user">${userQuestion}</div>`;
        input.value = '';
        history.scrollTop = history.scrollHeight;

        const loadingMsg = document.createElement('div');
        loadingMsg.className = 'chat-msg assistant';
        loadingMsg.innerHTML = 'Анализирую...';
        history.appendChild(loadingMsg);
        history.scrollTop = history.scrollHeight;

        fogLayer.style.opacity = '1';
        fogLayer.style.background = 'radial-gradient(circle at 50% 50%, rgba(95, 141, 144, 0.3) 0%, transparent 100%)';

        try {
            const roleData = ROLE_MAPPING[currentRole];

            let contextText = "";
            if (currentData) {
                contextText = `Заголовок: ${currentData.event.headline}. Сигнал: ${currentData.interpretation.why_it_matters}. Риски: ${currentData.interpretation.consequences.filter(c => c.type === 'risk').map(c => c.text).join(' ')}`;
            }

            const response = await fetch('http://127.0.0.1:8000/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    question: userQuestion,
                    company_id: roleData.uid,
                    role: currentRole,
                    context: contextText
                })
            });

            const result = await response.json();

            history.removeChild(loadingMsg);
            history.innerHTML += `<div class="chat-msg assistant">${result.answer}</div>`;
            history.scrollTop = history.scrollHeight;

        } catch (error) {
            history.removeChild(loadingMsg);
            history.innerHTML += `<div class="chat-msg assistant" style="color:#EF3124;">Ошибка: ${error.message}</div>`;
            history.scrollTop = history.scrollHeight;
        } finally {
            fogLayer.style.opacity = '';
            fogLayer.style.background = '';
        }
    };
});