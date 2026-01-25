-- Add body composition fields to subjects table
-- 2026-01-25

ALTER TABLE subjects ADD COLUMN IF NOT EXISTS body_fat_percent FLOAT;
ALTER TABLE subjects ADD COLUMN IF NOT EXISTS skeletal_muscle_mass FLOAT;
ALTER TABLE subjects ADD COLUMN IF NOT EXISTS bmi FLOAT;

-- Add comments
COMMENT ON COLUMN subjects.body_fat_percent IS '체지방률 (%)';
COMMENT ON COLUMN subjects.skeletal_muscle_mass IS '골격근량 (kg)';
COMMENT ON COLUMN subjects.bmi IS 'Body Mass Index';
