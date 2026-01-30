// static/js/virtual_keyboard.js

const Keyboard = window.SimpleKeyboard.default;
let keyboard;
let currentInput;

/**
 * Khởi tạo bàn phím ảo và gắn vào các ô input được chỉ định.
 * @param {string} inputSelectors - Một CSS selector cho tất cả các ô input cần bàn phím, vd: '[data-vkb]'.
 */
function initVirtualKeyboard(inputSelectors) {
    const inputs = document.querySelectorAll(inputSelectors);
    
    // Chỉ khởi tạo một lần duy nhất để tránh lãng phí tài nguyên
    if (!keyboard) {
        keyboard = new Keyboard({
            onChange: input => onKeyboardChange(input),
            onKeyPress: button => onKeyboardKeyPress(button),
            theme: "hg-theme-default",
            // Layout đầy đủ cho các trường văn bản
            layout: {
                'default': [
                    "` 1 2 3 4 5 6 7 8 9 0 - = {bksp}",
                    "{tab} q w e r t y u i o p [ ] \\",
                    "{lock} a s d f g h j k l ; ' {enter}",
                    "{shift} z x c v b n m , . / {shift}",
                    "@ {space}"
                ],
                'shift': [
                    "~ ! @ # $ % ^ & * ( ) _ + {bksp}",
                    "{tab} Q W E R T Y U I O P { } |",
                    "{lock} A S D F G H J K L : \" {enter}",
                    "{shift} Z X C V B N M < > ? {shift}",
                    "@ {space}"
                ],
                // Layout số cho các trường loại 'number'
                'numeric': [
                    "1 2 3",
                    "4 5 6",
                    "7 8 9",
                    ". 0 {bksp}",
                    "{enter}"
                ]
            },
            display: {
                '{enter}': 'Enter',
                '{bksp}': '⌫',
                '{shift}': 'Shift',
                '{lock}': 'Caps',
                '{tab}': 'Tab',
                '{space}': ' '
            }
        });

        // Ẩn bàn phím ngay sau khi khởi tạo
        document.querySelector('.simple-keyboard').style.display = 'none';
    }

    // Gán sự kiện 'focus' cho mỗi ô input được chọn
    inputs.forEach(input => {
        // Thêm thuộc tính 'data-vkb' để dễ dàng nhận diện trong các sự kiện khác
        input.setAttribute('data-vkb', 'true');
        input.addEventListener('focus', (event) => onInputFocus(event.target));
    });
}

/**
 * Xử lý khi một ô input được focus.
 * @param {HTMLElement} inputElement - Ô input vừa được focus.
 */
function onInputFocus(inputElement) {
    currentInput = inputElement;
    
    // Tự động chọn layout phù hợp: 'numeric' cho số, 'default' cho các loại khác
    const layoutName = inputElement.type === 'number' ? 'numeric' : 'default';
    
    // Định danh input cho keyboard (dùng ID nếu có, nếu không thì dùng 'default')
    const inputName = inputElement.id || 'default';

    keyboard.setOptions({
        inputName: inputName,
        layoutName: layoutName
    });
    
    // --- KHẮC PHỤC LỖI BUFFER CŨ & AUTOFILL ---
    // 1. Xóa sạch bộ nhớ đệm nội bộ của bàn phím cho input này để tránh ký tự rác
    keyboard.clearInput(inputName);

    // 2. Nếu trình duyệt đã autofill (hoặc input có giá trị), đồng bộ giá trị đó vào bàn phím
    if (inputElement.value) {
        keyboard.setInput(inputElement.value, inputName);
    } else {
        // Nếu input rỗng, đảm bảo visual của bàn phím cũng rỗng
        keyboard.setInput("", inputName);
    }
    
    // Hiển thị bàn phím
    document.querySelector('.simple-keyboard').style.display = 'block';
}

/**
 * Cập nhật giá trị của ô input mỗi khi có thay đổi trên bàn phím.
 * @param {string} input - Giá trị mới từ bàn phím.
 */
function onKeyboardChange(input) {
    if (currentInput) {
        currentInput.value = input;
    }
}

/**
 * Xử lý khi một phím được nhấn.
 * @param {string} button - Phím được nhấn (vd: '{enter}', '{shift}', 'a', 'b'...).
 */
function onKeyboardKeyPress(button) {
    if (button === "{shift}" || button === "{lock}") {
        handleShift();
    }
    
    // Khi nhấn Enter, giả lập sự kiện 'change' để trigger logic đã có (như quét mã vạch)
    if (button === "{enter}" && currentInput) {
        currentInput.dispatchEvent(new Event('change', { bubbles: true }));
        hideKeyboard();
    }
}

/**
 * Chuyển đổi giữa layout chữ thường và chữ hoa.
 */
function handleShift() {
    let currentLayout = keyboard.options.layoutName;
    let shiftToggle = currentLayout === "default" ? "shift" : "default";
    keyboard.setOptions({ layoutName: shiftToggle });
}

/**
 * Hàm ẩn bàn phím và reset input hiện tại.
 */
function hideKeyboard() {
    const keyboardEl = document.querySelector('.simple-keyboard');
    if (keyboardEl) {
        keyboardEl.style.display = 'none';
    }
    currentInput = null;
}

// Lắng nghe sự kiện click trên toàn bộ tài liệu để ẩn bàn phím khi người dùng click ra ngoài.
document.addEventListener('click', function(event) {
    const keyboardEl = document.querySelector('.simple-keyboard');
    
    // Nếu bàn phím đang hiển thị VÀ nơi được click không phải là bàn phím VÀ không phải là ô input được quản lý
    if (keyboardEl && keyboardEl.style.display !== 'none' && !keyboardEl.contains(event.target) && !event.target.hasAttribute('data-vkb')) {
        hideKeyboard();
    }
}, true); // Sử dụng 'capturing' để bắt sự kiện sớm hơn