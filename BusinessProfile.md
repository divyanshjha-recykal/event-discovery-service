# Retearn Business Profile

## How to use this document

Facts below are stated directly. Where a field is genuinely unknown, it's marked **Not disclosed** or **Unknown**, treat that as `unclear`, not as a negative. Figures in lakh/crore are as reported internally; do not round or convert unless the criterion requires it.

## About Retearn

Retearn Technologies Private Limited builds AI-powered reverse vending machines (RVMs) and Deposit Return System (DRS) infrastructure. Product line: **Reklaim PRO, ACE, Mini, Neo, FastScan**. Devices identify and sort PET, HDPE, LDPE, MLP, glass, and metal cans using edge AI, running fully offline on NVIDIA Jetson hardware, and pay users an instant UPI refund on deposit. Deployed across India, Bhutan, Mauritius, and the UK. Operates within the Recykal group.

## Identity

- Legal entity: **Retearn Technologies Private Limited**
- Incorporated: **2024**, India
- HQ: Gachibowli, Hyderabad, Telangana
- Website: retearn.in
- Nominated product: AI-Enabled Waste Collection & Recovery System — Reklaim Line
- First commercial launch of the nominated product: **2024**
- Relationship to Recykal: operates within the Recykal group; own legal entity and own financials, distinct from Recykal's (Rapidue Technologies Pvt. Ltd.)
- Named leadership: **Not disclosed** in current records; do not assume Recykal's leadership applies to Retearn without confirmation

## Scale and financial standing

- Employees on payroll: **38** (as of April 2026)
- FY 2024–25 standalone revenue: **₹0.21 crore**
- FY 2025–26 standalone revenue: **₹4.76 crore** (≈22x year-on-year growth)
- FY 2025–26 ARR attributable to Reklaim: **₹4.76 crore** (i.e. effectively all revenue)
- Revenue from AI products: **99%** of total
- R&D / AI innovation spend: **80%** of FY 2025–26 revenue
- Funding stage: **Bootstrapped**
- MSME/Udyam registration, DPIIT recognition: **Not disclosed**

Job creation and workforce figures elsewhere in this profile (110+ jobs, 12,000+ informal workers onboarded, a 5-member on-ground team at Kedarnath) refer to livelihoods enabled through deployments, not Retearn's own payroll. Don't conflate the two on a headcount criterion.

## Sector and business model

- Sector: reverse vending hardware and Deposit Return System infrastructure, circular economy / waste-tech
- Materials handled: PET, HDPE, LDPE, MLP, glass, metal cans
- Business model: device sales/leasing, software and platform subscriptions, operations & maintenance services, DRS transaction/service fees, EPR and traceability solutions for brands, recovered-material value
- Customers: B2B (brands, retailers, MRFs/ULBs) and B2G (municipal and state DRS programmes)
- Platform integration: real-time traceability via CircularNet, from collection through recycling

## Operational scale in India(PRIMARY BUSINESS Region)

- **Char Dham circuit** (Kedarnath, Gangotri, Yamunotri, Badrinath): 30 lakh+ bottles collected and recycled across 105 collection points, impacting 16.5 lakh+ people along the 33 km Guptkashi–Kedarnath corridor
- **Kedarnath dDRS pilot**: 1.63 lakh bottles prevented from entering Himalayan water bodies, 7.5 lakh bottles sent for recycling, 90% recycling rate, 9 sq km landfill space saved, 250+ MT coal saved, 38+ MT CO2e saved
- Kedarnath context: ~10,000 kg waste generated daily during the Char Dham yatra against an influx of 10+ lakh pilgrims
- Material contamination at deployment sites reduced from ~15% to **<1%**
- FY 2025–26: 3.91 lakh plastic bottles collected via the ₹10 deposit-refund model
- Collection rate: 12,36,450 QR codes issued vs 11,43,772 claimed, **93%** overall (Apr 2025–Mar 2026)
- Collection-rate trend: **52%** (2022–23 pilot) → **92%** (2025–26)
- **Pune MRF**: 10+ tonnes/day processed via AI-enabled sorting
- **Goa DRS**: statewide rollout, 191 panchayats and 14 ULBs installing RVMs ahead of launch
- **Chennai**: pilot under TASMAC
- **Uttarakhand**: Deposit Refund System Experience Zones live in Bhimtal, Haldwani, Haridwar, Nainital
- Named active deployment: Goa DRS; other markets listed under Primary Markets below

## International operations(Secondary)

- **Bhutan**: national-scale deployment. Gelephu Mindfulness City — 26 lakh+ bottles collected. Phuentsholing — 1.25 lakh+ bottles collected. Population participation exceeding **75%**. Refunds integrated with the Bank of Bhutan.
- **Mauritius**: listed as a primary market served. No deployment-level figures disclosed.
- **UK**: listed as a primary market served. No deployment-level figures disclosed.
- Primary markets, as stated internally: India (Goa, Uttarakhand, Tamil Nadu, Himachal Pradesh, and other states), Bhutan, Mauritius, UK

## Technology

