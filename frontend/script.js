const USE_REAL_API = false; 
const API_URL = 'http://localhost:8000/api/insights';

document.addEventListener("DOMContentLoaded", () => {
    const insightContainer = document.getElementById('insight-container');
    const blockedContainer = document.getElementById('blocked-container');
    const emptyContainer = document.getElementById('empty-container');
    const dashboardScreen = document.getElementById('dashboard-screen');
    const entryScreen = document.getElementById('entry-screen');
    const timeline = document.getElementById('timeline-steps');

    let currentRole = 'CFO';
    let currentData = null;
    
    const ROLE_MAPPING = {
        'CFO': { file: 'insights_U_26030_CFO.json', uid: 'U_26030', toast: 'Акцент на финансовые риски' },
        'OWNER': { file: 'insights_U_1941_CFO.json', uid: 'U_1941', toast: 'Акцент на стратегические риски' },
        'CHIEF_ACCOUNTANT': { file: 'insights_U_106783_CFO.json', uid: 'U_106783', toast: 'Акцент на контрагентов' }
    };

    window.startAnalysis = function() {
        entryScreen.style.display = 'none';
        dashboardScreen.style.display = 'grid';
        loadInsight();
        loadTrace();
    };

    // Переключение табов
    window.switchTab = function(tabName) {
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
        
        document.getElementById(`tab-${tabName}`).classList.add('active');
        document.getElementById(`tab-content-${tabName}`).classList.add('active');
    };

    window.openSourceModal = function(label, ref) {
        document.getElementById('modal-body').innerHTML = `
            <p><strong>Документ:</strong> ${label}</p>
            <p><strong>Ссылка:</strong> <code>${ref}</code></p>
        `;
        document.getElementById('source-modal').style.display = 'flex';
    };

    window.openActionModal = function(title, text) {
        document.getElementById('action-modal-body').innerHTML = `
            <p><strong>${title}</strong></p>
            <p>${text}</p>
        `;
        document.getElementById('action-modal').style.display = 'flex';
    };

    window.closeModal = function(modalId) {
        document.getElementById(modalId).style.display = 'none';
    };

    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.style.display = 'none';
        });
    });

    async function loadInsight() {
        try {
            const roleData = ROLE_MAPPING[currentRole];
            const url = USE_REAL_API ? `${API_URL}?u_id=${roleData.uid}&role=${currentRole}` : roleData.file;
            
            const response = await fetch(url);
            if (!response.ok) throw new Error("Файл не найден");
            const data = await response.json();
            
            if (data.total === 0) { 
                insightContainer.style.display = 'none';
                if (data.empty_reason && data.empty_reason.code === 'blocked_by_guard') {
                    blockedContainer.style.display = 'block';
                } else {
                    emptyContainer.style.display = 'block';
                }
                return; 
            }

            currentData = data.items[0];
            const item = currentData;
            const event = item.event;
            const interp = item.interpretation;
            const scorePercent = item.relevance ? (item.relevance.score * 100).toFixed(0) : '?';

            insightContainer.style.display = 'block';
            blockedContainer.style.display = 'none';
            emptyContainer.style.display = 'none';

            insightContainer.innerHTML = `
                <div class="insight-card">
                    <div class="insight-header">
                        <div class="header-tags">
                            <span class="tag-alfa">Аналитика Альфа-Банка</span>
                            <span class="tag-score">Релевантность: ${scorePercent}%</span>
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
                            <div class="consequence ${c.type}">
                                <span class="badge badge-${c.type}">${c.type === 'risk' ? 'Риск' : 'Возможность'}</span>
                                <p>${c.text}</p>
                            </div>
                        `).join('')}
                    </div>
                    
                    <div class="bank-view-box">
                        <div class="bank-view-header">
                            <h4>Мнение Альфа-Банка</h4>
                            <span class="bank-date">На ${interp.bank_view.as_of_date || 'дату'}</span>
                        </div>
                        <blockquote>"${interp.bank_view.quote}"</blockquote>
                        <div class="source-links">
                            ${item.evidence ? item.evidence.map(e => `
                                <a href="javascript:void(0)" class="evidence-badge ${e.kind}" onclick="openSourceModal('${e.label}', '${e.ref}')">
                                    ${e.kind === 'verified_fact' ? 'Факт' : e.kind === 'alfa_view' ? 'Аналитика' : 'ИИ'}
                                </a>
                            `).join('') : ''}
                        </div>
                    </div>
                </div>
            `;

            // Отрисовка действий в таб
            document.getElementById('actions-list').innerHTML = item.actions.map(a => `
                <button class="action-btn" onclick="openActionModal('${a.text}', 'Переход в раздел: ${a.product_hint}')">
                    ${a.text}
                </button>
            `).join('');

        } catch (error) {
            console.error(error);
            insightContainer.innerHTML = `<div style="color:#FC8181;">Ошибка: ${error.message}</div>`;
        }
    }

    async function loadTrace() {
        try {
            const response = await fetch('trace_trc_4c90de.json');
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
                            ${step.note ? `<br><small style="color:#FC8181;">${step.note}</small>` : ''}
                        </div>
                    </div>
                `;
            }).join('');
        } catch (error) {
            console.error("Ошибка трассы", error);
        }
    }

    window.changeRole = function() {
        currentRole = document.getElementById('role-selector').value;
        loadInsight();
        loadTrace();
    };

    window.sendQuestion = function() {
        const input = document.getElementById('chat-input');
        const history = document.getElementById('chat-history');
        if (!input.value.trim()) return;

        const userQuestion = input.value;
        history.innerHTML += `<div class="chat-msg user">${userQuestion}</div>`;
        input.value = '';
        history.scrollTop = history.scrollHeight;

        setTimeout(() => {
            let answer = "В данных витрины ответа пока нет.";
            if (currentData) {
                const q = userQuestion.toLowerCase();
                if (q.includes('покупател') || q.includes('плательщик')) {
                    answer = `На основе данных: ${currentData.interpretation.why_it_matters}`;
                } else if (q.includes('риск')) {
                    answer = `Риски: ${currentData.interpretation.consequences.filter(c => c.type === 'risk').map(c => c.text).join(' ')}`;
                } else {
                    answer = `Главное: ${currentData.interpretation.why_it_matters.split('.')[0]}.`;
                }
            }
            history.innerHTML += `<div class="chat-msg assistant">${answer}</div>`;
            history.scrollTop = history.scrollHeight;
        }, 1000);
    };
});