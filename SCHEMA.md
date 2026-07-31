# Karmika Portal — Database Schema

Designed from the TBOCWWB sample data (Workers + Schemes sheets).

## Entity-Relationship overview

```
Scheme (1) ──< SubScheme (many)
Worker (1) ──< Application (many) >── (1) SubScheme
```

## Tables

### Worker  (from workers_clean.csv)
| Column | Type | Notes |
|---|---|---|
| reg_no | varchar, UNIQUE | e.g. KP/2026/00001 (auto-generated) |
| temp_id, alo_code | varchar | source-system identifiers |
| reg_year, reg_date | int, date | reg_date converted from Excel serials |
| worker_name / father_name | varchar | + Telugu variants (worker_name_telugu…) |
| gender | enum | decoded from 1/2 → Male/Female |
| date_of_birth, age | date, int | 36/42 source rows had missing DOB |
| caste_code, trade_code, district_code | varchar | numeric codes kept as-is (no legend in source) |
| bank_code, ifsc_code, ifsc_valid | varchar, bool | IFSC validated against ^[A-Z]{4}0[A-Z0-9]{6}$ |
| trade_union_member, migrant_worker | bool | |
| is_test_row, age_flag | bool | data-quality flags from the cleaning pipeline |

### Scheme  (7 rows, from schemes_clean.csv)
code (unique int), description, scheme_type

### SubScheme  (26 rows, from subschemes_clean.csv)
FK scheme → Scheme, code, description, required_fields
(required_fields = pipe-separated list parsed from the source's "n"=>"label" format)

### Application  (created by users / seeded demo)
app_no (unique, KPA-YYYY-NNNNN), FK worker, FK subscheme,
applicant_name, relationship, phone, bank_account, details,
status ∈ {SUBMITTED, UNDER_REVIEW, APPROVED, REJECTED}, remarks, submitted_at

Status transitions are managed through the Django admin (/admin/).


## Phase 2 additions

```
District (1) ──< Mandal (1) ──< Village          [geographic master]
ALOCircle                                          [administrative master]
Worker ──> Village, ALOCircle                      [links to masters]
Worker (1) ──< Nominee                             [dependents]
Worker (1) ──< Renewal                             [5-year validity extensions]
Worker (1) ──< ChangeRequest                       [name/nominee/bank corrections]
Application (1) ──< DBTPayment >── (1) DBTBatch    [Direct Benefit Transfer]
DBTPayment.retry_of ──> DBTPayment                 [failed-transaction retries]
```

### New tables
- **District / Mandal / Village** — Telangana geographic hierarchy (master data)
- **ALOCircle** — Assistant Labour Officer circles (State → District → Circle)
- **Nominee** — worker dependents/nominees (name, relationship, share %, primary flag)
- **Renewal** — KPR-YYYY-NNNNN; approval in admin extends Worker.valid_until by the period
- **ChangeRequest** — KPC-YYYY-NNNNN; approval auto-applies the change to the worker record
- **DBTBatch / DBTPayment** — DBT-YYYY-NNN batches; payments SUCCESS/FAILED/PENDING with
  failure reasons; admin action retries FAILED payments into a new batch (retry_of link)

### Worker additions
gender now includes "Others"; valid_until (registration + 5 years, extended by renewals);
village FK; alo_circle FK; is_expired property.


## Phase 3 additions

### Establishment (employer/organization — the "Enterprise/Labour" side)
est_no (unique, EST-YYYY-NNNNN), name, employer_name, category
(Builder/Contractor/Developer/Govt project/Other), phone, address,
village FK, est_workers_count, cess_paid (funds the welfare schemes),
registered_date, valid_until (5 years).

Worker.employer FK → Establishment (workers linked to where they work).

### Utility endpoints
/worker/<reg_no>/card/ — printable registration card
/workers/export/ — CSV download of the worker register
/establishment/<est_no>/ — establishment detail with linked workers


## v4 (monitoring redesign)
Scheme gained task-specification fields: eligibility, procedure, benefit_amount.
Citizen-facing form pages removed (register/apply/renew/corrections/establishments);
their tables remain as monitored data. Public routes now: /, /schemes/, /track/,
/status/, /worker/<reg_no>/ (read-only record view), /dashboard/, /api/chat, /admin/.
