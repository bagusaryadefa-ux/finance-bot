# ============= GRAFIK BERDASARKAN TAHUN =============
def receive_year(update: Update, context: CallbackContext):
    try:
        target_year = update.message.text.strip()
        gs = get_gsheet()
        monthly_data = {}
        
        for ws in gs.worksheets():
            try:
                title = ws.title
                if target_year in title:
                    data = ws.get_all_values()[1:]
                    total_in = sum(float(r[3]) if r[3] else 0 for r in data)
                    total_out = sum(float(r[4]) if r[4] else 0 for r in data)
                    if total_in or total_out:
                        monthly_data[title] = {"in": total_in, "out": total_out}
            except:
                pass
        
        if not monthly_data:
            update.message.reply_text(f"⚠️ Tidak ada data untuk tahun {target_year}.")
            return ConversationHandler.END
        
        labels = list(monthly_data.keys())
        in_values = [v["in"] for v in monthly_data.values()]
        out_values = [v["out"] for v in monthly_data.values()]
        
        plt.figure(figsize=(10, 6))
        x = range(len(labels))
        width = 0.35
        plt.bar([i - width/2 for i in x], in_values, width, label='Pemasukan', color='#22c55e')
        plt.bar([i + width/2 for i in x], out_values, width, label='Pengeluaran', color='#ef4444')
        plt.xlabel('Bulan')
        plt.ylabel('Jumlah (Rp)')
        plt.title(f'Grafik Keuangan {target_year}')
        plt.xticks(x, labels, rotation=45, ha='right')
        plt.legend()
        plt.tight_layout()
        plt.savefig('year_chart.png')
        plt.close()
        
        with open('year_chart.png', 'rb') as f:
            context.bot.send_photo(update.effective_user.id, f)
        
        update.message.reply_text(f"✅ Berikut grafik tahun {target_year}:")
        return ConversationHandler.END
    
    except Exception as e:
        update.message.reply_text("⚠️ Format tahun tidak valid. Coba lagi dengan /statistik")
        return ConversationHandler.END

# ============= BATAL =============
def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("❌ Dibatalkan.")
    return ConversationHandler.END

# ============= ERROR HANDLER =============
def error(update: Update, context: CallbackContext):
    print(f"Error: {context.error}")

# ============= MAIN =============
def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Conversation Handler untuk masuk/keluar
    entry_points = [CommandHandler('masuk', masuk), CommandHandler('keluar', keluar)]
    conv_handler = ConversationHandler(
        entry_points=entry_points,
        states={
            AMOUNT: [MessageHandler(Filters.text & ~Filters.command, receive_amount)],
            DESCRIPTION: [MessageHandler(Filters.text & ~Filters.command, receive_description)],
            PROOF: [
                CallbackQueryHandler(proof_choice, pattern=r'^proof_'),
                MessageHandler(Filters.photo, receive_proof)
            ],
        },
        fallbacks=[CommandHandler('batal', cancel)]
    )
    dp.add_handler(conv_handler)
    
    # Conversation Handler untuk statistik
    stats_conv = ConversationHandler(
        entry_points=[CommandHandler('statistik', statistik)],
        states={
            STATS_CHOICE: [CallbackQueryHandler(stats_choice)],
            STATS_WEEKLY: [CallbackQueryHandler(stats_weekly_choice)],
            STATS_MONTHLY: [CallbackQueryHandler(stats_monthly_choice)],
            WAIT_YEAR: [MessageHandler(Filters.text & ~Filters.command, receive_year)],
        },
        fallbacks=[CommandHandler('batal', cancel)]
    )
    dp.add_handler(stats_conv)
    
    # Perintah biasa
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('summary', summary))
    dp.add_error_handler(error)
    
    print("✅ Bot berjalan...")
    updater.start_polling()
    updater.idle()

if name == "main":
    main()