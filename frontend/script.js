const USE_REAL_API = false; 
const API_URL = 'http://localhost:8000/api/insights';

document.addEventListener("DOMContentLoaded", () => {
    const insightContainer = document.getElementById('insight-container');
    const blockedContainer = document.getElementById('blocked-container');
    const emptyContainer = document.getElementById('empty-container');
    const traceContainer = document.getElementById('trace-container');
    const chatContainer = document.getElementById('chat-container');
    const clientProfile = document.getElementById('client-profile');
    const timeline = document.getElementById('timeline-steps');
    const dashboardGrid = document.getElementById('dashboard-grid');

    let currentRole = 'CFO';
    
    const ROLE_MAPPING = {
        'CFO': { file: 'insights_U_26030_CFO.json', uid: 'U_26030', toast: 'Акцент на финансовые риски' },
        'OWNER': { file: 'insights_U_1941_CFO.json', uid: 'U_1941', toast: 'Акцент на стратегические риски' },
        'CHIEF_ACCOUNTANT': { file: 'insights_U_106783_CFO.json', uid: 'U_106783', toast: 'Акцент на контрагентов' }
    };

    function showToast(message) {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.innerHTML = `<span>🔔</span> ${message}`;
        container.appendChild(toast);
        setTimeout(() => {
            toast.classList.add('fade-out');
            toast.addEventListener('animationend', () => toast.remove());
        }, 3500);
    }

    window.startAnalysis = function() {
        document.getElementById('entry-widget').style.display = 'none';
        document.getElementById('demo-panel').style.display = 'flex';
        dashboardGrid.style.display = 'grid';
        switchState('insight');
    };

    // Отрисовка профиля (только теги, без лишнего заголовка)
    function renderProfile(client) {
        if (!client || !client.features_used) return;
        clientProfile.style.display = 'block';
        
        const tagsContainer = document.getElementById('profile-tags');
        tagsContainer.innerHTML = client.features_used.map(f => `
            <div class="profile-tag">
                ${f.label}: <strong>${typeof f.value === 'number' ? f.value.toLocaleString('ru-RU') : f.value}</strong>
            </div>
        `).join('');

        const missingContainer = document.getElementById('profile-missing');
        if (client.features_missing && client.features_missing.length > 0) {
            const missingMapping = {
                'AMOUNT_WORKERS_SPARK_GRADATION': 'численность сотрудников (СПАРК)',
                'AMOUNT_WORKERS_FNS_GRADATION': 'численность сотрудников (ФНС)',
                'FTS_COUNTRY_NAME': 'страна закупки (ФТС)'
            };
            const humanReadableMissing = client.features_missing.map(code => missingMapping[code] || code);
            missingContainer.style.display = 'block';
            missingContainer.innerText = `Ограничение: нет данных о ${humanReadableMissing.join(', ')}`;
        } else {
            missingContainer.style.display = 'none';
        }
    }

    async function renderInsight() {
        try {
            const roleData = ROLE_MAPPING[currentRole];
            const url = USE_REAL_API ? `${API_URL}?u_id=${roleData.uid}&role=${currentRole}` : roleData.file;
            
            const response = await fetch(url);
            if (!response.ok) throw new Error("Файл не найден: " + url);
            const data = await response.json();
            
            if (data.total === 0) { 
                if (data.empty_reason && data.empty_reason.code === 'blocked_by_guard') switchState('blocked');
                else switchState('empty');
                return; 
            }

            const item = data.items[0];
            const event = item.event;
            const interp = item.interpretation;

            if (item.client) renderProfile(item.client);

            const scorePercent = item.relevance ? (item.relevance.score * 100).toFixed(0) : '?';
            const thresholdPercent = item.relevance ? (item.relevance.threshold * 100).toFixed(0) : '?';
            const scoreTitle = item.relevance ? `Оценка релевантности: ${scorePercent}% (порог ${thresholdPercent}%)` : '';

            insightContainer.innerHTML = `
                <div class="insight-card">
                    <div class="insight-header">
                        <div class="header-tags">
                            <span class="tag-alfa">Аналитика Альфа-Банка</span>
                            <span class="tag-score" title="${scoreTitle}">Релевантность: ${scorePercent}%</span>
                        </div>
                        <span class="date">${new Date(event.published_at).toLocaleDateString('ru-RU')}</span>
                    </div>
                    <h1 class="event-headline">${event.headline}</h1>
                    
                    <div class="why-matters-box">
                        <h3>Почему это важно для вашей компании?</h3>
                        <p>${interp.why_it_matters}</p>
                    </div>
                    
                    <div class="consequences">
                        ${interp.consequences.map(c => `
                            <div class="consequence ${c.type === 'risk' ? 'risk' : 'opportunity'}">
                                <span class="badge badge-${c.type}">${c.type === 'risk' ? '⚠️ Риск' : '💡 Возможность'}</span>
                                <p>${c.text}</p>
                            </div>
                        `).join('')}
                    </div>
                    
                    <div class="bank-view-box">
                        <div class="bank-view-header">
                            <h4>Мнение Альфа-Банка</h4>
                            <span class="bank-date">Актуально на: ${interp.bank_view.as_of_date || 'дата не указана'}</span>
                        </div>
                        <blockquote>"${interp.bank_view.quote}"</blockquote>
                        <div class="source-links">
                            ${item.evidence ? item.evidence.map(e => `
                                <a href="#" class="evidence-badge ${e.kind}" title="${e.label}" onclick="alert('Источник: ${e.label}\\nСсылка: ${e.ref}')">
                                    ${e.kind === 'verified_fact' ? 'Факт банка' : 
                                      e.kind === 'alfa_view' ? 'Аналитика' : 'Вывод ИИ'}
                                </a>
                            `).join('') : ''}
                        </div>
                    </div>

                    <div class="actions-box">
                        <h4>Рекомендуемые действия</h4>
                        ${item.actions ? item.actions.map(a => `
                            <button class="action-btn" onclick="alert('Переход в раздел банка: ${a.product_hint}')">
                                ${a.text}
                            </button>
                        `).join('') : ''}
                    </div>
                </div>
            `;
        } catch (error) {
            console.error(error);
            insightContainer.innerHTML = `<div style="background:#ffeaea; padding:20px; border-radius:12px; color:#d32f2f;"><h3>Ошибка загрузки</h3><p>${error.message}</p></div>`;
        }
    }

    async function renderTrace() {
        try {
            const response = await fetch('trace_trc_4c90de.json');
            const data = await response.json();
            timeline.innerHTML = data.steps.map(step => {
                let icon = '✓';
                if (step.status === 'failed') icon = '✗';
                if (step.status === 'retry') icon = '↻';
                
                let details = '';
                if (step.tool || step.result_summary) {
                    details = `
                        <details>
                            <summary>Детали шага</summary>
                            ${step.tool ? `<p><strong>Инструмент:</strong> ${step.tool}</p>` : ''}
                            ${step.result_summary ? `<p><strong>Результат:</strong> ${step.result_summary}</p>` : ''}
                            ${step.tokens_in ? `<p><strong>Токенов:</strong> ${step.tokens_in} in / ${step.tokens_out} out</p>` : ''}
                        </details>
                    `;
                }

                return `
                    <div class="step ${step.status}">
                        <div class="step-icon">${icon}</div>
                        <div class="step-content">
                            <strong>Шаг ${step.step_no}: ${step.title}</strong>
                            ${step.note ? `<br><small style="color:#d32f2f;">${step.note}</small>` : ''}
                            ${details}
                        </div>
                    </div>
                `;
            }).join('');
        } catch (error) {
            console.error("Ошибка трассы", error);
            timeline.innerHTML = `<p style="color:#999; font-size:12px;">Трасса недоступна.</p>`;
        }
    }

    window.switchState = function(state) {
        document.querySelectorAll('.btn-demo').forEach(btn => btn.classList.remove('active'));
        insightContainer.style.display = 'none';
        blockedContainer.style.display = 'none';
        emptyContainer.style.display = 'none';
        traceContainer.style.display = 'none';
        chatContainer.style.display = 'none';
        clientProfile.style.display = 'none';

        if (state === 'insight') {
            document.getElementById('btn-insight').classList.add('active');
            insightContainer.style.display = 'block';
            traceContainer.style.display = 'block';
            chatContainer.style.display = 'block';
            renderInsight();
            renderTrace();
        } 
        else if (state === 'blocked') {
            document.getElementById('btn-blocked').classList.add('active');
            blockedContainer.style.display = 'block';
            document.getElementById('blocked-detail').innerHTML = `
                <p><strong>Причина:</strong> Наблюдаемый поток покрывает менее 20% выручки — вывод о зависимости недостоверен.</p>
                <p><strong>Что видит банк:</strong> Покрытие выручки: 3.2%. Всего плательщиков: 3.</p>
            `;
        } 
        else if (state === 'empty') {
            document.getElementById('btn-empty').classList.add('active');
            emptyContainer.style.display = 'block';
            document.getElementById('empty-detail').innerHTML = `
                <p><strong>Проверено новостей:</strong> 214</p>
                <p><strong>Порог релевантности:</strong> 0.55</p>
                <p><strong>Лучший результат:</strong> 0.41</p>
            `;
        }
    };

    window.changeRole = function() {
        const select = document.getElementById('role-selector');
        currentRole = select.value;
        const roleInfo = ROLE_MAPPING[currentRole];
        
        showToast(`Интерфейс переключен: ${roleInfo.toast}`);
        dashboardGrid.classList.add('switching');

        setTimeout(() => {
            document.getElementById('insight-container').innerHTML = '';
            document.getElementById('timeline-steps').innerHTML = '';
            switchState('insight');
            dashboardGrid.classList.remove('switching');
        }, 300);
    };

    window.sendQuestion = function() {
        const input = document.getElementById('chat-input');
        const history = document.getElementById('chat-history');
        if (!input.value.trim()) return;

        history.innerHTML += `<div class="chat-msg user">${input.value}</div>`;
        input.value = '';
        history.scrollTop = history.scrollHeight;

        setTimeout(() => {
            history.innerHTML += `<div class="chat-msg assistant">В данных витрины ответа пока нет (ждем API).</div>`;
            history.scrollTop = history.scrollHeight;
        }, 800);
    };
});