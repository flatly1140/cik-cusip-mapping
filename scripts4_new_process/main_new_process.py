#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This script is designed to download and process SEC (Securities and Exchange Commission) security tickers and cusips.
It is based on data related to failures to deliver (FTDs) in the stock market. We're not familiar with FTDs; instead, we use this data
as a means to an end: to create a mapping between U.S. exchange tickers and CUSIPS for common stock.
Here's a breakdown of its main functionalities:

URL Generation:
-   The script builds a list of URLs for SEC zip files containing FTD data from 2004 to the current year. It handles various URL formats
    that have changed over time.

Data Download and Processing:
-   It downloads each zip file, extracts the contents, and processes the data using pandas. The script focuses on extracting key information
    including settlement date, CUSIP (a unique identifier for stocks and registered bonds), stock symbol (exchange tickers), and description.

Data Consolidation:
-   The the historical data is consolidated into a single DataFrame, ensuring consistency in format and handling potential encoding issues.

Error Handling and Logging:
-   The script manage issues like HTTP errors, malformed data, or parsing problems with some logging and light error-trapping.

Data Sorting and File Output:
-   Processed data is sorted by settlement date and then written to CSV files, organized by year and month (YYYYMM format).

CUSIP-Ticker Mapping:
-   There's a function to create a mapping between CUSIP numbers and stock ticker symbols, which is saved as both CSV and JSON files.

Modular Design:
-   The script is structured with separate functions for URL generation, data downloading and processing, and file output, allowing for
flexibility in execution.

SEC Compliance:
-   The script uses a custom User-Agent header to identify itself to the SEC's servers, which is a requirement for accessing their data.

