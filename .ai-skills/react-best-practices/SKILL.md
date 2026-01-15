---
name: cpet-db-react-best-practices
description: React and Next.js performance optimization guidelines for CPET.db. Tailored for three-tier architecture with Vercel frontend, Google Cloud Run backend, and Supabase database. Use when writing, reviewing, or refactoring React components, data fetching, or optimizing performance.
license: MIT
metadata:
  author: cpet-db-team
  version: "1.0.0"
---

# CPET.db React Best Practices

Comprehensive performance optimization guide for React and Next.js applications in CPET.db, optimized for AI-assisted development with Vercel, Google Cloud Run, and Supabase.

## When to Apply

Reference these guidelines when:
- Writing new React components or Next.js pages
- Implementing data fetching (client or server-side)
- Reviewing code for performance issues
- Refactoring existing React/Next.js code
- Optimizing bundle size or load times
- Working with Supabase real-time subscriptions
- Integrating with Cloud Run APIs

## Rule Categories by Priority

| Priority | Category | Impact | Prefix |
|----------|----------|--------|--------|
| 1 | Eliminating Waterfalls | CRITICAL | `async-` |
| 2 | Bundle Size Optimization | CRITICAL | `bundle-` |
| 3 | Server-Side Performance | HIGH | `server-` |
| 4 | Client-Side Data Fetching | MEDIUM-HIGH | `client-` |
| 5 | Re-render Optimization | MEDIUM | `rerender-` |
| 6 | Rendering Performance | MEDIUM | `rendering-` |
| 7 | JavaScript Performance | LOW-MEDIUM | `js-` |
| 8 | Advanced Patterns | LOW | `advanced-` |
| 9 | CPET-Specific Patterns | MEDIUM | `cpet-` |

## How to Use

Read individual rule files for detailed explanations and code examples:

```
rules/async-parallel.md
rules/bundle-barrel-imports.md
rules/cpet-supabase-queries.md
rules/_sections.md
```

Each rule file contains:
- Brief explanation of why it matters
- Incorrect code example with explanation
- Correct code example with explanation
- Additional context and references

## Full Compiled Document

For the complete guide with all rules expanded: `AGENTS.md`
