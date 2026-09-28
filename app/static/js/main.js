// app/static/js/main.js - VIBE FASHION 클라이언트 인터랙션 스크립트

// 장바구니 수량 상태 변수
let cartItemCount = 0;

/**
 * 장바구니 담기 기능
 * @param {string} productName - 상품 이름
 */
function addToCart(productName) {
    cartItemCount += 1;
    
    // 네비게이션 바의 장바구니 뱃지 숫자 업데이트
    const cartCountBadge = document.getElementById("cartCount");
    if (cartCountBadge) {
        cartCountBadge.textContent = cartItemCount;
        // 깜빡이는 애니메이션 효과
        cartCountBadge.classList.add("bg-warning", "text-dark");
        setTimeout(() => {
            cartCountBadge.classList.remove("bg-warning", "text-dark");
            cartCountBadge.classList.add("bg-danger");
        }, 300);
    }

    // Bootstrap 토스트 알림 표시
    const toastMessage = document.getElementById("toastMessage");
    const toastElement = document.getElementById("cartToast");
    
    if (toastMessage && toastElement) {
        toastMessage.textContent = `"${productName}" 상품이 장바구니에 추가되었습니다!`;
        const toast = new bootstrap.Toast(toastElement, { delay: 2500 });
        toast.show();
    }
}

/**
 * 위시리스트 하트 토글 기능
 * @param {HTMLButtonElement} button - 클릭된 위시리스트 버튼
 */
function toggleWishlist(button) {
    const icon = button.querySelector("i");
    if (icon) {
        if (icon.classList.contains("bi-heart")) {
            icon.classList.remove("bi-heart");
            icon.classList.add("bi-heart-fill");
        } else {
            icon.classList.remove("bi-heart-fill");
            icon.classList.add("bi-heart");
        }
    }
}
