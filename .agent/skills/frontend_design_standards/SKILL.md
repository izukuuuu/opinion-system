---
name: Frontend Design Standards
description: Enforces design rules including color usage and hover effect restrictions.
---

# Frontend Design Standards

This skill enforces specific design constraints and standards for all frontend development tasks in the Opinion System project.

## Micro-description
Use this skill for any task involving frontend code generation, UI design, CSS modifications, or component creation.

## Instructions

### 1. Source of Truth for Colors
All colors MUST be sourced from `frontend/src/assets/colors.css`.
- **Do not** hardcode hex values or RGB values if a variable exists.
- **Do not** introduce new color palettes unless explicitly requested.

### 2. Strict Design Constraints
The user has explicit preferences that must be followed without exception:
- **NO Hover Suspension**: Do not use `transform: translateY(...)` or similar effects on hover. Elements should remain static in position.
- **NO Hover Shadows**: Do not add `box-shadow` or increase elevation on hover.
- **NO Blue-Purple Gradients**: Avoid "mysterious" or generic blue-purple gradients often found in default templates.
- **Theme Color Focus**: Stick to the project's defined theme colors (Brand, Accent, Success, Warning, Danger) defined in `colors.css`.

### 3. Usage Guidelines

#### Color Variable Usage
- **Primary Actions/Brand**: Use `var(--color-brand-*)`.
- **Backgrounds**: Use `var(--color-bg-base)`, `var(--color-bg-base-soft)`, or `var(--color-surface)`.
- **Text**: Use `var(--color-text-primary)`, `var(--color-text-secondary)`, `var(--color-text-muted)`.

#### Component Styling
When creating or modifying components (Vue, HTML, CSS):
- Adhere to the flat, clean aesthetic implied by the "No Hover Shadow/Suspension" rule.
- interactive states should use color changes (e.g., background-color darken/lighten) or border changes rather than spatial movement or shadows.

### 4. Trigger Keywords
- frontend
- ui
- design
- css
- style
- vue
- html
- component
- page
- layout
