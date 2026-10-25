// animations.js

class ForestEffects {
    constructor() {
        this.canvas = document.getElementById('effects-canvas');
        if (!this.canvas) return;

        this.ctx = this.canvas.getContext('2d');
        this.resize();
        window.addEventListener('resize', () => this.resize());

        this.particles = [];
        this.roots = [];
        this.rayActive = false;
        this.rayPath = null;
        this.rayProgress = 0;

        this.animate();
    }

    resize() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
    }

    // 2. ПРОРАСТАНИЕ КОРНЕЙ
    drawRoot(startX, startY, endX, endY) {
        // Запоминаем контрольную точку для изгиба, чтобы корень не дрожал
        const midX = (startX + endX) / 2;
        const midY = (startY + endY) / 2;
        const curveX = midX + (Math.random() - 0.5) * 40; // Смещение для естественности
        const curveY = midY + (Math.random() - 0.5) * 40;

        this.roots.push({
            x: startX, y: startY,
            tx: endX, ty: endY,
            cx: curveX, cy: curveY, // Контрольная точка
            progress: 0
        });
    }

    // 6. СБОРКА ИНСАЙТА ИЗ ЧАСТИЦ
    spawnInsightParticles(targetX, targetY) {
        for (let i = 0; i < 50; i++) {
            this.particles.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height,
                vx: (targetX - Math.random() * this.canvas.width) * 0.02,
                vy: (targetY - Math.random() * this.canvas.height) * 0.02,
                life: 1
            });
        }
    }

    // 7. ЛУЧ ИСТИНЫ
    activateTruthRay(pathPoints) {
        this.rayActive = true;
        this.rayPath = pathPoints; // Массив точек {x, y}
        this.rayProgress = 0;
    }

    animate() {
        if (!this.ctx) return;
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        // --- РИСУЕМ КОРНИ ---
        this.roots.forEach((root, index) => {
            if (root.progress < 1) root.progress += 0.02;

            this.ctx.beginPath();
            this.ctx.moveTo(root.x, root.y);

            // Используем сохраненную контрольную точку (без рандома в кадре)
            this.ctx.quadraticCurveTo(
                root.cx, root.cy,
                root.x + (root.tx - root.x) * root.progress,
                root.y + (root.ty - root.y) * root.progress
            );

            this.ctx.strokeStyle = 'rgba(156, 198, 201, 0.4)';
            this.ctx.lineWidth = 2;
            this.ctx.stroke();

            // Удаляем корень, когда он полностью пророс
            if (root.progress >= 1) {
                this.roots.splice(index, 1);
            }
        });

        // --- РИСУЕМ ЧАСТИЦЫ ---
        this.particles.forEach((p, i) => {
            p.x += p.vx;
            p.y += p.vy;
            p.life -= 0.02;

            this.ctx.fillStyle = `rgba(156, 198, 201, ${p.life})`;
            this.ctx.fillRect(p.x, p.y, 2, 2);

            if (p.life <= 0) this.particles.splice(i, 1);
        });

        // --- РИСУЕМ ЛУЧ ИСТИНЫ ---
        if (this.rayActive && this.rayPath) {
            this.rayProgress += 0.01;
            if (this.rayProgress > 1) {
                this.rayActive = false;
                this.rayProgress = 0;
            } else {
                const totalPoints = this.rayPath.length;
                const currentIndex = Math.floor(this.rayProgress * (totalPoints - 1));
                const point = this.rayPath[currentIndex];

                // Рисуем светящуюся точку, которая бежит по пути
                this.ctx.beginPath();
                this.ctx.arc(point.x, point.y, 6, 0, Math.PI * 2);
                this.ctx.fillStyle = 'rgba(156, 198, 201, 0.8)';
                this.ctx.shadowColor = 'rgba(156, 198, 201, 1)';
                this.ctx.shadowBlur = 20;
                this.ctx.fill();
                this.ctx.shadowBlur = 0; // Сбрасываем
            }
        }

        requestAnimationFrame(() => this.animate());
    }
}

// Глобальная инициализация
window.effects = new ForestEffects();