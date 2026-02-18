# 🌌 ModderUI + ModderOS Core  
### **Deep Blue Liquid Glass UI Framework with Auto-Inject System Engine**  
**Version:** 4.0  
**Author:** @modderboy  
<p align="center">
  <img src="https://raw.githubusercontent.com/modderboyy/modderui/main/modderui-banner.svg" width="100%" />
</p>

ModderUI is a next-generation Liquid Glass UI kit designed for premium dashboards, super-apps, and macOS/iOS-inspired systems.  
ModderOS Core is the JavaScript engine that powers menus, modals, context actions, system clock, auto-inject features, and desktop-like interactions.

Together they form a complete **UI + UX System Framework**.

---

# 🇬🇧 English Version

## ✨ Features (UI Layer — ModderUI)
- Liquid Glass components (blur, gradients, glow)
- macOS/iOS-style top bar & sidebar  
- 3D interactive card engine  
- Floating Dock (iOS-style)  
- Calendar widget  
- WiFi Loader (animated)  
- Modal system with smooth scale animations  
- Native Dark Mode  
- Full palette + variable-driven theming  
- Responsive grid system  
- Neumorphic + glass hybrid effects  

---

## ⚙️ Features (System Layer — ModderOS Core JS Engine)
- Auto-inject menus (context & edit menu, even if HTML doesn’t contain them)  
- Error-free initialization (null checks everywhere)  
- Smart Context Menu (right-click tracking + bounds checking)  
- Smart Edit Menu (selection tracking + position auto alignment)  
- Modal Controller (open / close with animations)  
- System Clock rendering  
- Password visibility toggle  
- Global click handler for UI cleanup  
- App toggle endpoint support (Django-ready)  
- CSRF-safe requests  

---

# 📦 Folder Structure

```
modderui/
│
├── modderui.css          # Full CSS UI Framework
├── main.js               # ModderOS Core System Engine
├── README.md
└── demo/
    └── index.html        # Live example
```

---
<p align="center">
  <img src="https://raw.githubusercontent.com/modderboyy/modderui/main/Screenshot_1.png" width="100%" />
</p>
# 🚀 Installation

### 1. Add CSS
```html
<link rel="stylesheet" href="modderui.css">
```

### 2. Add JS
```html
<script src="main.js" defer></script>
```

### 3. Django Example
```django
<link href="{% static 'css/modderui.css' %}" rel="stylesheet">
<script src="{% static 'js/main.js' %}" defer></script>
```

---
<p align="center">
  <img src="https://raw.githubusercontent.com/modderboyy/modderui/main/Screenshot_2.png" width="100%" />
</p>
# 🧪 Usage Examples

## Glass Card
```html
<section class="card">
    <h1>Welcome to ModderUI</h1>
</section>
```

## Primary Button
```html
<button class="primary">Continue</button>
```

## Floating Dock
```html
<div class="floating-dock">
    <div class="dock-icon active">🏠</div>
    <div class="dock-icon">⚙️</div>
</div>
```
<p align="center">
  <img src="https://raw.githubusercontent.com/modderboyy/modderui/main/Screenshot_3.png" width="100%" />
</p>
## Context Menu (Auto Injected)
No HTML needed.  
The JS engine creates it automatically.

## Modal Trigger
```html
<button onclick="toggleModal('settingsModal')">Open Settings</button>
```

---

# 🔧 System Engine API (ModderOS Core)

## `toggleModal(id)`
Opens or closes a modal with animated scaling.

## `getCookie(name)`
Django-compatible CSRF cookie extraction.

## Auto-Injected Menus
Generated if missing:

### Context Menu:
- Refresh  
- Back  
- Settings  
- Logout  

### Edit Menu:
- Copy  
- Paste  
- Cut  
<p align="center">
  <img src="https://raw.githubusercontent.com/modderboyy/modderui/main/Screenshot_5.png" width="100%" />
</p>
No HTML required — system engine handles everything.

---

# 🎨 Theming

Modify palette via CSS root variables:

```css
--c-electric: #0d00a4;
--c-navy: #22007c;
--glass-blur: blur(30px);
```

All components inherit theme automatically.

---

# 📊 Suitable For:
- Super Apps  
- Admin Panels  
- Dashboards  
- Authentication Systems  
- Desktop-like Web Apps  
- ModderOS ecosystem  

---

# 🇺🇿 O‘zbekcha Versiya

## ✨ UI Xususiyatlari (ModderUI)
- Liquid Glass dizayn (blur + shaffof)  
- macOS/iOS uslubidagi menyu bar  
- 3D karta effektlari  
- Floating Dock  
- Kalendar vidjeti  
- WiFi loader animatsiyasi  
- Modal tizimi  
- To‘liq Dark Mode  
- O‘zgaruvchilar orqali boshqariladigan tema  
- Responsive Grid sistemasi  

---

## ⚙️ JS Xususiyatlari (ModderOS Core)
- HTML bo‘lmasa ham menyularni avto-yaratish  
- Xatosiz ishlaydigan null-check asosli kod  
- Smart Context Menu (o‘ng bosishda joylashuvni aniqlash)  
- Smart Edit Menu (matn tanlanganda chiqadi)  
- Modal boshqaruvi  
- Soat funksiyasi  
- Parolni ko‘rsatish tugmasi  
- Django CSRF qo‘llab-quvvatlashi  
- Global UI tozalash mexanizmi  

---

# 🧭 Foydalanish

## Glass Card:
```html
<section class="card">Salom ModderUI!</section>
```

## Tugma:
```html
<button class="primary">Davom etish</button>
```

## Modal:
```html
<button onclick="toggleModal('modal1')">Ochish</button>
```

---

# 👨‍💻 Developer  
**Made with ❤️ by @modderboy**  
ModderOS · ModderUI Ecosystem  

