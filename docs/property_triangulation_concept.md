# Property Record Monitoring — Concept Sketch

Working name: **Deedwatch** (placeholder). One-line pitch: *credit monitoring, but for
property records.* You verify who you are, and the service watches the public record and
tells you when something about you or your assets changes or becomes visible.

This is the defensible inversion of the original idea ("triangulate other people's hidden
property"). Same data, same plumbing, pointed at the user's own identity instead of at a
third party. That flip is what makes it legal to build, sellable in app stores, and —
usefully — it also *solves the hardest technical problem* (entity resolution) instead of
fighting it.

---

## 1. Why the self-monitoring framing wins

**Legally.** A tool marketed for checking up on a spouse or partner is surveillance of a
specific person: it drifts into stalkerware territory, gets rejected by app stores, and
attracts FCRA/state-privacy liability. A tool that shows *you* what the public record says
about *you* is squarely legitimate — the same category as credit monitoring, identity
theft protection, and Google Alerts on your own name.

**Technically.** The killer problem in third-party property search is entity resolution:
deeds carry bare names, "Michael Johnson" isn't unique, and you can never be sure a parcel
belongs to the specific human you meant. Self-monitoring dissolves this: the user hands
you the disambiguators voluntarily — full legal name and variants, DOB, current and prior
addresses, known LLCs/trusts they control. You go from guessing identity to *verifying*
it once, then matching against a rich anchor profile forever after.

**The LLC problem inverts too.** Third-party search misses exactly the properties people
hide behind LLCs and trusts. In self-monitoring, users *register their own* entities
("watch my name, plus Blue Harbor LLC, plus the Johnson Family Trust") — the feature that
defeats the surveillance product is just a settings screen in this one.

## 2. Who actually pays for this

1. **Title/deed fraud watch.** Deed theft (someone records a forged deed transferring your
   home) is a real, growing crime; FBI IC3 tracks it. Incumbent "Home Title Lock"-style
   products are widely criticized as overpriced alarm-selling — there's room for an honest,
   cheaper, better-explained version. This is the anchor use case.
2. **"What's public about me" awareness.** Exactly the moment that sparked this idea:
   you're closing on a house Friday and the purchase becomes public record — price, name,
   address, mortgage amount. An alert that says *"here is what just became visible, here's
   who indexes it, here's how to request redaction where your state allows it"* has obvious
   value for people going through separations, domestic-violence survivors (many states
   have address-confidentiality programs), judges/LEOs (Daniel's Law-type statutes),
   executives, and the merely private.
3. **Surprise liens and encumbrances.** Mechanic's liens, HOA liens, tax liens, HELOCs you
   forgot — recorded against your parcel without a notification path today.
4. **Authorized third-party discovery** (later, B2B): divorce attorneys and estate
   attorneys running asset discovery *with legal authority* (subpoena power, fiduciary
   duty). Same engine, gated behind verified professional accounts and an attestation of
   authority. This is where the original "find the hidden house" demand actually lives
   legitimately — discovery in litigation — and it's a real market (family-law tooling).

## 3. Data layer

Don't scrape 3,000 counties yourself on day one. Tiered approach:

- **Tier 1 (buy):** license a national parcel/deed feed — ATTOM, CoreLogic, First
  American DataTree, Regrid. Gets recorder documents (deeds, mortgages, liens, releases)
  plus assessor rolls. Expensive but instant coverage; fine for a funded build, too
  expensive for a nights-and-weekends MVP.
- **Tier 2 (scrape/pull):** many counties expose free recorder search portals and some
  states publish bulk data (e.g. Florida counties, NYC ACRIS is fully open). An MVP can
  cover a handful of open-data counties end-to-end for ~free.
- **Tier 3 (crowd/direct):** county-by-county FOIA/bulk-purchase of recorder indexes;
  slow, but each county acquired is a moat.

Refresh cadence matters more than depth: the product is a *diff alert*, so daily/weekly
polling of the recorder index for watched names/parcels is the core loop — you don't need
full history to start.

## 4. Architecture sketch

```
county feeds / vendor API
        │  ingest (per-source adapters, raw docs archived)
        ▼
  normalize (doc type, party names, parcel IDs/APN, legal description, amounts, dates)
        │
        ▼
  identity graph ──── user anchor profiles (verified identity + registered entities)
        │                    │
        ▼                    ▼
  match engine: score(record_party, anchor) →  {exact, strong, weak}
        │
        ▼
  diff/alert service ── "new deed recorded", "new lien", "your sale is now public",
        │               "a strong name-match appeared 2 counties over — is this you?"
        ▼
  app/email/push  +  guidance content (redaction requests, fraud response playbook)
```

Key design points:

- **Verification at signup** (KYC-lite: ID doc or knowledge-based auth) is what keeps this
  a self-monitoring product rather than a people-search product. You cannot watch a name
  you haven't verified as yours or attested authority over (professional tier).
- **Match scoring, not binary matching.** Name + prior-address + entity-registry signals
  produce a confidence score; low-confidence matches surface as *questions to the user*
  ("is this you?"), and their answer trains the anchor profile. The user is the oracle —
  this is the cheat code third-party search never gets.
- **Raw document archival** from day one; normalization improves over time and you'll want
  to re-run it.

## 5. Legal guardrails (design constraints, not afterthoughts)

- **Do not become a consumer reporting agency.** The moment output is used for credit,
  employment, tenancy, or insurance decisions, FCRA applies with heavy obligations.
  Self-monitoring output shown only to the data subject stays outside FCRA; the
  professional tier needs explicit non-FCRA-use attestations (how ATTOM etc. license).
- **No general people-search.** Never expose search-by-arbitrary-name to consumers. This
  single product decision is the difference between "monitoring service" and "data broker"
  under CCPA/state broker-registration laws — and between app-store approval and a ban.
- **State privacy/redaction statutes are a feature, not a compliance burden:** build the
  redaction-request workflows (address confidentiality programs, Daniel's Law analogues)
  as product surface.
- **Vendor license terms** (ATTOM/CoreLogic) already prohibit stalking/harassment use;
  the self-monitoring design makes compliance structural rather than policy-based.

## 6. MVP cut

1. Pick 2–3 open-data counties (e.g. NYC via ACRIS + one or two Florida counties).
2. Signup: verify identity, collect name variants + prior addresses + owned entities +
   parcels you already own (geocode/APN lookup).
3. Nightly poll of recorder indexes for watched names/parcels; diff; alert by email.
4. Two alert playbooks written well: "a document was recorded against your property"
   (fraud-response steps) and "your transaction is now public" (what's visible, to whom,
   redaction options).
5. Subscription pricing comparable to credit monitoring (~$5–10/mo), undercutting the
   $200/yr title-lock incumbents.

Deliberately **not** in the MVP: national coverage, the professional/attorney tier,
any third-party search, LLC beneficial-ownership inference.

## 7. Honest risks

- **Coverage gaps read as product failure.** A user in an uncovered county gets nothing;
  a missed recording in a covered county is worse than no product. Ship county-level
  coverage transparency ("we watch these 3 counties, updated nightly") from day one.
- **Incumbent smear.** Title-lock products have poisoned the well with fear-marketing;
  differentiation is honesty about what recording fraud actually is (rare, recoverable,
  but miserable) — which is a marketing constraint as much as a copy choice.
- **The pull toward the dark version.** Every growth conversation will rediscover
  "let people search anyone." The verification gate is the product's spine; removing it
  converts the company into a data broker with all the liability sketched above.
