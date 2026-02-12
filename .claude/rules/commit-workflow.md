# commit-workflow.md - Git & Commit Conventions

## Branch Strategy

### Branch Types
- main/ — Production-ready
- staging/ — Pre-production testing
- develop/ — Integration branch
  - feature/* — New features
  - bugfix/* — Bug fixes
  - refactor/* — Code refactoring

## Commit Messages

### Format (Conventional Commits)
```
<type>(<scope>): <subject>

<body>

<footer>
```

### Commit Types
- **feat**: New feature
- **fix**: Bug fix
- **refactor**: Code restructuring
- **perf**: Performance improvement
- **test**: Add/update tests
- **docs**: Documentation
- **style**: Code formatting
- **chore**: Dependencies, tooling
- **ci**: CI/CD configuration

### Scope
- backend, frontend, db, api, parser, analyzer, ui, docker

### Subject Line
- Imperative mood: "add", "fix", "remove"
- Lowercase first letter
- No period at end
- <= 50 characters

## Pull Request Workflow

1. **Author**: Create PR from feature branch → develop
2. **Reviewer**: Check logic, tests, documentation
3. **Author**: Address feedback
4. **Merge**: Squash or rebase for clean history

## Release Process

- Version: MAJOR.MINOR.PATCH (semver)
- Tag: git tag -a vX.Y.Z
- Release notes with changelog
