# testing.md - Testing Conventions

## Backend Testing (pytest + FastAPI)

### Test Structure
- tests/unit/ — Unit tests (no external deps)
- tests/integration/ — Integration tests (with DB)
- tests/fixtures/ — Shared pytest fixtures

### pytest Configuration
- **Runner**: pytest
- **Async mode**: asyncio_mode = "auto"
- **Coverage**: 80% minimum
- **Command**: pytest -v --tb=short --cov=app

### Test Naming
- test_module_scenario_expected() — descriptive

### Using Fixtures
```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.fixture
async def db_session():
    session = AsyncSession(...)
    yield session
```

### Mocking External APIs
- Use unittest.mock for external deps
- Mock network calls, database transactions

## Frontend Testing (Vitest + React Testing Library)

### Unit Tests
```tsx
import { render, screen } from "@testing-library/react";

describe("Button", () => {
  it("renders with correct label", () => {
    render(<Button label="Click me" />);
    expect(screen.getByText("Click me")).toBeInTheDocument();
  });
});
```

## Coverage Requirements
- core modules: 90%+
- services: 85%+
- utils: 100%
