#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This script parses SEC filing archives to extract CIK (Central Index Key) and CUSIP codes,
writing the extracted information to both CSV and JSON files. It's designed to work
efficiently with large datasets, providing progress updates and handling batch processing.

The script processes tar.gz archives organized in a directory structure:
staging/{filing_type}_filings/{year}_{month}/*.tar.gz

It uses multithreading for efficient processing and implements batching to manage
large volumes of data effectively.
"""

# Standard library imports
import os
import csv
import tarfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Union, Optional, Dict, Generator

# Local application imports
# Import compiled regular expressions from an external module
from main_parameters import RX_CLEAN_HTML, RX_GET_CUSIP, RX_GET_WORDCHARS, RX_HTML_JUNK

# Import parameters from EDGAR_params
from main_parameters import FILING_TYPES, DATA_RAW, DATA_PROCESSED

# Constants
BATCH_SIZE = 100  # Number of files to process before writing a batch to JSON
MAX_WORKERS = 20  # Maximum number of threads for parallel processing
DEBUG_MODE = False # Debug mode flag


def check_zero_float(cusip_candidates: Union[str, List[str], None]) -> List[str]:
    """
    Check if the given string(s) represent zero when converted to a float.
    Args:
        input_data (Union[str, List[str], None]): A string, a list of strings, or None.
    Returns:
        List[str]: A list of strings indicating only those candidates that do not evaluate to zero as a float.
    """
    if cusip_candidates is None:
        return []

    if isinstance(cusip_candidates, str):
        cusip_candidates = [cusip_candidates]

    non_zero_candidates: List[str] = []
    for s in cusip_candidates:
        try:
            if float(s) != 0:
                non_zero_candidates.append(s)
        except ValueError:
            non_zero_candidates.append(s)  # Not a valid number, so include it in the result
    return non_zero_candidates

# Function to check for CUSIP-like numbers with surrounding context
def parse_file_content(content: str) -> Dict[str, Optional[str]]:
    """
    Parse the content of a file to extract CIK and CUSIP codes.

    This function processes the file content, extracts the CIK (Central Index Key)
    and CUSIP (Committee on Uniform Securities Identification Procedures) codes
    using regular expressions and specific markers in the text.

    :param content: The content of the file to be parsed.
    :return: A dictionary containing the CIK and CUSIP code.
    """
    # Important prep-work
    lines = content.replace("<DOCUMENT>", "***starter***")
    lines = RX_CLEAN_HTML.sub('\n', lines).split('\n')
    lines = [line for line in lines if line.strip() != '']

    # Extract CIK
    accession = None
    cik = None
    record = False
    for line in lines:
        if 'ACCESSION NUMBER' in line.upper():
            accession = str(line.split('\t\t')[-1].strip())
        if 'SUBJECT COMPANY' in line.upper():
            record = True
        if 'CENTRAL INDEX KEY' in line.upper() and record:
            cik = str(line.split('\t\t\t')[-1].strip()).zfill(10)
            break

    # Extract CUSIP
    accepted_cusips = []
    record = False

    for i in range(len(lines)):
        if '***starter***' in lines[i]:
            record = True
        if record:
            current_line = lines[i].strip().upper()
            current_line = RX_HTML_JUNK.sub('', current_line)
            current_line = RX_CLEAN_HTML.sub('', current_line)

            # Check the current line for CUSIP-like numbers
            cusip_matches = RX_GET_CUSIP.findall(current_line)

            # Remove white-spaces from the matches
            cusip_matches = [match.replace("(", "").replace(" ", "").replace("-", "").replace(")", "") for match in cusip_matches]

            # Remove zero-valued matches like "000000"
            cusip_matches = check_zero_float(cusip_matches)

            if cusip_matches:
                # Check the context lines for "CUSIP"
                prev2_line = lines[i-2].strip() if i > 1 else ""
                prev_line = lines[i-1].strip() if i > 0 else ""
                next_line = lines[i+1].strip() if i < len(lines) - 1 else ""

                if "CUSIP" in current_line or "CUSIP" in next_line or "CUSIP" in prev_line or "CUSIP" in prev2_line:
                    accepted_cusips.extend(cusip_matches)

    accepted_cusip = None
    accepted_alt = None
    if accepted_cusips:
        accepted_cusip = Counter(accepted_cusips).most_common()[0][0]
        accepted_cusip = ''.join(RX_GET_WORDCHARS.findall(accepted_cusip))

        if len(Counter(accepted_cusips).most_common()) >= 2:
            accepted_alt = Counter(accepted_cusips).most_common()[1][0]
            accepted_alt = ''.join(RX_GET_WORDCHARS.findall(accepted_alt))


    return {"accession": accession, "cik": cik, "cusip": accepted_cusip, "alt": accepted_alt}


def process_archive(archive_path: Path) -> Generator[Dict[str, Optional[str]], None, None]:
    """
    Process a single tar.gz archive, yielding parsed results for each file.

    This function opens a tar.gz archive and processes its contents without
    fully extracting the archive to disk. It reads and processes files
    directly from the archive, ensuring no unnecessary disk usage.

    :param archive_path: Path to the tar.gz archive.
    :yield: Dictionary containing file name, CIK, and CUSIP for each processed file.
    """
    print(f"Processing archive: {archive_path}")  # Debug print
    try:
        with tarfile.open(archive_path, 'r:gz') as tar:
            file_count = 0  # Debug counter
            for member in tar.getmembers():
                if member.isfile() and member.name.endswith('.txt'):
                    file_count += 1  # Debug counter
                    with tar.extractfile(member) as f:
                        if f is not None:
                            content = f.read().decode('utf-8', errors='ignore')
                            result = parse_file_content(content)
                            yield {"file": member.name, **result}
            print(f"Processed {file_count} files in archive {archive_path}")  # Debug print
    except Exception as e:
        print(f"Error processing archive {archive_path}: {e}")


def process_filing_type(filing_type: str) -> None:
    """
    Process all archives for a given filing type.
    This function orchestrates the processing of all tar.gz archives for a specific
    filing type. It sets up CSV output files, manages multithreaded processing,
    and handles batch writing of sorted results.
    :param filing_type: The type of filing to process (e.g., '10-K', '10-Q').
    """
    base_path = Path(f"{DATA_RAW}/{filing_type}_filings")
    output_csv = f"{DATA_PROCESSED}/{filing_type}_output.csv"
    print(f"Processing filing type: {filing_type}")
    print(f"Base path: {base_path}")
    print(f"Output CSV: {output_csv}")

    os.makedirs(DATA_PROCESSED, exist_ok=True)
    total_processed = 0
    archives_found = 0  # Debug counter
    all_results: List[Dict[str, Optional[str]]] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for archive in sorted(base_path.glob("*.tar.gz")):
            archives_found += 1
            print(f"Found archive: {archive}")
            futures.append(executor.submit(process_archive, archive))

        print(f"Found {archives_found} archives for {filing_type}")

        for future in as_completed(futures):
            try:
                for result in future.result():
                    all_results.append(result)
                    total_processed += 1
            except Exception as e:
                print(f"Error processing future: {e}")

    # Sort the results by CIK and then by CUSIP
    sorted_results = sorted(all_results, key=lambda x: (x['cik'] or '', x['cusip'] or '', x['accession'] or ''))

    # Write sorted results to CSV
    with open(output_csv, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["file", "accession", "cik", "cusip", "alt"])
        writer.writeheader()
        for result in sorted_results:
            writer.writerow(result)

    print(f"Completed processing {total_processed} files for {filing_type}")

def main() -> None:
    """
    Main function to orchestrate the parsing of SEC filings and output generation.

    This function determines which filing types to process based on the EDGAR_FILINGS
    configuration, and initiates the processing for each filing type.
    """
    if isinstance(FILING_TYPES, str):
        filings_to_process = [FILING_TYPES]
    elif isinstance(FILING_TYPES, list):
        filings_to_process = FILING_TYPES
    else:
        raise ValueError("EDGAR_FILINGS must be a string or a list of strings.")

    print(f"Filings folder: {DATA_PROCESSED}")  # Debug print
    print(f"EDGAR_FILINGS: {FILING_TYPES}")  # Debug print

    for filing in filings_to_process:
        print(f"Starting processing for {filing}")
        process_filing_type(filing)
        print(f"Completed processing for {filing}")

if __name__ == '__main__':
    main()
