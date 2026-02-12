# Frontend Module

React + TypeScript SPA for CPET data visualization and user interface.

## Overview

Vite-based React 18 application (port 3100) with interactive CPET data visualization, test management, and user authentication.

## Tech Stack

- **Framework**: React 18 + TypeScript 5
- **Bundler**: Vite 5
- **Styling**: Tailwind CSS + Shadcn UI
- **Data**: React Query (server state), Zustand (client state)
- **Visualization**: Recharts (charts)
- **HTTP**: Axios with custom interceptors
- **Testing**: Vitest + React Testing Library

## Key Modules

- `src/pages/` — Route pages (lazy loaded):
  - Dashboard, MetabolismAnalysis, TestHistory, Settings
- `src/components/` — Reusable UI components
- `src/hooks/` — Custom hooks:
  - `useAuth()` — Authentication state
  - `useFetch()` — Data fetching with retry
- `src/lib/api.ts` — Centralized axios client
- `src/types/` — TypeScript interfaces

## Commands

```bash
npm run dev                # Vite dev server (port 3100)
npm run build              # Production build
npm run lint               # ESLint
pnpm test                  # Vitest
pnpm test:e2e              # Playwright E2E
```

## Environment

- `VITE_API_URL`: Backend API base URL (http://localhost:8100)

## Patterns

- **Lazy loading**: All pages wrapped in React.lazy()
- **Error boundaries**: Top-level error handling
- **Data fetching**: React Query with 1s polling
- **State**: Zustand for auth, React Query for server state

## Parent Rules

Inherit from `@../../.claude/rules/`:
- code-style.md — React/TypeScript conventions
- testing.md — Vitest + RTL patterns
- api-conventions.md — API client design
- commit-workflow.md — Git conventions
- security.md — Auth tokens, XSS prevention
