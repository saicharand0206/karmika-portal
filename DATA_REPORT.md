# Data Cleaning & Analysis Report

Source: Sample_test_data.xlsx (Workers: 42 rows × 97 cols; Schemes: 7 main + 26 sub-schemes)

## Cleaning steps applied
1. **Dates** — reg_date and date_of_birth were Excel serial numbers (e.g. 43466);
   converted with origin 1899-12-30.
2. **Gender** — numeric codes decoded: 1 → Male, 2 → Female.
3. **Names** — trimmed and title-cased; Telugu-script variants preserved.
4. **Junk rows** — 2 rows flagged (`sdfsdf`, keyboard-mash names / "TEST" markers).
5. **IFSC validation** — regex `^[A-Z]{4}0[A-Z0-9]{6}$`; 22 of 27 codes valid,
   5 invalid/truncated (e.g. "ANDB", "ANDB000099" — 10 chars).
6. **Age sanity flag** — outside 18–60 flagged (none in this sample).
7. **Booleans** — TRUE/FALSE strings and 0/1 normalised.
8. **Scheme form fields** — the `"n"=>"label"` strings parsed into clean lists
   of required fields/documents per sub-scheme.

## Key findings
- Registrations by year: 2009: 1, 2015: 3, 2016: 1, **2017: 13, 2018: 16**, 2019: 8 — activity peaks 2017–18.
- Gender: 41 male, 1 female — heavily male-skewed sample.
- Age: mean 37.1 (range 19–55).
- 36 of 42 records missing date of birth — the biggest completeness gap.
- 0 migrant workers, 2 trade-union members in sample.
- Most common trade codes: 9 (9 workers), 13 (6), 14 (5), 15 (4).
- Scheme catalogue: 7 schemes, 26 benefit sub-categories, each with a
  documented checklist (FIR, death/disability certificate, bank passbook, Aadhaar, ALO enquiry report, etc.).
