---
name: Frontend Design Standards
description: Enforces strict design rules including color usage, hover effects restrictions, and theme prioritization.
---

# Frontend Design Standards

This skill defines the strict design standards for the frontend of the Opinion System. All frontend changes must adhere to these rules.

## 1. Color Usage

-   **Source of Truth:** All colors MUST use the variables defined in `frontend/src/assets/colors.css`.
-   **No Hardcoded Colors:** Do NOT use hex codes or RGB values directly in components (except when defining the variables in `colors.css` itself). Use the CSS variables or the utility classes.
-   **Theme Prioritization:**
    -   Use **Brand** colors (`--color-brand-*`) for primary actions, active states, and key branding elements.
    -   Use **Accent** colors (`--color-accent-*`) for secondary information, highlights, and complementary elements.
    -   Use **Neutral** colors (`--color-bg-base`, `--color-surface`, `--color-text-*`) for structure, backgrounds, and typography.
    -   Use **Semantic** colors (Success, Danger, Warning) ONLY for their specific semantic meanings (success messages, errors, warnings).

## 2. Interaction Design

-   **Hover Effects:**
    -   **AVOID** unnecessary hover effects.
    -   Buttons and interactive elements should have subtle state changes (e.g., slight color shift, opacity change) but avoid defining new, complex hover animations unless strictly required.
    -   Do NOT add hover effects to non-interactive elements.
-   **Shadows:**
    -   **AVOID** heavy or large shadows.
    -   Use flat design principles where possible.
    -   If shadows are necessary for depth (e.g., modals, dropdowns), use the minimal shadow variables if available, or extremely subtle custom shadows.

## 3. Typography

-   Use the defined utility classes for text colors (`.text-primary`, `.text-secondary`, `.text-muted`, `.text-brand`, etc.).

## 4. Components

-   Reusable components (Buttons, Inputs, etc.) are defined in `colors.css` (e.g., `.btn-primary`, `.input`). Use these classes instead of recreating styles.
-   **Cards:**
    -   Use the `.card-surface` class for all card-like containers.
    -   **Layout Rules:**
        -   Use `space-y-6` for vertical spacing between elements within the card or between stacks of cards.
        -   Do **NOT** add horizontal padding to the main card container itself; content should be managed internally if needed.
    -   **Reason:** This ensures consistent styling across the application, specifically:
        -   **Rounded Corners:** Applies `rounded-3xl` for a modern, soft look.
        -   **Background:** Uses `var(--color-surface)` for consistent theming.
        -   **Border:** Uses `var(--color-border-soft)` for subtle separation.
        -   **Effects:** Includes `backdrop-blur` and `overflow-hidden` for polished visuals.
-   **Icons:**
    -   Use **Heroicons** for all icon needs.
    -   Import from `@heroicons/vue/24/outline` for outline icons or `@heroicons/vue/24/solid` for solid icons.
    -   **Reason:** Heroicons provides a consistent, modern icon set that integrates seamlessly with Vue, ensuring visual consistency across the application.
