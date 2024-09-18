# CIK-CUSIP-mapping

Forked from [leoliu0/cik-cusip-mapping](https://github.com/leoliu0/cik-cusip-mapping), with originally stated purpose:

This repository produces the link between cik and cusip using EDGAR 13D and 13G fillings, that is more robust than Compustat (due to backward filling of new cusip to old records). It is a competitor to WRDS SEC platform while this one is free.

## This project

Aims to streamline original project: to download, parse, and process SEC filings archives to extract CIK-CUSIP mappings.

## Understanding CIKs, CUSIPs, and Tickers

- **CIK (Central Index Key)**: A globally unique identifier assigned by the SEC to entities filing reports in the EDGAR system. Each company has one CIK used across all its filings, regardless of the number or type of securities.

  *Example*: Apple Inc.'s CIK is 0000320193.

- **CUSIP**: A nine-character alphanumeric code identifying a specific U.S. security (e.g., stocks or bonds). Managed by the American Bankers Association, each CUSIP is unique to a particular security. A company may have multiple CUSIPs for different securities like common stock, bonds, or preferred stock.

  *Example*: Apple Inc.'s common stock CUSIP is 037833100; its bonds have different CUSIPs.

- **Ticker Symbol**: An abbreviation used to identify a company's stock on exchanges like NYSE or NASDAQ. Unique within a specific exchange or country but can be reused internationally.

  *Example*: Apple's NASDAQ ticker is AAPL, but "AAPL" might be used by another company on an exchange outside the U.S.

**Summary**: The CIK uniquely identifies the entity with the SEC, while its individual securities are uniquely identified by their CUSIPs.

---

## When might a company's CUSIP change?

A company's CUSIP for its common stock typically changes due to:

- **Corporate Actions**: Mergers, acquisitions, spinoffs, or significant restructurings that create new legal entities generally result in new CUSIPs.

- **Stock Splits**: Forward stock splits with a mandatory exchange of shares and reverse stock splits usually lead to new CUSIPs.

- **Name Changes**:
  - *Before October 2021*: Name changes typically resulted in new CUSIPs for equity securities.
  - *After October 2021*: Under the "CUSIP Permanence" policy, CUSIPs for equity securities no longer change solely due to a name change.

  *Source*: [CUSIP Global Services Permanence FAQ](https://www.cusip.com/pdf/news/CUSIPGlobalServices-Permanence-FAQ.pdf)

**Key Considerations**:

- The first six digits of a CUSIP identify the company; digits 7–8 identify the specific security.

- CUSIP Global Services manages changes, creating 1,000 to 2,000 new identifiers daily.

- For most investors, CUSIP changes are not a significant concern; they are primarily used by brokerage and clearing firms for transaction settlement and record-keeping.

**Note**: While these guidelines generally apply, exceptions may occur depending on specific corporate actions or regulatory requirements.

## Modules

### `main_parameters.py`

- Defines global configuration settings

### `main.py`

- Entry point for program execution
- Orchestrates workflow across modules

### `dl_idx.py`

- Downloads *reference data* (SEC's master index archive) to archived SEC filing documents

### `dl.py`

- Handles downloads of *SEC filings*, based on references sourced from the master index archive.

### `parse_cusip_html.py`

- Extracts CIK-CUSIP pairs (mappings) from the SEC filings by scraping their HTML-like stucture.

### `post_proc.py`

- Performs light data cleaning and pruning of CIK-CUSIP mappings. Exports as CSV and JSON.

## Workflow

1) Set parameters in `main_parameters.py`
2) Execute `main.py` which will:

- Download data using `dl_idx.py` (master index) and `dl.py` (SEC filings, type 13D and 13G)
- Parse CIK-CUSIP mappings with `parse_cusip_html.py` from SEC filings
- Lightly prune mappings results using `post_proc.py`

### Dependencies

- pathlib's Path  # For handling and manipulating filesystem paths
- re  # For regular expressions, useful in pattern matching and text processing
- time  # For time-related functions such as sleeping or measuring durations
- datetime  # For handling dates and times
- csv  # For reading from and writing to CSV files
- requests  # For making HTTP requests, useful for downloading data from the web
- collections  # For specialized container datatypes (e.g., namedtuple, deque)
- multiprocessing's Pool  # For parallel processing using multiple processes
- pandas  # For data manipulation and analysis

MIT License
Copyright (c) [2024] [@flatly1140]
