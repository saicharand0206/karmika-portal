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
