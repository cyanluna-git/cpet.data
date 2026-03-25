-- Blood Samples table for lactate/glucose blood data
-- Stores per-step blood sample measurements from CPET tests

CREATE TABLE IF NOT EXISTS blood_samples (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cpet_test_id UUID NOT NULL REFERENCES cpet_tests(test_id) ON DELETE CASCADE,

    -- Sample identification
    block VARCHAR(20),               -- rest, block_1, block_2, block_3
    step VARCHAR(20),                -- 0, 1-1, 1-2, 2-1, 3-1, etc.

    -- Exercise load
    load_w DOUBLE PRECISION,         -- Power (Watts)
    ftp_pct VARCHAR(10),             -- FTP percentage (e.g., "80%")
    duration_min DOUBLE PRECISION,   -- Step duration (minutes)

    -- Timing
    sample_time_kst VARCHAR(20),     -- Sample collection time (KST)
    elapsed_sec DOUBLE PRECISION,    -- Elapsed time from test start (seconds)

    -- Measurements
    hr_bpm DOUBLE PRECISION,         -- Heart rate (bpm)
    lactate_mmol DOUBLE PRECISION,   -- Blood lactate (mmol/L)
    glucose_mmol DOUBLE PRECISION,   -- Blood glucose (mmol/L)

    -- Metadata
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_blood_samples_cpet_test_id
    ON blood_samples(cpet_test_id);

CREATE INDEX IF NOT EXISTS idx_blood_samples_block
    ON blood_samples(cpet_test_id, block);

COMMENT ON TABLE blood_samples IS 'Blood sample measurements (lactate/glucose) taken during CPET tests';
COMMENT ON COLUMN blood_samples.block IS 'Test block: rest, block_1 (LT1), block_2 (VO2max), block_3 (clearance)';
COMMENT ON COLUMN blood_samples.lactate_mmol IS 'Blood lactate concentration (mmol/L)';
COMMENT ON COLUMN blood_samples.glucose_mmol IS 'Blood glucose concentration (mmol/L)';
