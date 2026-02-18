---
paths:
  - "backend/**/*.py"
  - "frontend/src/**/*.{ts,tsx}"
---

# code-style.md - Coding Standards

## Python (Backend / FastAPI)

### Style & Formatting
- **Line length**: 100 characters (Black configured)
- **Formatter**: Black v24+
- **Import order**: isort (Black profile)
- **Target version**: Python 3.11+

### Type Annotations
- **Required**: All function signatures must have type hints
- **Strict mypy**: disallow_untyped_defs = true

### Naming Conventions
- **Classes**: PascalCase (e.g., COSMEDParser, MetabolismAnalyzer)
- **Functions/methods**: snake_case (e.g., parse_excel, analyze_breath_data)
- **Constants**: UPPER_SNAKE_CASE
- **Private attributes**: Leading underscore

### Async/Await
- Use async def for I/O-bound operations
- Never block event loop
- Await all coroutines

### Error Handling
- Define custom exceptions in app/exceptions.py
- Use specific exception types
- Log before re-raising

## TypeScript / React (Frontend)

### Component Patterns
- **Functional components only** (no class components)
- **Custom hooks** for shared logic (useAuth, useFetch)
- **Memoization**: React.memo() for expensive renders

### File Structure
- src/components/ — Reusable UI components
- src/pages/ — Page-level components (lazy loaded)
- src/hooks/ — Custom React hooks
- src/lib/ — API client (axios)
- src/types/ — TypeScript type definitions
- src/utils/ — Helper functions

### TypeScript Strict Mode
- No implicit any
- Strict null checks
- Strict function types

## YAML Configuration

- **Indentation**: 2 spaces
- **Strings with special chars**: Double quotes
