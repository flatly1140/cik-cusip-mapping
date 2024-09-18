#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
An enhanced script to download specific SEC filings based on given form types, store them in organized folders,
and compress folders after downloads are complete. This version uses ThreadPoolExecutor for concurrent downloads,
implements batched processing, and includes other optimizations for handling many small files efficiently.
The script reads an index Parquet file, filters records by the specified filing types, and downloads the
corresponding documents from the SEC website. Files are initially saved uncompressed, and folders are
compressed after all downloads for a year_month are complete. Failed downloads are recorded in a separate file.
This version strictly adheres to the SEC's rate limit and can resume from previous runs by checking existing files.
"""

# Standard library imports
import os                   # Provides functions for interacting with the operating system, including file and directory manipulation
from pathlib import Path    # Provides an object-oriented interface for filesystem paths, making path manipulations more convenient
import shutil               # Offers high-level file operations such as copying and removal of files and directories
import time                 # Provides various time-related functions, such as time tracking and sleeping
from collections import defaultdict  # Provides a dictionary subclass that calls a factory function to supply missing values
from concurrent.futures import ThreadPoolExecutor, as_completed  # Provides a high-level interface for asynchronously executing callables
import threading            # Provides thread-based parallelism
import tarfile              # Provides tools for creating, reading, and writing tar archives

import logging
from time import sleep
from dataclasses import dataclass
from typing import Optional

# Third-party imports
import pyarrow.parquet as pq    # Provides tools for reading and writing Parquet files, a columnar storage file format
import pyarrow.compute as pc    # Offers various computational functions and operations on Arrow arrays and tables
import pyarrow as pa        # Provides the Table class and other core functionality
import requests                 # Allows sending HTTP requests, making it easy to interact with web services and APIs

# Local imports
from main_parameters import DATA_FOLDER, DATA_RAW
from main_parameters import USER_AGENT, SEC_RATE_LIMIT
from main_parameters import FILTERED_INDEX_FILE, FILING_TYPES, SEC_URL_PREFIX
from main_parameters import FAILED_DOWNLOADS_FILE

BATCH_SIZE = 100  # Number of files to process in each batch
MAX_WORKERS = 20  # Maximum number of threads to use for concurrent downloads


class RateLimiter:
    """A thread-safe rate limiter to ensure adherence to SEC's rate limit."""
    def __init__(self, rate_limit):
        self.rate_limit = rate_limit
        self.last_request_time = 0
        self.lock = threading.Lock()

    def wait(self):
        """Wait if necessary to comply with the rate limit."""
        with self.lock:
            current_time = time.time()
            time_since_last_request = current_time - self.last_request_time
            if time_since_last_request < 1 / self.rate_limit:
                time.sleep((1 / self.rate_limit) - time_since_last_request)
            self.last_request_time = time.time()


@dataclass
class DownloadStatus:
    success: bool
    attempts: int
    error: Optional[str] = None


def read_index_file(filings: str | list[str]) -> pa.Table:
    """Reads the index Parquet file and filters rows based on the specified filing type(s).
    Args:
    filings (str | list[str]): The form type(s) to filter by.
    Returns:
    pq.Table: A PyArrow Table representing the filtered rows.
    """
    print(f"Reading Parquet file: {FILTERED_INDEX_FILE}")
    table = pq.read_table(FILTERED_INDEX_FILE)
    print(f"Total rows in Parquet file: {table.num_rows}")

    # print out the data types of your Parquet file columns to understand what you're working with.
    print("Column data types:")
    for field in table.schema:
        print(f"{field.name}: {field.type}")

    unique_forms = pc.unique(table['form'])
    print(f"Unique form types in Parquet file: {unique_forms}")

    if isinstance(filings, str):
        filings = [filings]
    print(f"Filtering for filing types: {filings}")

    # Create a mask for each filing type using partial matching
    masks = [pc.match_substring(table['form'], filing) for filing in filings]

    # Combine masks appropriately
    if len(masks) == 1:
        combined_mask = masks[0]
    else:
        combined_mask = pc.or_kleene(*masks)

    filtered_table = table.filter(combined_mask)
    print(f"Rows after filtering: {filtered_table.num_rows}")
    unique_filtered_forms = pc.unique(filtered_table['form'])
    print(f"Unique form types after filtering: {unique_filtered_forms}")
    return filtered_table


