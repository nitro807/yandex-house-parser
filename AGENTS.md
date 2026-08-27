# Project agent notes

- Keep the application in its intentionally light visual theme; do not derive its
  semantic color tokens from the operating-system dark-mode preference.
- Results tables must stay within their panel. Use a fixed table layout and allow
  untrusted parser output (including strings without spaces) to wrap.
- After UI changes, run `npm run lint` and `npm test` and visually verify the page
  at desktop and narrow viewport widths when the preview environment is available.

## Latest UI update

- Improved semantic text contrast for the results and warning states.
- Constrained result columns and enabled wrapping so parsed content cannot expand
  the table beyond its card.
- Overrode the shared table cells' `whitespace-nowrap` rule for result content and
  enabled `overflow-wrap: anywhere` for concatenated parser text.

## Latest parser update

- Require an organization's address to match the recognized house when that
  house address is known; addressless businesses from map payloads are excluded.
- Limit the DOM fallback to organization result cards so nearby map labels are
  not reported as businesses inside the requested building.
