/**
 * ModderOS Core - v4.0 (Error Free & Auto-Inject)
 * Features: Auto Menu Injection, Null Checks, Modal Logic
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Global Menularni yaratish (HTMLda bo'lmasa ham ishlaydi)
    injectGlobalMenus();

    // 2. Soatni ishga tushirish (Xatoliksiz)
    initClock();

    // 3. Parolni ko'rsatish (Login page uchun)
    initPasswordToggle();


    // 5. Menyular logikasi
    initContextLogic();
});

/* --- A. AUTO INJECT MENUS (Xatolikni oldini olish uchun) --- */
function injectGlobalMenus() {
    // Agar Context Menu yo'q bo'lsa, yaratamiz
    if (!document.getElementById('context-menu')) {
        const ctxHtml = `
            <div id="context-menu" class="ios-context-menu hidden">
                <div class="ctx-item" data-action="refresh">Yangilash</div>
                <div class="ctx-item" data-action="back">Orqaga</div>
                <div class="ctx-separator"></div>
                <div class="ctx-item" data-action="settings">Sozlamalar</div>
                <div class="ctx-item destructive" data-action="logout">Chiqish</div>
            </div>`;
        document.body.insertAdjacentHTML('beforeend', ctxHtml);
    }

    // Agar Edit Menu yo'q bo'lsa, yaratamiz
    if (!document.getElementById('edit-menu')) {
        const editHtml = `
            <div id="edit-menu" class="edit-pill-menu hidden">
                <button class="edit-pill-btn" data-action="copy">Nusxalash</button>
                <button class="edit-pill-btn" data-action="paste">Joylash</button>
                <button class="edit-pill-btn" data-action="cut">Qirqish</button>
            </div>`;
        document.body.insertAdjacentHTML('beforeend', editHtml);
    }
}

/* --- B. CLOCK (Null Check bilan) --- */
function initClock() {
    const clockEl = document.getElementById('clock') || document.getElementById('system-clock');
    if (!clockEl) return; // Agar soat elementi yo'q bo'lsa, to'xtaydi (Xatolik bermaydi)

    const update = () => {
        const now = new Date();
        let h = now.getHours();
        let m = now.getMinutes();
        h = h % 12 || 12;
        m = m < 10 ? '0' + m : m;
        clockEl.textContent = `${h}:${m}`;
    };
    setInterval(update, 1000);
    update();
}

/* --- C. PASSWORD TOGGLE --- */
function initPasswordToggle() {
    const btn = document.getElementById('toggle-pass');
    const input = document.getElementById('password');
    if (btn && input) {
        btn.addEventListener('click', () => {
            const type = input.type === 'password' ? 'text' : 'password';
            input.type = type;
            btn.style.fill = type === 'text' ? '#0a84ff' : 'rgba(255,255,255,0.5)';
        });
    }
}

// /* --- D. LOGIN FORM --- */
// function initLoginForm() {
//     const form = document.getElementById('login-form');
//     if (form) {
//         form.addEventListener('submit', (e) => {
//             e.preventDefault();
//             const btn = document.getElementById('btn-submit');
//             const loader = document.getElementById('loader-container');

//             if(btn) btn.style.display = 'none';
//             if(loader) loader.style.display = 'flex';

//             setTimeout(() => {
//                 window.location.href = '/dashboard'; // Dashboardga o'tish
//             }, 2000);
//         });
//     }
// }

/* --- E. MENU & MODAL LOGIC (CORE) --- */
function initContextLogic() {
    const contextMenu = document.getElementById('context-menu');
    const editMenu = document.getElementById('edit-menu');

    // Hamma menyuni yopish
    const hideAll = () => {
        if(contextMenu) contextMenu.classList.add('hidden');
        if(editMenu) editMenu.classList.add('hidden');
    };

    // 1. Context Menu (Right Click)
    document.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        hideAll();

        if (!contextMenu) return;

        let x = e.clientX;
        let y = e.clientY;

        // Ekranda sig'ishini tekshirish
        if (x + 200 > window.innerWidth) x -= 200;
        if (y + 200 > window.innerHeight) y -= 200;

        contextMenu.style.left = `${x}px`;
        contextMenu.style.top = `${y}px`;

        requestAnimationFrame(() => {
            contextMenu.classList.remove('hidden');
        });
    });

    // 2. Edit Menu (Text Selection)
    document.addEventListener('mouseup', (e) => {
        if (contextMenu && contextMenu.contains(e.target)) return;

        setTimeout(() => {
            const selection = window.getSelection();
            const text = selection.toString();

            if (text.length > 0 && editMenu) {
                const range = selection.getRangeAt(0);
                const rect = range.getBoundingClientRect();

                hideAll();

                let top = rect.top - 50 + window.scrollY;
                let left = rect.left + (rect.width / 2) - (editMenu.offsetWidth / 2);

                if (top < 10) top = rect.bottom + 10 + window.scrollY;

                editMenu.style.top = `${top}px`;
                editMenu.style.left = `${left}px`;
                editMenu.classList.remove('hidden');
            }
        }, 50);
    });

    // 3. Global Click (Yopish)
    document.addEventListener('mousedown', (e) => {
        // Null check qo'shildi
        const clickedCtx = contextMenu && contextMenu.contains(e.target);
        const clickedEdit = editMenu && editMenu.contains(e.target);

        if (!clickedCtx && !clickedEdit) {
            hideAll();
        }
    });

    // 4. Menu Actions
    document.addEventListener('click', (e) => {
        if (e.target.closest('[data-action]')) {
            const action = e.target.getAttribute('data-action');

            if(['copy', 'cut', 'paste'].includes(action)) {
                document.execCommand(action);
            } else if (action === 'refresh') {
                window.location.reload();
            } else if (action === 'logout') {
                window.location.href = '/logout';
            } else if (action === 'back') {
                window.history.back();
            } else if (action === 'settings') {
                window.location.href='/settings';
            }
            hideAll();
        }
    });
}

/* --- F. MODAL SYSTEM (Dashboard uchun) --- */
function toggleModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        if (modal.classList.contains('active')) {
            modal.classList.remove('active');
            setTimeout(() => modal.style.display = 'none', 300);
        } else {
            modal.style.display = 'flex';
            setTimeout(() => modal.classList.add('active'), 10);
        }
    }
}

// Modaldan tashqariga bosganda yopish
window.onclick = function(event) {
    if (event.target.classList.contains('modal-overlay')) {
        event.target.classList.remove('active');
        setTimeout(() => event.target.style.display = 'none', 300);
    }
}
function toggleApp(appId) {
    fetch(`/apps/toggle/${appId}/`, {
        method: "POST",
        headers: {
            "X-CSRFToken": getCookie("csrftoken"),
        }
    })
    .then(res => res.json())
    .then(data => {
        console.log("Updated:", data);
    })
    .catch(err => console.log("Error", err));
}


// Django CSRF cookie olish
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");
        for (let cookie of cookies) {
            cookie = cookie.trim();
            if (cookie.substring(0, name.length + 1) === (name + "=")) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
