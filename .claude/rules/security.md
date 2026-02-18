# security.md - Security Guidelines

## Environment Variables

### Sensitive Data (Never commit)
- DATABASE_URL
- SECRET_KEY
- API_KEYS
- CORS_ORIGINS (production specific)

Use `.env` (gitignored) for development.

## Authentication & Authorization

### JWT Security
- Use strong random SECRET_KEY
- Set expiration times (24h typical)
- Hash tokens before storing
- Revoke immediately on request

### Role-Based Access Control
- admin: Full access
- researcher: Read/write test data
- subject: Read own data only

## Input Validation

### Data Validation
- All user input validated with Pydantic models
- File upload: Check MIME type + file signature
- Excel parsing: Validate sheet structure

### SQL Injection Prevention
- Use SQLAlchemy ORM (never raw SQL)
- Use parameterized queries
- Never interpolate user input

### File Upload Security
- Validate file size (max 10MB)
- Check file extension whitelist (.xlsx only)
- Store in secure location (not web root)
- Scan for malicious content

## Secrets Management

### Key Rotation
- Rotate API keys every 90 days
- Rotate DB passwords every 6 months
- Maintain rollover period (both keys valid)

## Logging & Monitoring

### What NOT to Log
- Tokens, passwords, secrets
- Personal health information (PII)

### What to Log
- Important state changes
- File uploads/downloads
- Authentication events
- Errors with context

### Log Levels
- DEBUG: Development only
- INFO: Important events
- WARNING: Recoverable issues
- ERROR: Errors (app continues)
- CRITICAL: Severe issues
