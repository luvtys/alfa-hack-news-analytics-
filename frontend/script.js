const USE_REAL_API = false;
const API_URL = 'http://localhost:8000/api/insights';

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
        'CFO': { file: 'insights_U_26030_CFO.json', uid: 'U_26030', toast: 'Фокус: Финансовые риски', label: 'Финансовый директор' },
        'OWNER': { file: 'insights_U_1941_CFO.json', uid: 'U_1941', toast: 'Фокус: Стратегические риски', label: 'Собственник' },
        'CHIEF_ACCOUNTANT': { file: 'insights_U_106783_CFO.json', uid: 'U_106783', toast: 'Фокус: Контрагенты', label: 'Главный бухгалтер' }
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
        // 1. Создаем оверлей
        const overlay = document.createElement('div');
        overlay.className = 'fog-reveal-overlay';

        // 2. Добавляем три текста "хао"
        overlay.innerHTML = `
            <div class="fog-reveal-text">хао...</div>
            <div class="fog-reveal-text">хао...</div>
            <div class="fog-reveal-text">хао...</div>
        `;

        document.body.appendChild(overlay);

        // 3. Активируем затемнение
        setTimeout(() => {
            overlay.classList.add('active');
        }, 50);

        // 4. Туман двигается
        fogLayer.style.animation = 'fogPulse 3s infinite alternate';

        // 5. Через 3 секунды убираем оверлей и показываем экран
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
            loadTrace();
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

    // --- ЗАГРУЗКА ИНСАЙТА ---
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
                        <blockquote>"${interp.bank_view.quote}"</blockquote>
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

        } catch (error) {
            console.error(error);
            insightContainer.innerHTML = `<div style="color:var(--accent-danger);">Ошибка: ${error.message}</div>`;
        }
    }

    // --- ЗАГРУЗКА ТРАССЫ ---
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
                            ${step.note ? `<br><small style="color:var(--accent-danger);">${step.note}</small>` : ''}
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

    // --- ЧАТ ---
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
                    answer = `На основе данных: ${currentData.interpretation.why_it_matters}`;
                } else if (q.includes('риск')) {
                    answer = `Угрозы: ${currentData.interpretation.consequences.filter(c => c.type === 'risk').map(c => c.text).join(' ')}`;
                } else {
                    answer = `Главное: ${currentData.interpretation.why_it_matters.split('.')[0]}.`;
                }
            }
            history.innerHTML += `<div class="chat-msg assistant">${answer}</div>`;
            history.scrollTop = history.scrollHeight;
        }, 1500);
    };
});