#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List     # For type annotations of function parameters and return types
import pandas as pd         # Data analysis and manipulation library, used for handling CSV files and dataframes

from pathlib import Path
from main_parameters import DATA_PROCESSED, DATA_FINAL

def cusip9_from_cusip8_dataframe(df: pd.DataFrame, column_name: str):
    """
    Function to calculate CUSIP-9 from CUSIP-8 for all rows in a DataFrame.
    
    Parameters:
    df : pd.DataFrame
        The DataFrame containing the CUSIP-8 strings.
    column_name : str
        The column name that contains the CUSIP-8 values.
    
    Returns:
    pd.DataFrame
        A DataFrame with the original CUSIP-8 values and the corresponding CUSIP-9 values.
    """

    "based on Wikipedia's Check-digit pseudocode https://en.wikipedia.org/w/index.php?title=CUSIP&action=edit&section=6"
    def char_value(c):
        if c.isdigit():
            return int(c)
        elif c.isalpha():
            return ord(c.upper()) - ord('A') + 10
        elif c == '*':
            return 36
        elif c == '@':
            return 37
        elif c == '#':
            return 38
        else:
            raise ValueError(f"Invalid character in CUSIP: {c}")

    def cusip9_from_cusip8(in_cusip: str):
        if len(in_cusip) != 8:
            return None
        
        sum = 0
        for i, c in enumerate(in_cusip):
            v = char_value(c)
            if i % 2 != 0:
                v *= 2
            sum += (v // 10) + (v % 10)
        
        check_digit = (10 - (sum % 10)) % 10
        cusip9 = in_cusip + f"{check_digit}"
        return cusip9

    # Apply the CUSIP conversion function to the DataFrame column
    df['cusip9_check'] = df[column_name].str[:8].apply(cusip9_from_cusip8)
    
    return df

def process_files(files: List[str]) -> pd.DataFrame:
    """
    Process a list of CSV files to extract and transform CIK and CUSIP data.

    Args:
        files (List[str]): List of file paths to CSV files.

    Returns:
        pd.DataFrame: Processed DataFrame containing unique CIK, cusip6, and cusip8 mappings.
    """
    # Read and concatenate data from all files
    df = pd.concat([pd.read_csv(f, names=['f', 'accession', 'cik', 'cusip', 'alt']).dropna() for f in files])

    # Filter rows where CUSIP length is 6, 8, or 9
    df['leng'] = df.cusip.map(len)

    df = df[df['leng'].isin([6, 8, 9])]

    # Extract cusip6 and filter out invalid entries
    df['cusip6'] = df.cusip.str[:6]

    invalid_cusip6 = ['000000', '0001pt']
    df = df[~df['cusip6'].isin(invalid_cusip6)]

    # Extract cusip8
    df['cusip8'] = df.cusip.str[:8]

    # Extract cusip9
    df['cusip9'] = df.cusip.str[:9]

    # Create cusip8_with_checksum to compare with cusip9
    df = cusip9_from_cusip8_dataframe(df, 'cusip')  

    # Convert CIK to numeric and remove duplicates

    # df = df[['cik', 'cusip6', 'cusip8', 'cusip9', 'cusip9_check']].drop_duplicates()
    # df['Comparison_Result'] = df['cusip9'] == df['cusip9_check']

    df = df[['cik', 'cusip6', 'cusip9']].drop_duplicates()
    df.reset_index(drop=True, inplace=True)

    return df

## NOTE: cusip9 will have eight chars rather than nine if its cusip8 doesn't pass the checksum. consider dropping cusip6 and using only 'cusip9'... 
## in this case, cusip9 will have 6 chars if only cusip6 was found, 8 chars if it is likely not a valid cusip, otherwise 9 chars...
## in this case, we could consider filtering 'cuspi9' for obs of len in {6,9}, effectively dropping the assumed invalid cusip8s.

def main():
    # Get file paths from command line arguments
    files = list(Path(DATA_PROCESSED).glob("*.csv"))

    # Process files and save the resulting DataFrame to CSV
    df = process_files(files)
    
    # Final output files
    DATA_FINAL.mkdir(parents=True, exist_ok=True)
    df.to_csv(f'{DATA_FINAL}/cik-cusip-maps.csv', index=False)
    df.to_json(f'{DATA_FINAL}/cik-cusip-maps.json', index=False)


if __name__ == "__main__":
    main()
