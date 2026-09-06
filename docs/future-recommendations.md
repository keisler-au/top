# Future recommendations

## Automated browser and accessibility regression tests

**Deferred on 2026-09-05:** browser functionality will be tested manually for
now. Do not add Playwright or axe dependencies as part of the current work.

When automated browser regression coverage is wanted, consider Playwright with
axe accessibility scans as development-only dependencies. This would verify
actual browser layout, keyboard focus, history navigation, mobile drawer
behavior, and preview isolation, which the existing Node unit tests cannot
establish.

Suggested coverage:

- Overview → targeted generation and sidebar/mobile-header → generation.
- Generation → nested template management → generation, preserving evidence,
  guidance, and valid template selection.
- Legacy `/taxonomy` and `/templates` redirects, refresh, and Back/Forward.
- Keyboard order, focus visibility and return, drawer containment, landmarks,
  accessible names, and active-route announcements.
- Sidebar generation action visibility on long pages at 320px, tablet, desktop,
  short landscape viewports, and 200% browser zoom.
- Accessibility scans across primary routes and nested template management.

Use deterministic API fixtures for frontend regressions; retain separate live
backend/database integration checks. Browser automation and automated scans
also complement, rather than replace, manual screen-reader review.

Current verification instructions are in
[the manual navigation checklist](manual-navigation-checklist.md). The broader
integration and security work remains in
[WP11](dashboard-remaining-work-packages.md#wp11--integration-database-browser-accessibility-and-security-testing).
