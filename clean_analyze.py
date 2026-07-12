import pandas as pd
import numpy as np
import re

xl = pd.read_excel("/mnt/user-data/uploads/Sample_test_data.xlsx", sheet_name=None)
workers = xl["Workers"]

# ---------- CLEAN WORKERS ----------
w = workers.copy()
for col in ["reg_date", "date_of_birth"]:
    w[col] = pd.to_numeric(w[col], errors="coerce")
    w[col] = pd.to_datetime(w[col], unit="D", origin="1899-12-30", errors="coerce")

w["gender"] = w["gender"].map({1: "Male", 2: "Female"}).fillna("Unknown")

for col in ["worker_name", "father_name"]:
    w[col] = w[col].astype(str).str.strip().str.title().replace("Nan", np.nan)

def is_junk(name):
    if not isinstance(name, str): return True
    n = name.lower().replace(" ", "")
    return bool(re.fullmatch(r"[sdfa]{3,}", n)) or "test" in n
w["is_test_row"] = w["worker_name"].apply(is_junk)

def ifsc_ok(x):
    return bool(re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", str(x).strip()))
w["ifsc_valid"] = w["branch_name"].apply(ifsc_ok)

w["age"] = pd.to_numeric(w["age"], errors="coerce")
w["age_flag"] = (w["age"] < 18) | (w["age"] > 60)

for col in ["member_tradeunion", "migrantworker", "jana", "indira", "rajiv"]:
    w[col] = w[col].astype(str).str.upper().isin(["TRUE", "1"])

clean = w[["reg_no","temp_id","alocode","reg_year","reg_date","worker_name","father_name",
           "gender","date_of_birth","age","caste","bank_name","branch_name","ifsc_valid",
           "member_tradeunion","migrantworker","nature_emp","pres_emp_district",
           "worker_name_t","father_name_t","is_test_row","age_flag"]].copy()
clean.columns = ["reg_no","temp_id","alo_code","reg_year","reg_date","worker_name","father_name",
                 "gender","date_of_birth","age","caste_code","bank_code","ifsc_code","ifsc_valid",
                 "trade_union_member","migrant_worker","trade_code","district_code",
                 "worker_name_telugu","father_name_telugu","is_test_row","age_flag"]
clean.to_csv("data/workers_clean.csv", index=False)

# ---------- CLEAN SCHEMES (header is on row index 1) ----------
sch = pd.read_excel("/mnt/user-data/uploads/Sample_test_data.xlsx", sheet_name="Schemes", header=1)
main = sch.iloc[:, 0:3].dropna(subset=[sch.columns[0]])
main.columns = ["scheme_code","scheme_desc","scheme_type"]
main["scheme_code"] = main["scheme_code"].astype(int)
main.to_csv("data/schemes_clean.csv", index=False)

sub = sch.iloc[:, 4:8].dropna(subset=[sch.columns[4]])
sub.columns = ["scheme_code","subscheme_code","subscheme_desc","form_fields"]
sub["scheme_code"] = sub["scheme_code"].astype(int)
sub["subscheme_code"] = sub["subscheme_code"].astype(int)
# Parse the "n"=>"label" strings into clean JSON-ish lists of required fields/documents
def parse_fields(s):
    if not isinstance(s, str): return ""
    items = re.findall(r'"\d+"=>"([^"]+)"', s)
    return " | ".join(i.strip() for i in items)
sub["form_fields"] = sub["form_fields"].apply(parse_fields)
sub.to_csv("data/subschemes_clean.csv", index=False)

# ---------- ANALYSIS ----------
print("=== CLEANING SUMMARY ===")
print("Workers: %d rows, %d flagged as junk/test entries" % (len(clean), clean.is_test_row.sum()))
print("Dates converted from Excel serials; missing DOB:", clean.date_of_birth.isna().sum())
print("IFSC present: %d, valid format: %d" % (clean.ifsc_code.notna().sum(), clean.ifsc_valid.sum()))
print("\n=== ANALYSIS ===")
print("Registrations by year:")
print(clean.reg_year.value_counts().sort_index().to_string())
print("\nGender:", dict(clean.gender.value_counts()))
print("Age: mean %.1f | min %d | max %d | outside 18-60: %d" % (clean.age.mean(), clean.age.min(), clean.age.max(), clean.age_flag.sum()))
print("Migrant workers:", int(clean.migrant_worker.sum()), "| Trade union members:", int(clean.trade_union_member.sum()))
print("Top trade codes:", dict(clean.trade_code.value_counts().head(4)))
print("\nSchemes: %d main, %d sub-schemes" % (len(main), len(sub)))
for _, r in main.iterrows():
    print(f"  {r.scheme_code}: {r.scheme_desc}")
