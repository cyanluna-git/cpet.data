# api-conventions.md - API Design Rules

## REST API Standards

### URL Structure
- GET    /api/tests — List all tests
- GET    /api/tests/{id} — Get single test
- POST   /api/tests — Upload/create test
- PATCH  /api/tests/{id} — Update test
- DELETE /api/tests/{id} — Delete test

### Response Format

**Success (200/201):**
```json
{
  "data": { "id": "...", "vo2_max": 45.2 },
  "meta": { "timestamp": "2025-02-11T12:00:00Z" }
}
```

**Error (4xx/5xx):**
```json
{
  "error": {
    "code": "INVALID_FILE",
    "message": "File must be .xlsx format"
  }
}
```

### HTTP Status Codes
- 200 OK — Successful GET/PATCH/DELETE
- 201 Created — Successful POST
- 400 Bad Request — Invalid input
- 401 Unauthorized — Missing auth
- 404 Not Found — Resource not found
- 500 Internal Server Error — Unexpected

## Authentication
- **Method**: JWT tokens
- **Header**: Authorization: Bearer <token>
- **Role-based access**: admin, researcher, subject

## OpenAPI Documentation
- Swagger UI: /docs
- ReDoc: /redoc
