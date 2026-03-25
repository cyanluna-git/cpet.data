-- Add energy_system JSONB column to processed_metabolism table
-- Stores 3-pathway energy system analysis results

ALTER TABLE processed_metabolism
    ADD COLUMN IF NOT EXISTS energy_system JSONB;

COMMENT ON COLUMN processed_metabolism.energy_system IS
    'Energy system 3-pathway analysis results (oxidative, glycolytic, phosphagen). '
    'Includes pathway kJ values, percentages, mono-exponential fit parameters, '
    'and recovery window configuration.';
