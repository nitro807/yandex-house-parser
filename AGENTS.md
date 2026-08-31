# Project agent notes

- Keep the application in its intentionally light visual theme; do not derive its
  semantic color tokens from the operating-system dark-mode preference.
- Results tables must stay within their panel. Use a fixed table layout and allow
  untrusted parser output (including strings without spaces) to wrap.
- After UI changes, run `npm run lint` and `npm test` and visually verify the page
  at desktop and narrow viewport widths when the preview environment is available.

## Latest UI update

- Switched the results table to a fixed layout with explicit column widths.
- Overrode the shared table cells' `whitespace-nowrap` rule for result rows and
  enabled `overflow-wrap: anywhere`, including for parser text without spaces.
- Added a rendered-component regression test for long organization, category,
  address, and phone values.

## Latest parser update

- Prefer network responses triggered by opening the building's organization tab,
  excluding unrelated businesses loaded earlier for the surrounding map.
- Keep addressless organizations when they come from that trusted building list,
  while still rejecting entries that explicitly contain a different address.
- Limit the DOM fallback to organization result cards; these cards may omit an
  address because their membership in the building list provides the context.
