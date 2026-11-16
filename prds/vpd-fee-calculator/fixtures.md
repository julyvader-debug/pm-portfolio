# Prototype Fixtures

Seeded data for the prototype. Every screen must show this data by default — no empty states.

## SKU Queue (Screen 1 — Unpriced SKU List)

| SKU ID    | Product Name                                | Status        | Assigned To | Last Updated  |
|-----------|---------------------------------------------|---------------|-------------|---------------|
| RX-20387  | Simparica Trio 5.6–11 lbs — 6 pack          | Needs Pricing | A. Rivera   | 2026-05-01    |
| RX-10042  | Atenolol 25mg Tablets — 30 count            | Needs Pricing | D. Chen     | 2026-05-02    |
| RX-30094  | Carprofen 75mg Chewable Tablets — 30 count  | In Progress   | A. Rivera   | 2026-05-05    |
| RX-40221  | Metronidazole 250mg Tablets — 60 count      | In Progress   | D. Chen     | 2026-05-06    |
| RX-55018  | Adequan Canine Injectable 100mg/mL          | Needs Review  | A. Rivera   | 2026-04-15    |
| RX-61703  | Advantage II for Dogs 3–10 lbs — 4 pack     | Published     | D. Chen     | 2026-04-20    |

Status definitions for the prototype:
- **Needs Pricing** — no fee set; new SKU or manufacturer price was reset
- **In Progress** — fee entry started and saved as draft; not yet published
- **Needs Review** — fee was published but acquisition cost changed after a manufacturer price import; requires analyst re-approval
- **Published** — fee is live and current

## SKU Detail (Screen 2 — used for RX-30094 as the demo flow)

| Field                  | Value                                         |
|------------------------|-----------------------------------------------|
| SKU ID                 | RX-30094                                      |
| Product Name           | Carprofen 75mg Chewable Tablets — 30 count    |
| NDC                    | 10177-0094-30                                 |
| Manufacturer           | Putney Inc.                                   |
| Units per Package      | 30                                            |
| Acquisition Cost       | $42.00                                        |
| Parent SKU             | RX-30001 (Carprofen 75mg Chewable — 60 count) |
| Parent MAP Price       | $55.00                                        |
| Current Fee Type       | None (draft in progress)                      |

## Calculator Output Preview (Screen 3 — pre-filled state for RX-30094)

| Field                  | Value                 |
|------------------------|-----------------------|
| Unit Cost              | $1.4000               |
| MAP per Unit           | $0.9167               |
| Fee Type (suggested)   | Percentage            |
| Fee Value (suggested)  | 12%                   |
| Fee Applied            | $0.1680               |
| Wholesale Price        | $1.5680               |
| Price at 1 unit        | $1.5680               |
| Price at 30 units      | $47.0400              |
| Price at 90 units      | $141.1200             |
| Anomaly Flags          | None                  |

## Audit Record (Screen 5 — confirmation after publish)

| Field              | Value                                          |
|--------------------|------------------------------------------------|
| Published By       | A. Rivera                                      |
| Fee Formula        | Percentage 12% of unit cost                    |
| Acquisition Cost   | $42.00 at time of publish                      |
| Previous Fee       | None (first-time pricing)                      |
| Timestamp          | 2026-05-07 14:32:11 UTC                        |

## Data sourcing notes

- Product names (Simparica Trio, Adequan, Carprofen, Atenolol, Metronidazole, Advantage II) are representative of the product categories discussed with the pricing team.
- SKU IDs (RX-XXXXX format), NDC number, and exact acquisition costs are generated placeholders. All prices are illustrative.
- Owner names are fictional placeholders.
- Timestamps are plausible relative to today (2026-05-07) but generated.
