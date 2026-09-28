-- ============================================================
-- VIBE-FASHION 초기 시드 데이터 (Seed SQL)
-- Supabase SQL Editor용
-- ============================================================

-- 1. 카테고리 등록 (7개)
INSERT INTO public.categories (name, slug, sort_order)
VALUES 
    ('상의', 'top', 1),
    ('하의', 'bottom', 2),
    ('아우터', 'outer', 3),
    ('원피스/세트', 'dress', 4),
    ('액세서리', 'acc', 5),
    ('가방', 'bag', 6),
    ('신발', 'shoes', 7)
ON CONFLICT (slug) DO UPDATE
SET name = EXCLUDED.name,
    sort_order = EXCLUDED.sort_order;

-- 2. 샘플 상품 등록 (4개)
-- 상품 1: 베이직 크롭 티셔츠 (상의, 정상가 29,900원 / 할인가 19,900원)
INSERT INTO public.products (category_id, name, slug, description, price, sale_price, status)
SELECT 
    id,
    '베이직 크롭 티셔츠',
    'basic-crop-tshirt',
    '트렌디한 실루엣과 편안한 착용감을 선사하는 데일리 베이직 크롭 티셔츠입니다.',
    29900,
    19900,
    'active'
FROM public.categories WHERE slug = 'top'
ON CONFLICT (slug) DO UPDATE 
SET price = EXCLUDED.price,
    sale_price = EXCLUDED.sale_price,
    description = EXCLUDED.description;

-- 상품 2: 와이드 데님 팬츠 (하의, 39,900원)
INSERT INTO public.products (category_id, name, slug, description, price, sale_price, status)
SELECT 
    id,
    '와이드 데님 팬츠',
    'wide-denim-pants',
    '자연스러운 워싱감과 여유로운 와이드 핏으로 체형을 커버해 주는 데님 팬츠입니다.',
    39900,
    NULL,
    'active'
FROM public.categories WHERE slug = 'bottom'
ON CONFLICT (slug) DO UPDATE 
SET price = EXCLUDED.price,
    sale_price = EXCLUDED.sale_price,
    description = EXCLUDED.description;

-- 상품 3: 오버핏 코튼 자켓 (아우터, 59,900원)
INSERT INTO public.products (category_id, name, slug, description, price, sale_price, status)
SELECT 
    id,
    '오버핏 코튼 자켓',
    'overfit-cotton-jacket',
    '탄탄한 고밀도 코튼 소재로 제작되어 간절기 시즌 단정하고 멋스럽게 연출하기 좋습니다.',
    59900,
    NULL,
    'active'
FROM public.categories WHERE slug = 'outer'
ON CONFLICT (slug) DO UPDATE 
SET price = EXCLUDED.price,
    sale_price = EXCLUDED.sale_price,
    description = EXCLUDED.description;

-- 상품 4: 플로럴 미디 원피스 (원피스, 45,900원)
INSERT INTO public.products (category_id, name, slug, description, price, sale_price, status)
SELECT 
    id,
    '플로럴 미디 원피스',
    'floral-midi-dress',
    '은은한 플로럴 패턴과 허리 스트링 디테일로 페미닌한 무드를 완성하는 미디 원피스입니다.',
    45900,
    NULL,
    'active'
FROM public.categories WHERE slug = 'dress'
ON CONFLICT (slug) DO UPDATE 
SET price = EXCLUDED.price,
    sale_price = EXCLUDED.sale_price,
    description = EXCLUDED.description;

-- 상품 5: 컨스트럭션 아우터 (아우터, 20,000원)
INSERT INTO public.products (category_id, name, slug, description, price, sale_price, status)
SELECT 
    id,
    '컨스트럭션 아우터',
    'construction-outer',
    '내구성이 뛰어나고 워크웨어 무드가 돋보이는 모던한 컨스트럭션 자켓입니다.',
    20000,
    NULL,
    'active'
FROM public.categories WHERE slug = 'outer'
ON CONFLICT (slug) DO UPDATE 
SET price = EXCLUDED.price,
    sale_price = EXCLUDED.sale_price,
    description = EXCLUDED.description;

