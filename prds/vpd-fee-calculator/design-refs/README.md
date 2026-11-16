# Design References

## Reference products

- **Linear**: Borrow the inline anomaly flag pattern. When a field value is out of range, a subtle warning banner appears inside the form row — not a blocking modal, not a toast — so the analyst can see the issue and still choose to proceed. Apply this to the VPD calculator when fee percentage exceeds the 25% threshold.
  Screenshot: `design-refs/linear-reference.png` (drop your own screenshot here)

- **Height**: Borrow the side-by-side calculator panel layout. Input fields sit on the left; a live preview of calculated results updates in real time on the right as values are entered. No submit button needed to see results. Apply this to Screen 3 (VPD Fee Calculator).
  Screenshot: `design-refs/height-reference.png` (drop your own screenshot here)

- **Notion**: Borrow the draft/published state chip pattern. Draft records display a gray pill label; published records display a green pill label. Both are visible inline in list views so analysts can scan status without opening a record. Apply this to the SKU queue on Screen 1.
  Screenshot: `design-refs/notion-reference.png` (drop your own screenshot here)

- **Monday**: Borrow the grouped board/queue view with count badges. SKUs are grouped by status (Needs Pricing, In Progress, Needs Review, Published), each group shows a count, and rows are scannable at a glance. Apply this to the unpriced SKU queue on Screen 1.
  Screenshot: `design-refs/monday-reference.png` (drop your own screenshot here)

## Explicit avoid-list

- No gradients
- No purple defaults (Shadcn default palette)
- No emoji empty states
- No shadcn default component styling without customization
- No Lorem ipsum in any UI state

## UI-state rules

- No loading skeletons — every screen loads with seeded data visible immediately
- No empty states — the prototype must always show the fixtures data by default
- One-click login — no auth form required for the prototype
