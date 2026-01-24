-- Migration: Alter parsing_status column length from VARCHAR(20) to VARCHAR(50)
-- Reason: 'skipped_protocol_mismatch' exceeds 20 characters
-- Date: 2026-01-24

ALTER TABLE cpet_tests
ALTER COLUMN parsing_status TYPE VARCHAR(50);
