-- ============================================
-- Seed data cho P-146
-- Chạy SAU khi alembic upgrade head
-- ============================================

-- 1. Roles (system roles)
INSERT INTO roles (id, code, name, description, is_system, created_at)
VALUES
    ('a1b2c3d4-0001-4000-8000-000000000001', 'vehicle_user',      'Vehicle User',      'Chủ sở hữu xe / người dùng xe',       true, NOW()),
    ('a1b2c3d4-0001-4000-8000-000000000002', 'workshop_owner',    'Workshop Owner',     'Chủ xưởng / đại lý dịch vụ',          true, NOW()),
    ('a1b2c3d4-0001-4000-8000-000000000003', 'maintenance_staff', 'Maintenance Staff',  'Nhân viên kỹ thuật bảo dưỡng',        true, NOW())
ON CONFLICT (id) DO NOTHING;

-- 2. Vehicle Users (demo accounts)
INSERT INTO vehicle_user (user_id, firebase_uid, email, phone, status, created_at, updated_at)
VALUES
    (1, 'firebase_demo_001', 'nguyen.vana@example.com',  '0901000001', 'active', NOW(), NOW()),
    (2, 'firebase_demo_002', 'tran.thib@example.com',    '0901000002', 'active', NOW(), NOW()),
    (3, 'firebase_demo_003', 'le.vanc@example.com',      '0901000003', 'active', NOW(), NOW()),
    (4, 'firebase_demo_004', 'pham.thid@example.com',    '0901000004', 'active', NOW(), NOW()),
    (5, 'firebase_demo_005', 'hoang.vane@example.com',   '0901000005', 'inactive', NOW(), NOW())
ON CONFLICT (user_id) DO NOTHING;
