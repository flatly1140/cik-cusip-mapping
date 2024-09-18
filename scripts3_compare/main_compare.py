import pandas as pd

def append_csv_files(file1, file2):
    """
    Appends two CSV files and writes the result to appended_file.
    """
    # Read the first CSV
    df1 = pd.read_csv(file1)
    print(f"Read {len(df1)} rows from {file1}")
    
    # Read the second CSV
    df2 = pd.read_csv(file2)
    print(f"Read {len(df2)} rows from {file2}")
    
    # Check if both DataFrames has same number of columns
    if df1.shape[1] != df2.shape[1]:
        raise ValueError("CSV files expected to have same number of columns.")
    
    # Append the DataFrames
    appended_df = pd.concat([df1, df2], ignore_index=True)
    print(f"Appended DataFrame has {len(appended_df)} rows.")
    
    return appended_df

def filter_rows_based_on_matches(source_df, match_file, output_file):
    """
    Filters rows in appended_df where column 2 match any row in match_file.
    Writes the filtered rows to output_file.
    """
    # Read the match CSV (assuming it has no header)
    matches_df = pd.read_csv(match_file, header=None)
    matches_df.columns = ['Ticker', 'CIK']
    print(f"Read {len(matches_df)} match rows from {match_file}")
    
    # Assuming columns are zero-indexed
    # Adjust if your CSVs have headers
    # In pandas, columns are labeled from 0 to n-1 if no headers are specified
    # Here, we assume the appended_df has headers; adjust if necessary
    
    # Merge to find matching rows
    merged_df = source_df.merge(matches_df, left_on=[source_df.columns[2]], 
                                  right_on=['CIK'], how='inner')
    print(f"Found {len(merged_df)} matching rows.")
    
    # Drop the match columns if not needed
    merged_df = merged_df.drop(['Ticker', 'CIK'], axis=1)
    
    # Write the filtered DataFrame to a new CSV
    merged_df.to_csv(output_file, index=False)
    print(f"Filtered rows written to {output_file}")


def main():
    from pathlib import Path

    # Get the directory where the current script is located
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    DATA_FOLDER = PROJECT_ROOT / "scripts0_orig_process" / "data_dir_2024" / "processed"
    csv_13D = DATA_FOLDER / "13D_output.csv"
    csv_13G = DATA_FOLDER / "13G_output.csv"
    
    # Step 1: Append the two CSV files
    appended_df = append_csv_files(csv_13D, csv_13G)
    
    # Prep for output files
    SCRIPT_DIR = Path(__file__).resolve().parent / "output"
    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    match_csv = SCRIPT_DIR / "cik.csv"                  # Third 2-column CSV for matching
    output_csv = SCRIPT_DIR / "filtered_output.csv"     # Final output CSV

    # Step 2: Filter based on matches and write to output
    filter_rows_based_on_matches(appended_df, match_csv, output_csv)

if __name__ == "__main__":
    main()
