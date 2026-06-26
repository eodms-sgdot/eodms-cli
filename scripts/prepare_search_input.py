"""
Reads a file-report CSV (columns: file, country, downloads),
extracts order_key and datetime from the 'file' path,
and outputs a TSV with order_key and datetime columns.

The order_key is the product-directory segment (e.g., RCM3_OK3960571_PK4126077_1_SC30MCPA_20260419_005732_CH_CV_MLC).
The datetime is parsed from the order_key (YYYYMMDD_HHMMSS format converted to ISO).

Usage:
    python scripts/prepare_search_input.py <input_csv> <output_tsv>
"""

import csv
import sys
from datetime import datetime


def extract_order_key_and_datetime(file_path: str) -> tuple:
    """Extract order_key and datetime ISO string from the file path.
    
    Returns:
        (order_key, datetime_iso_str) or ("", "") if parsing fails
    """
    try:
        parts = file_path.replace("\\", "/").split("/")
        
        # order_key is the parent folder of the file (second-to-last component)
        if len(parts) < 2:
            return "", ""
        
        order_key = parts[-2]
        
        # Parse datetime from order_key: look for YYYYMMDD_HHMMSS pattern
        order_key_parts = order_key.split("_")
        
        for i in range(len(order_key_parts) - 1):
            if len(order_key_parts[i]) == 8 and len(order_key_parts[i + 1]) == 6:
                try:
                    date_str = order_key_parts[i]  # YYYYMMDD
                    time_str = order_key_parts[i + 1]  # HHMMSS
                    dt_str = f"{date_str}{time_str}"  # 20260419005732
                    dt = datetime.strptime(dt_str, "%Y%m%d%H%M%S")
                    datetime_iso = dt.isoformat() + "Z"
                    return order_key, datetime_iso
                except ValueError:
                    continue
        
        return order_key, ""
    except Exception:
        return "", ""


def main(input_csv: str, output_tsv: str) -> None:
    rows = []
    
    # Read input CSV
    with open(input_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SystemExit("ERROR: CSV has no header row.")
        
        for row in reader:
            file_path = row.get("file", "")
            order_key, datetime_iso = extract_order_key_and_datetime(file_path)
            
            if order_key and datetime_iso:
                rows.append({"order_key": order_key, "datetime": datetime_iso})
    
    # Write output TSV
    with open(output_tsv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["order_key", "datetime"], delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"Extracted {len(rows)} rows to {output_tsv}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(f"Usage: python {sys.argv[0]} <input_csv> <output_tsv>")
    main(sys.argv[1], sys.argv[2])
