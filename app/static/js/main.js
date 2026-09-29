// app/static/js/main.js - VIBE FASHION 클라이언트 인터랙션 스크립트

// 전역 상태 변수
let cartCount = 0;
let wishlistCount = 0;
const wishlistedItems = new Set();
let activeFilter = 'all';
let currentSort = 'newest';
let originalProductNodes = [];

/**
 * 1. 장바구니 담기 기능 (백엔드 세션 API 연동 + 토스트 팝업)
 */
function addToCart(productName, price, imgUrl, option = "FREE / 기본") {
    fetch('/order/cart/add', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            name: productName,
            price: price,
            image_url: imgUrl,
            option: option,
            quantity: 1
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            // 헤더 카운트 뱃지 갱신
            const cartCountBadge = document.getElementById("cartCount");
            if (cartCountBadge) {
                cartCountBadge.textContent = data.cartCount;
                cartCountBadge.classList.add("scale-pop");
                setTimeout(() => cartCountBadge.classList.remove("scale-pop"), 300);
            }

            // 토스트 팝업 노출
            const toastTitle = document.getElementById("toastTitle");
            const toastMessage = document.getElementById("toastMessage");
            const toastElement = document.getElementById("cartToast");
            
            if (toastElement) {
                if (toastTitle) toastTitle.textContent = "장바구니에 담겼습니다";
                if (toastMessage) toastMessage.innerHTML = `${productName} (${price || ''})가 추가되었습니다.<br><a href="/order/cart" class="text-white text-decoration-underline fw-bold mt-1 d-inline-block">장바구니 바로가기 &gt;</a>`;
                const toast = new bootstrap.Toast(toastElement, { delay: 3500 });
                toast.show();
            }
        }
    })
    .catch(err => {
        console.error("Cart Add Error:", err);
    });
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
 * 3. 카테고리 탭 필터링 기능 (전체, 상의, 하의, 아우터, 액세서리)
 */
function filterCategory(categorySlug, targetBtn) {
    activeFilter = categorySlug || 'all';

    // 탭 버튼 active 클래스 제어
    const allTabs = document.querySelectorAll(".ms-filter-pill, .btn-filter-tab");
    allTabs.forEach(tab => tab.classList.remove("active"));
    if (targetBtn) {
        targetBtn.classList.add("active");
    } else {
        // 일치하는 버튼 활성화
        const matchBtn = Array.from(allTabs).find(
            b => b.getAttribute("onclick")?.includes(`'${categorySlug}'`)
        );
        if (matchBtn) matchBtn.classList.add("active");
    }

    applyFiltersAndSort();
}

/**
 * 인기 검색어 클릭 시 퀵 필터
 */
function quickFilter(categorySlug) {
    const targetTab = Array.from(document.querySelectorAll(".ms-filter-pill")).find(
        btn => btn.getAttribute("onclick")?.includes(`'${categorySlug}'`)
    );
    filterCategory(categorySlug, targetTab);
    const rankingEl = document.getElementById("ranking");
    if (rankingEl) {
        rankingEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }
}

/**
 * 4. 실시간 검색 핸들러 (상품명 및 태그 기반)
 */
function handleSearch(query) {
    const clearBtn = document.getElementById("searchClearBtn");
    const val = (query || "").trim();

    // 지우기 버튼 노출/숨김
    if (clearBtn) {
        if (val.length > 0) {
            clearBtn.classList.remove("d-none");
        } else {
            clearBtn.classList.add("d-none");
        }
    }

    // 헤더 검색창과 상품목록 검색창 동기화
    const catalogInput = document.getElementById("productSearchInput");
    const headerInput = document.getElementById("searchInput");
    if (catalogInput && catalogInput.value !== query) catalogInput.value = query;
    if (headerInput && headerInput.value !== query) headerInput.value = query;

    applyFiltersAndSort();
}

/**
 * 검색창 클리어 버튼 동작
 */
function clearSearchInput() {
    const catalogInput = document.getElementById("productSearchInput");
    const headerInput = document.getElementById("searchInput");
    const clearBtn = document.getElementById("searchClearBtn");

    if (catalogInput) catalogInput.value = "";
    if (headerInput) headerInput.value = "";
    if (clearBtn) clearBtn.classList.add("d-none");

    applyFiltersAndSort();
}

/**
 * 5. 정렬 옵션 변경 핸들러 (신상품순, 가격 낮은순, 가격 높은순)
 */
function handleSort(sortOption) {
    currentSort = sortOption || 'newest';
    applyFiltersAndSort();
}

/**
 * 6. 통합 필터링 및 정렬 실행 (카테고리 + 실시간 검색 + 정렬)
 */
