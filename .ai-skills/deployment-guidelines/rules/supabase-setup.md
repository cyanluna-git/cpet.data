# Supabase - Database Setup

## Initial Migration

```sql
-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgvector";

-- Create tables (see your schema files)
-- Enable Row-Level Security on all tables
-- Create indexes for common queries
CREATE INDEX idx_cohorts_organization ON cohorts(organization_id);
CREATE INDEX idx_subjects_cohort ON subjects(cohort_id);
CREATE INDEX idx_cpet_tests_subject ON cpet_tests(subject_id);
CREATE INDEX idx_cpet_tests_created_at ON cpet_tests(created_at DESC);
```

## Real-Time Configuration

Enable real-time for tables that need live updates:

```sql
ALTER TABLE subjects REPLICA IDENTITY FULL;
ALTER TABLE cpet_tests REPLICA IDENTITY FULL;

ALTER PUBLICATION supabase_realtime ADD TABLE subjects;
ALTER PUBLICATION supabase_realtime ADD TABLE cpet_tests;
```

## Backups

- Enable automatic backups (daily or more frequent)
- Test restore procedures monthly
- Store backups in separate region
- Document backup retention policy (recommend 30 days)

## Security

- Enable RLS on all tables
- Use service role key only on backend (Cloud Run)
- Rotate API keys quarterly
- Enable audit logs in Supabase
