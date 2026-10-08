import re
import httpx
from datetime import datetime

from bot.config import TELEGRAM_TOKEN, ALLOWED_USER_ID, TIMEZONE
from bot.supabase_client import get_user_state, set_user_state, upload_proof
from bot.sheets import add_transaction, get_current_month_summary
from bot.charts import generate_weekly_chart, generate_monthly_chart
import pytz

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

async def send_message(chat_id: int, text: str, reply_markup: dict = None):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)

async def send_photo(chat_id: int, photo_bytes: bytes, caption: str = ""):
    url = f"{TELEGRAM_API_URL}/sendPhoto"
    files = {'photo': ('chart.png', photo_bytes, 'image/png')}
    data = {'chat_id': chat_id, 'caption': caption}
    async with httpx.AsyncClient() as client:
        await client.post(url, data=data, files=files)

async def get_file_bytes(file_id: str) -> bytes:
    # 1. Get file path
    url = f"{TELEGRAM_API_URL}/getFile?file_id={file_id}"
    async with httpx.AsyncClient() as client:
        res = await client.get(url)
        data = res.json()
        if not data.get("ok"):
            return b""

        file_path = data["result"]["file_path"]

        # 2. Download file
        download_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        file_res = await client.get(download_url)
        return file_res.content

def build_inline_keyboard(buttons_layout):
    inline_keyboard = []
    for row in buttons_layout:
        keyboard_row = []
        for text, callback_data in row:
            keyboard_row.append({"text": text, "callback_data": callback_data})
        inline_keyboard.append(keyboard_row)
    return {"inline_keyboard": inline_keyboard}

