# Personal Oura exporter

## Description

Exports the following fields to a CSV file:

- Date
- Readiness Score
- Sleep Score
- Lowest Resting HR
- Average HRV
- SpO2 (%)
- Breathing Disturbance Index
- Sleep Efficiency (%)
- Restless Periods
- Respiratory Rate
- Activity Score
- Time in Bed (min)
- Sleep Time (min)
- Latency (min)
- Awake Time (min)
- Deep Sleep (min)
- REM Sleep (min)

Dates are written as mm/dd/yyyy; existing CSV dates may be
either yyyy-mm-dd or mm/dd/yyyy.

By default retrieves the last 30 days, ignoring days
that already have complete data in the CSV.

This behavior can be overridden using

- `-f` or `--file` - set the CSV file to use (default `oura.csv`)
- `-n` or `--num_days` - set the number of days to include relative to end date (default is 30)
- `-s` or `--start_date` - sets the start date in yyyy-mm-dd or mm/dd/yyyy format (overrides `--num_days`)
- `-e` or `--end_date` - sets the inclusive end date in yyyy-mm-dd or mm/dd/yyyy format (default today)
- `--force` - ignore existing data
- `--exclude_empty` - skip days with no data
- `--debug` - print the raw sleep API response for the most recent day and exit

## Instructions

1. Create application and credentials on http://developer.ouraring.com
2. Set redirect URI to http://localhost:8080/callback
3. Create `.env` file with `CLIENT_ID` and `CLIENT_SECRET` variables
4. Install Python and create VM
5. Run `pip install -r requirements.txt` in VM
6. Run `python main.py`