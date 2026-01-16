-- CPET 피험자 사용자 및 subject 데이터 생성 스크립트
-- 생성일: 2026-01-16 11:27:36
-- 기본 패스워드: Cpet2024!Strong#Pass

BEGIN;

-- 기존 테스트 데이터 정리 (선택적)
-- DELETE FROM users WHERE email LIKE '%@cpet.com' AND email != 'gerald.park@cpet.com';


-- Junghooon Park (1 files)
INSERT INTO subjects (research_id, encrypted_name, gender, notes, created_at, updated_at)
VALUES (
    'SUB-PAR-JUN',
    'Junghooon Park',
    NULL,
    'CPET 테스트 피험자 (1개 파일)',
    NOW(),
    NOW()
)
ON CONFLICT (research_id) DO UPDATE SET updated_at = NOW()
RETURNING id;


INSERT INTO users (email, password_hash, role, is_active, subject_id, created_at, updated_at)
SELECT 
    'junghooon.park@cpet.com',
    '$2b$12$qQTrsYblvK7sTBX8OKpgEObo2IgHT.u/LoSS6g8lsPi3GBdZ89jde',
    'user',
    true,
    s.id,
    NOW(),
    NOW()
FROM subjects s
WHERE s.research_id = 'SUB-PAR-JUN'
ON CONFLICT (email) DO UPDATE SET 
    password_hash = EXCLUDED.password_hash,
    updated_at = NOW();


-- Sunghoon Chung (2 files)
INSERT INTO subjects (research_id, encrypted_name, gender, notes, created_at, updated_at)
VALUES (
    'SUB-CHU-SUN',
    'Sunghoon Chung',
    NULL,
    'CPET 테스트 피험자 (2개 파일)',
    NOW(),
    NOW()
)
ON CONFLICT (research_id) DO UPDATE SET updated_at = NOW()
RETURNING id;


INSERT INTO users (email, password_hash, role, is_active, subject_id, created_at, updated_at)
SELECT 
    'sunghoon.chung@cpet.com',
    '$2b$12$qQTrsYblvK7sTBX8OKpgEObo2IgHT.u/LoSS6g8lsPi3GBdZ89jde',
    'user',
    true,
    s.id,
    NOW(),
    NOW()
FROM subjects s
WHERE s.research_id = 'SUB-CHU-SUN'
ON CONFLICT (email) DO UPDATE SET 
    password_hash = EXCLUDED.password_hash,
    updated_at = NOW();


-- Changsun Hong (7 files)
INSERT INTO subjects (research_id, encrypted_name, gender, notes, created_at, updated_at)
VALUES (
    'SUB-HON-CHA',
    'Changsun Hong',
    NULL,
    'CPET 테스트 피험자 (7개 파일)',
    NOW(),
    NOW()
)
ON CONFLICT (research_id) DO UPDATE SET updated_at = NOW()
RETURNING id;


INSERT INTO users (email, password_hash, role, is_active, subject_id, created_at, updated_at)
SELECT 
    'changsun.hong@cpet.com',
    '$2b$12$qQTrsYblvK7sTBX8OKpgEObo2IgHT.u/LoSS6g8lsPi3GBdZ89jde',
    'user',
    true,
    s.id,
    NOW(),
    NOW()
FROM subjects s
WHERE s.research_id = 'SUB-HON-CHA'
ON CONFLICT (email) DO UPDATE SET 
    password_hash = EXCLUDED.password_hash,
    updated_at = NOW();


-- Dongwook Kim (5 files)
INSERT INTO subjects (research_id, encrypted_name, gender, notes, created_at, updated_at)
VALUES (
    'SUB-KIM-DON',
    'Dongwook Kim',
    NULL,
    'CPET 테스트 피험자 (5개 파일)',
    NOW(),
    NOW()
)
ON CONFLICT (research_id) DO UPDATE SET updated_at = NOW()
RETURNING id;


INSERT INTO users (email, password_hash, role, is_active, subject_id, created_at, updated_at)
SELECT 
    'dongwook.kim@cpet.com',
    '$2b$12$qQTrsYblvK7sTBX8OKpgEObo2IgHT.u/LoSS6g8lsPi3GBdZ89jde',
    'user',
    true,
    s.id,
    NOW(),
    NOW()