-- 상품 6: 척테일러 올스타 언얼스드 (신발, 69,000원)
INSERT INTO public.products (category_id, name, slug, description, price, sale_price, status)
SELECT 
    id,
    '척테일러 올스타 언얼스드',
    'chuck-taylor-all-star-unearthed',
    '내추럴한 어스톤 무드와 편안한 착화감을 자랑하는 클래식 스니커즈입니다.',
    69000,
    NULL,
    'active'
FROM public.categories WHERE slug = 'shoes'
ON CONFLICT (slug) DO UPDATE 
SET price = EXCLUDED.price,
    sale_price = EXCLUDED.sale_price,
    description = EXCLUDED.description;

-- 3. 첫 번째 상품(베이직 크롭 티셔츠) 옵션 9개 (블랙/화이트/베이지 × S/M/L)
WITH p AS (
    SELECT id FROM public.products WHERE slug = 'basic-crop-tshirt'
),
opts AS (
    SELECT '블랙' AS color, 'S' AS size, 50 AS stock UNION ALL
    SELECT '블랙', 'M', 50 UNION ALL
    SELECT '블랙', 'L', 30 UNION ALL
    SELECT '화이트', 'S', 50 UNION ALL
    SELECT '화이트', 'M', 50 UNION ALL
    SELECT '화이트', 'L', 30 UNION ALL
    SELECT '베이지', 'S', 40 UNION ALL
    SELECT '베이지', 'M', 40 UNION ALL
    SELECT '베이지', 'L', 20
)
INSERT INTO public.product_options (product_id, color, size, stock_quantity, additional_price)
SELECT p.id, opts.color, opts.size, opts.stock, 0
FROM p
CROSS JOIN opts
WHERE NOT EXISTS (
    SELECT 1 FROM public.product_options po 
    WHERE po.product_id = p.id AND po.color = opts.color AND po.size = opts.size
);

-- 4. 썸네일 이미지 등록
-- 상품 1: 베이직 크롭 티셔츠 이미지
INSERT INTO public.product_images (product_id, image_url, is_primary, sort_order)
SELECT p.id, 'https://static-resource.mlb-korea.com/cdn-cgi/image/q=75,w=1668,format=auto,fit=scale-down,onerror=redirect/images/goods/ec/M26S3FTSB126350BKS/thnail/0068DD5346C5436ABA173B6675370BC8.png', true, 1
FROM public.products p
WHERE p.slug = 'basic-crop-tshirt'
  AND NOT EXISTS (SELECT 1 FROM public.product_images pi WHERE pi.product_id = p.id AND pi.image_url = 'https://static-resource.mlb-korea.com/cdn-cgi/image/q=75,w=1668,format=auto,fit=scale-down,onerror=redirect/images/goods/ec/M26S3FTSB126350BKS/thnail/0068DD5346C5436ABA173B6675370BC8.png');

-- 상품 2: 와이드 데님 팬츠 이미지
INSERT INTO public.product_images (product_id, image_url, is_primary, sort_order)
SELECT p.id, 'https://img.ssfshop.com/cmd/LB_750x1000/src/https://img.ssfshop.com/goods/8SBR/24/08/19/GM0024081982620_0_THNAIL_ORGINL_20240822164421561.jpg', true, 1
FROM public.products p
WHERE p.slug = 'wide-denim-pants'
  AND NOT EXISTS (SELECT 1 FROM public.product_images pi WHERE pi.product_id = p.id AND pi.image_url = 'https://img.ssfshop.com/cmd/LB_750x1000/src/https://img.ssfshop.com/goods/8SBR/24/08/19/GM0024081982620_0_THNAIL_ORGINL_20240822164421561.jpg');

-- 상품 3: 오버핏 코튼 자켓 이미지
INSERT INTO public.product_images (product_id, image_url, is_primary, sort_order)
SELECT p.id, 'https://covernat.co.kr/web/product/extra/big/20251015/766dc5d2a11b0417d5c9e746f56facc3.jpg', true, 1
FROM public.products p
WHERE p.slug = 'overfit-cotton-jacket'
  AND NOT EXISTS (SELECT 1 FROM public.product_images pi WHERE pi.product_id = p.id AND pi.image_url = 'https://covernat.co.kr/web/product/extra/big/20251015/766dc5d2a11b0417d5c9e746f56facc3.jpg');

