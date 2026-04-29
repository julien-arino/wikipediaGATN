import csv
with open('data/tmp_results/missing_from_ourairports_active.csv', 'r') as f:
    rows = list(csv.DictReader(f))
header = rows[0].keys()
for row in rows:
    if row['iata_code'] == '89D':
        with open('data/tmp_results/temp_active.csv', 'w') as out:
            writer = csv.DictWriter(out, fieldnames=header)
            writer.writeheader()
            writer.writerow(row)
        break
