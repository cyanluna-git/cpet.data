-- Migration: Add demographic fields to subjects and cpet_tests tables
-- Date: 2026-01-18
-- Description:
--   - Add birth_date to subjects table for storing full date of birth
--   - Add age and height_cm to cpet_tests table for storing test-time demographics

-- Add birth_date to subjects table
ALTER TABLE subjects
ADD COLUMN IF NOT EXISTS birth_date DATE;

COMMENT ON COLUMN subjects.birth_date IS '피험자 생년월일 (전체 날짜)';

-- Add age and height_cm to cpet_tests table
ALTER TABLE cpet_tests
ADD COLUMN IF NOT EXISTS age FLOAT,
ADD COLUMN IF NOT EXISTS height_cm FLOAT;

COMMENT ON COLUMN cpet_tests.age IS '테스트 수행 시점의 나이 (세)';
COMMENT ON COLUMN cpet_tests.height_cm IS '테스트 수행 시점의 키 (cm)';

-- Note: weight_kg already exists in cpet_tests table
-- Note: birth_year already exists in subjects table and will be kept for backward compatibility
