# Save as src/processing/check_gmp_unmatched.py
# Run: python3 src/processing/check_gmp_unmatched.py

import pandas as pd

RAW = "data/raw"

det = pd.read_csv(f"{RAW}/raw_ipo_details.csv")
gmp = pd.read_csv(f"{RAW}/raw_gmp_data.csv")

det["det_date"] = pd.to_datetime(det["listed_on"], format="mixed", errors="coerce")
gmp["gmp_date"] = pd.to_datetime(gmp["Listing Date▲▼"], format="mixed", errors="coerce")

# The 11 unmatched GMP names
unmatched_gmp = [
    "CAMS", "Paytm", "SJS Enterprises", "Policybazaar", "KIMS",
    "Five Star Business Finance", "Mufti Jeans", "Firstcry",
    "Aasaan Loans", "NSDL", "Leela Hotels"
]

print("For each unmatched GMP name, here are the candidate companies")
print("that listed on the same date. Pick the correct one.\n")

for name in unmatched_gmp:
    row = gmp[gmp["IPO▲▼"].str.strip() == name]
    if len(row) == 0:
        print(f"  {name}: NOT FOUND IN GMP DATA\n")
        continue
    
    gmp_date = row.iloc[0]["gmp_date"]
    gmp_price = row.iloc[0]["IPO Price▲▼"]
    candidates = det[det["det_date"] == gmp_date][["company", "issue_price"]].values.tolist()
    
    print(f"  GMP: '{name}' (issue price: {gmp_price}, date: {gmp_date.date()})")
    print(f"  Candidates on that date:")
    for company, price in candidates:
        print(f"    → {company} (issue price: {price})")
    print()