
from pathlib import Path
import datetime as datetime


# Get the directory where the current script is located
SCRIPT_DIR = Path(__file__).resolve().parent.parent

# Default starting point for raw file downloads
# START_YEAR, START_QUARTER = (1994, 1)
# CURRENT_YEAR, CURRENT_QUARTER = (2023, 4)
# DATA_FOLDER = SCRIPT_DIR / "data_dir_prior"

START_YEAR, START_QUARTER = (2024, 3)
CURRENT_YEAR, CURRENT_QUARTER     = (datetime.datetime.now().year, (datetime.datetime.now().month - 1) // 3 + 1)
DATA_FOLDER = SCRIPT_DIR / "data_dir"

# Repo for all intermediate and final files from the SEC's EDGAR system
DATA_FOLDER.mkdir(parents=True, exist_ok=True)

DATA_RAW        = DATA_FOLDER / "raw_downloads"
DATA_PROCESSED  = DATA_FOLDER / "processed"
DATA_FINAL      = DATA_FOLDER / "final"


# EDGAR filings to process (str or List[str])
FILING_TYPES           =  ["13D", "13G"]
# FILING_TYPES           =  ["10-K", "10-Q"]
INDEX_PREFIX = "edgar_index"
# Filename for the raw (intermediate) EDGAR master file (a text file)
RAW_INDEX_FILE          = (DATA_RAW / INDEX_PREFIX).with_suffix(".tar.gz")
# Filename for the EDGAR archive download, compressed as an index Parquet file (for fast columnar retrieval)
FILTERED_INDEX_FILE      = (DATA_PROCESSED / INDEX_PREFIX).with_suffix(".parquet")
# Filename for list of failed filings downloads
FAILED_DOWNLOADS_FILE   = DATA_FINAL / "failed_downloads_list.txt"


# URL-PREFIX TO EDGAR ARCHIVES
SEC_URL_PREFIX  = "https://www.sec.gov/Archives/"
# Rate-request limit (number of requests per second), required by EDGAR
SEC_RATE_LIMIT      = 9.5
# User-agent header required by EDGAR
USER_AGENT      = {
   'User-Agent': "Fingage samer.habl@fingage.com",  # 'ACME Co jane.doe@acme.co',
  'Accept-Encoding': 'deflate',
  'Host': 'www.sec.gov'
}


"""
This following defines regular expressions used to process SEC filings from EDGAR
"""

import re

RX_GET_TEXT = re.compile(r'.*?\.txt')

RX_CLEAN_HTML = re.compile(r'<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});')
# This regex matches and can be used to remove HTML tags and entities:
# - '<.*?>' matches any HTML tag (opening or closing)
# - '&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});' matches HTML entities like &amp; or &#123;

RX_GET_CUSIP = re.compile(r'[\( >]*[0-9A-Z]{1}[0-9]{3}[0-9A-Za-z]{2}[- ]*[0-9]{0,2}[- ]*[0-9]{0,1}[\) \n<]*')
# This pattern would match:
# - CUSIP-6 codes (first 6 characters)
# - CUSIP-8 codes (all 8 characters)
# - Slight variations in formatting (spaces, hyphens, parentheses)
# - Codes embedded in larger text (due to the optional characters before and after)

RX_GET_WORDCHARS = re.compile(r'\w+')
# This simple regex matches one or more word characters (letters, digits, or underscores)
# It can be used to extract words from a string

RX_HTML_JUNK = re.compile(r'''["].*["]|=#.*\d+''')
# This regex matches two patterns:
# - Anything enclosed in double quotes
# - Or a string starting with '=#', followed by any characters and ending with one or more digits
# It might be used to remove certain attributes or values from HTML-like content