function applyFiltersAndSort() {
    const gridEl = document.getElementById("productGrid");
    if (!gridEl) return;

    // 초기 노드 순서 캐싱
    if (originalProductNodes.length === 0) {
        originalProductNodes = Array.from(gridEl.querySelectorAll(".product-item-col"));
    }

    const currentSearch = (
        document.getElementById("productSearchInput")?.value ||
        document.getElementById("searchInput")?.value ||
        ""
    ).trim().toLowerCase();

    // 1단계: 카테고리 및 검색어(상품명, 태그, 브랜드) 필터링
    const visibleItems = [];

    originalProductNodes.forEach((col, idx) => {
        const cat = (col.getAttribute("data-category") || "").toLowerCase();
        const name = (col.getAttribute("data-name") || col.querySelector(".ms-goods-title")?.textContent || "").toLowerCase();
        const tag = (col.getAttribute("data-tag") || col.querySelector(".ms-tag-badge")?.textContent || "").toLowerCase();
        const brand = (col.getAttribute("data-brand") || col.querySelector(".ms-brand-name")?.textContent || "").toLowerCase();

        // 카테고리 매칭
        let matchesCategory = (activeFilter === "all");
        if (!matchesCategory) {
            matchesCategory = (cat === activeFilter);
            // 'bottom' 선택 시 'pants' 등 유사 슬러그 호환
            if (!matchesCategory && activeFilter === 'bottom' && (cat.includes('bottom') || cat.includes('pants'))) {
                matchesCategory = true;
            }
        }

        // 검색어 매칭 (상품명, 태그, 브랜드명 포함)
        const matchesSearch = !currentSearch ||
            name.includes(currentSearch) ||
            tag.includes(currentSearch) ||
            brand.includes(currentSearch);

        if (matchesCategory && matchesSearch) {
            col.classList.remove("d-none");
            visibleItems.push({
                element: col,
                originalIndex: idx,
                price: parseFloat(col.getAttribute("data-price") || 0),
                date: col.getAttribute("data-date") || "",
                name: name
            });
        } else {
            col.classList.add("d-none");
        }
    });

    // 2단계: 정렬 적용 (신상품순, 가격 낮은순, 가격 높은순)
    visibleItems.sort((a, b) => {
        if (currentSort === "price-asc") {
            return a.price - b.price;
        } else if (currentSort === "price-desc") {
            return b.price - a.price;
        } else {
            // "newest" 신상품순 (날짜 내림차순, 동일할 경우 원래 순서 유지)
            if (a.date && b.date) {
                const diff = new Date(b.date) - new Date(a.date);
                if (diff !== 0) return diff;
            }
            return a.originalIndex - b.originalIndex;
        }
    });

    // 3단계: 정렬된 순서대로 DOM 재배치 & 랭킹 뱃지 순위 업데이트
    visibleItems.forEach((item, index) => {
        gridEl.appendChild(item.element);

        // 랭킹 뱃지 업데이트
        const rankBadge = item.element.querySelector(".ms-rank-badge");
        if (rankBadge) {
            rankBadge.textContent = index + 1;
            if (index < 3) {
                rankBadge.classList.add("top-rank");
            } else {
                rankBadge.classList.remove("top-rank");
            }
        }
    });

    // 4단계: 개수 표시 업데이트
    const countEl = document.getElementById("productCount");
    if (countEl) {
        countEl.textContent = visibleItems.length;
    }

    // 5단계: 결과 없음 상태 뷰 처리
    const noResultsEl = document.getElementById("noResultsState");
    if (noResultsEl) {
        if (visibleItems.length === 0) {
            noResultsEl.classList.remove("d-none");
        } else {
            noResultsEl.classList.add("d-none");
        }
    }
}

/**
 * 7. 전체 목록 보기 / 전체 필터 리셋
 */
function resetAllFilters() {
    activeFilter = 'all';
    currentSort = 'newest';

    // 1. 검색창 초기화
    const catalogInput = document.getElementById("productSearchInput");
    const headerInput = document.getElementById("searchInput");
    const clearBtn = document.getElementById("searchClearBtn");
    if (catalogInput) catalogInput.value = "";
    if (headerInput) headerInput.value = "";
    if (clearBtn) clearBtn.classList.add("d-none");

    // 2. 카테고리 탭 초기화 ('전체' 활성화)
    const allTabs = document.querySelectorAll(".ms-filter-pill, .btn-filter-tab");
    allTabs.forEach(tab => tab.classList.remove("active"));
    const firstTab = document.querySelector(".ms-filter-pill");
    if (firstTab) firstTab.classList.add("active");

    // 3. 정렬 옵션 초기화
    const sortSelect = document.getElementById("productSortSelect");
    if (sortSelect) sortSelect.value = "newest";

    // 4. 필터 및 정렬 재적용
    applyFiltersAndSort();
}

// 레거시 호환
function resetFilters() {
    resetAllFilters();
}

// 8. 초기화 및 스무스 스크롤 네비게이션
document.addEventListener("DOMContentLoaded", () => {
    // 상품 노드 원본 캐싱
    const gridEl = document.getElementById("productGrid");
    if (gridEl) {
        originalProductNodes = Array.from(gridEl.querySelectorAll(".product-item-col"));
    }

    // 스무스 스크롤
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