FROM subjects s
WHERE s.research_id = 'SUB-KIM-DON'
ON CONFLICT (email) DO UPDATE SET 
    password_hash = EXCLUDED.password_hash,
    updated_at = NOW();


-- Sungjun Joo (3 files)
INSERT INTO subjects (research_id, encrypted_name, gender, notes, created_at, updated_at)
VALUES (
    'SUB-JOO-SUN',
    'Sungjun Joo',
    NULL,
    'CPET 테스트 피험자 (3개 파일)',
    NOW(),
    NOW()
)
ON CONFLICT (research_id) DO UPDATE SET updated_at = NOW()
RETURNING id;


INSERT INTO users (email, password_hash, role, is_active, subject_id, created_at, updated_at)
SELECT 
    'sungjun.joo@cpet.com',
    '$2b$12$qQTrsYblvK7sTBX8OKpgEObo2IgHT.u/LoSS6g8lsPi3GBdZ89jde',
    'user',
    true,
    s.id,
    NOW(),
    NOW()
FROM subjects s
WHERE s.research_id = 'SUB-JOO-SUN'
ON CONFLICT (email) DO UPDATE SET 
    password_hash = EXCLUDED.password_hash,
    updated_at = NOW();


-- Geunyun Park (4 files)
INSERT INTO subjects (research_id, encrypted_name, gender, notes, created_at, updated_at)
VALUES (
    'SUB-PAR-GEU',
    'Geunyun Park',
    NULL,
    'CPET 테스트 피험자 (4개 파일)',
    NOW(),
    NOW()
)
ON CONFLICT (research_id) DO UPDATE SET updated_at = NOW()
RETURNING id;


INSERT INTO users (email, password_hash, role, is_active, subject_id, created_at, updated_at)
SELECT 
    'geunyun.park@cpet.com',
    '$2b$12$qQTrsYblvK7sTBX8OKpgEObo2IgHT.u/LoSS6g8lsPi3GBdZ89jde',
    'user',
    true,
    s.id,
    NOW(),
    NOW()
FROM subjects s
WHERE s.research_id = 'SUB-PAR-GEU'
ON CONFLICT (email) DO UPDATE SET 
    password_hash = EXCLUDED.password_hash,
    updated_at = NOW();


-- Haesung Shin (2 files)
INSERT INTO subjects (research_id, encrypted_name, gender, notes, created_at, updated_at)
VALUES (
    'SUB-SHI-HAE',
    'Haesung Shin',
    NULL,
    'CPET 테스트 피험자 (2개 파일)',
    NOW(),
    NOW()
)
ON CONFLICT (research_id) DO UPDATE SET updated_at = NOW()
RETURNING id;


INSERT INTO users (email, password_hash, role, is_active, subject_id, created_at, updated_at)
SELECT 
    'haesung.shin@cpet.com',
    '$2b$12$qQTrsYblvK7sTBX8OKpgEObo2IgHT.u/LoSS6g8lsPi3GBdZ89jde',
    'user',
    true,
    s.id,
    NOW(),
    NOW()
FROM subjects s
WHERE s.research_id = 'SUB-SHI-HAE'
ON CONFLICT (email) DO UPDATE SET 
    password_hash = EXCLUDED.password_hash,
    updated_at = NOW();


-- Woochan Seok (4 files)
INSERT INTO subjects (research_id, encrypted_name, gender, notes, created_at, updated_at)
VALUES (
    'SUB-SEO-WOO',
    'Woochan Seok',
    NULL,
    'CPET 테스트 피험자 (4개 파일)',
    NOW(),
    NOW()
)
ON CONFLICT (research_id) DO UPDATE SET updated_at = NOW()
RETURNING id;


INSERT INTO users (email, password_hash, role, is_active, subject_id, created_at, updated_at)
SELECT 
    'woochan.seok@cpet.com',
    '$2b$12$qQTrsYblvK7sTBX8OKpgEObo2IgHT.u/LoSS6g8lsPi3GBdZ89jde',
    'user',
    true,
    s.id,
    NOW(),
    NOW()
FROM subjects s
WHERE s.research_id = 'SUB-SEO-WOO'
ON CONFLICT (email) DO UPDATE SET 
    password_hash = EXCLUDED.password_hash,
    updated_at = NOW();


