# Sections

This file defines all sections, their ordering, impact levels, and descriptions.
The section ID (in parentheses) is the filename prefix used to group rules.

---

## 1. Eliminating Waterfalls (async)

**Impact: CRITICAL**

Prevent sequential data fetching that blocks rendering. Parallelize independent operations and defer awaits until needed.

---

## 2. Bundle Size Optimization (bundle)

**Impact: CRITICAL**

Reduce initial bundle size through strategic imports, code splitting, and lazy loading.

---

## 3. Server-Side Performance (server)

**Impact: HIGH**

Optimize server components and API routes. Minimize computation in request handlers.

---

## 4. Client-Side Data Fetching (client)

**Impact: MEDIUM-HIGH**

Efficient data fetching patterns for client components. Handle loading, error, and caching states properly.

---

## 5. Re-render Optimization (rerender)

**Impact: MEDIUM**

Minimize unnecessary re-renders through proper dependency management and memoization.

---

## 6. Rendering Performance (rendering)

**Impact: MEDIUM**

Optimize DOM rendering and visual updates. Use modern CSS and rendering techniques.

---

## 7. JavaScript Performance (js)

**Impact: LOW-MEDIUM**

Micro-optimizations for JavaScript execution. Cache operations and reduce algorithmic complexity.

---

## 8. Advanced Patterns (advanced)

**Impact: LOW**

Advanced patterns and techniques for specific scenarios.

---

## 9. CPET-Specific Patterns (cpet)

**Impact: MEDIUM**

Patterns and practices specific to CPET data visualization and metabolic analysis. Integration with Supabase and Cloud Run APIs.
