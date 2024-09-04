#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py

This is the main entry point of the program. It orchestrates the execution of various
tasks by utilizing different modules such as downloading master index data from the SEC,
filtering the index for weblinks to 13D and 13F filings, parsing those filings to extract
a mapping between CIK and CUSIP, and post-processing that data.

Usage:
    Run this script directly to start the program.
"""

import dl_idx
import dl
import parse_cusip_html
import post_proc

def main():

    # 1) Download master indexes: a listing of weblinks to SEC filing documents archived in their EDGAR system (*.idx)
    dl_idx.download_sec_index_files()
    # 2) Filter index for filing documents of user-selected filing type (*.parquet)
    dl_idx.filter_sec_index_of_filings_to_parquet()

    # 3) Download all filing documents listed in filtered index (*.tar.gz)
    dl.main()

    # 4) Parse filings to create mapping between CIK and CUSIP for each filing type (*.csv)
    parse_cusip_html.main()

    # 5) Consolidate and clean CIK-CUSIP (*.csv, *.json)
    post_proc.main()

if __name__ == '__main__':
    main()
