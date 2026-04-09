---
name: Frontend Design Standards
description: Enforces strict frontend visual rules for Opinion System. Prioritize this skill for any visual changes under frontend/src/**, especially when requests mention hover, shadows, buttons, tabs, cards, or colors.
---

# Frontend Design Standards

This skill defines the strict design standards for the frontend of the Opinion System. All frontend changes must adhere to these rules.

## Trigger Guidance

Prefer reading this skill first for any visual or interaction polish work under `frontend/src/**`.

### Strong Match Keywords

- hover
- 阴影
- shadow
- 按钮
- button
- tab
- 卡片
- card
- 颜色
- color

### Preferred Scenarios

- Any UI styling or layout change in `frontend/src/**`
- Requests to adjust button, tab, card, modal, or input appearance
- Requests to remove or soften hover effects, shadows, borders, or animations
- Requests to align frontend visuals with the Opinion System design language

## 0. Design Philosophy: Material You (M3) with Strict Constraints

The visual identity of this project is **Modern, Expressive, and Adaptive**, heavily inspired by **Material Design 3 (Material You)**.

### The "Sense" & Vibe
-   **Alive & Responsive:** Every interaction should provide immediate, delightful feedback. The interface should feel like it's responding to the user's touch/cursor.
-   **Spacious & Clean:** Use generous whitespace. Don't cram information. Let the content breathe. This creates a sense of calm and clarity.
-   **Playful Geometry:** Embrace large corner radii (like `rounded-3xl`) to create a friendly, approachable interface.
-   **Elevation via Tonal Surfaces:** Since we strictly avoid shadows, depth MUST be achieved through **Surface Tones**. Higher elevation = lighter/different surface color, not a drop shadow.

### Specific Mapping to Constraints
While aiming for this modern feel, you MUST strictly adhere to these specific implementation rules:

-   **Borders:** Use **1px subtle borders** to define boundaries instead of heavy shadows or harsh lines.
-   **Corner Radius:** Consistently use the specified large radii (e.g., `rounded-3xl` for containers, `rounded-full` for buttons) to maintain the "organic" feel.
-   **Colors:** All colors must come from `frontend/src/assets/colors.css`. Use the color variables to create hierarchy (Surface > Surface Variant > Background).
-   **Interaction:**
    -   **Hover:** Use subtle background color shifts (state layers) instead of shadows.
    -   **Active:** Use distinct color changes to indicate activation.

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
    -   **STRICTLY AVOID** any hover shadows. The design must remain flat during interactions.
    -   **AVOID** heavy or large shadows.
    -   Use flat design principles where possible.
    -   Only use shadows for necessary depth (e.g., modals, dropdowns).

## 3. UX & Communication Guidelines

-   **User-Centric Language:**
    -   Focus on the **User's Goal**, not the system's process.
    -   **BAD:** "Executing `process_data` on backend worker."
    -   **GOOD:** "Analyzing your data..."
-   **Hide Backend Complexity:**
    -   **NEVER** expose internal variable names (e.g., `is_processed`, `db_id`), raw JSON, or file paths unless specifically requested in a "Debug" mode.
    -   **No Technical Jargon:** Avoid terms like "API", "Endpoint", "Latency", or "Schema" in general UI. Use "Connection", "Speed", or "Structure".
-   **Clarity & Simplicity:**
    -   Keep labels and messages short and scannable.
    -   Use natural language for status updates (e.g., "Ready" instead of "State: 1").

## 4. Typography

-   Use the defined utility classes for text colors (`.text-primary`, `.text-secondary`, `.text-muted`, `.text-brand`, etc.).

## 5. Components

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
    -   **Muted Cards:**
        -   Use `.mute-card-surface` for secondary or less prominent card containers.
        -   **Features:** Identical to `.card-surface` (including rounded corners) but uses `var(--color-surface-muted)` background.
-   **Icons:**
    -   Use **Heroicons** for all icon needs.
    -   Import from `@heroicons/vue/24/outline` for outline icons or `@heroicons/vue/24/solid` for solid icons.
    -   **Reason:** Heroicons provides a consistent, modern icon set that integrates seamlessly with Vue, ensuring visual consistency across the application.
-   **Standardized Input & Button Styles:**
    -   **Inputs:**
        -   **Background:** Use `bg-base-soft` (`--color-bg-base-soft`) for a clean, light, and grounded look. Avoid using darker tints like `bg-surface-muted` or `bg-brand-50/30` for primary inputs.
        -   **Interaction:** Use `focus:bg-surface focus:ring-2 focus:ring-brand-500/20` for a soft, premium focus state.
        -   **Rounding:** Standardize on `rounded-2xl` for inputs.
    -   **Buttons:**
        -   **Primary:** Use `bg-brand-600` (`--color-brand-600`) with white text, `rounded-full`, and no diffuse shadows for a flat, modern look.
