// app/static/js/main.js - VIBE FASHION 클라이언트 인터랙션 스크립트

// 전역 상태 변수
let cartCount = 0;
let wishlistCount = 0;
const wishlistedItems = new Set();
let activeFilter = 'all';

/**
 * 1. 장바구니 담기 기능 (토스트 알림 + 뱃지 카운트 애니메이션)
 */
function addToCart(productName, price, imgUrl) {
    cartCount += 1;
    
    // 네비게이션 헤더 장바구니 뱃지 업데이트
    const cartCountBadge = document.getElementById("cartCount");
    if (cartCountBadge) {
        cartCountBadge.textContent = cartCount;
        cartCountBadge.classList.add("scale-pop");
        setTimeout(() => cartCountBadge.classList.remove("scale-pop"), 300);
    }

    // Bootstrap 토스트 팝업 표시
    const toastTitle = document.getElementById("toastTitle");
    const toastMessage = document.getElementById("toastMessage");
    const toastElement = document.getElementById("cartToast");
    
    if (toastElement) {
        if (toastTitle) toastTitle.textContent = "쇼핑백에 추가되었습니다";
        if (toastMessage) toastMessage.textContent = `${productName} (${price || ''})가 추가되었습니다.`;
        const toast = new bootstrap.Toast(toastElement, { delay: 3000 });
        toast.show();
    }
}

/**
 * 2. 위시리스트 토글 (좋아요 버튼 애니메이션 및 카운트 반영)
 */
function toggleWishlist(button, productName) {
    const icon = button.querySelector("i");
    if (!icon) return;

    const isLiked = icon.classList.contains("bi-heart-fill");
    const wishlistBadge = document.getElementById("wishlistCount");

    if (isLiked) {
        icon.classList.remove("bi-heart-fill", "text-danger");
        icon.classList.add("bi-heart");
        button.classList.remove("active");
        wishlistCount = Math.max(0, wishlistCount - 1);
        wishlistedItems.delete(productName);
    } else {
        icon.classList.remove("bi-heart");
        icon.classList.add("bi-heart-fill", "text-danger");
        button.classList.add("active");
        wishlistCount += 1;
        wishlistedItems.add(productName);

        // 좋아요 알림 토스트
        const toastTitle = document.getElementById("toastTitle");
        const toastMessage = document.getElementById("toastMessage");
        const toastElement = document.getElementById("cartToast");
        if (toastElement) {
            if (toastTitle) toastTitle.textContent = "관심 상품에 등록되었습니다";
            if (toastMessage) toastMessage.textContent = `"${productName}"를 위시리스트에 담았습니다.`;
            const toast = new bootstrap.Toast(toastElement, { delay: 2000 });
            toast.show();
        }
    }

    if (wishlistBadge) {
        wishlistBadge.textContent = wishlistCount;
    }
}

/**
 * 3. 카테고리 탭 필터링 기능
 */
function filterCategory(categorySlug, targetBtn) {
    activeFilter = categorySlug;

    // 탭 버튼 active 클래스 제어
    const allTabs = document.querySelectorAll(".btn-filter-tab");
    allTabs.forEach(tab => tab.classList.remove("active"));
    if (targetBtn) {
        targetBtn.classList.add("active");
    }

    applyFilters();
}

/**
 * 4. 실시간 검색 필터링 기능
 */
function handleSearch(query) {
    applyFilters(query.trim().toLowerCase());
}

/**
 * 5. 통합 필터링 (카테고리 + 검색어)
 */
function applyFilters(searchQuery = "") {
    const productCols = document.querySelectorAll(".product-item-col");
    let visibleCount = 0;

    const currentSearch = searchQuery || (document.getElementById("searchInput")?.value || "").trim().toLowerCase();

    productCols.forEach(col => {
        const cat = col.getAttribute("data-category") || "";
        const title = (col.querySelector(".product-card-title")?.textContent || "").toLowerCase();
        const desc = (col.querySelector(".product-card-desc")?.textContent || "").toLowerCase();

        const matchesCategory = (activeFilter === "all") || (cat === activeFilter);
        const matchesSearch = !currentSearch || title.includes(currentSearch) || desc.includes(currentSearch);

        if (matchesCategory && matchesSearch) {
            col.classList.remove("d-none");
            visibleCount++;
        } else {
            col.classList.add("d-none");
        }
    });

    // 개수 표시 업데이트
    const countEl = document.getElementById("productCount");
    if (countEl) {
        countEl.textContent = visibleCount;
    }

    // 결과 없음 상태 뷰
    const noResultsEl = document.getElementById("noResultsState");
    const gridEl = document.getElementById("productGrid");
    if (noResultsEl && gridEl) {
        if (visibleCount === 0) {
            noResultsEl.classList.remove("d-none");
        } else {
            noResultsEl.classList.add("d-none");
        }
    }
}

/**
 * 필터 리셋
 */
function resetFilters() {
    const searchInput = document.getElementById("searchInput");
    if (searchInput) searchInput.value = "";
    const firstTab = document.querySelector(".btn-filter-tab");
    filterCategory('all', firstTab);
}

// 6. 스무스 스크롤 네비게이션
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            const targetId = this.getAttribute('href');
            if (targetId && targetId !== '#') {
                const targetEl = document.querySelector(targetId);
                if (targetEl) {
                    e.preventDefault();
                    targetEl.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            }
        });
    });
});