def download_file(session: requests.Session, url: str, file_path: Path, rate_limiter: RateLimiter, max_retries: int = 4) -> DownloadStatus:
    """Downloads a file from the specified URL and saves it to the given path without compression.

    Args:
        session (requests.Session): The session to use for the request.
        url (str): The URL of the file to download.
        file_path (Path): The local path to save the downloaded file.
        rate_limiter (RateLimiter): The rate limiter to use for adhering to SEC's rate limit.
        max_retries (int): Maximum number of retry attempts.

    Returns:
        DownloadStatus: Object containing download status information.
    """
    for attempt in range(max_retries):
        try:
            rate_limiter.wait()  # Wait if necessary to comply with rate limit
            response = session.get(url, headers=USER_AGENT, timeout=5)
            response.raise_for_status()  # Raise an error for bad status codes

            with open(file_path, 'wb') as f_out:
                f_out.write(response.content)

            return DownloadStatus(success=True, attempts=attempt + 1)

        except requests.HTTPError as e:
            if e.response.status_code == 404:
                logging.error(f"File not found: {url}")
                return DownloadStatus(success=False, attempts=attempt + 1, error="File not found")
            elif e.response.status_code in (429, 503):
                logging.warning(f"Rate limited or service unavailable. Retrying in {2**attempt} seconds.")
                sleep(2**attempt)  # Exponential backoff
            else:
                logging.error(f"HTTP error occurred: {e}")
                return DownloadStatus(success=False, attempts=attempt + 1, error=str(e))

        except requests.RequestException as e:
            logging.error(f"Failed to download {url}: {e}")
            if attempt < max_retries - 1:
                logging.info(f"Retrying in {2**attempt} seconds.")
                sleep(2**attempt)  # Exponential backoff
            else:
                return DownloadStatus(success=False, attempts=attempt + 1, error=str(e))

    return DownloadStatus(success=False, attempts=max_retries, error="Max retries reached")


def process_batch(session: requests.Session, batch: list[dict], current_folder: Path, rate_limiter: RateLimiter) -> tuple[list[str], int]:
    """Process a batch of files for downloading.

    Args:
        session (requests.Session): The session to use for downloads.
        batch (list[dict]): A list of dictionaries containing file information.
        current_folder (Path): The folder to save downloaded files.
        rate_limiter (RateLimiter): The rate limiter to use for adhering to SEC's rate limit.

    Returns:
        tuple[list[str], int]: A list of failed downloads and the number of successful downloads.
    """
    failed_downloads = []
    successful_downloads = 0

    for i, row in enumerate(batch):
        cik = row["cik"].strip()
        # This change will convert the date to a string before applying the .strip() method, and it will handle None values as well.
        # Since the 'date' column is of type 'timestamp[us]', this alternative is required
        date = row["date"] if row["date"] is not None else ""  # add a potential check for None values
        url = row["filename"].strip()
        accession = url.split(".")[0].split("-")[-1]

        file_path = current_folder / f"{cik}_{date:%Y-%m-%d}_{accession}.txt"
        if not file_path.exists():
            file_url = f"{SEC_URL_PREFIX}{url}"

            status = download_file(session, file_url, file_path, rate_limiter)
            if status.success:
                # print(f"File #{i+1} of {len(batch)} downloaded successfully after {status.attempts} attempt(s)")
                successful_downloads += 1
            else:
                print(f"Download failed after {status.attempts} attempt(s). Error: {status.error}")

    return failed_downloads, successful_downloads


