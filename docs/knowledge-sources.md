# RESQIVO — Knowledge Sources (Task 4.1)

**Verification date:** 2026-10-21
**Machine-readable manifest:** `knowledge/seed/sources.json` (metadata only; no documents are stored in the repository)

RESQIVO's knowledge base supports simulated planning and education. These documents are general guidance; they do not replace local emergency services or official instructions issued during a real emergency.

## 1. Summary

Ten candidate documents were identified from the three approved publishers, and one further candidate was considered and excluded.

| Status | Count | Meaning |
|---|---|---|
| **VERIFIED** | 8 | The document's official URL was fetched on 2026-10-21 and returned a PDF (HTTP 200, `%PDF` header). Title and date were taken from the publisher's own page. For WHO-02 only access is verified, not its licence. |
| **PARTIALLY VERIFIED** | 2 | The official publication page appears in search results on the publisher's domain, but direct access was blocked (HTTP 403 bot protection). The document itself was not opened. |
| **EXCLUDED** | 1 | Verified, but its scope does not fit RESQIVO. |

Being able to **read** a document is not the same as being allowed to **redistribute or embed** it. Only one document currently has verified terms that permit non-commercial redistribution and adaptation.

| Reuse status | Documents |
|---|---|
| Open licence verified (CC BY-NC-SA 3.0 IGO) | WHO-01 |
| Publisher policy suggests an open licence; not confirmed for the specific document | WHO-02, UNDRR-01, UNDRR-02 |
| Written permission required before reuse | NDMA-01 to NDMA-06 |

This is a factual record of the published terms, not legal advice.

## 2. How Sources Were Verified

