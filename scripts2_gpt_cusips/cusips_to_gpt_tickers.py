import csv
import openai
import os

# Set your OpenAI API key from environment variable
openai.api_key = os.getenv("OPENAI_API_KEY")

def get_ticker_from_chatgpt(cusip):
    """
    Retrieves the ticker for a given CUSIP using OpenAI's API.

    Parameters:
        cusip (str): The CUSIP of a common stock security.

    Returns:
        str: The TICKER if retrieved successfully; otherwise, None.
    """

    system_prompt = """You are a helpful assistant that provides the common stock ticker for a given CUSIP.
    Respond with only common stock TICKER corresponding to the CUSIP, without any preamble or discussion. 
    Do not make up a false TICKER.
    If you do not know the answer, respond with 'NONE'."""

    user_prompt = f"What is the latest common stock TICKER for {cusip[:8]}?"

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
        print(f"Error retrieving TICKER for {cusip}: {e}")
        return None


def compile_gpt_ticker_files(merge_list):
    import pandas as pd

   # Concatenate the DataFrames
    combined = pd.DataFrame()
    for i, file_n in enumerate(merge_list):

        combined = pd.concat([combined, pd.read_csv(file_n)], ignore_index=True)

    return combined


def main():
    from pathlib import Path

    # Get the directory where the script is located
    SCRIPT_DIR = Path(__file__).resolve().parent

    # stage for output
    output_dir = SCRIPT_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Compile: grab output from scripts1 folder
    merge_source_dir = SCRIPT_DIR.parent / "scripts1_gpt_cusips" / "output"
    file_names = ["cusip9.csv", "cusip8.csv", "cusip6.csv"]
    merge_list = [merge_source_dir / file_name for file_name in file_names]
    combined = compile_gpt_ticker_files(merge_list)

    output_ticker = output_dir / "cusips_matched_to_gpt_tickers.csv"    # Results of attempted search for tickers given cusips
    output_missing = output_dir / "cusips_missing_gpt_tickers.csv"      # CUSIPS that failed to find corresponding tickers

    # Open all output files once to improve performance
    with open(output_ticker, "w", newline='', encoding='utf-8') as ticker_file, \
         open(output_missing, "w", newline='', encoding='utf-8') as missing_file:
        
        writer_ticker = csv.writer(ticker_file)
        writer_missing = csv.writer(missing_file)

        # Write headers to each CSV
        writer_ticker.writerow(["CUSIP", "Ticker_GPT"])
        writer_missing.writerow(["CUSIP"])

        # Iterate over each cusip in the 'combined' DataFrame
        for row_num, cusip in enumerate(combined['CUSIP_GPT'], start=0):
            if not cusip:
                print(f"Row {row_num}: Empty row skipped.")
                continue  # Skip empty rows

            cusip = cusip.strip().upper()  # Ensure cusip is uppercase and stripped

            print(f"Processing Row {row_num}: cusip = {cusip}")

            # Attempt to get TICKER from ChatGPT
            ticker = get_ticker_from_chatgpt(cusip)
            if ticker != 'NONE':
                writer_ticker.writerow([cusip, ticker])
                print(f"  TICKER found: {ticker}")
                continue  # Move to next cusip

            # If all attempts fail, write to missing.csv
            writer_missing.writerow([cusip])
            print(f"  CUSIP not found. Ticker added to missing.csv.")

if __name__ == "__main__":
    main()
