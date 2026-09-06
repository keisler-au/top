# Manual navigation verification (NAV-WP4)

**Status: awaiting manual execution.** These checks have not been claimed as
passed. Automated browser tooling is deferred; see
[future recommendations](future-recommendations.md).

Start the backend and frontend using the repository setup instructions. Run
`npm run dev` from `frontend/`. Use test data with generation-eligible evidence
and an active template. Use enough Overview rows to make the page several
screens tall. Record browser/version, viewport, date, and any failures below.

Repeat the navigation and visibility checks at 320px width, tablet width
(e.g. 768px), desktop width (e.g. 1440px), a short landscape viewport, and
200% browser zoom. Use actual browser zoom, not only device pixel ratio.

## Navigation and layout

- [ ] Primary navigation contains only Overview, Articles, and Forms. No
  standalone Templates or Themes & topics links appear.
- [ ] Overview has no generic Generate article header action. Targeted row and
  recommendation actions remain available and open the intended target.
- [ ] The sidebar Generate article action stays fully visible at both the top
  and bottom of a long page, and is keyboard reachable without scrolling the
  main page to its end.
- [ ] Sidebar and mobile-header generation actions open a usable generation
  starting point.
- [ ] Articles is indicated as current on both the library and article detail
  routes; Overview and Forms correctly indicate their current routes.

## Keyboard and accessibility

- [ ] Tab and Shift+Tab show visible focus and follow a logical order. The skip
  link reaches main content. Page headings and navigation/main landmarks have
  useful names in browser accessibility tools or a screen reader.
- [ ] Opening the mobile drawer moves focus to navigation; Tab and Shift+Tab
  stay within the drawer, including its brand and generation action.
- [ ] Escape and clicking the backdrop close the drawer and return focus to
  the menu button. Selecting a route closes it and moves focus into the page.
- [ ] Resizing an open mobile drawer to desktop leaves page controls usable;
  returning to mobile does not leave an invisible drawer trapping focus.
- [ ] Screen-reader announcements identify the current page, route changes,
  loading/error states, and generation progress meaningfully.

## Generation and template management

- [ ] Open targeted generation from Overview, deselect one evidence item, choose
  a template, and enter guidance. Return to Template and open Manage templates.
- [ ] Inspect template history and preview, open/cancel an archive dialog, and
  return to template selection. Dialog dismissal restores focus to its trigger.
- [ ] Target, selected evidence, guidance, and the previously selected valid
  template/version remain intact. If testing archival, use a disposable template
  and verify the archived selection is no longer usable.
- [ ] Complete these navigation steps with the keyboard. Preview remains inside
  its isolated frame and does not interfere with dashboard navigation.
- [ ] Submit a test generation request and refresh its job URL. The durable job
  is recovered without duplicate submission.

## Compatibility and history

- [ ] Visit `/taxonomy/?type=topic&search=cost&sort=name&direction=asc&page=2&page_size=25#coverage-heading`.
  It becomes `/?type=topic&search=cost&sort=name&direction=asc&page=2&page_size=25#coverage-heading`
  with query/hash state preserved.
- [ ] Visit `/templates/?step=template#preview`. It becomes `/generate`, with a
  usable initial step and no stale query/hash state.
- [ ] From another page, visit each legacy URL, then use Back and Forward.
  Neither redirect adds an extra history entry or loops.
- [ ] Refresh destination routes and navigate Overview → generation → Back →
  Forward. The intended target is restored. Unsaved request edits across full
  page navigation are not the same as durable submitted-job recovery; record
  observed behavior separately.

## Results

| Date | Browser/version | Viewport/zoom | Checks performed | Result/issues |
| --- | --- | --- | --- | --- |
| Pending | — | — | — | Not yet executed |
