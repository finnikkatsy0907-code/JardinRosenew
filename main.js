const products = [
    {
        id: 1,
        name: "Смартфон 'Nebula X1'",
        price: 89900,
        popularity: 150,
        category: "Электроника",
        image: "product-1.jpg"
    },
    {
        id: 2,
        name: "Наушники 'Nova Sound'",
        price: 24500,
        popularity: 120,
        category: "Электроника",
        image: "product-2.jpg"
    },
    {
        id: 3,
        name: "Куртка 'Star Cruiser'",
        price: 15700,
        popularity: 90,
        category: "Одежда",
        image: "product-3.jpg"
    },
    {
        id: 4,
        name: "Кроссовки 'Moon Walker'",
        price: 12300,
        popularity: 110,
        category: "Одежда",
        image: "product-4.jpg"
    },
    {
        id: 5,
        name: "Проектор 'Galaxy Core'",
        price: 8900,
        popularity: 200,
        category: "Дом и сад",
        image: "product-5.jpg"
    },
    {
        id: 6,
        name: "Часы 'Aurora Time'",
        price: 32000,
        popularity: 85,
        category: "Электроника",
        image: "product-6.jpg"
    }
];

let cartCount = 0;
let cartItems = []; // МАССИВ ДЛЯ ТОВАРОВ В КОРЗИНЕ
let currentCategory = 'Все';
let currentSort = 'popular';

const productGrid = document.getElementById('productGrid');
const cartBadge = document.getElementById('cartBadge');
const searchInput = document.getElementById('searchInput');
const sortSelect = document.getElementById('sortSelect');
const minPriceInput = document.getElementById('minPrice');
const maxPriceInput = document.getElementById('maxPrice');
const categoryItems = document.querySelectorAll('.category-item');

// Модальное окно
const authModal = document.getElementById('authModal');
const pilotBtn = document.getElementById('pilotBtn'); // Кнопка Пилот
const closeModal = document.querySelector('.close-modal');
const loginForm = document.getElementById('loginForm');
const registerForm = document.getElementById('registerForm');

// Элементы корзины
const cartModal = document.getElementById('cartModal');
const closeCart = document.getElementById('closeCart');
const cartBtn = document.getElementById('cartBtn');
const cartItemsList = document.getElementById('cartItemsList');
const cartTotalSum = document.getElementById('cartTotalSum');

function renderProducts() {
    let filtered = products.filter(p => {
        const matchesCategory = currentCategory === 'Все' || p.category === currentCategory;
        const min = parseFloat(minPriceInput.value) || 0;
        const max = parseFloat(maxPriceInput.value) || Infinity;
        const matchesPrice = p.price >= min && p.price <= max;
        const matchesSearch = p.name.toLowerCase().includes(searchInput.value.toLowerCase());

        return matchesCategory && matchesPrice && matchesSearch;
    });

    if (currentSort === 'cheap') {
        filtered.sort((a, b) => a.price - b.price);
    } else if (currentSort === 'expensive') {
        filtered.sort((a, b) => b.price - a.price);
    } else {
        filtered.sort((a, b) => b.popularity - a.popularity);
    }

    productGrid.innerHTML = '';
    filtered.forEach(product => {
        const card = document.createElement('div');
        card.className = 'product-card';
        card.innerHTML = `
            <img src="${product.image}" alt="${product.name}" class="product-image">
            <div class="product-price">${product.price.toLocaleString()} 💫</div>
            <div class="product-name">${product.name}</div>
            <div class="product-actions">
                <button class="btn-buy" onclick="handleBuy(${product.id})">Купить</button>
                <button class="btn-cart" onclick="addToCart(event, ${product.id})">В корзину</button>
            </div>
        `;
        productGrid.appendChild(card);
    });
}

window.addToCart = function (event, id) {
    const product = products.find(p => p.id === id);
    if (!product) return;

    cartItems.push(product);
    cartCount = cartItems.length;
    cartBadge.textContent = cartCount;

    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = 'ДОБАВЛЕНО';
    btn.style.borderColor = 'var(--secondary-color)';
    btn.style.color = 'var(--secondary-color)';

    setTimeout(() => {
        btn.textContent = originalText;
        btn.style.borderColor = '';
        btn.style.color = '';
    }, 1500);
};