-- 상품 4: 플로럴 미디 원피스 이미지
INSERT INTO public.product_images (product_id, image_url, is_primary, sort_order)
SELECT p.id, 'https://thumb.cjonstyle.net/unsafe/fit-in/470x470/itemimage.cjonstyle.net/goods_images/20/442/2064699442L.jpg?timestamp=20260803191600', true, 1
FROM public.products p
WHERE p.slug = 'floral-midi-dress'
  AND NOT EXISTS (SELECT 1 FROM public.product_images pi WHERE pi.product_id = p.id AND pi.image_url = 'https://thumb.cjonstyle.net/unsafe/fit-in/470x470/itemimage.cjonstyle.net/goods_images/20/442/2064699442L.jpg?timestamp=20260803191600');

-- 상품 5: 컨스트럭션 아우터 이미지
INSERT INTO public.product_images (product_id, image_url, is_primary, sort_order)
SELECT p.id, 'https://image.production.fruitsfamily.com/public/product/resized%40width1125/fC5TOfKvU9-72ECE7E0-C812-4D2C-9F09-36CF3F277B81.jpg', true, 1
FROM public.products p
WHERE p.slug = 'construction-outer'
  AND NOT EXISTS (SELECT 1 FROM public.product_images pi WHERE pi.product_id = p.id AND pi.image_url = 'https://image.production.fruitsfamily.com/public/product/resized%40width1125/fC5TOfKvU9-72ECE7E0-C812-4D2C-9F09-36CF3F277B81.jpg');

-- 상품 6: 척테일러 올스타 언얼스드 이미지
INSERT INTO public.product_images (product_id, image_url, is_primary, sort_order)
SELECT p.id, 'https://image.msscdn.net/thumbnails/images/goods_img/20260831/7205930/7205930_17881638240251_big.jpg?w=1200', true, 1
FROM public.products p
WHERE p.slug = 'chuck-taylor-all-star-unearthed'
  AND NOT EXISTS (SELECT 1 FROM public.product_images pi WHERE pi.product_id = p.id AND pi.image_url = 'https://image.msscdn.net/thumbnails/images/goods_img/20260831/7205930/7205930_17881638240251_big.jpg?w=1200');

-- 5. 신규 상품 옵션 및 재고 등록
-- 컨스트럭션 아우터 옵션 (검정 × M/L/XL)
WITH p AS (
    SELECT id FROM public.products WHERE slug = 'construction-outer'
),
opts AS (
    SELECT '검정' AS color, 'M' AS size, 30 AS stock UNION ALL
    SELECT '검정' AS color, 'L' AS size, 40 AS stock UNION ALL
    SELECT '검정' AS color, 'XL' AS size, 20 AS stock
)
INSERT INTO public.product_options (product_id, color, size, stock_quantity, additional_price)
SELECT p.id, opts.color, opts.size, opts.stock, 0
FROM p
CROSS JOIN opts
WHERE NOT EXISTS (
    SELECT 1 FROM public.product_options po 
    WHERE po.product_id = p.id AND po.color = opts.color AND po.size = opts.size
);

-- 척테일러 올스타 언얼스드 옵션 (갈색 × 250/260/270/280)
WITH p AS (
    SELECT id FROM public.products WHERE slug = 'chuck-taylor-all-star-unearthed'
),
opts AS (
    SELECT '갈색' AS color, '250' AS size, 20 AS stock UNION ALL
    SELECT '갈색' AS color, '260' AS size, 30 AS stock UNION ALL
    SELECT '갈색' AS color, '270' AS size, 30 AS stock UNION ALL
    SELECT '갈색' AS color, '280' AS size, 15 AS stock
)
INSERT INTO public.product_options (product_id, color, size, stock_quantity, additional_price)
SELECT p.id, opts.color, opts.size, opts.stock, 0
FROM p
CROSS JOIN opts
WHERE NOT EXISTS (
    SELECT 1 FROM public.product_options po 
    WHERE po.product_id = p.id AND po.color = opts.color AND po.size = opts.size
);