-- Daesoon Kim (3 files)
INSERT INTO subjects (research_id, encrypted_name, gender, notes, created_at, updated_at)
VALUES (
    'SUB-KIM-DAE',
    'Daesoon Kim',
    NULL,
    'CPET 테스트 피험자 (3개 파일)',
    NOW(),
    NOW()
)
ON CONFLICT (research_id) DO UPDATE SET updated_at = NOW()
RETURNING id;


INSERT INTO users (email, password_hash, role, is_active, subject_id, created_at, updated_at)
SELECT 
    'daesoon.kim@cpet.com',
    '$2b$12$qQTrsYblvK7sTBX8OKpgEObo2IgHT.u/LoSS6g8lsPi3GBdZ89jde',
    'user',
    true,
    s.id,
    NOW(),
    NOW()
FROM subjects s
WHERE s.research_id = 'SUB-KIM-DAE'
ON CONFLICT (email) DO UPDATE SET 
    password_hash = EXCLUDED.password_hash,
    updated_at = NOW();


-- Kwangho Cho (1 files)
INSERT INTO subjects (research_id, encrypted_name, gender, notes, created_at, updated_at)
VALUES (
    'SUB-CHO-KWA',
    'Kwangho Cho',
    NULL,
    'CPET 테스트 피험자 (1개 파일)',
    NOW(),
    NOW()
)
ON CONFLICT (research_id) DO UPDATE SET updated_at = NOW()
RETURNING id;


INSERT INTO users (email, password_hash, role, is_active, subject_id, created_at, updated_at)
SELECT 
    'kwangho.cho@cpet.com',
    '$2b$12$qQTrsYblvK7sTBX8OKpgEObo2IgHT.u/LoSS6g8lsPi3GBdZ89jde',
    'user',
    true,
    s.id,
    NOW(),
    NOW()
FROM subjects s
WHERE s.research_id = 'SUB-CHO-KWA'
ON CONFLICT (email) DO UPDATE SET 
    password_hash = EXCLUDED.password_hash,
    updated_at = NOW();


-- Kyoungkyu Son (1 files)
INSERT INTO subjects (research_id, encrypted_name, gender, notes, created_at, updated_at)
VALUES (
    'SUB-SON-KYO',
    'Kyoungkyu Son',
    NULL,
    'CPET 테스트 피험자 (1개 파일)',
    NOW(),
    NOW()
)
ON CONFLICT (research_id) DO UPDATE SET updated_at = NOW()
RETURNING id;


INSERT INTO users (email, password_hash, role, is_active, subject_id, created_at, updated_at)
SELECT 
    'kyoungkyu.son@cpet.com',
    '$2b$12$qQTrsYblvK7sTBX8OKpgEObo2IgHT.u/LoSS6g8lsPi3GBdZ89jde',
    'user',
    true,
    s.id,
    NOW(),
    NOW()
FROM subjects s
WHERE s.research_id = 'SUB-SON-KYO'
ON CONFLICT (email) DO UPDATE SET 
    password_hash = EXCLUDED.password_hash,
    updated_at = NOW();


-- Doyoon Kim (1 files)
INSERT INTO subjects (research_id, encrypted_name, gender, notes, created_at, updated_at)
VALUES (
    'SUB-KIM-DOY',
    'Doyoon Kim',
    NULL,
    'CPET 테스트 피험자 (1개 파일)',
    NOW(),
    NOW()
)
ON CONFLICT (research_id) DO UPDATE SET updated_at = NOW()
RETURNING id;


INSERT INTO users (email, password_hash, role, is_active, subject_id, created_at, updated_at)
SELECT 
    'doyoon.kim@cpet.com',
    '$2b$12$qQTrsYblvK7sTBX8OKpgEObo2IgHT.u/LoSS6g8lsPi3GBdZ89jde',
    'user',
    true,
    s.id,
    NOW(),
    NOW()
FROM subjects s
WHERE s.research_id = 'SUB-KIM-DOY'
ON CONFLICT (email) DO UPDATE SET 
    password_hash = EXCLUDED.password_hash,
    updated_at = NOW();


COMMIT;

-- 생성된 사용자 확인
SELECT u.email, u.role, s.research_id, s.encrypted_name
FROM users u
LEFT JOIN subjects s ON u.subject_id = s.id
WHERE u.email LIKE '%@cpet.com'
ORDER BY u.email;