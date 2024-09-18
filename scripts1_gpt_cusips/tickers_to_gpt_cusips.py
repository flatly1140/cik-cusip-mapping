#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
import sys
import csv
import openai
import os

"""
This script retrieves ticker-CIK pairs from the SEC’s website and filters it for relevant pairs, based on ticker symbols
contained in a "missingCusips" CSV file.

It then attempts to retrieve the corresponding CUSIPs using OpenAI's API.

The results are recorded in different CSV files based on the CUSIP length (9, 8, or 6 digits), and any tickers for which
a CUSIP is not found are logged in a separate "stillMissing" CSV file.
"""

# Set your OpenAI API key from environment variable
openai.api_key = os.getenv("OPENAI_API_KEY")

def fetch_ticker_cik_mapping(url="https://www.sec.gov/include/ticker.txt"):
    """
    Fetches the ticker to CIK mapping from the SEC's website.

    Args:
        url (str): URL to the ticker-CIK mapping file.

    Returns:
        dict: A dictionary mapping ticker symbols to CIKs.
    """
    headers = {
        "User-Agent": "Fingage, samer.habl@fingage.com"  # Replace with your information
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an error for bad status codes
        mapping = {}
        for line in response.text.strip().splitlines():
            ticker, cik = line.strip().split('\t')
            mapping[ticker.upper()] = cik
        return mapping
    except requests.exceptions.RequestException as e:
        print(f"Error fetching ticker-CIK mapping: {e}")
        sys.exit(1)


def get_cik_from_mapping(ticker, mapping):
    """
    Retrieves the CIK for a given ticker from the mapping.

    Args:
        ticker (str): The stock ticker symbol.
        mapping (dict): The ticker to CIK mapping.

    Returns:
        str or None: The 10-digit CIK if found, else None.
    """
    ticker = ticker.upper()
    cik = mapping.get(ticker)
    if cik:
        return cik.zfill(10)  # Pad with leading zeros to make it 10 digits
    else:
        return None


def get_cusip_from_chatgpt(ticker, cusip_length):
    """
    Retrieves the CUSIP code of the specified length for a given ticker using OpenAI's API.

    Parameters:
        ticker (str): The stock ticker symbol.
        cusip_length (int): The desired length of the CUSIP code (9, 8, or 6).

    Returns:
        str: The CUSIP code if retrieved successfully; otherwise, None.
    """
    system_prompt = f"""You are a helpful assistant that provides the official CUSIP{cusip_length} codes for stock tickers.
    Respond with only the CUSIP{cusip_length} code, without any preamble or discussion. 
    Do not make up false cusips. 
    If you do not know the answer, respond with ''."""

    user_prompt = f"What is the CUSIP{cusip_length} for {ticker}?"

    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=20,
            n=1,
            stop=None,
            temperature=0
        )
        cusip = response.choices[0].message.content.strip()
        return cusip
    except Exception as e:
        print(f"Error retrieving CUSIP{cusip_length} for {ticker}: {e}")
        return None

def main():
    from pathlib import Path
    # Get the directory where the current script is located
    SCRIPT_DIR = Path(__file__).resolve().parent

    # stage for output
    output_dir = SCRIPT_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    input_file = SCRIPT_DIR / "tickers_needing_cusips.csv"
    
    output_cusip9 = output_dir / "cusip9.csv"
    output_cusip8 = output_dir / "cusip8.csv"
    output_cusip6 = output_dir / "cusip6.csv"
    output_missing = output_dir / "tickers_missing_gpt_cusips.csv"

    # Open all output files once to improve performance
    with open(input_file, "r", newline='', encoding='utf-8') as infile, \
         open(output_cusip9, "w", newline='', encoding='utf-8') as c9_file, \
         open(output_cusip8, "w", newline='', encoding='utf-8') as c8_file, \
         open(output_cusip6, "w", newline='', encoding='utf-8') as c6_file, \
         open(output_missing, "w", newline='', encoding='utf-8') as missing_file:

        reader = csv.reader(infile)
        
        writer_cusip9 = csv.writer(c9_file)
        writer_cusip8 = csv.writer(c8_file)
        writer_cusip6 = csv.writer(c6_file)
        writer_missing = csv.writer(missing_file)
        
        # Write headers to each CSV
        writer_cusip9.writerow(["Ticker", "CIK", "CUSIP_GPT"])
        writer_cusip8.writerow(["Ticker", "CIK", "CUSIP_GPT"])
        writer_cusip6.writerow(["Ticker", "CIK", "CUSIP_GPT"])
        writer_missing.writerow(["Ticker", "CIK"])

        mapping = fetch_ticker_cik_mapping()
        
        # Iterate over each ticker in the input file
        for row_num, row in enumerate(reader, start=0):
            # if row_num >= 5:  # testing
            #     break

            if not row:
                print(f"Row {row_num}: Empty row skipped.")
                continue  # Skip empty rows

            ticker = row[0].strip().upper()  # Ensure ticker is uppercase and stripped

            cik = get_cik_from_mapping(ticker, mapping)          # plucks the cik from sec's ticker mapping file

            if not ticker:
                print(f"Row {row_num}: Empty ticker skipped.")
                continue  # Skip rows with empty ticker

            print(f"Processing Row {row_num}: Ticker = {ticker}")

            # Attempt to get CUSIP9
            cusip9 = get_cusip_from_chatgpt(ticker, 9)
            if cusip9 and len(cusip9) == 9:
                writer_cusip9.writerow([ticker, cik, cusip9])
                print(f"  CUSIP9 found: {cusip9}")
                continue  # Move to next ticker

            # Attempt to get CUSIP8
            cusip8 = get_cusip_from_chatgpt(ticker, 8)
            if cusip8 and len(cusip8) == 8:
                writer_cusip8.writerow([ticker, cik, cusip8])
                print(f"  CUSIP8 found: {cusip8}")
                continue  # Move to next ticker

            # Attempt to get CUSIP6
            cusip6 = get_cusip_from_chatgpt(ticker, 6)
            if cusip6 and len(cusip6) == 6:
                writer_cusip6.writerow([ticker, cik, cusip6])
                print(f"  CUSIP6 found: {cusip6}")
                continue  # Move to next ticker

            # If all attempts fail, write to missing.csv
            writer_missing.writerow([ticker, cik])
            print(f"  CUSIP not found. Ticker added to missing.csv.")

if __name__ == "__main__":
    main()