The main purpose of this script is to create a simplified mapping between CUSIP numbers and stock symbols.
"""
import requests
import zipfile
import io
import pandas as pd
import logging

from io import StringIO
from datetime import datetime
from tqdm import tqdm
from pathlib import Path

USER_AGENT      = {
   'User-Agent': "Fingage samer.habl@fingage.com",  # 'ACME Co jane.doe@acme.co',
  'Accept-Encoding': 'deflate',
  'Host': 'www.sec.gov'
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_url_list(start_year=2004, end_year=2024, current_date=None):
    """
    Builds a list of SEC zip file URLs from 2004 to the specified end year.
    
    Parameters:
        start_year (int): The starting year for the URLs.
        end_year (int): The ending year for the URLs.
        current_date (datetime): The current date to limit the URLs.
        
    Returns:
        List[str]: A list of URLs to download.
    """
    if current_date is None:
        current_date = datetime.today()

    urls = []
    
    url_stub1 = "https://www.sec.gov/files/data/fails-deliver-data/cnsp_sec_fails_" # 2004Q1
    url_stub2 = "https://www.sec.gov/files/data/frequently-requested-foia-document-fails-deliver-data/cnsp_sec_fails_" # 2004Q2 to 2009Q2
    url_stub3 = "https://www.sec.gov/files/data/frequently-requested-foia-document-fails-deliver-data/cnsfails" # 200907 to 201706a
    url_stub4 = "https://www.sec.gov/files/data/fails-deliver-data/cnsfails" # 201707b to current
    url_stub5 = "https://www.sec.gov/files/node/add/data_distribution/cnsfails" # 202002 to 202004 (covid)


    # Phase 1a: Quarterly files from 2004 through 2008
    for year in range(start_year, min(2009, end_year)):
        for quarter in range(1, 5):
            if year==2004 and quarter==1:
                url = f"{url_stub1}{year}q{quarter}.zip"
                # e.g. url_stub1: https://www.sec.gov/files/data/fails-deliver-data/cnsp_sec_fails_2004q1.zip
            else:
                url = f"{url_stub2}{year}q{quarter}.zip"
                # e.g. url_stub2: https://www.sec.gov/files/data/frequently-requested-foia-document-fails-deliver-data/cnsp_sec_fails_2004q2.zip
            urls.append(url)
    
    # Phase 1b: 2009 Q1 and Q2
    for year in range(2009, 2009+1):
        for quarter in range(1, 3):
            url = f"{url_stub2}{year}q{quarter}.zip"
            # e.g. url_stub2: https://www.sec.gov/files/data/frequently-requested-foia-document-fails-deliver-data/cnsp_sec_fails_2009q2.zip
            urls.append(url)

    # Phase 3: Twice-monthly files from July 2009 to end_year
    start_month = 7
    for year in range(max(start_year, 2009), end_year + 1):
        if year == 2009:
            month_start = start_month
        else:
            month_start = 1
        month_end = 12 if year < current_date.year else current_date.month
        for month in range(month_start, month_end + 1):
            for p in ['a', 'b']:
                if year == current_date.year and month >= current_date.month:
                    continue  # Skip current month: files produced ~ 2-week lag; skip future months, obvi
                if year < 2017 or (year == 2017 and month < 6) or (year == 2017 and month == 6 and p == 'a'):
                    url = f"{url_stub3}{year}{month:02d}{p}.zip"
                    # e.g. url_stub3: https://www.sec.gov/files/data/frequently-requested-foia-document-fails-deliver-data/cnsfails200907a.zip
                elif year == 2019 and month == 10 and p == 'a':
                    url = f"{url_stub4}{year}{month:02d}{p}_0.zip"  # idiosyncratic filename
                elif year == 2020 and month in [2, 3, 4]:
                    url == f"{url_stub4}{year}{month:02d}{p}.zip"   # idiosyncratic filenames
                else:
                    url = f"{url_stub4}{year}{month:02d}{p}.zip"
                    # e.g. url_stub4: https://www.sec.gov/files/data/fails-deliver-data/cnsfails201706b.zip

                urls.append(url)
    
    return urls


def download_and_process(urls):
    """
    Downloads each zip file from the list of URLs, extracts the required data using pandas,
    and consolidates it into a single DataFrame.
    
    Parameters:
        urls (List[str]): The list of URLs to download.
        
    Returns:
        pd.DataFrame: The consolidated DataFrame with the required columns.
    """
    consolidated_data = []
    
    for url in tqdm(urls, desc="Processing URLs"):
        try:
            response = requests.get(url, headers=USER_AGENT, timeout=60)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error for {url}: {e}")
            continue
        except requests.exceptions.RequestException as e:
            logger.error(f"Request exception for {url}: {e}")
            continue
        
        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                # Iterate through each file in the zip archive
                for file_info in z.infolist():
                    with z.open(file_info) as f:
                        try:
                            # Read the file content as bytes
                            data = f.read()
                            
                            # Decode with utf-8, ignoring errors
                            try:
                                text = data.decode('utf-8')
                            except UnicodeDecodeError:
                                text = data.decode('latin1')  # or another fallback encoding

                            
                            # Use StringIO to read the string data into pandas
                            s = StringIO(text)
                            
                            # Read the CSV using pandas with '|' as the delimiter
                            df = pd.read_csv(s, sep='|', dtype=str, on_bad_lines='skip')
                            
                            # Check if required columns are present
                            required_columns = ["SETTLEMENT DATE", "CUSIP", "SYMBOL", "DESCRIPTION"]
                            if not all(col in df.columns for col in required_columns):
                                logger.error(f"Missing required columns in {url}. Available columns: {df.columns.tolist()}")
                                continue
                            
                            # Filter the required columns
                            df_filtered = df[required_columns].copy()
                            
                            # Drop rows with any missing required fields
                            df_filtered.dropna(subset=required_columns, inplace=True)
                            
                            # Validate 'SETTLEMENT DATE' format (YYYYMMDD)
                            df_filtered = df_filtered[df_filtered["SETTLEMENT DATE"].str.match(r'^\d{8}$')]
                            
                            # Strip whitespace from DESCRIPTION
                            df_filtered["DESCRIPTION"] = df_filtered["DESCRIPTION"].str.strip()
                            
                            # Append to the consolidated list
                            consolidated_data.append(df_filtered)
                            
                        except pd.errors.ParserError as e:
                            logger.error(f"Pandas parser error for file {file_info.filename} in {url}: {e}")
                            continue
                        except Exception as e:
                            logger.error(f"Error processing file {file_info.filename} in {url}: {e}")
                            continue
        except zipfile.BadZipFile as e:
            logger.error(f"Bad zip file {url}: {e}")
            continue
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            continue
    
    if consolidated_data:
        final_df = pd.concat(consolidated_data, ignore_index=True)
    else:
        # ["SETTLEMENT DATE", "CUSIP", "SYMBOL", "DESCRIPTION"]
        # ["settle_date", "cusip", "ticker", "description"]
        final_df = pd.DataFrame(columns=["SETTLEMENT DATE", "CUSIP", "SYMBOL", "DESCRIPTION"])
    
    return final_df


def sort_and_write(df, output_subdir = "processed"):
    """
    Sorts the DataFrame by SETTLEMENT DATE in descending order and writes
    the data to CSV files organized by YYYYMM in the specified output directory.
    
    Parameters:
        df (pd.DataFrame): The consolidated DataFrame.
        output_dir (str): The directory to save the CSV files.
    """

    # Prep for output files
    if '__file__' in globals():
        output_dir = Path(__file__).resolve().parent / output_subdir
    else:
        output_dir = Path.cwd() / output_subdir

    output_dir.mkdir(parents=True, exist_ok=True)

    # Convert SETTLEMENT DATE to datetime for sorting
    initial_count = len(df)
    df['SETTLEMENT DATE'] = pd.to_datetime(df['SETTLEMENT DATE'], format='%Y%m%d', errors='coerce')
    df = df.dropna(subset=['SETTLEMENT DATE'])
    dropped_count = initial_count - len(df)
    if dropped_count > 0:
        logger.warning(f"Dropped {dropped_count} records due to invalid settlement dates.")

    # Sort descending by SETTLEMENT DATE
    df = df.sort_values(by='SETTLEMENT DATE', ascending=False)
    
    # Add YYYYMM column
    df['YYYYMM'] = df['SETTLEMENT DATE'].dt.strftime('%Y%m')
    
    # Group by YYYYMM and write to CSV
    grouped = df.groupby('YYYYMM')
    for yyyymm, group in tqdm(grouped, desc="Writing CSVs"):
        output_path = output_dir / f"{yyyymm}.csv"
        # Select required columns
        group[['SETTLEMENT DATE', 'CUSIP', 'SYMBOL', 'DESCRIPTION']].to_csv(
            output_path, index=False
        )


def process_year_by_year():
    b_year, e_year = (2024, 2024) # (2004, 2024)
    for year in range(b_year, e_year + 1):
        print("Building list of URLs...")
        urls = build_url_list(start_year=year, end_year=year)
        print(f"Total URLs to process: {len(urls)}")
        
        print("Downloading and processing files...")
        df = download_and_process(urls)
        print(f"Total records collected: {len(df)}")
        
        print("Sorting and writing to CSV...")
        sort_and_write(df)
        print(f"Process completed successfully for {year}\n")


def read_and_prune(source_dir = "processed", target_dir = "final"):

    # Prep for output files
    if '__file__' in globals():
        output_dir = Path(__file__).resolve().parent / target_dir
    else:
        output_dir = Path.cwd() / target_dir
    
    # Create 'final' directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Define source directories
    processed_dir = output_dir.parent / "processed"
    
    # Get list of all CSV files in 'processed' directory
    csv_files = list(processed_dir.glob('*.csv'))
    
    if not csv_files:
        print("No CSV files found in the 'processed' folder.")
        return
    
    # Sort files in descending order based on YYYYMM in filename
    # Assuming filenames are exactly in the format YYYYMM.csv
    try:
        csv_files_sorted = sorted(
            csv_files,
            key=lambda x: int(x.stem),
            reverse=True
        )
    except ValueError:
        print("Filename format incorrect. Ensure filenames are in 'YYYYMM.csv' format.")
        return
    
    # Initialize an empty list to hold DataFrames
    data_frames = []
    
    # Read each CSV file and append to the list
    for file in csv_files_sorted:
        try:
            df = pd.read_csv(file, delimiter=',')
            data_frames.append(df)
            print(f"Loaded {file.name}")
        except Exception as e:
            print(f"Error reading {file.name}: {e}")
    
    if not data_frames:
        print("No data to process after reading files.")
        return
    
    # Concatenate all DataFrames
    concatenated_df = pd.concat(data_frames, ignore_index=True)
    print("All files concatenated.")
    
    # Extract unique [CUSIP, SYMBOL] pairs
    unique_pairs = concatenated_df[['CUSIP', 'SYMBOL']].drop_duplicates()
    print(f"Extracted {len(unique_pairs)} unique [CUSIP, SYMBOL] pairs.")
    
    # Define output file path
    output_file = output_dir / 'cusip-ticker-map.csv'
    
    # Save to CSV without the index
    unique_pairs.to_csv(output_file, index=False)
    unique_pairs.to_json(output_file.with_suffix(".json"), orient='records')
    print(f"Unique pairs saved to {output_file}")


if __name__ == "__main__":
    # process_year_by_year()
    read_and_prune(source_dir = "processed", target_dir = "final")