window.handleBuy = function (id) {
    alert('Система: Подготовка к гиперпрыжку... Оформляем товар #' + id);
};

// --- ЛОГИКА АВТОРИЗАЦИИ ---

window.openAuthModal = function () {
    authModal.style.display = 'flex';
    document.body.style.overflow = 'hidden'; // Запрет прокрутки
};

window.closeAuthModal = function () {
    authModal.style.display = 'none';
    document.body.style.overflow = '';
};

window.switchAuthMode = function (mode) {
    if (mode === 'register') {
        loginForm.style.display = 'none';
        registerForm.style.display = 'block';
    } else {
        loginForm.style.display = 'block';
        registerForm.style.display = 'none';
    }
};

window.handleLoginSubmit = function () {
    const id = document.getElementById('loginId').value;
    const pass = document.getElementById('loginPass').value;
    if (id && pass) {
        alert(`Добро пожаловать на борт, ${id}! Гиперпрыжок разрешен.`);
        closeAuthModal();
    } else {
        alert('Ошибка: Введите ваши позывные!');
    }
};

window.handleRegisterSubmit = function () {
    const phone = document.getElementById('regPhone').value;
    const name = document.getElementById('regName').value;
    const pass = document.getElementById('regPass').value;
    if (phone && name && pass) {
        alert(`Регистрация завершена! Пилот ${name} внесен в базу данных флота.`);
        closeAuthModal();
    } else {
        alert('Ошибка: Заполните все данные для регистрации!');
    }
};

// Слушатели
pilotBtn.addEventListener('click', openAuthModal);
closeModal.addEventListener('click', closeAuthModal);
// Слушатели корзины
cartBtn.addEventListener('click', openCartModal);
closeCart.addEventListener('click', closeCartModal);

// --- ЛОГИКА КОРЗИНЫ ---

function openCartModal() {
    renderCart();
    cartModal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

function closeCartModal() {
    cartModal.style.display = 'none';
    document.body.style.overflow = '';
}

function renderCart() {
    cartItemsList.innerHTML = '';
    let total = 0;

    if (cartItems.length === 0) {
        cartItemsList.innerHTML = '<div class="empty-cart-msg">Ваш отсек пуст. Добавьте снаряжение!</div>';
    } else {
        cartItems.forEach((item, index) => {
            total += item.price;
            const itemElement = document.createElement('div');
            itemElement.className = 'cart-item';
            itemElement.innerHTML = `
                <img src="${item.image}" alt="${item.name}" class="cart-item-img">
                <div class="cart-item-info">
                    <div class="cart-item-name">${item.name}</div>
                    <div class="cart-item-price">${item.price.toLocaleString()} 💫</div>
                </div>
                <button class="btn-remove" onclick="removeFromCart(${index})">&times;</button>
            `;
            cartItemsList.appendChild(itemElement);
        });
    }

    cartTotalSum.textContent = total.toLocaleString() + ' 💫';
}

window.removeFromCart = function (index) {
    cartItems.splice(index, 1);
    cartCount = cartItems.length;
    cartBadge.textContent = cartCount;
    renderCart();
};

window.handleCheckout = function () {
    if (cartItems.length === 0) {
        alert('Система: Отсек пуст. Нечего отправлять в гиперпространство.');
    } else {
        alert('Система: Курс проложен. Запуск процесса доставки груза...');
        cartItems = [];
        cartCount = 0;
        cartBadge.textContent = 0;
        closeCartModal();
    }
};

window.addEventListener('click', (e) => {
    if (e.target === authModal) closeAuthModal();
    if (e.target === cartModal) closeCartModal();
});

searchInput.addEventListener('input', renderProducts);
minPriceInput.addEventListener('input', renderProducts);
maxPriceInput.addEventListener('input', renderProducts);

sortSelect.addEventListener('change', (e) => {
    currentSort = e.target.value;
    renderProducts();
});

categoryItems.forEach(item => {
    item.addEventListener('click', () => {
        categoryItems.forEach(i => i.classList.remove('active'));
        item.classList.add('active');
        currentCategory = item.dataset.category;
        document.getElementById('pageTitle').textContent = currentCategory === 'Все' ? 'Весь сектор' : currentCategory;
        renderProducts();
    });
});

renderProducts();
