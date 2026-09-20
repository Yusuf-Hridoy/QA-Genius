# Fixtures — the Aurora Storefront data set

All demo data in this app lives in one fictional universe: **Aurora Storefront**, an
e-commerce web app (Next.js front end, Node API, Postgres), Jira project key `AUR`,
staging URL `https://staging.aurora-shop.dev`. Personas: shopper, admin, support agent.

Every generator has:

- `input-1.json` / `input-2.json` — valid request bodies; the UI's **Load example**
  button fills the form from `input-1.json`.
- `sample-output.json` — a valid output object (parses against the kind's Zod schema),
  used by tests and by the e2e stream mocks.

These are demo data only; do not reference real companies or products.
