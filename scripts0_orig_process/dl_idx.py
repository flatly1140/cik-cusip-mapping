#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to download and process EDGAR master index files.
This script downloads master index files from the SEC EDGAR database for each quarter from 1994 to the current year,
processes the data, and writes it to single index Parquet file.
"""
# Standard library imports
import os  # Provides functions to interact with the operating system
import io
import time  # Time-related functions (e.g., sleep, time)
import tarfile
import re
import csv

# Typing imports
from typing import IO, Tuple  # Type hinting for IO streams and tuples

# Third-party library imports
import pandas as pd  # Data manipulation and analysis
import pyarrow.parquet as pq  # Reading and writing Parquet files
import requests  # HTTP library for making requests to web servers

from main_parameters import (
    START_YEAR, START_QUARTER,
    CURRENT_YEAR, CURRENT_QUARTER,
    RAW_INDEX_FILE,
    USER_AGENT, SEC_RATE_LIMIT,
    FILTERED_INDEX_FILE, SEC_URL_PREFIX,
    FILING_TYPES,
)


def get_last_processed_quarter(output_file: str) -> Tuple[int, int]:
    """
    Read the last fully processed quarter from the Parquet file.
    
    Args:
    output_file (str): Path to the output Parquet file.
    
    Returns:
    Tuple[int, int]: The year and quarter of the prior quarter-end (aka the beginning of the latest quarter in the parquet file.)
    """

    # Compute prior quarter-end aka BEGINNING of starting quarter
    PRIOR_YEAR, PRIOR_QUARTER = (START_YEAR, START_QUARTER-1) if START_QUARTER > 1 else (START_YEAR-1, 4)  # <-- prior year & quarter-end

    print(f"Checking last processed quarter from {output_file}...")
    if not os.path.exists(output_file):
        print(f"{output_file} does not exist. Starting from {START_YEAR} Q{START_QUARTER}.")
        return PRIOR_YEAR, PRIOR_QUARTER  # Start from BEGINNING of start quarter if file doesn't exist
    
    parquet_file = pq.ParquetFile(output_file)
    # Reading only the 'date' column
    dates = parquet_file.read(['date'])
    
    df = dates.to_pandas()
    if df.empty:
        print(f"{output_file} is empty. Starting from {START_YEAR} Q{START_QUARTER}.")  # <-- given year and quarter
        return PRIOR_YEAR, PRIOR_QUARTER
    
    # Compute the latest quarter in the file
    last_date = pd.to_datetime(df['date'].max())
    (last_date_year, last_date_quarter) = (last_date.year, ((last_date.month-1)//3+1))
    print(f"Last processed quarter found: {last_date_year} Q{last_date_quarter}")

    # Return the quarter-end prior to the latest quarter (aka beginning of current quarterly period)
    PRIOR_YEAR, PRIOR_QUARTER = (last_date_year, last_date_quarter-1) if last_date_quarter > 1 else (last_date_year-1, 4) 
    return PRIOR_YEAR, PRIOR_QUARTER


def download_sec_index_of_filings(year: int, quarter: int, file_handle: IO[bytes]) -> None:
    """
    Download the master index file for a given year and quarter and write it to the provided file handle.
    
    Args:
    year (int): The year of the index file.
    quarter (int): The quarter of the index file.
    file_handle (file): The file handle to write the downloaded content.
    """
    # url = os.path.join(SEC_URL_PREFIX, "edgar", "full-index",f"{year}", f"QTR{quarter}", "master.idx")
    url = f"{SEC_URL_PREFIX}edgar/full-index/{year}/QTR{quarter}/master.idx"
    print(f"Downloading {url}...")
    response = requests.get(url, headers=USER_AGENT)
    if response.status_code == 200:
        file_handle.write(response.content)
        print(f"Successfully downloaded data for {year} QTR{quarter}")
    else:
        print(f"Failed to retrieve data for {year} QTR{quarter}: Status code {response.status_code}")
    time.sleep(1 / SEC_RATE_LIMIT)  # Respect rate limit


def download_sec_index_files() -> None:
    """
    Main function to download and process the EDGAR master index files.
    This function now handles both past quarters and the current quarter,
    ensuring daily updates for the current quarter.
    Args:
    CURRENT_YEAR (int): The current year to process up to.
    CURRENT_QUARTER (int): The current quarter to process up to.
    delete_temp_file (bool): Whether to delete the temporary index file after processing.
    """
    
    # Get the last fully processed quarter
    prior_year, prior_quarter = (START_YEAR, START_QUARTER-1) if START_QUARTER > 1 else (START_YEAR-1, 4)  # <-- prior year & quarter-end

    # Download master index files starting from the last processed quarter + 1
    with io.BytesIO() as byte_stream:
        start_year = prior_year + 1 if prior_quarter == 4 else prior_year
        for year in range(start_year, CURRENT_YEAR + 1):
            start_quarter = 1 if year > prior_year else prior_quarter + 1
            end_quarter = 4 if year < CURRENT_YEAR else CURRENT_QUARTER
            for quarter in range(start_quarter, end_quarter + 1):
                download_sec_index_of_filings(year, quarter, byte_stream)

        RAW_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Now save the byte stream into a tar.gz archive
        with tarfile.open(RAW_INDEX_FILE, "w:gz") as tar:
            tarinfo = tarfile.TarInfo(name=RAW_INDEX_FILE.name)
            tarinfo.size = byte_stream.tell()
            byte_stream.seek(0)
            tar.addfile(tarinfo, byte_stream)


def apply_pattern_to_lines(pattern, lines):
    """
    Filters lines based on a regular expression pattern.
    Args:
        pattern (re.Pattern): Compiled regular expression pattern to match against.
        lines (iterator): An iterator yielding lines from a file.
    Yields:
        list: Fields from each line that matches the pattern.
    """
    for line in lines:
        if ".txt" in line:
            fields = line.strip().split("|")
            if len(fields) > 2 and pattern.search(fields[2]):
                yield fields

def process_tarfile(tar_path, line_processor):
    """
    Processes files within a tar.gz archive and applies a line processor function.
    Args:
        tar_path (Path): Path to the tar.gz archive.
        line_processor (function): Function to apply to each line in the extracted files.
    Yields:
        generator: Yields processed lines from the tar.gz archive.
    """
    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar.getmembers():
            with tar.extractfile(member) as file_obj:
                lines = (line.decode('latin1') for line in file_obj)
                yield from line_processor(lines)


def write_parquet(output_file, headers, data_generator):
    """
    Writes filtered data to a Parquet file.
    Args:
        output_file (Path): Path to the output Parquet file.
        headers (list): List of column headers for the Parquet file.
        data_generator (iterator): An iterator yielding rows of data to write to the Parquet file.
    """
    # Convert the generator to a list of rows
    data = list(data_generator)

    # Create a DataFrame from the data
    df = pd.DataFrame(data, columns=headers)

    # Make sure the 'date' column is in datetime format, if not, convert it
    df["date"] = pd.to_datetime(df["date"])

    # Sort the DataFrame by the 'date' column
    df = df.sort_values(by="date")

    # Write the DataFrame to a Parquet file
    df.to_parquet(output_file, index=False)


def write_csv(output_file, headers, data_generator):
    """
    Writes filtered data to a CSV file.
    Args:
        output_file (Path): Path to the output CSV file.
        headers (list): List of column headers for the CSV file.
        data_generator (iterator): An iterator yielding rows of data to write to the CSV file.
    """
    with output_file.open(mode="w", errors="ignore") as csvfile:
        wr = csv.writer(csvfile)
        wr.writerow(headers)
        for row in data_generator:
            wr.writerow(row)

def filter_sec_index_of_filings_to_parquet():
    """
    Filters the master index of filings by applying a pattern to select specific filing types.

    This function extracts files from a tar.gz archive, decodes the lines, filters them based on 
    specified filing types, and writes the filtered data to a CSV file.
    """
    master_index_archive = RAW_INDEX_FILE
    pattern = re.compile("|".join(FILING_TYPES), re.IGNORECASE)
    headers = ["cik", "comnam", "form", "date", "filename"]

    filtered_data = process_tarfile(master_index_archive, lambda lines: apply_pattern_to_lines(pattern, lines))

    # make sure the directory exists
    FILTERED_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    # write_csv(FILTERED_INDEX_PATH.with_suffix(".csv"), headers, filtered_data)
    write_parquet(FILTERED_INDEX_FILE, headers, filtered_data)


if __name__ == "__main__":
    download_sec_index_files()
    filter_sec_index_of_filings_to_parquet()