const USE_REAL_API = true;
const API_URL = 'http://127.0.0.1:8000/api/insight';

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

    const ROLE_MAPPING = {
        'CFO': { uid: 'U_26030', toast: 'Фокус: Финансовые риски', label: 'Финансовый директор' },
        'OWNER': { uid: 'U_1941', toast: 'Фокус: Стратегические риски', label: 'Собственник' },
        'CHIEF_ACCOUNTANT': { uid: 'U_106783', toast: 'Фокус: Контрагенты', label: 'Главный бухгалтер' }
    };

    // ТЕСТОВОЕ СОБЫТИЕ ДЛЯ ДЕМО (пока нет парсера новостей)
    const DEMO_EVENT = {
        id: "event_001",
        title: "ЦБ РФ сохранил ключевую ставку на уровне 14% годовых",
        facts: "Совет директоров Банка России принял решение сохранить ключевую ставку на уровне 14% годовых.",
        date: "2026-09-11",
        region: "Свердловская область",
        event_type: "monetary_policy",
        entities: ["KEY_RATE", "CBR"],
        scope: "national"
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

    // --- СТАРТ АНАЛИЗА С ТЕКСТОМ "ХАО" ---
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

            loadInsight();
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

    // --- РЕЖИМ ОБЪЯСНЕНИЯ (ГРАФ) ---
    window.openExplainMode = function () {
        const overlay = document.getElementById('ai-explain-overlay');
        overlay.style.display = 'flex';

        const nodes = overlay.querySelectorAll('.node');
        nodes.forEach((node, index) => {
            setTimeout(() => {
                node.classList.add('active');
                if (nodes[index + 1] && window.effects) {
                    const rect1 = node.getBoundingClientRect();
                    const rect2 = nodes[index + 1].getBoundingClientRect();
                    window.effects.drawRoot(
                        rect1.left + rect1.width / 2, rect1.bottom,
                        rect2.left + rect2.width / 2, rect2.top
                    );
                }
            }, index * 800);
        });
    };

    window.closeExplainMode = function () {
        document.getElementById('ai-explain-overlay').style.display = 'none';
    };

    // --- СМЕНА РОЛИ ---
    window.changeRole = function (roleValue) {
        currentRole = roleValue;

        fogLayer.style.opacity = '1';
        fogLayer.style.background = 'radial-gradient(circle at 50% 50%, rgba(95, 141, 144, 0.6) 0%, rgba(7, 19, 21, 1) 100%)';

        setTimeout(() => {
            loadInsight();
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

    // --- ЗАГРУЗКА ИНСАЙТА (POST-ЗАПРОС) ---
    async function loadInsight() {
        try {
            const roleData = ROLE_MAPPING[currentRole];

            // Показываем загрузку
            insightContainer.innerHTML = '<div style="color: #fff; padding: 20px;">Загрузка данных...</div>';
            insightContainer.style.display = 'block';
            blockedContainer.style.display = 'none';
            emptyContainer.style.display = 'none';

            const response = await fetch(API_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    company_id: roleData.uid,
                    role: currentRole,
                    event: DEMO_EVENT
                })
            });

            const result = await response.json();

            // Обработка отказа (skipped)
            if (result.status === 'skipped') {
                insightContainer.style.display = 'none';
                emptyContainer.style.display = 'block';
                document.getElementById('empty-message-text').innerText = result.reason || 'Новость нерелевантна для этой компании.';
                return;
            }

            if (result.status === 'error') {
                throw new Error(result.message);
            }

            if (result.status === 'success') {
                const item = result.insight;
                currentData = item;

                // Обработка guard'ов (refused)
                if (item.data_quality && item.data_quality.refused && item.data_quality.refused.length > 0) {
                    insightContainer.style.display = 'none';
                    blockedContainer.style.display = 'block';
                    document.getElementById('blocked-message-text').innerText = item.data_quality.refused[0].message;
                    return;
                }

                const event = item.event;
                const interp = item.interpretation;
                const scorePercent = item.relevance ? (item.relevance.score * 100).toFixed(0) : '?';

                insightContainer.style.display = 'block';
                blockedContainer.style.display = 'none';
                emptyContainer.style.display = 'none';

                // Проверка на наличие цитаты (если нет - используем text)
                const bankQuote = interp.bank_view.quote || interp.bank_view.text;

                insightContainer.innerHTML = `
                    <div class="insight-card">
                        <div class="insight-header">
                            <div class="header-tags">
                                <span class="tag-alfa">Alfa Analytics</span>
                                <span class="tag-score">Релевантность ${scorePercent}%</span>
                            </div>
                            <span class="date">${new Date(event.published_at).toLocaleDateString('ru-RU')}</span>
                        </div>
                        <h1 class="event-headline">${event.headline}</h1>
                        
                        <div class="why-matters-box">
                            <h3>Скрытый сигнал</h3>
                            <p>${interp.why_it_matters}</p>
                        </div>
                        
                        <div class="consequences">
                            ${interp.consequences.map(c => `
                                <div class="consequence ${c.type}">
                                    <span class="badge badge-${c.type}">${c.type === 'risk' ? 'Угроза' : 'Возможность'}</span>
                                    <p>${c.text}</p>
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
                                ${item.evidence ? item.evidence.map(e => `
                                    <a href="javascript:void(0)" class="evidence-badge ${e.kind}" onclick="openSourceModal('${e.label}', '${e.ref}')">
                                        ${e.kind === 'verified_fact' ? 'Факт' : e.kind === 'alfa_view' ? 'Аналитика' : 'AI'}
                                    </a>
                                `).join('') : ''}
                            </div>
                        </div>
                    </div>
                `;

                document.getElementById('actions-list').innerHTML = item.actions.map(a => `
                    <button class="action-btn" onclick="openActionModal('${a.text}', 'Переход в раздел: ${a.product_hint}')">
                        ${a.text}
                    </button>
                `).join('');
            }

        } catch (error) {
            console.error(error);
            insightContainer.style.display = 'block';
            insightContainer.innerHTML = `<div style="color:#EF3124; padding: 20px;">Ошибка загрузки данных: ${error.message}</div>`;
        }
    }

    // --- ЗАГРУЗКА ТРАССЫ (МОК, ТАК КАК БЭК ПОКА НЕ ОТДАЕТ TRACE) ---
    async function loadTrace() {
        try {
            // Для демо используем моковый файл трассы, который лежит у фронта
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
                            ${step.note ? `<br><small style="color:#EF3124;">${step.note}</small>` : ''}
                        </div>
                    </div>
                `;
            }).join('');

            if (!document.getElementById('explain-btn')) {
                const btn = document.createElement('button');
                btn.id = 'explain-btn';
                btn.className = 'action-btn';
                btn.style.marginTop = '20px';
                btn.innerText = 'Как получен вывод? (Граф)';
                btn.onclick = openExplainMode;
                timeline.appendChild(btn);
            }
        } catch (error) {
            console.error("Ошибка трассы", error);
        }
    }

    // --- ЧАТ (ОТВЕЧАЕТ НА ОСНОВЕ РЕАЛЬНЫХ ДАННЫХ) ---
    window.sendQuestion = function () {
        const input = document.getElementById('chat-input');
        const history = document.getElementById('chat-history');
        if (!input.value.trim()) return;

        const userQuestion = input.value;
        history.innerHTML += `<div class="chat-msg user">${userQuestion}</div>`;
        input.value = '';
        history.scrollTop = history.scrollHeight;

        fogLayer.style.opacity = '1';
        fogLayer.style.background = 'radial-gradient(circle at 50% 50%, rgba(95, 141, 144, 0.3) 0%, transparent 100%)';
        setTimeout(() => { fogLayer.style.opacity = ''; fogLayer.style.background = ''; }, 1000);

        setTimeout(() => {
            let answer = "В данных витрины ответа пока нет.";
            if (currentData) {
                const q = userQuestion.toLowerCase();
                if (q.includes('покупател') || q.includes('плательщик')) {
                    // Ищем в why_it_matters упоминание контрагентов
                    answer = `На основе данных: ${currentData.interpretation.why_it_matters}`;
                } else if (q.includes('риск')) {
                    const risks = currentData.interpretation.consequences.filter(c => c.type === 'risk').map(c => c.text).join(' ');
                    answer = risks ? `Угрозы: ${risks}` : 'Явных угроз в инсайте не выделено.';
                } else {
                    answer = `Главное: ${currentData.interpretation.why_it_matters.split('.')[0]}.`;
                }
            }
            history.innerHTML += `<div class="chat-msg assistant">${answer}</div>`;
            history.scrollTop = history.scrollHeight;
        }, 1500);
    };
});