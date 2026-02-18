# Model Router Skill

## Metadata

```yaml
name: model-router
version: 1.0.0
description: Intelligently route tasks to appropriate Claude model based on complexity
author: CPET Team
triggers:
  - patterns:
      - "(?:implement|build|create|develop|add|write|refactor|redesign|optimize|architect).*\\b(?:API|endpoint|feature|component|function|system|pipeline|framework|architecture)\\b"
      - "(?:plan|design|architect).*(?:full-stack|entire|comprehensive|system-wide|large-scale)"
      - "(?:refactor|rewrite|redesign)\\b.{0,50}\\b(?:all|entire|whole|complete|major)"
      - "(?:what|which|list|find|show|explain|describe)\\b.*\\b(?:files|functions|modules|components|how|logic)\\b"
      - "(?:analyze|investigate|debug|profile|check).*\\b(?:performance|efficiency|bottleneck|issue|problem)\\b"
    model_hints:
      - pattern: "(?:implement|build|develop)\\b.{0,100}\\b(?:API|endpoint|feature|component)\\b(?!.*refactor)(?!.*optimize)"
        model: sonnet
        reason: "Medium-scale feature implementation"
      - pattern: "(?:what|which|list|find|explain)\\b"
        model: haiku
        reason: "Simple query or search"
      - pattern: "(?:plan|design|architect|refactor|redesign|rewrite).*\\b(?:entire|all|whole|comprehensive|full-stack|system-wide)"
        model: opus
        reason: "Large-scale architecture or design"
      - pattern: "(?:analyze|profile|debug|optimize).*\\b(?:performance|efficiency|bottleneck)"
        model: sonnet
        reason: "Detailed analysis task"

proactive: true
auto_trigger: true
```

## How It Works

Automatically detects task complexity from user input and routes to the appropriate model:

### Detection Rules

1. **Haiku (Fast)** - Triggered by:
   - Questions: "What files...", "Which modules...", "Explain...", "List..."
   - Simple searches or lookups
   - Code reading/understanding

2. **Sonnet (Balanced)** - Triggered by:
   - Feature implementation: "Implement new API endpoint..."
   - Detailed analysis: "Analyze performance..."
   - Medium-scale changes (3-5 files)

3. **Opus (Deep)** - Triggered by:
   - Architecture terms: "design", "architect", "plan"
   - Scale keywords: "entire", "all", "full-stack", "comprehensive"
   - Large refactoring: "Refactor entire...", "Redesign..."

## Examples

```
User: "What files contain FATMAX logic?"
→ Auto-triggers Haiku

User: "Implement new API endpoint /api/vo2max/export"
→ Auto-triggers Sonnet

User: "Design the entire data pipeline from collection to visualization"
→ Auto-triggers Opus
```

## Integration

Works seamlessly with:
- CLAUDE.md Model Selection Guide (lines 100-137)
- Explicit override: `[Opus] your task` forces specific model
- Auto routing when no model specified
