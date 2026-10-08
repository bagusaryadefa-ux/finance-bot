import json
import base64
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timezone
import pytz

from bot.config import GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID, TIMEZONE

# Indonesian month names
MONTH_NAMES = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
               "Juli", "Agustus", "September", "Oktober", "November", "Desember"]

def get_gspread_client():
    if not GOOGLE_CREDENTIALS_JSON:
        print("Missing GOOGLE_CREDENTIALS_JSON")
        return None

    try:
        # Check if it's base64 encoded by trying to decode it
        try:
            creds_data = json.loads(base64.b64decode(GOOGLE_CREDENTIALS_JSON).decode('utf-8'))
        except (ValueError, TypeError, base64.binascii.Error):
            # Fallback to string if not base64
            creds_data = json.loads(GOOGLE_CREDENTIALS_JSON)

        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_data, scopes)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"Error authenticating with Google Sheets: {e}")
        return None

def get_current_time():
    tz = pytz.timezone(TIMEZONE)
    return datetime.now(tz)

def get_sheet_name(dt: datetime):
    month_name = MONTH_NAMES[dt.month - 1]
    return f"{month_name} {dt.year}"

def ensure_month_sheet(client, sh, target_sheet_name: str):
    """
    Ensure the target_sheet_name exists.
    If not, create it. Additionally, if there are previous month sheets, calculate summary for the most recent one.
    """
    worksheets = sh.worksheets()
    worksheet_titles = [ws.title for ws in worksheets]

    if target_sheet_name in worksheet_titles:
        return sh.worksheet(target_sheet_name)

    # Sheet does not exist, meaning we've entered a new month (or it's the very first time).
    # Create the new sheet
    new_ws = sh.add_worksheet(title=target_sheet_name, rows="1000", cols="6")

    # Set headers
    headers = ["Tanggal & Waktu", "Tipe", "Nominal", "Keterangan", "Link Bukti"]
    new_ws.append_row(headers)

    # Format headers to bold (optional, can be skipped for simplicity/speed)

    # -------------------------------------------------------------
    # Auto-summary for the previous sheets if they exist and haven't been summarized
    # This requires looking for the previous month's sheet, calculating total and appending a row.
    # -------------------------------------------------------------
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    # Simple heuristic: Just calculate summary for all sheets except the new one,
    # if they don't already have 'TOTAL PEMASUKAN' at the bottom.
    for ws in worksheets:
        # Avoid running on the newly created sheet
        if ws.title == target_sheet_name: continue

        # We don't read the whole sheet to save API quota, just the last rows,
        # but to sum properly we need all values or at least column C & B.
        try:
            records = ws.get_all_records()
            if not records:
                continue

            # Check if summary already exists by checking the last row
            # Usually cell (last_row, Tipe) or (last_row, Keterangan) might say "TOTAL PEMASUKAN"
            last_record = records[-1]
            if "TOTAL" in str(last_record.get('Tipe', '')).upper() or "TOTAL" in str(last_record.get('Keterangan', '')).upper() or "TOTAL" in str(last_record.get('Tanggal & Waktu', '')).upper():
                continue # Already summarized

            pemasukan = 0
            pengeluaran = 0
            for row in records:
                # Row format depends on header
                tipe = str(row.get('Tipe', '')).upper()
                nominal_str = str(row.get('Nominal', '0')).replace('.', '').replace(',', '')
                try:
                    nominal = int(nominal_str)
                    if tipe == 'MASUK':
                        pemasukan += nominal
                    elif tipe == 'KELUAR':
                        pengeluaran += nominal
                except ValueError:
                    pass

            selisih = pemasukan - pengeluaran

            # Append empty row as separator
            ws.append_row(["", "", "", "", ""])

            # Append summary rows
            ws.append_row(["", "TOTAL PEMASUKAN", str(pemasukan), "", ""])
            ws.append_row(["", "TOTAL PENGELUARAN", str(pengeluaran), "", ""])
            ws.append_row(["", "SISA SALDO (SELISIH)", str(selisih), "", ""])

        except Exception as e:
            print(f"Error generating summary for {ws.title}: {e}")

    return new_ws

def add_transaction(tipe: str, nominal: int, keterangan: str, link_bukti: str = ""):
    client = get_gspread_client()
    if not client:
        return False

    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        now = get_current_time()
        sheet_name = get_sheet_name(now)

        ws = ensure_month_sheet(client, sh, sheet_name)

        row = [
            now.strftime("%Y-%m-%d %H:%M:%S"),
            "Masuk" if tipe == "masuk" else "Keluar",
            nominal,
            keterangan,
            link_bukti
        ]

        ws.append_row(row)
        return True
    except Exception as e:
        print(f"Error adding transaction: {e}")
        return False

def get_current_month_summary():
    client = get_gspread_client()
    if not client:
        return None

    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        now = get_current_time()
        sheet_name = get_sheet_name(now)

        try:
            ws = sh.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            # Sheet not found, meaning 0 balance
            return 0, 0, 0

        records = ws.get_all_records()
        pemasukan = 0
        pengeluaran = 0

        for row in records:
            tipe = str(row.get('Tipe', '')).upper()

            # Stop if we hit a summary row
            if "TOTAL" in tipe or "TOTAL" in str(row.get('Keterangan', '')).upper():
                break

            nominal_str = str(row.get('Nominal', '0')).replace('.', '').replace(',', '')
            try:
                nominal = int(float(nominal_str))
                if tipe == 'MASUK':
                    pemasukan += nominal
                elif tipe == 'KELUAR':
                    pengeluaran += nominal
            except ValueError:
                pass

        selisih = pemasukan - pengeluaran
        return pemasukan, pengeluaran, selisih
    except Exception as e:
        print(f"Error getting summary: {e}")
        return None

def get_all_data():
    """Fetches all history across all sheets for stats/graphs."""
    client = get_gspread_client()
    if not client:
        return []
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        worksheets = sh.worksheets()
        all_transactions = []

        for ws in worksheets:
            try:
                records = ws.get_all_records()
                for row in records:
                    t = str(row.get('Tipe', '')).upper()
                    # Skip summary rows or empty rows
                    if "TOTAL" in t or "TOTAL" in str(row.get('Keterangan', '')).upper():
                        continue
                    if t not in ["MASUK", "KELUAR"]:
                        continue

                    date_val = str(row.get('Tanggal & Waktu', ''))
                    nom_val = str(row.get('Nominal', '0')).replace('.', '').replace(',', '')
                    if date_val and nom_val.isdigit():
                        all_transactions.append({
                            "date": date_val,
                            "tipe": t,
                            "nominal": int(nom_val)
                        })
            except Exception:
                pass
        return all_transactions
    except Exception as e:
        print(e)
        return []
