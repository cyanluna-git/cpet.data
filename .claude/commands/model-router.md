---
allowed-tools: Task
description: Analyze task complexity and automatically route to appropriate Claude model (Haiku/Sonnet/Opus)
argument-hint: "[task description]"
model: haiku
---

# Model Router

Analyzes task description and automatically routes to the most appropriate Claude model based on complexity.

## Model Selection Criteria

### Haiku (Fast)
- Basic questions, queries, searches
- File reading, simple modifications
- Code analysis, type checking
- **Time:** <30s
- **Examples:** "Which files contain FATMAX logic?", "Explain this function"

### Sonnet (Balanced)
- Detailed analysis, exploration
- Medium-scale design (3–5 files)
- Feature implementation, bug fixes
- **Time:** 30s–2m
- **Examples:** "Implement new API endpoint", "Find performance bottlenecks"

### Opus (Deep reasoning)
- Complex architecture design
- Large-scale refactoring (5+ files)
- Comprehensive implementations
- **Time:** 2–10m
- **Examples:** "Redesign entire data pipeline", "Build new testing framework"

## Usage

```
/model-router "your task description"
```

## How It Works

1. **Complexity Analysis**: Extract scope, file count, reasoning required
2. **Model Selection**: Choose Haiku/Sonnet/Opus based on analysis
3. **Task Execution**: Run with selected model
4. **Result Return**: Present results

## Examples

### Haiku Routing
```
/model-router "List files related to FATMAX analysis"
→ Fast search, Haiku execution
```

### Sonnet Routing
```
/model-router "Implement new API endpoint /api/vo2max/export"
→ Medium-scale code, Sonnet execution
```

### Opus Routing
```
/model-router "Redesign entire data pipeline from collection to visualization"
→ Complex design, Opus execution
```

## Notes

- Clearer descriptions → better model selection
- Tasks more complex than expected → auto-upgrade to stronger model
- Force specific model: `[Opus] your task`
