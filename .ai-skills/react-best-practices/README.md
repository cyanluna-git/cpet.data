# React Best Practices for CPET.db

Optimized React performance guidelines tailored for your CPET.db application stack:
- **Frontend**: Vercel (Next.js/React)
- **Backend**: Google Cloud Run (FastAPI)
- **Database**: Supabase (PostgreSQL)

This skill is adapted from [Vercel's agent-skills](https://github.com/vercel-labs/agent-skills).

## Structure

- `rules/` - Individual rule files (one per rule)
  - `_sections.md` - Section metadata (titles, impacts, descriptions)
  - `_template.md` - Template for creating new rules
  - `area-description.md` - Individual rule files
- `src/` - Build scripts and utilities
- `metadata.json` - Document metadata (version, organization, abstract)
- `AGENTS.md` - Compiled output (generated)

## Getting Started

1. Install dependencies:
   ```bash
   cd .ai-skills/react-best-practices
   pnpm install
   ```

2. Build AGENTS.md from rules:
   ```bash
   pnpm build
   ```

3. Validate rule files:
   ```bash
   pnpm validate
   ```

## Creating a New Rule

1. Copy `rules/_template.md` to `rules/area-description.md`
2. Choose the appropriate area prefix:
   - `async-` for Eliminating Waterfalls (Section 1)
   - `bundle-` for Bundle Size Optimization (Section 2)
   - `server-` for Server-Side Performance (Section 3)
   - `client-` for Client-Side Data Fetching (Section 4)
   - `rerender-` for Re-render Optimization (Section 5)
   - `rendering-` for Rendering Performance (Section 6)
   - `js-` for JavaScript Performance (Section 7)
   - `cpet-` for CPET-Specific Patterns (Section 9)
3. Fill in the frontmatter and content
4. Ensure you have clear examples with explanations
5. Run `pnpm build` to regenerate AGENTS.md

## Rule File Structure

Each rule file should follow this structure:

```markdown
---
title: Rule Title Here
impact: MEDIUM
impactDescription: Optional description
tags: tag1, tag2, tag3
---

## Rule Title Here

Brief explanation of the rule and why it matters.

**Incorrect (description of what's wrong):**

```typescript
// Bad code example
```

**Correct (description of what's right):**

```typescript
// Good code example
```

Optional explanatory text after examples.

Reference: [Link](https://example.com)
```

## Scripts

- `pnpm build` - Compile rules into AGENTS.md
- `pnpm validate` - Validate all rule files
- `pnpm dev` - Build and validate

## Contributing

When adding or modifying rules:

1. Use the correct filename prefix for your section
2. Follow the `_template.md` structure
3. Include clear bad/good examples with explanations
4. Add appropriate tags
5. Run `pnpm build` to regenerate AGENTS.md
6. Rules are automatically sorted by title - no need to manage numbers!
