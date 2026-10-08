import io
from datetime import datetime
import matplotlib
matplotlib.use('Agg') # Server-side rendering without display
import matplotlib.pyplot as plt
from collections import defaultdict
from bot.sheets import get_all_data

def generate_weekly_chart(month_only: bool = False, target_month=None, target_year=None) -> bytes:
    data = get_all_data()
    if not data:
        return b""

    # Aggregate by week
    # Format: "YYYY-WXX"
    weekly_in = defaultdict(int)
    weekly_out = defaultdict(int)

    for row in data:
        try:
            dt = datetime.strptime(row['date'], "%Y-%m-%d %H:%M:%S")
            if month_only and target_month and target_year:
                if dt.month != target_month or dt.year != target_year:
                    continue

            # %V gives iso week number (01-53)
            # %G gives iso year
            week_key = dt.strftime("%G-W%V")

            if row['tipe'] == 'MASUK':
                weekly_in[week_key] += row['nominal']
            elif row['tipe'] == 'KELUAR':
                weekly_out[week_key] += row['nominal']
        except Exception:
            pass

    return _plot_bar_chart(weekly_in, weekly_out, "Statistik Mingguan")

def generate_monthly_chart(target_year=None) -> bytes:
    data = get_all_data()
    if not data:
        return b""

    monthly_in = defaultdict(int)
    monthly_out = defaultdict(int)

    for row in data:
        try:
            dt = datetime.strptime(row['date'], "%Y-%m-%d %H:%M:%S")
            if target_year and dt.year != target_year:
                continue

            month_key = f"{dt.year}-{dt.month:02d}"

            if row['tipe'] == 'MASUK':
                monthly_in[month_key] += row['nominal']
            elif row['tipe'] == 'KELUAR':
                monthly_out[month_key] += row['nominal']
        except Exception:
            pass

    title = f"Statistik Bulanan ({target_year})" if target_year else "Statistik Bulanan Keseluruhan"
    return _plot_bar_chart(monthly_in, monthly_out, title)

def _plot_bar_chart(data_in: dict, data_out: dict, title: str) -> bytes:
    # Get all sorted keys
    all_keys = sorted(list(set(data_in.keys()).union(set(data_out.keys()))))

    if not all_keys:
        return b""

    vals_in = [data_in.get(k, 0) for k in all_keys]
    vals_out = [data_out.get(k, 0) for k in all_keys]

    x = range(len(all_keys))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 6))

    # Plotting
    ax.bar([i - width/2 for i in x], vals_in, width, label='Pemasukan', color='#2ecc71')
    ax.bar([i + width/2 for i in x], vals_out, width, label='Pengeluaran', color='#e74c3c')

    ax.set_ylabel('Nominal (Rupiah)')
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(all_keys, rotation=45, ha='right')
    ax.legend()
    ax.grid(axis='y', linestyle='--', alpha=0.7)

    # Avoid scientific notation
    ax.get_yaxis().set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda x, p: format(int(x), ','))
    )

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()