async def process_update(update: dict):
    # Check if message
    if "message" in update:
        message = update["message"]
        chat_id = message["chat"]["id"]
        # Security Check
        if chat_id != ALLOWED_USER_ID:
            # Silently ignore unauthorized users
            return

        text = message.get("text", "").strip()
        photo = message.get("photo")

        state_entry = await get_user_state(chat_id)
        current_state = state_entry.get("state", "idle")
        state_data = state_entry.get("data", {})

        # ----------------------------------------------------
        # Handle Commands
        # ----------------------------------------------------
        if text.startswith("/start"):
            await send_message(chat_id, "Halo! Saya adalah Asisten Keuangan Pribadi Anda.\n\nGunakan /masuk untuk mencatat pemasukan.\nGunakan /keluar untuk mencatat pengeluaran.\nGunakan /summary untuk melihat ringkasan bulan ini.\nGunakan /statistik untuk melihat grafik.")
            await set_user_state(chat_id, "idle")
            return

        elif text.startswith("/masuk") or text.startswith("/keluar"):
            trans_type = "masuk" if text.startswith("/masuk") else "keluar"
            await set_user_state(chat_id, "wait_amount", {"type": trans_type})
            await send_message(chat_id, "Jumlah:")
            return

        elif text.startswith("/summary"):
            summary_data = get_current_month_summary()
            if summary_data:
                pemasukan, pengeluaran, selisih = summary_data
                msg = f"📊 *Ringkasan Bulan Ini*\n\n"
                msg += f"🟢 Total Pemasukan: Rp {pemasukan:,}\n"
                msg += f"🔴 Total Pengeluaran: Rp {pengeluaran:,}\n"
                msg += f"💰 Sisa Saldo: Rp {selisih:,}"
                await send_message(chat_id, msg)
            else:
                await send_message(chat_id, "Belum ada data di bulan ini.")
            await set_user_state(chat_id, "idle")
            return

        elif text.startswith("/statistik"):
            kb = build_inline_keyboard([
                [("📅 Mingguan", "stat_mingguan"), ("📊 Bulanan", "stat_bulanan")]
            ])
            await send_message(chat_id, "Pilih jenis statistik:", reply_markup=kb)
            await set_user_state(chat_id, "idle")
            return

        # ----------------------------------------------------
        # Handle States
        # ----------------------------------------------------
        if current_state == "wait_amount":
            # Clean non-digit chars but keep logic simple
            clean_amount = re.sub(r"[^\d]", "", text)
            if not clean_amount.isdigit():
                await send_message(chat_id, "Mohon masukkan angka yang valid untuk jumlah:")
                return

            state_data["amount"] = int(clean_amount)
            await set_user_state(chat_id, "wait_desc", state_data)
            await send_message(chat_id, "Keterangan:")
            return

        elif current_state == "wait_desc":
            state_data["desc"] = text
            await set_user_state(chat_id, "wait_proof_ask", state_data)

            kb = build_inline_keyboard([
                [("Ya", "bukti_ya"), ("Tidak", "bukti_tidak")]
            ])
            await send_message(chat_id, "Bukti?", reply_markup=kb)
            return

        elif current_state == "wait_proof_upload":
            if not photo:
                await send_message(chat_id, "Harap kirimkan foto sebagai bukti.")
                return

            # Get highest resolution photo
            best_photo = photo[-1]
            file_id = best_photo["file_id"]

            await send_message(chat_id, "Sedang mengunggah bukti...")

            photo_bytes = await get_file_bytes(file_id)
            if photo_bytes:
                # Generate unique filename
                ext = "jpg"
                filename = f"{chat_id}_{int(datetime.now().timestamp())}.{ext}"

                proof_url = await upload_proof(photo_bytes, filename)

                # Save to sheet
                ok = add_transaction(
                    tipe=state_data.get("type"),
                    nominal=state_data.get("amount"),
                    keterangan=state_data.get("desc"),
                    link_bukti=proof_url
                )

                if ok:
                    tipe_str = "pemasukan" if state_data.get("type") == "masuk" else "pengeluaran"
                    await send_message(chat_id, f"{tipe_str} sudah dicatat")
                else:
                    await send_message(chat_id, "Gagal mencatat ke Google Sheets.")
            else:
                await send_message(chat_id, "Gagal mengunduh foto dari Telegram.")

            await set_user_state(chat_id, "idle")
            return

        elif current_state == "wait_stat_year":
            if not text.isdigit() or len(text) != 4:
                await send_message(chat_id, "Mohon masukkan tahun dengan 4 angka valid (misal: 2026):")
                return

            year = int(text)
            await send_message(chat_id, f"Mempersiapkan grafik bulanan tahun {year}...")

            chart_bytes = generate_monthly_chart(target_year=year)
            if chart_bytes:
                await send_photo(chat_id, chart_bytes, caption=f"Statistik Bulanan {year}")
            else:
                await send_message(chat_id, "Tidak ada data untuk ditampilkan.")

            await set_user_state(chat_id, "idle")
            return

    # Check if Callback Query (Inline Button Click)
    elif "callback_query" in update:
        cb = update["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        data = cb["data"]

        if chat_id != ALLOWED_USER_ID:
            return

        state_entry = await get_user_state(chat_id)
        current_state = state_entry.get("state", "idle")
        state_data = state_entry.get("data", {})

        # Answer callback to remove loading state
        async with httpx.AsyncClient() as client:
            await client.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json={"callback_query_id": cb["id"]})

        if current_state == "wait_proof_ask":
            if data == "bukti_tidak":
                # Save immediately without photo
                ok = add_transaction(
                    tipe=state_data.get("type"),
                    nominal=state_data.get("amount"),
                    keterangan=state_data.get("desc"),
                    link_bukti=""
                )

                if ok:
                    tipe_str = "pemasukan" if state_data.get("type") == "masuk" else "pengeluaran"
                    await send_message(chat_id, f"{tipe_str} sudah dicatat")
                else:
                    await send_message(chat_id, "Gagal mencatat ke Google Sheets.")

                await set_user_state(chat_id, "idle")

            elif data == "bukti_ya":
                await set_user_state(chat_id, "wait_proof_upload", state_data)
                await send_message(chat_id, "Silakan kirimkan foto sebagai bukti:")

        # Statistik callbacks
        elif data == "stat_mingguan":
            kb = build_inline_keyboard([
                [("🌐 Keseluruhan", "stat_minggu_all"), ("📆 Bulan Ini", "stat_minggu_now")]
            ])
            await send_message(chat_id, "Pilih periode mingguan:", reply_markup=kb)

        elif data == "stat_bulanan":
            kb = build_inline_keyboard([
                [("🗓️ Tahun", "stat_bulan_year"), ("🌐 Keseluruhan", "stat_bulan_all")]
            ])
            await send_message(chat_id, "Pilih periode bulanan:", reply_markup=kb)

        elif data == "stat_minggu_all":
            await send_message(chat_id, "Mempersiapkan grafik keseluruhan mingguan...")
            chart_bytes = generate_weekly_chart(month_only=False)
            if chart_bytes:
                await send_photo(chat_id, chart_bytes, caption="Statistik Mingguan Keseluruhan")
            else:
                await send_message(chat_id, "Tidak ada data untuk ditampilkan.")

        elif data == "stat_minggu_now":
            await send_message(chat_id, "Mempersiapkan grafik mingguan bulan ini...")
            now = datetime.now(pytz.timezone(TIMEZONE))
            chart_bytes = generate_weekly_chart(month_only=True, target_month=now.month, target_year=now.year)
            if chart_bytes:
                await send_photo(chat_id, chart_bytes, caption=f"Statistik Mingguan (Bulan Ini)")
            else:
                await send_message(chat_id, "Tidak ada data untuk ditampilkan.")

        elif data == "stat_bulan_all":
            await send_message(chat_id, "Mempersiapkan grafik keseluruhan bulanan...")
            chart_bytes = generate_monthly_chart()
            if chart_bytes:
                await send_photo(chat_id, chart_bytes, caption="Statistik Bulanan Keseluruhan")
            else:
                await send_message(chat_id, "Tidak ada data untuk ditampilkan.")

        elif data == "stat_bulan_year":
            await set_user_state(chat_id, "wait_stat_year")
            await send_message(chat_id, "masukan tahun:")