- **Discovery:** web searches restricted to `ndma.gov.in`, `who.int`, `iris.who.int`, `undrr.org` and `preventionweb.net` (UNDRR's knowledge platform).
- **Existence and access:** each document URL was requested directly. Verified documents returned HTTP 200 with `application/pdf` content and a `%PDF-` header. Files were not kept.
- **Titles and dates:** taken from the publisher's own listing or publication page, not from search summaries.
- **Terms:** read from each publisher's copyright, terms-of-use or website-policy page, and from the publication page where it shows a licence.

**NDMA site note:** NDMA has restructured its website. The document URLs returned by search engines (for example under `/images/guidelines/`) now return HTTP 404. The URLs below are taken from NDMA's current English guidelines listing (`https://ndma.gov.in/en/ndma-guidelines`) and plan page (`https://ndma.gov.in/en/nationalstate-dm-plan`). Requests to unprefixed paths such as `/ndma-guidelines` are served in Hindi.

## 3. Publisher Terms

### NDMA India

Source: `https://ndma.gov.in/website-policy` and `https://ndma.gov.in/terms-use`, read 2026-10-21.

- Website policy, Copyright Policy (Clause 5.1.4): *"All content available on this website, including text, graphics, logos, images, documents, and other material, is the property of NDMA unless otherwise stated. Reproduction, reuse, modification, distribution, or republication of the content in any form is strictly prohibited without prior written permission from the competent authority."*
- Terms of use: *"Material featured on this Directory may be reproduced free of charge after taking proper permission by sending a mail to us. However, the material has to be reproduced accurately and not to be used in a derogatory manner or in a misleading context. Wherever the material is being published or issued to others, the source must be prominently acknowledged."*

**Consequence:** NDMA documents are freely accessible to read. Copying their text into a knowledge base requires NDMA's prior written permission. None has been requested or granted.

### WHO

Source: `https://www.who.int/about/policies/publishing/copyright`, read 2026-10-21.

- WHO publications are under **CC BY-NC-SA 3.0 IGO**. Under this licence, users may *"freely copy, reproduce, reprint, distribute, translate and adapt the work for non-commercial purposes"*.
- *"Permission from WHO is not required for the use of WHO materials issued under"* this licence. *"Permission is required for commercial uses and licensing of WHO materials."*
- The page does not say how the policy applies to older publications. Third-party figures, tables, maps or photos inside a document may need separate permission.

### UNDRR

Direct access to `undrr.org` and `preventionweb.net` returned HTTP 403 on 2026-10-21, so UNDRR's terms page could not be read. Search results for UNDRR's own pages (UNVERIFIED, not opened) indicate:

- Recent UNDRR publications state a CC BY-NC 3.0 IGO licence.
- Some older publications carry "All rights reserved" with permission to quote with acknowledgement.
- The website terms (`http://www.undrr.org/terms-and-conditions-use-undrrorg`) reportedly allow personal, non-commercial use without the right to redistribute or create derivative works, unless an item states otherwise.

**Consequence:** each UNDRR document's own licence must be checked in a browser before use.

## 4. Documents

### NDMA-01 — National Disaster Management Plan 2019

| Field | Value |
|---|---|
| Publisher | National Disaster Management Authority, Government of India |
| Official URL | https://ndma.gov.in/sites/default/files/PDF/ndmp-2019.pdf |
| Listing page | https://ndma.gov.in/en/nationalstate-dm-plan ("National Disaster Management Plan 2019 – English – PDF, 19.8 MB") |
| Date / version | 2019 (exact month not shown on the listing) |
| Topics | Multi-hazard preparedness and response; roles and responsibilities; coordination across government levels |
| Intended use | Grounding answers on national response structure and responsibilities |
| Reuse | Prior written permission from NDMA required |
| Verification | VERIFIED 2026-10-21: HTTP 200, PDF, 20,743,176 bytes |

### NDMA-02 — Guidelines on Incident Response System

| Field | Value |
|---|---|
| Publisher | National Disaster Management Authority, Government of India |
| Official URL | https://ndma.gov.in/sites/default/files/PDF/Guidelines/incidentresponsesystemjuly.pdf |
| Listing page | https://ndma.gov.in/en/ndma-guidelines (item 31) |
| Date / version | July 2010 |
| Topics | Incident management, command structure, operations, planning and logistics functions |
| Intended use | Coordination and incident-management guidance for plan explanations |
| Reuse | Prior written permission from NDMA required |
| Verification | VERIFIED 2026-10-21: HTTP 200, PDF, 9,401,764 bytes |

### NDMA-03 — Guidelines on Minimum Standards of Relief

| Field | Value |
|---|---|
| Publisher | National Disaster Management Authority, Government of India |
| Official URL | https://ndma.gov.in/sites/default/files/PDF/Guidelines/guideline-on-minimum-standard-of-relief.pdf |
| Listing page | https://ndma.gov.in/en/ndma-guidelines (item 21) |
| Date / version | February 2016 |
| Topics | Relief camps and shelter, food, water, sanitation, medical cover |
| Intended use | Shelter and resource-allocation guidance; the most directly relevant NDMA document for RESQIVO's planning domain |
| Reuse | Prior written permission from NDMA required |
| Verification | VERIFIED 2026-10-21: HTTP 200, PDF, 3,143,566 bytes |

### NDMA-04 — Guidelines on Management of Floods

| Field | Value |
|---|---|
| Publisher | National Disaster Management Authority, Government of India |
| Official URL | https://ndma.gov.in/sites/default/files/PDF/Guidelines/flood.pdf |
| Listing page | https://ndma.gov.in/en/ndma-guidelines (item 37) |
| Date / version | January 2008 |
| Topics | Flood preparedness, response and evacuation |
| Intended use | Hazard-specific guidance for the flood scenarios already used in RESQIVO's sample plans |
| Reuse | Prior written permission from NDMA required |
| Verification | VERIFIED 2026-10-21: HTTP 200, PDF, 6,120,219 bytes |

### NDMA-05 — Guidelines on Management of Cyclones

| Field | Value |
|---|---|
| Publisher | National Disaster Management Authority, Government of India |
| Official URL | https://ndma.gov.in/sites/default/files/PDF/Guidelines/cyclones.pdf |
| Listing page | https://ndma.gov.in/en/ndma-guidelines (item 36) |
| Date / version | April 2008 |
| Topics | Cyclone preparedness, warning, evacuation and shelters |
| Intended use | Hazard-specific guidance for cyclone scenarios |
| Reuse | Prior written permission from NDMA required |
| Verification | VERIFIED 2026-10-21: HTTP 200, PDF, 4,744,510 bytes |

### NDMA-06 — Guidelines on Management of Urban Flooding

| Field | Value |
|---|---|
| Publisher | National Disaster Management Authority, Government of India |
| Official URL | https://ndma.gov.in/sites/default/files/PDF/Guidelines/management_urban_flooding.pdf |
| Listing page | https://ndma.gov.in/en/ndma-guidelines (item 28) |
| Date / version | September 2010 |
| Topics | Urban flood preparedness and response |
| Intended use | Optional; urban flood scenarios |
| Reuse | Prior written permission from NDMA required |
| Verification | VERIFIED 2026-10-21: HTTP 200, PDF, 15,046,313 bytes |

### WHO-01 — Health Emergency and Disaster Risk Management Framework

| Field | Value |
|---|---|
| Publisher | World Health Organization |
| Official URL | https://iris.who.int/server/api/core/bitstreams/219a1a08-9ec5-4f2d-9aff-54c713fcfa7c/content |
| Publication page | https://www.who.int/publications/i/item/9789241516181 |
| Date / version | 30 July 2019; 31 pages; ISBN 9789241516181 |
| Topics | Public health in emergencies; health disaster risk management across prevention, preparedness, response and recovery; planning and coordination; logistics |
| Intended use | Public-health and coordination guidance; the first document recommended for indexing |
| Reuse | CC BY-NC-SA 3.0 IGO, shown on the publication page: non-commercial redistribution and adaptation without permission, with attribution and share-alike |
| Verification | VERIFIED 2026-10-21: HTTP 200, PDF, 1,688,353 bytes; licence shown on the publication page |

### WHO-02 — Technical Note 9: How much water is needed in emergencies

| Field | Value |
|---|---|
| Publisher | World Health Organization (series prepared with WEDC, per the WHO page heading "Updated WHO/WEDC Technical Notes on WASH in Emergencies") |
| Official URL | https://cdn.who.int/media/docs/default-source/wash-documents/who-tn-09-how-much-water-is-needed.pdf |
| Series page | https://www.who.int/teams/environment-climate-change-and-health/water-sanitation-and-health/environmental-health-in-emergencies/technical-notes-on-wash-in-emergencies |
| Date / version | Series "originally prepared in 2011 and updated in 2013" (WHO series page) |
| Topics | Water quantity requirements in emergencies; public health |
| Intended use | Grounding drinking-water allocation explanations |
| Reuse | **UNVERIFIED.** The series page shows no licence. The PDF has no extractable text layer, so its own copyright statement could not be read. WHO's general policy applies CC BY-NC-SA 3.0 IGO to WHO publications, but its application to this 2011/2013 note was not confirmed. |
| Verification | VERIFIED access 2026-10-21: HTTP 200, PDF, 895,946 bytes. Text content not verified (the PDF appears to be graphics-based). |

**Note:** because this PDF has no text layer, a standard text-extraction pipeline will likely produce no usable text. It may need manual transcription or another source for the same figures.

### UNDRR-01 — Sendai Framework for Disaster Risk Reduction 2015–2030

| Field | Value |
|---|---|
| Publisher | United Nations Office for Disaster Risk Reduction |
| Official URL | https://www.undrr.org/publication/sendai-framework-disaster-risk-reduction-2015-2030 (publication page; PDF URL not confirmed) |
| Date / version | 2015 (adopted 18 March 2015, per search results; not opened) |
| Topics | Disaster risk reduction priorities, preparedness, "Build Back Better" |
| Intended use | Framing for disaster risk reduction and preparedness concepts |
| Reuse | **UNVERIFIED** (see section 3) |
| Verification | **PARTIALLY VERIFIED** 2026-10-21. The page appears in search results on `undrr.org`. Direct requests to the page and to a PreventionWeb PDF copy returned HTTP 403 or a bot-challenge page. Not opened. |

### UNDRR-02 — Words into Action: Enhancing Disaster Preparedness for Effective Response

| Field | Value |
|---|---|
| Publisher | United Nations Office for Disaster Risk Reduction |
| Official URL | https://www.undrr.org/enhancing-disaster-preparedness-effective-response |
| PDF link shown on that page | https://www.undrr.org/media/43008/download (returned HTTP 403 to a direct request) |
| Date / version | 2020 ("This 2020 Words into Action guide", read from the UNDRR page on 2026-10-21) |
| Topics | Preparedness planning, early warning, response capacity, coordination |
| Intended use | Practical preparedness and response-planning guidance |
| Reuse | **UNVERIFIED.** No licence statement was shown on the page. |
| Verification | **PARTIALLY VERIFIED** 2026-10-21. The landing page was read once through a web reader (title, year and PDF link); later requests returned HTTP 403. The PDF was not opened. |

### Considered and excluded

| Document | Reason |
|---|---|
| WHO Emergency Response Framework (ERF), Edition 2.1, 12 February 2024, ISBN 978-92-4-005806-4, CC BY-NC-SA 3.0 IGO (https://www.who.int/publications/i/item/9789240058064) | It describes WHO's internal procedures for its own staff ("provides WHO staff with essential guidance"), not guidance for emergency planners. |

## 5. Topic Coverage

| Topic | Documents |
|---|---|
| Disaster preparedness and response | NDMA-01, NDMA-04, NDMA-05, UNDRR-02 |
| Emergency coordination and incident management | NDMA-02, NDMA-01, WHO-01 |
| Evacuation and shelter planning | NDMA-03, NDMA-04, NDMA-05 |
| Emergency resource allocation | NDMA-03, WHO-02 |
| Public health during disasters | WHO-01, WHO-02, NDMA-03 |
| Disaster risk reduction | UNDRR-01, UNDRR-02, WHO-01 |

## 6. Recommended Initial Knowledge-Base Scope

1. **Index first: WHO-01 only.** It is the only document with verified terms permitting non-commercial redistribution and adaptation. Attribution and share-alike apply.
2. **Request permission from NDMA** for NDMA-01 to NDMA-06, following its terms of use (email request). NDMA-03, NDMA-02 and NDMA-04 are the most valuable for RESQIVO's shelter, coordination and flood scenarios. Do not index NDMA documents until written permission is received and recorded.
3. **Confirm in a browser** the licences of WHO-02, UNDRR-01 and UNDRR-02, record them in the manifest, then add them if their terms permit.
4. **Do not commit any source documents or the generated index.** Store downloaded files and the ChromaDB index outside version control (`plan.md` section 2).
5. **Retrieval tests (Task 4.2) should use small synthetic text fixtures,** not publisher documents. They then do not depend on these permissions.

With WHO-01 alone, the knowledge base covers public health and coordination, but not shelter standards, evacuation or hazard-specific guidance. Those depend mainly on the NDMA permission request.

## 7. Open Questions

- NDMA permission for knowledge-base use: not yet requested.
- Licences for WHO-02, UNDRR-01 and UNDRR-02: not confirmed.
- UNDRR documents: not opened, because automated access was blocked.
- WHO-02: no text layer; usable text needs another approach.
- Whether NDMA documents carry third-party material with separate copyright: not checked.