def process_filing(filing: str) -> None:
    """Process a single filing type.
    This function reads the index file for the specified filing type, downloads the corresponding
    documents from the SEC website using concurrent threads, and organizes them into year-month folders.
    It checks for existing files and skips already processed ones. After all files for a year-month
    have been downloaded, the folder is compressed if not already done.

    Args:
        filing (str): The filing type to process.
    """
    filtered_table = read_index_file(filing)
    total_files = filtered_table.num_rows
    print(f"Found {total_files} files to process for {filing}.")
    print("Starting downloads...")

    # Group the files by year_month
    files_by_year_month = defaultdict(list)
    for row in filtered_table.to_pylist():
        # This change will convert the date to a string before applying the .strip() method, and it will handle None values as well.
        # Since the 'date' column is of type 'timestamp[us]', this alternative is required
        date = row["date"] if row["date"] is not None else ""  # add a potential check for None values
        year, month = date.year, date.month
        year_month = f"{year}_{month:02d}"
        files_by_year_month[year_month].append(row)

    failed_downloads = []
    total_successful_downloads = 0

    rate_limiter = RateLimiter(SEC_RATE_LIMIT)  # Create a rate limiter

    with requests.Session() as session, ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for year_month, files in sorted(files_by_year_month.items()):
            current_folder = Path(f"{DATA_RAW}/{filing}_filings/{year_month}")
            # current_folder = os.path.join(DATA_RAW,f"{filing}_filings",f"{year_month}")
            gz_file = current_folder.with_suffix('.tar.gz')

            # Skip if .tar.gz file already exists
            if gz_file.exists():
                print(f"Skipping {year_month} - already processed and compressed.")
                continue

            print(f"Processing {year_month}")
            start_time = time.time()

            # Get existing files in the folder
            current_folder.mkdir(parents=True, exist_ok=True)
            existing_files = set()
            if current_folder.exists():
                for file_path in current_folder.glob('*.txt'):
                    existing_files.add(file_path.stem)

            print(f"{current_folder.name} has {len(existing_files)} files initially.")

            # Filter out already downloaded files
            # Since the 'date' column is of type 'timestamp[us]', this alternative is required
            files_to_process = [
                file for file in files
                if f"{file['cik'].strip()}_{file['date']}_{file['filename'].strip().split('.')[0].split('-')[-1]}" not in existing_files
            ]

            # Process files in batches
            file_batches = [files_to_process[i:i + BATCH_SIZE] for i in range(0, len(files_to_process), BATCH_SIZE)]
            futures = []

            for batch in file_batches:
                future = executor.submit(process_batch, session, batch, current_folder, rate_limiter)
                futures.append(future)

            # Wait for all batches to complete
            for future in as_completed(futures):
                batch_failed, batch_successful = future.result()
                failed_downloads.extend(batch_failed)
                total_successful_downloads += batch_successful

            # Compress the folder after all files for this year_month have been downloaded
            archive_name = current_folder.with_suffix('.tar.gz')
            with tarfile.open(archive_name, "w:gz") as tar:
                for file_path in current_folder.glob('*.txt'):
                    tar.add(file_path, arcname=file_path.name)
                    os.remove(file_path)  # Remove the original file after adding to archive

            shutil.rmtree(current_folder)  # Remove the original folder
            print(f"Compressed folder: {current_folder}")

            end_time = time.time()
            print(f"Time spent processing {year_month}: {end_time - start_time:.2f} seconds")

    print(f"Total successful downloads: {total_successful_downloads}")
    print(f"Total failed downloads: {len(failed_downloads)}")

    # Save failed downloads to a file
    if failed_downloads:
        failed_downloads_path = Path(f"{DATA_FOLDER}{filing}_{FAILED_DOWNLOADS_FILE}")
        with open(failed_downloads_path, 'w') as f:
            for item in failed_downloads:
                f.write(f"{item}\n")
        print(f"Saved list of failed downloads to {failed_downloads_path}")


def main() -> None:
    """Main function to orchestrate the downloading of SEC filings and subsequent folder compression."""
    if isinstance(FILING_TYPES, str):
        process_filing(FILING_TYPES)
    elif isinstance(FILING_TYPES, list):
        for filing in FILING_TYPES:
            print(f"Processing filing type: {filing}")
            process_filing(filing)
    else:
        print("Error: EDGAR_FILINGS must be a string or a list of strings.")


if __name__ == "__main__":
    main()