- Hardware: Reklaim PRO, ACE, Mini, Neo, FastScan, modular form factor from 1 sq ft to 40 sq ft
- Compute: on-device edge AI on NVIDIA Jetson modules (Nano/Orin/Xavier), no dependency on cloud connectivity for recognition
- Model: CNN plus attention/transformer architecture, 5-level taxonomy (material → form → rigidity → condition → brand), built with Google under a Responsible AI framework
- Sensing: fused RGB, Time-of-Flight depth, and NIR imaging with QR and telemetry data
- Training data: 2M+ labeled waste images across 50+ Indian locations, covering crushed, wet, dirty, and label-removed items
- Performance: >90% material detection accuracy across 200+ classes, ~60% contamination reduction, <20ms edge inference latency (raw model), <120ms for full on-device recognition + contamination detection + validation cycle
- Model size: 60% smaller via quantization, deployed via TensorRT
- Environmental resilience: solar-ready, operates -10°C to 60°C, proven at 11,750 ft altitude (Char Dham)
- Language support: 5 Indian languages/dialects, configurable per deployment — English, Hindi, Telugu, Tamil, Marathi. Audio prompts, icons, and minimal-text UI for low-literacy users.
- Fraud prevention: multi-factor verification, secure cloud telemetry, full audit trails
- Patents: **1 granted** — "A Method and System for Automated Waste Counting, Identification, Classification, and Sorting with Artificial Intelligence," Indian Patent Office, granted **June 17, 2026**. **5 additional patents published** (not yet granted per current records).

### Competitive position (as stated internally, vs named competitors)


| Feature              | Retearn                                         | TOMRA (Norway)                   | Envipco (Netherlands)        |
| -------------------- | ----------------------------------------------- | -------------------------------- | ---------------------------- |
| Material recognition | 200+ classes                                    | 3 classes                        | 1–3 standardized types       |
| Infrastructure need  | Offline, solar-ready, -10°C to 60°C             | Stable power + internet required | Controlled environment only  |
| DRS dependency       | Works with or without DRS (92% collection)      | Requires mature DRS              | DRS-dependent only           |
| Package handling     | Damaged, crushed, contaminated accepted         | Pristine bottles only            | Standardized containers only |
| Informal sector      | Integrates and empowers (37.5% income increase) | Replaces workers                 | No integration               |
| Form factor          | Modular, 1–40 sq ft                             | Fixed 200+ sq ft                 | Fixed 100–200 sq ft          |
| Cost per unit        | ~1/10th of listed competitor cost               | $50K–$150K                       | $40K–$100K                   |


## Certifications and regulatory standing

- ISO 14001:2015 (environmental management)
- ISO 9001:2015 (quality management)
- ISO 45001:2018 (occupational health and safety)
- ISO/IEC 27001:2022 (information security)
- ISO/IEC 27701:2019 (privacy information management)
- EMI/EMC compliance for devices
- DPDP Act (India) alignment claimed: data minimisation, purpose limitation, controlled retention, applicable user-data rights. This is a stated alignment, not a third-party certification.
- CPCB EPR registration: **Not disclosed** for Retearn specifically

## Sustainability and environmental impact

- 38+ MT CO2e saved, 250+ MT coal saved, 9 sq km landfill space saved — Kedarnath dDRS pilot specifically
- 90% recycling rate at Kedarnath; contamination reduced from ~15% to <1% across deployment sites
- 30 lakh+ bottles collected and recycled across the full Char Dham circuit
- Figures above are internally reported; no independent third-party audit of these figures is on record

## Social impact

- 12,000+ informal waste workers digitally onboarded with transparent, traceable payment systems
- 110+ jobs and new income streams created for pithuwalas, retailers, and waste workers at Kedarnath
- 5-member all-women team leading on-ground collection and awareness at Kedarnath
- 37.5% income increase for informal-sector workers integrated into the system (stated in competitive comparison vs TOMRA/Envipco)
- Job creation stated as 10x versus traditional waste-management methods

## Recognition history

- Nasscom AI Game Changers Award 2024, "for pioneering circular technology" — stated on Retearn's own site; not independently verified in outside coverage
- An internal nomination deck covering FY 2025–26 data and AI for Bharat / Social Impact AI categories exists, confirming Retearn actively prepares detailed award submissions; this is evidence of nomination activity, not confirmation of a specific win beyond the 2024 claim above
- Recykal's own recognition history (NASSCOM Emerge 50, Digital India Awards for the Kedarnath DRS work, Fortune Change the World) remains relevant background given Retearn's role in that same Kedarnath project, but is Recykal's recognition, not Retearn's

## Known exclusions

- Not focused on beneficiary/welfare schemes: explicitly not built around PMJAY, PM-KISAN, Ayushman Bharat, or DigiLocker integration. Government integration is limited to waste-management, EPR, and DRS ecosystems via APIs and CircularNet.
- AI is object-centric, not person-centric: no gender, caste, religion, ethnicity, or facial-recognition data used in device decision-making
- No prior disqualifications from any award or programme are on record

## Standard descriptions

- One-sentence description: "Retearn builds AI-powered reverse vending machines and Deposit Return System infrastructure, deployed across India, Bhutan, Mauritius, and the UK, running fully offline on edge AI hardware to identify, sort, and refund recyclable materials in real time."

---

