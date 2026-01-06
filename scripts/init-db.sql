-- CPET Database Initialization Script
-- PostgreSQL + TimescaleDB Extension

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- 1. Users/Subjects Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS subjects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    research_id VARCHAR(50) UNIQUE NOT NULL,
    encrypted_name VARCHAR(255),
    birth_year INT,
    gender VARCHAR(10),
    job_category VARCHAR(50),
    medical_history JSONB,
    training_level VARCHAR(20),
    weight_kg DOUBLE PRECISION,
    height_cm DOUBLE PRECISION,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_subjects_research_id ON subjects(research_id);
CREATE INDEX idx_subjects_gender_birth_year ON subjects(gender, birth_year);

-- ============================================================================
-- 2. CPET Tests Metadata Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS cpet_tests (
    test_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subject_id UUID REFERENCES subjects(id) ON DELETE CASCADE,
    test_date TIMESTAMP NOT NULL,
    test_time TIME,
    protocol_name VARCHAR(100),
    protocol_type VARCHAR(10),
    test_type VARCHAR(20) DEFAULT 'Maximal',
    maximal_effort VARCHAR(20),
    test_duration TIME,
    exercise_duration TIME,

    -- Environmental conditions
    barometric_pressure DOUBLE PRECISION,
    ambient_temp DOUBLE PRECISION,
    ambient_humidity DOUBLE PRECISION,
    device_temp DOUBLE PRECISION,

    -- Body measurements at test time
    weight_kg DOUBLE PRECISION,
    bsa DOUBLE PRECISION,
    bmi DOUBLE PRECISION,

    -- Main analysis results
    vo2_max DOUBLE PRECISION,
    vo2_max_rel DOUBLE PRECISION,
    vco2_max DOUBLE PRECISION,
    hr_max INT,

    -- FATMAX related
    fat_max_hr INT,
    fat_max_watt DOUBLE PRECISION,
    fat_max_g_min DOUBLE PRECISION,

    -- Threshold related
    vt1_hr INT,
    vt1_vo2 DOUBLE PRECISION,
    vt2_hr INT,
    vt2_vo2 DOUBLE PRECISION,

    -- Analysis configuration
    calc_method VARCHAR(20) DEFAULT 'Frayn',
    smoothing_window INT DEFAULT 10,

    -- Phase information
    warmup_end_sec INT,
    test_end_sec INT,

    -- File tracking
    source_filename VARCHAR(255),
    file_upload_timestamp TIMESTAMP,
    parsing_status VARCHAR(20),
    parsing_errors JSONB,

    -- Other
    notes TEXT,
    data_quality_score DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_cpet_tests_subject_id ON cpet_tests(subject_id);
CREATE INDEX idx_cpet_tests_test_date ON cpet_tests(test_date);
CREATE INDEX idx_cpet_tests_subject_date ON cpet_tests(subject_id, test_date);

-- ============================================================================
-- 3. Breath Data Table (TimescaleDB Hypertable)
-- ============================================================================
CREATE TABLE IF NOT EXISTS breath_data (
    time TIMESTAMP NOT NULL,
    test_id UUID NOT NULL,

    -- Raw measurements from COSMED K5
    t_sec DOUBLE PRECISION,
    rf DOUBLE PRECISION,
    vt DOUBLE PRECISION,
    vo2 DOUBLE PRECISION,
    vco2 DOUBLE PRECISION,
    ve DOUBLE PRECISION,
    hr INT,
    vo2_hr DOUBLE PRECISION,

    -- Exercise load
    bike_power INT,
    bike_torque DOUBLE PRECISION,
    cadence INT,

    -- Gas fractions
    feo2 DOUBLE PRECISION,
    feco2 DOUBLE PRECISION,
    feto2 DOUBLE PRECISION,
    fetco2 DOUBLE PRECISION,

    -- Ventilation ratios
    ve_vo2 DOUBLE PRECISION,
    ve_vco2 DOUBLE PRECISION,

    -- Calculated metrics
    rer DOUBLE PRECISION,
    fat_oxidation DOUBLE PRECISION,
    cho_oxidation DOUBLE PRECISION,
    pro_oxidation DOUBLE PRECISION,
    vo2_rel DOUBLE PRECISION,
    mets DOUBLE PRECISION,

    -- Energy expenditure
    ee_total DOUBLE PRECISION,
    ee_kcal_day DOUBLE PRECISION,

    -- Quality indicators
    is_valid BOOLEAN DEFAULT true,
    phase VARCHAR(20),
    raw_t_value TIME,
    data_source VARCHAR(10),

    PRIMARY KEY (time, test_id)
);

-- Convert to TimescaleDB hypertable
SELECT create_hypertable('breath_data', 'time', if_not_exists => TRUE);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_breath_data_test_id ON breath_data(test_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_breath_data_phase ON breath_data(test_id, phase);

-- ============================================================================
-- 4. Cohort Statistics Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS cohort_stats (
    stat_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    gender VARCHAR(10),
    age_group VARCHAR(20),
    training_level VARCHAR(20),

    -- Statistical values
    metric_name VARCHAR(50),
    mean_value DOUBLE PRECISION,
    median_value DOUBLE PRECISION,
    std_dev DOUBLE PRECISION,
    percentile_10 DOUBLE PRECISION,
    percentile_25 DOUBLE PRECISION,
    percentile_75 DOUBLE PRECISION,
    percentile_90 DOUBLE PRECISION,

    sample_size INT,
    last_updated TIMESTAMP DEFAULT NOW(),

    UNIQUE(gender, age_group, training_level, metric_name)
);

CREATE INDEX idx_cohort_stats_lookup ON cohort_stats(gender, age_group, training_level, metric_name);

-- ============================================================================
-- 5. User Accounts Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL,
    subject_id UUID REFERENCES subjects(id) ON DELETE SET NULL,

    is_active BOOLEAN DEFAULT true,
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_subject_id ON users(subject_id);

-- ============================================================================
-- Triggers for updated_at timestamp
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_subjects_updated_at BEFORE UPDATE ON subjects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_cpet_tests_updated_at BEFORE UPDATE ON cpet_tests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Initial data (optional)
-- ============================================================================
-- Insert a default admin user (password: admin123 - change in production!)
-- Password hash generated with bcrypt
INSERT INTO users (email, password_hash, role, is_active)
VALUES ('admin@cpet.db', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYqQnLhF0uG', 'admin', true)
ON CONFLICT (email) DO NOTHING;
