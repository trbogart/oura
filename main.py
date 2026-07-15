import csv
import json
import os
import secrets
import webbrowser
from argparse import ArgumentParser
from datetime import date, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs

import requests
from dotenv import load_dotenv

AUTH_URL = 'https://cloud.ouraring.com/oauth/authorize'
TOKEN_URL = 'https://api.ouraring.com/oauth/token'
API_BASE = 'https://api.ouraring.com/v2/usercollection'
REDIRECT_URI = 'http://localhost:8080/callback'
TOKEN_FILE = '.oura_token.json'

default_export_file = 'oura.csv'
default_max_days = 30

FIELDNAMES = [
    'Date', 'Readiness Score', 'Sleep Score', 'Sleep Time (min)',
    'Deep Sleep (min)', 'REM Sleep (min)', 'Lowest Resting HR', 'Average HRV',
    'SpO2 (%)', 'Breathing Disturbance Index',
]


class _CallbackHandler(BaseHTTPRequestHandler):
    code = None

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        if 'code' in params:
            _CallbackHandler.code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(
                b'<html><body><h1>Authorization successful!</h1><p>You can close this window.</p></body></html>')
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        pass


class Exporter:
    def __init__(self, export_file: str, client_id: str, client_secret: str, max_days: int = 1,
                 start_date: date | None = None, end_date: date | None = None):
        self.export_file = export_file
        self.client_id = client_id
        self.client_secret = client_secret

        if end_date is None:
            end_date = date.today()

        if start_date is None:
            last_date = end_date - timedelta(days=max_days)
            if os.path.exists(export_file):
                with open(export_file, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        day = date.fromisoformat(row['Date'])
                        complete = all(row.get(f) for f in FIELDNAMES[1:])
                        if complete and day > last_date:
                            last_date = day
            start_date = last_date + timedelta(days=1)

        if start_date > end_date:
            print("No new data to export.")
            return

        token = self._authenticate()
        rows = self._fetch_data(token, start_date, end_date)
        self._write_csv(rows)
        print(f"Exported {len(rows)} rows to {self.export_file}")

    def _authenticate(self):
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as f:
                token = json.load(f)
            if 'refresh_token' in token:
                refreshed = self._refresh_token(token['refresh_token'])
                if refreshed:
                    return refreshed
        return self._oauth_flow()

    def _oauth_flow(self):
        state = secrets.token_urlsafe(16)
        auth_url = AUTH_URL + '?' + urlencode({
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': REDIRECT_URI,
            'scope': 'daily sleep spo2',
            'state': state,
        })
        print("Opening browser for Oura authorization...")
        webbrowser.open(auth_url)

        _CallbackHandler.code = None
        server = HTTPServer(('localhost', 8080), _CallbackHandler)
        while _CallbackHandler.code is None:
            server.handle_request()

        response = requests.post(TOKEN_URL, data={
            'grant_type': 'authorization_code',
            'code': _CallbackHandler.code,
            'redirect_uri': REDIRECT_URI,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        })
        response.raise_for_status()
        token = response.json()
        self._save_token(token)
        return token

    def _refresh_token(self, refresh_token: str):
        try:
            response = requests.post(TOKEN_URL, data={
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
            })
            response.raise_for_status()
            token = response.json()
            self._save_token(token)
            return token
        except Exception:
            return None

    def _save_token(self, token: dict):
        with open(TOKEN_FILE, 'w') as f:
            json.dump(token, f)

    def _api_get(self, token: dict, endpoint: str, params: dict) -> dict:
        headers = {'Authorization': f"Bearer {token['access_token']}"}
        response = requests.get(f"{API_BASE}/{endpoint}", headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    def _fetch_data(self, token: dict, start_date: date, end_date: date) -> list[dict]:
        params = {'start_date': start_date.isoformat(), 'end_date': end_date.isoformat()}

        readiness = {r['day']: r for r in self._api_get(token, 'daily_readiness', params).get('data', [])}
        sleep_scores = {r['day']: r for r in self._api_get(token, 'daily_sleep', params).get('data', [])}
        spo2 = {r['day']: r for r in self._api_get(token, 'daily_spo2', params).get('data', [])}

        # Pick the longest sleep session per day (type=long_sleep preferred)
        sleep_sessions: dict[str, dict] = {}
        for s in self._api_get(token, 'sleep', params).get('data', []):
            day = s.get('day')
            if not day:
                continue
            existing = sleep_sessions.get(day)
            prefer = (
                    existing is None
                    or (s.get('type') == 'long_sleep' and existing.get('type') != 'long_sleep')
                    or (s.get('type') == existing.get('type')
                        and (s.get('total_sleep_duration') or 0) > (existing.get('total_sleep_duration') or 0))
            )
            if prefer:
                sleep_sessions[day] = s

        def mins(seconds):
            return round(seconds / 60) if seconds is not None else None

        rows = []
        current = start_date
        while current <= end_date:
            day = current.isoformat()
            r = readiness.get(day, {})
            sc = sleep_scores.get(day, {})
            sl = sleep_sessions.get(day, {})
            sp = spo2.get(day, {})

            rows.append({
                'Date': day,
                'Readiness Score': r.get('score'),
                'Sleep Score': sc.get('score'),
                'Sleep Time (min)': mins(sl.get('total_sleep_duration')),
                'Deep Sleep (min)': mins(sl.get('deep_sleep_duration')),
                'REM Sleep (min)': mins(sl.get('rem_sleep_duration')),
                'Average HRV': sl.get('average_hrv'),
                'Lowest Resting HR': sl.get('lowest_heart_rate'),
                'SpO2 (%)': sp.get('spo2_percentage', {}).get('average'),
                'Breathing Disturbance Index': sp.get('breathing_disturbance_index'),
            })
            current += timedelta(days=1)

        return rows

    def _write_csv(self, new_rows: list[dict]):
        new_dates = {r['Date'] for r in new_rows}
        existing_rows = []
        if os.path.exists(self.export_file):
            with open(self.export_file, 'r') as f:
                for row in csv.DictReader(f):
                    if row['Date'] not in new_dates:
                        existing_rows.append(row)

        all_rows = sorted(existing_rows + new_rows, key=lambda r: r['Date'])
        with open(self.export_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(all_rows)


if __name__ == '__main__':
    load_dotenv()
    client_id = os.getenv('CLIENT_ID')
    client_secret = os.getenv('CLIENT_SECRET')
    if not client_id or not client_secret:
        raise SystemExit("CLIENT_ID and CLIENT_SECRET must be set in .env")

    parser = ArgumentParser('Personal Oura Data Exporter')
    parser.add_argument('-f', '--file', default=default_export_file,
                        help=f'Export file (default {default_export_file})')
    parser.add_argument('-n', '--max_days', type=int, default=default_max_days,
                        help=f'Maximum days to export (default {default_max_days})')
    parser.add_argument('-s', '--start_date', type=date.fromisoformat,
                        help=f'Start date in yyyy-mm-hh format (optional)')
    parser.add_argument('-e', '--end_date', type=date.fromisoformat, help=f'End date in yyyy-mm-hh format (optional)')
    parser.add_argument('--debug', action='store_true',
                        help='Print raw sleep API response for the most recent day and exit')
    args = parser.parse_args()

    if args.debug:
        from pprint import pprint

        exp = object.__new__(Exporter)
        exp.client_id = client_id
        exp.client_secret = client_secret
        token = exp._authenticate()
        start = date.today() - timedelta(days=7)
        raw = exp._api_get(token, 'sleep', {'start_date': start.isoformat(), 'end_date': date.today().isoformat()})
        pprint(raw)
    else:
        Exporter(args.file, client_id, client_secret, args.max_days, args.start_date, args.end_date)
