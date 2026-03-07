CREATE TABLE IF NOT EXISTS inscyd_reports (
    report_id UUID PRIMARY KEY,
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    external_test_id VARCHAR(100),
    report_date DATE,
    sport VARCHAR(100),
    test_type VARCHAR(100),
    athlete_name VARCHAR(255),
    coach_name VARCHAR(255),
    body_mass_kg DOUBLE PRECISION,
    body_height_cm DOUBLE PRECISION,
    body_mass_index DOUBLE PRECISION,
    projected_bsa_m2 DOUBLE PRECISION,
    body_fat_percent DOUBLE PRECISION,
    body_fat_kg DOUBLE PRECISION,
    fat_free_percent DOUBLE PRECISION,
    fat_free_kg DOUBLE PRECISION,
    vo2max_abs_ml_min DOUBLE PRECISION,
    vo2max_rel_ml_kg_min DOUBLE PRECISION,
    vlamax_mmol_l_s DOUBLE PRECISION,
    mfo_abs_kcal_h DOUBLE PRECISION,
    mfo_rel_kcal_h_kg DOUBLE PRECISION,
    fatmax_watt DOUBLE PRECISION,
    carbmax_abs_watt DOUBLE PRECISION,
    carbmax_rel_w_kg DOUBLE PRECISION,
    at_abs_watt DOUBLE PRECISION,
    at_rel_w_kg DOUBLE PRECISION,
    at_pct_vo2max DOUBLE PRECISION,
    glycogen_abs_g DOUBLE PRECISION,
    glycogen_rel_g_kg DOUBLE PRECISION,
    hr_max_bpm INTEGER,
    pwc150_watt DOUBLE PRECISION,
    training_zones JSONB,
    test_data_rows JSONB,
    weighted_regression JSONB,
    raw_sections JSONB,
    raw_text TEXT,
    source_filename VARCHAR(255),
    file_upload_timestamp TIMESTAMP,
    parsing_status VARCHAR(50) NOT NULL DEFAULT 'success',
    parsing_warnings JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_inscyd_reports_subject_id
    ON inscyd_reports(subject_id);

CREATE INDEX IF NOT EXISTS idx_inscyd_reports_report_date
    ON inscyd_reports(report_date);

CREATE INDEX IF NOT EXISTS idx_inscyd_reports_subject_date
    ON inscyd_reports(subject_id, report_date);
