-- ============================================================
-- VIBE-FASHION 쇼핑몰 DB 스키마 (최종)
-- Supabase SQL Editor용
-- ============================================================

-- 1. 확장 기능 활성화
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. 테이블 생성

-- profiles (사용자 프로필, auth.users와 1:1 연동)
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    name TEXT,
    avatar_url TEXT,
    phone TEXT,
    address TEXT,
    role TEXT NOT NULL DEFAULT 'customer' CHECK (role IN ('customer', 'admin')),
    grade TEXT NOT NULL DEFAULT 'BRONZE' CHECK (grade IN ('BRONZE', 'SILVER', 'GOLD', 'VIP')),
    total_spent NUMERIC(12, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- categories (상품 카테고리 계층 구조 지원)
CREATE TABLE IF NOT EXISTS public.categories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    parent_id UUID REFERENCES public.categories(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- products (상품 기본 정보)
CREATE TABLE IF NOT EXISTS public.products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    category_id UUID REFERENCES public.categories(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT,
    price NUMERIC(12, 2) NOT NULL,
    sale_price NUMERIC(12, 2),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'hidden', 'out_of_stock')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- product_options (색상, 사이즈 및 옵션별 재고)
CREATE TABLE IF NOT EXISTS public.product_options (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    color TEXT,
    size TEXT,
    stock_quantity INT NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    additional_price NUMERIC(12, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- product_images (상품 이미지)
CREATE TABLE IF NOT EXISTS public.product_images (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    image_url TEXT NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- carts (장바구니)
CREATE TABLE IF NOT EXISTS public.carts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    product_option_id UUID NOT NULL REFERENCES public.product_options(id) ON DELETE CASCADE,
    quantity INT NOT NULL DEFAULT 1 CHECK (quantity > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    CONSTRAINT uq_cart_user_option UNIQUE (user_id, product_option_id)
);

-- orders (주문 헤더)
CREATE TABLE IF NOT EXISTS public.orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    order_number TEXT NOT NULL UNIQUE,
    total_amount NUMERIC(12, 2) NOT NULL,
    discount_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    final_amount NUMERIC(12, 2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'preparing', 'shipping', 'delivered', 'cancelled')),
    recipient_name TEXT NOT NULL,
    recipient_phone TEXT NOT NULL,
    shipping_address TEXT NOT NULL,
    memo TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- order_items (주문 항목 상세)
CREATE TABLE IF NOT EXISTS public.order_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
    product_id UUID REFERENCES public.products(id) ON DELETE SET NULL,
    product_option_id UUID REFERENCES public.product_options(id) ON DELETE SET NULL,
    product_name TEXT NOT NULL,
    option_description TEXT,
    unit_price NUMERIC(12, 2) NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    total_price NUMERIC(12, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- refunds (환불 및 반품 요청)
CREATE TABLE IF NOT EXISTS public.refunds (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
    order_item_id UUID REFERENCES public.order_items(id) ON DELETE SET NULL,
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    refund_amount NUMERIC(12, 2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'requested' CHECK (status IN ('requested', 'approved', 'rejected', 'completed')),
    admin_note TEXT,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- notifications (사용자 알림)
CREATE TABLE IF NOT EXISTS public.notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    link_url TEXT,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- reviews (구매 후기)
CREATE TABLE IF NOT EXISTS public.reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    order_item_id UUID UNIQUE REFERENCES public.order_items(id) ON DELETE SET NULL,
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    rating INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    content TEXT NOT NULL,
    images TEXT[] DEFAULT ARRAY[]::TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- inquiries (1:1 상품문의 및 배송문의 게시판)
CREATE TABLE IF NOT EXISTS public.inquiries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    product_id UUID REFERENCES public.products(id) ON DELETE SET NULL,
    type TEXT NOT NULL CHECK (type IN ('product', 'shipping', 'other')),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    author_name TEXT NOT NULL,
    author_email TEXT,
    is_secret BOOLEAN NOT NULL DEFAULT FALSE,
    password TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'answered')),
    answer TEXT,
    answered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 3. 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_products_category ON public.products(category_id);
CREATE INDEX IF NOT EXISTS idx_product_options_product ON public.product_options(product_id);
CREATE INDEX IF NOT EXISTS idx_product_images_product ON public.product_images(product_id);
CREATE INDEX IF NOT EXISTS idx_carts_user ON public.carts(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_user ON public.orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON public.orders(status);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON public.order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_reviews_product ON public.reviews(product_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON public.notifications(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_inquiries_type ON public.inquiries(type);
CREATE INDEX IF NOT EXISTS idx_inquiries_product ON public.inquiries(product_id);
CREATE INDEX IF NOT EXISTS idx_inquiries_status ON public.inquiries(status);

-- 4. 신규 유저 생성(소셜/이메일) 시 자동 프로필 등록 함수 및 트리거
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO public.profiles (id, email, name, avatar_url)
    VALUES (
        NEW.id,
        COALESCE(NEW.email, ''),
        COALESCE(
            NEW.raw_user_meta_data->>'full_name',
            NEW.raw_user_meta_data->>'name',
            split_part(NEW.email, '@', 1)
        ),
        COALESCE(NEW.raw_user_meta_data->>'avatar_url', NEW.raw_user_meta_data->>'picture')
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();

-- 5. 주문 결제 완료 시 누적 구매금액 및 회원 등급 자동 갱신 함수 및 트리거
CREATE OR REPLACE FUNCTION public.update_customer_grade()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_user_id UUID;
    v_total_spent NUMERIC(12, 2);
    v_new_grade TEXT;
BEGIN
    v_user_id := NEW.user_id;

    -- 실결제 상태 주문들의 누적 금액 집계
    SELECT COALESCE(SUM(final_amount), 0)
    INTO v_total_spent
    FROM public.orders
    WHERE user_id = v_user_id
      AND status IN ('paid', 'preparing', 'shipping', 'delivered');

    -- 등급 기준: 100만↑ VIP / 50만↑ GOLD / 20만↑ SILVER / 그 외 BRONZE
    IF v_total_spent >= 1000000 THEN
        v_new_grade := 'VIP';
    ELSIF v_total_spent >= 500000 THEN
        v_new_grade := 'GOLD';
    ELSIF v_total_spent >= 200000 THEN
        v_new_grade := 'SILVER';
    ELSE
        v_new_grade := 'BRONZE';
    END IF;

    -- 프로필 테이블 갱신
    UPDATE public.profiles
    SET total_spent = v_total_spent,
        grade = v_new_grade,
        updated_at = timezone('utc'::text, now())
    WHERE id = v_user_id;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_update_customer_grade ON public.orders;
CREATE TRIGGER trg_update_customer_grade
    AFTER INSERT OR UPDATE OF status, final_amount ON public.orders
    FOR EACH ROW
    EXECUTE FUNCTION public.update_customer_grade();

-- 6. Row Level Security (RLS) 활성화
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_options ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_images ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.carts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.refunds ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reviews ENABLE ROW LEVEL SECURITY;

-- 7. RLS 보안 정책 설정 (중복 방지 DROP IF EXISTS 적용)

-- 공개 조회 가능 테이블
DROP POLICY IF EXISTS "Public categories are readable by everyone" ON public.categories;
CREATE POLICY "Public categories are readable by everyone" ON public.categories FOR SELECT USING (true);

DROP POLICY IF EXISTS "Active products are readable by everyone" ON public.products;
CREATE POLICY "Active products are readable by everyone" ON public.products FOR SELECT USING (status = 'active');

DROP POLICY IF EXISTS "Product options are readable by everyone" ON public.product_options;
CREATE POLICY "Product options are readable by everyone" ON public.product_options FOR SELECT USING (true);

DROP POLICY IF EXISTS "Product images are readable by everyone" ON public.product_images;
CREATE POLICY "Product images are readable by everyone" ON public.product_images FOR SELECT USING (true);

DROP POLICY IF EXISTS "Reviews are readable by everyone" ON public.reviews;
CREATE POLICY "Reviews are readable by everyone" ON public.reviews FOR SELECT USING (true);

-- 유저 개인 데이터 접근 정책
DROP POLICY IF EXISTS "Users can read own profile" ON public.profiles;
CREATE POLICY "Users can read own profile" ON public.profiles FOR SELECT USING (auth.uid() = id);

DROP POLICY IF EXISTS "Users can update own profile" ON public.profiles;
CREATE POLICY "Users can update own profile" ON public.profiles FOR UPDATE USING (auth.uid() = id);

DROP POLICY IF EXISTS "Users manage own cart" ON public.carts;
CREATE POLICY "Users manage own cart" ON public.carts FOR ALL USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users view own orders" ON public.orders;
CREATE POLICY "Users view own orders" ON public.orders FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users insert own orders" ON public.orders;
CREATE POLICY "Users insert own orders" ON public.orders FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users view own order items" ON public.order_items;
CREATE POLICY "Users view own order items" ON public.order_items FOR SELECT USING (
    EXISTS (SELECT 1 FROM public.orders WHERE orders.id = order_items.order_id AND orders.user_id = auth.uid())
);

DROP POLICY IF EXISTS "Users manage own reviews" ON public.reviews;
CREATE POLICY "Users manage own reviews" ON public.reviews FOR ALL USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users view own notifications" ON public.notifications;
CREATE POLICY "Users view own notifications" ON public.notifications FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users update own notifications" ON public.notifications;
CREATE POLICY "Users update own notifications" ON public.notifications FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users manage own refunds" ON public.refunds;
CREATE POLICY "Users manage own refunds" ON public.refunds FOR ALL USING (auth.uid() = user_id);
