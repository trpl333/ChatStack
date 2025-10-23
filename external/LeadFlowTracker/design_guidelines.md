# Design Guidelines: Insurance Sales Lead Tracker

## Design Approach
**System**: Productivity-focused design inspired by Linear and Notion
**Rationale**: This is a utility-first application where efficiency, clarity, and speed matter most. Sales teams need quick daily updates without visual distractions.

## Core Design Elements

### A. Color Palette
**Dark Mode (Primary)**
- Background: 222 10% 10% (deep charcoal)
- Surface: 222 10% 14% (elevated cards)
- Border: 222 10% 20% (subtle dividers)
- Primary: 210 100% 60% (trust-inspiring blue)
- Success: 142 76% 36% (closed/won)
- Warning: 38 92% 50% (follow-up needed)
- Danger: 0 84% 60% (lost)
- Text Primary: 0 0% 98%
- Text Secondary: 0 0% 70%

**Light Mode**
- Background: 0 0% 98%
- Surface: 0 0% 100%
- Border: 220 13% 91%
- Primary: 210 100% 50%
- Text colors inverted appropriately

### B. Typography
**Fonts**: Inter (primary), JetBrains Mono (data/metrics)
- Headings: Inter 600-700, 24-32px
- Body: Inter 400, 14-16px
- Labels: Inter 500, 12-14px uppercase tracking-wide
- Data/Numbers: JetBrains Mono 500, 16px

### C. Layout System
**Spacing**: Tailwind units of 2, 4, 6, 8, 12, 16
- Consistent padding: p-4 for cards, p-6 for containers
- Gap spacing: gap-4 between elements, gap-6 between sections
- Margins: mb-8 for major sections, mb-4 for subsections

### D. Component Library

**Navigation**
- Top bar: Fixed header with app title, sync status, add lead button
- Quick filters: Pill-style buttons for stage filtering (All, Active, Closed, Lost)

**Lead Card/Row**
- Horizontal layout with key info: Name, Company, Stage, Days in Stage, Actions
- Stage indicator: Colored badge with icon
- Checkbox progression: Linear horizontal stepper showing all milestones
- Expandable details: Click to reveal full contact info, notes, history

**Stage Progression System**
- Visual stepper: First Contact → Follow-up → Quote Sent → Application → Underwriting → Closed/Bound OR Lost
- Interactive checkboxes: Check to advance, auto-save to Google Sheets
- Progress bar: Visual indicator of completion percentage
- Time tracking: Auto-calculate days in each stage

**Forms**
- Add Lead Modal: Clean overlay with fields for Name, Company, Phone, Email, Source
- Inline editing: Click any field to edit directly in the tracker view
- Auto-save indicator: Subtle "Saving..." then "Synced" with checkmark

**Data Display**
- Table view (desktop): Sortable columns, row hover states
- Card view (mobile): Stacked cards with swipe actions
- Empty state: Motivational message with prominent "Add First Lead" CTA

**Status Indicators**
- Sync status: Green dot = connected, Yellow = syncing, Red = error
- Lead priority: Flag icon for high-priority leads
- Overdue alerts: Red badge if no action in 3+ days

### E. Interactions & Animations
**Minimal Motion**
- Checkbox toggle: Quick scale animation (150ms)
- Stage advancement: Smooth color transition (200ms)
- Modal entry: Fade + slight scale (250ms)
- Row hover: Subtle background shift
- NO unnecessary scroll animations or decorative effects

## Specialized Features

**Dashboard Widgets**
- Today's Summary: Cards showing total leads, pending actions, closed this week
- Quick Stats: Conversion rate, average time to close, pipeline value
- Activity Feed: Recent updates, stage changes, new leads

**Mobile Optimization**
- Bottom navigation for quick access: Dashboard, Add Lead, Settings
- Swipe gestures: Swipe right to advance stage, left for actions menu
- Large touch targets: Minimum 44x44px for all interactive elements

**Accessibility**
- High contrast mode support
- Keyboard shortcuts: N for new lead, / for search
- Screen reader labels for all stage indicators
- Focus indicators on all interactive elements

## Layout Structure

**Main View**
```
[Header: Logo | Sync Status | Add Lead Button]
[Filters: All | Active | Closed | Lost]
[Quick Stats Cards: 3-column grid on desktop, stack on mobile]
[Lead List/Table: Sortable, filterable, expandable rows]
```

**Add Lead Modal**
- Centered overlay (max-w-md)
- Clean form with labeled inputs
- Primary action: "Add Lead" button
- Secondary: "Cancel" text button

This design prioritizes speed, clarity, and ease of use for busy sales professionals making daily updates on-the-go.