# bot.py
# BOT DADU DUEL — FULL FITUR
# Telegram: Auto Roll (M1, M2, M3), Deposit QRIS, Withdraw, Last Win, Jackpot, Leaderboard

import random
import sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ==================== KONFIGURASI ====================
BOT_TOKEN = "8986690043:AAFhRUhCU6acJQ3LtTroQ7z7DjBmg4V1kFQ"
ADMIN_IDS = [8502398484]
MIN_BET = 0.2
MAX_BET = 100
WD_MIN = 10
KOIN_RATE = 1000
AUTO_ROLL_THRESHOLD = 0.2
MIN_TOTAL_BET = 0.4
FEE = 0.1
QRIS_IMAGE_PATH = "qris.png"

# ==================== DATABASE ====================
DB_NAME = "dadu.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            saldo REAL DEFAULT 0,
            dana TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS withdraw_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            dana TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS last_win (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            amount REAL,
            side TEXT,
            score TEXT,
            game INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# ==================== HELPER ====================
def get_user(user_id, username):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users (id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = c.fetchone()
    conn.close()
    return user

def update_saldo(user_id, amount):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET saldo = saldo + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def add_history(user_id, typ, amount, desc=""):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO history (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
        (user_id, typ, amount, desc),
    )
    conn.commit()
    conn.close()

def save_last_win(user_id, username, amount, side, score):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as total FROM last_win")
    total = c.fetchone()
    game_num = total["total"] + 1
    c.execute(
        "INSERT INTO last_win (user_id, username, amount, side, score, game) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, amount, side, score, game_num),
    )
    conn.commit()
    conn.close()

def get_last_win():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM last_win ORDER BY created_at DESC LIMIT 1")
    res = c.fetchone()
    conn.close()
    return res

def add_withdraw_request(user_id, amount, dana):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO withdraw_requests (user_id, amount, dana) VALUES (?, ?, ?)",
        (user_id, amount, dana),
    )
    conn.commit()
    conn.close()

def get_pending_wd():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT w.*, u.username FROM withdraw_requests w
        JOIN users u ON w.user_id = u.id
        WHERE w.status = 'pending'
    ''')
    res = c.fetchall()
    conn.close()
    return res

# ==================== DATA TARUHAN ====================
bets = {"K": [], "B": []}
auto_roll_enabled = True
user_states = {}

# ==================== COMMANDS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user(user.id, user.username)
    last = get_last_win()
    msg = f"🎲 Selamat datang {user.first_name}!\n\n"
    if last:
        msg += "𝗟𝗔𝗦𝗧 𝗪𝗜𝗡\n─────────────────\n"
        msg += f"𝗚{last['game']} : {last['side']} {last['score']} [ {last['amount']:.1f} ]\n─────────────────\n"
        msg += f"🏆 {last['side']} MENANG!\n\n"
    msg += (
        "📋 PERINTAH:\n"
        "/balance - Cek saldo\n"
        "/bet K/B [jumlah] - Pasang taruhan\n"
        "/rekap - Lihat total taruhan\n"
        "/deposit [jumlah] - Minta deposit QRIS\n"
        "/withdraw [jumlah] - Request WD\n"
        "/setdana [nomor] - Simpan nomor DANA\n"
        "/lastwin - Last win terakhir\n"
        "/autoon - Nyalakan auto roll\n"
        "/autooff - Matikan auto roll\n"
        "/help - Bantuan\n\n"
        "🎯 ADMIN ONLY:\n"
        "/roll - Roll manual\n"
        "/cekwd - Lihat WD pending\n"
        "/confirm @user [jumlah] - Konfirmasi WD\n"
        "/reject @user - Tolak WD\n"
        "/confirmdeposit @user [jumlah] - Konfirmasi deposit"
    )
    await update.message.reply_text(msg)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = get_user(user.id, user.username)
    await update.message.reply_text(
        f"💰 Saldo: {data['saldo']:.2f} Koin\n💵 Rp {data['saldo'] * KOIN_RATE:,.0f}"
    )

async def setdana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("❌ Contoh: /setdana 08123456789")
        return
    dana = context.args[0]
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET dana = ? WHERE id = ?", (dana, user.id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Nomor DANA: {dana}")

async def lastwin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last = get_last_win()
    if not last:
        await update.message.reply_text("📭 Belum ada kemenangan.")
        return
    await update.message.reply_text(
        f"𝗟𝗔𝗦𝗧 𝗪𝗜𝗡\n─────────────────\n"
        f"𝗚{last['game']} : {last['side']} {last['score']} [ {last['amount']:.1f} ]\n─────────────────\n"
        f"🏆 {last['side']} MENANG!"
    )

# ==================== BET ====================
async def bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) < 2:
        await update.message.reply_text("❌ Contoh: /bet K 0.5")
        return
    side = context.args[0].upper()
    if side not in ["K", "B"]:
        await update.message.reply_text("❌ Pilih K atau B!")
        return
    try:
        amount = float(context.args[1].replace(",", "."))
    except:
        await update.message.reply_text("❌ Jumlah harus angka!")
        return
    if amount < MIN_BET or amount > MAX_BET:
        await update.message.reply_text(f"❌ Min {MIN_BET} / Max {MAX_BET} Koin!")
        return
    user_data = get_user(user.id, user.username)
    if user_data["saldo"] < amount:
        await update.message.reply_text(f"❌ Saldo: {user_data['saldo']:.2f} Koin")
        return
    update_saldo(user.id, -amount)
    add_history(user.id, "bet", -amount, f"{side} {amount}")
    bets[side].append({"user_id": user.id, "username": user.username, "amount": amount})
    await update.message.reply_text(f"✅ Taruhan {side} {amount:.2f} Koin")
    total_k = sum(b["amount"] for b in bets["K"])
    total_b = sum(b["amount"] for b in bets["B"])
    total_all = total_k + total_b
    if auto_roll_enabled and total_all >= MIN_TOTAL_BET:
        selisih = abs(total_k - total_b)
        if selisih <= AUTO_ROLL_THRESHOLD:
            await update.message.reply_text(f"⚡ K {total_k:.2f} vs B {total_b:.2f} → roll dalam 3 detik...")
            await asyncio.sleep(3)
            await auto_roll(update, context)
        else:
            await update.message.reply_text(f"📊 K {total_k:.2f} vs B {total_b:.2f} (selisih {selisih:.2f})")
    else:
        await update.message.reply_text(f"📊 Total: {total_all:.2f} Koin")

# ==================== AUTO ROLL ====================
async def auto_roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not bets["K"] and not bets["B"]:
        return
    total_k = sum(b["amount"] for b in bets["K"])
    total_b = sum(b["amount"] for b in bets["B"])
    await update.message.reply_text("🎲 M1 123")
    await asyncio.sleep(1)
    d1 = random.randint(1, 6)
    d2 = random.randint(1, 6)
    total1 = d1 + d2
    if total1 <= 6:
        hasil1 = "K"
        side1 = "KECIL"
    elif total1 >= 8:
        hasil1 = "B"
        side1 = "BESAR"
    else:
        hasil1 = "DRAW"
        side1 = "DRAW"
    await update.message.reply_text(f"🎲 Dadu M1: {d1} - {d2} (Total {total1}) → {side1}")
    await update.message.reply_text("🎲 M2 123")
    await asyncio.sleep(1)
    d3 = random.randint(1, 6)
    d4 = random.randint(1, 6)
    total2 = d3 + d4
    if total2 <= 6:
        hasil2 = "K"
        side2 = "KECIL"
    elif total2 >= 8:
        hasil2 = "B"
        side2 = "BESAR"
    else:
        hasil2 = "DRAW"
        side2 = "DRAW"
    await update.message.reply_text(f"🎲 Dadu M2: {d3} - {d4} (Total {total2}) → {side2}")
    skor = {"K": 0, "B": 0}
    if hasil1 == "K":
        skor["K"] += 1
    elif hasil1 == "B":
        skor["B"] += 1
    if hasil2 == "K":
        skor["K"] += 1
    elif hasil2 == "B":
        skor["B"] += 1
    if skor["K"] == 2:
        winner_side = "KECIL"
        result = "K"
        score = "2-0"
    elif skor["B"] == 2:
        winner_side = "BESAR"
        result = "B"
        score = "2-0"
    else:
        await update.message.reply_text("🎲 M3 123 (BABAK PENENTU!)")
        await asyncio.sleep(1)
        d5 = random.randint(1, 6)
        d6 = random.randint(1, 6)
        total3 = d5 + d6
        if total3 <= 6:
            hasil3 = "K"
            side3 = "KECIL"
        elif total3 >= 8:
            hasil3 = "B"
            side3 = "BESAR"
        else:
            hasil3 = "DRAW"
            side3 = "DRAW"
        await update.message.reply_text(f"🎲 Dadu M3: {d5} - {d6} (Total {total3}) → {side3}")
        if hasil3 == "K":
            skor["K"] += 1
        elif hasil3 == "B":
            skor["B"] += 1
        if skor["K"] > skor["B"]:
            winner_side = "KECIL"
            result = "K"
            score = "2-1"
        else:
            winner_side = "BESAR"
            result = "B"
            score = "2-1"
    winner_amount = total_k if result == "K" else total_b
    winner_bets = bets["K"] if result == "K" else bets["B"]
    pot = winner_amount * (1 - FEE)
    msg = f"🎲 DUEL DADU\nSkor akhir: {score}\n🏆 {winner_side} MENANG!\n\n💰 Pot: {winner_amount:.2f} Koin\n🔧 Fee {FEE*100:.0f}%: {winner_amount*FEE:.2f}\n🏆 {len(winner_bets)} pemenang\n\n"
    for b in winner_bets:
        share = (b["amount"] / winner_amount) * pot
        update_saldo(b["user_id"], share)
        add_history(b["user_id"], "win", share, f"Win {winner_side} {score}")
        msg += f"  @{b['username']} +{share:.2f} Koin\n"
    await update.message.reply_text(msg)
    if winner_bets:
        w = winner_bets[0]
        save_last_win(w["user_id"], w["username"], w["amount"], winner_side, score)
    bets["K"].clear()
    bets["B"].clear()

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin!")
        return
    await auto_roll(update, context)

# ==================== DEPOSIT ====================
async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) < 1:
        await update.message.reply_text("❌ Contoh: /deposit 0.5")
        return
    try:
        amount = float(context.args[0].replace(",", "."))
    except:
        await update.message.reply_text("❌ Jumlah harus angka!")
        return
    if amount < MIN_BET:
        await update.message.reply_text(f"❌ Min deposit {MIN_BET} Koin!")
        return
    user_states[user.id] = {"deposit_amount": amount}
    keyboard = [[InlineKeyboardButton("📤 Kirim Bukti Transfer", callback_data="kirim_bukti")]]
    msg = f"💳 BAYAR KE QRIS\n💰 {amount} Koin (Rp {amount*KOIN_RATE:,.0f})\n📌 Klik tombol setelah transfer!"
    try:
        with open(QRIS_IMAGE_PATH, "rb") as f:
            await update.message.reply_photo(f, caption=msg, reply_markup=InlineKeyboardMarkup(keyboard))
    except:
        await update.message.reply_text(msg + "\n\n⚠️ QRIS tidak ditemukan!")

async def kirim_bukti_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    amount = user_states.get(user.id, {}).get("deposit_amount", 0)
    if not amount:
        await query.edit_message_text("❌ /deposit dulu!")
        return
    await query.edit_message_text(f"📤 Kirim FOTO BUKTI TRANSFER\n💰 {amount} Koin (Rp {amount*KOIN_RATE:,.0f})")
    user_states[user.id]["waiting_bukti"] = True

async def handle_bukti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    state = user_states.get(user.id, {})
    amount = state.get("deposit_amount", 0)
    if not state.get("waiting_bukti"):
        await update.message.reply_text("❌ /deposit dulu!")
        return
    if not update.message.photo:
        await update.message.reply_text("❌ Kirim FOTO!")
        return
    photo = update.message.photo[-1].file_id
    for admin_id in ADMIN_IDS:
        await context.bot.send_photo(
            admin_id,
            photo,
            caption=f"📥 BUKTI TRANSFER\n👤 @{user.username}\n💰 {amount} Koin\n/confirmdeposit @{user.username} {amount}"
        )
    await update.message.reply_text(f"✅ Bukti terkirim ke admin!\n💰 {amount} Koin")
    user_states[user.id] = {}

async def confirmdeposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /confirmdeposit @username 0.5")
        return
    username = context.args[0].replace("@", "")
    try:
        amount = float(context.args[1].replace(",", "."))
    except:
        await update.message.reply_text("❌ Jumlah harus angka!")
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    if not user:
        await update.message.reply_text(f"❌ @{username} tidak ditemukan!")
        return
    update_saldo(user["id"], amount)
    add_history(user["id"], "deposit", amount, f"Deposit {amount}")
    await update.message.reply_text(f"✅ Deposit @{username} +{amount:.2f} Koin berhasil!")

# ==================== WITHDRAW ====================
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) < 1:
        await update.message.reply_text("❌ /withdraw 0.5")
        return
    try:
        amount = float(context.args[0].replace(",", "."))
    except:
        await update.message.reply_text("❌ Jumlah harus angka!")
        return
    if amount < WD_MIN:
        await update.message.reply_text(f"❌ Min WD {WD_MIN} Koin!")
        return
    user_data = get_user(user.id, user.username)
    if user_data["saldo"] < amount:
        await update.message.reply_text(f"❌ Saldo: {user_data['saldo']:.2f}")
        return
    if not user_data["dana"]:
        await update.message.reply_text("❌ /setdana dulu!")
        return
    add_withdraw_request(user.id, amount, user_data["dana"])
    await update.message.reply_text(f"✅ WD {amount:.2f} Koin → admin!")

async def cekwd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin!")
        return
    pending = get_pending_wd()
    if not pending:
        await update.message.reply_text("✅ Tidak ada WD pending.")
        return
    msg = "📤 LIST WD PENDING\n\n"
    for w in pending:
        msg += f"@{w['username']} - {w['amount']:.2f} Koin\nDANA: {w['dana']}\nID: {w['id']}\n---\n"
    await update.message.reply_text(msg)

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /confirm @user 0.5")
        return
    username = context.args[0].replace("@", "")
    try:
        amount = float(context.args[1].replace(",", "."))
    except:
        await update.message.reply_text("❌ Jumlah harus angka!")
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    if not user:
        await update.message.reply_text(f"❌ @{username} tidak ditemukan!")
        conn.close()
        return
    c.execute("SELECT * FROM withdraw_requests WHERE user_id = ? AND status = 'pending'", (user["id"],))
    wd = c.fetchone()
    if not wd:
        await update.message.reply_text(f"❌ Tidak ada WD pending untuk @{username}")
        conn.close()
        return
    c.execute("UPDATE withdraw_requests SET status = 'done' WHERE id = ?", (wd["id"],))
    conn.commit()
    conn.close()
    update_saldo(user["id"], -wd["amount"])
    add_history(user["id"], "withdraw", -wd["amount"], f"WD {wd['amount']}")
    await update.message.reply_text(f"✅ WD @{username} {wd['amount']:.2f} Koin selesai!")

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin!")
        return
    if len(context.args) < 1:
        await update.message.reply_text("❌ /reject @user")
        return
    username = context.args[0].replace("@", "")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    if not user:
        await update.message.reply_text(f"❌ @{username} tidak ditemukan!")
        conn.close()
        return
    c.execute("SELECT * FROM withdraw_requests WHERE user_id = ? AND status = 'pending'", (user["id"],))
    wd = c.fetchone()
    if not wd:
        await update.message.reply_text(f"❌ Tidak ada WD pending untuk @{username}")
        conn.close()
        return
    c.execute("UPDATE withdraw_requests SET status = 'rejected' WHERE id = ?", (wd["id"],))
    conn.commit()
    conn.close()
    update_saldo(user["id"], wd["amount"])
    add_history(user["id"], "reject", wd["amount"], f"WD ditolak {wd['amount']}")
    await update.message.reply_text(f"❌ WD @{username} {wd['amount']:.2f} Koin ditolak!")

# ==================== REKAP ====================
async def rekap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_k = sum(b["amount"] for b in bets["K"])
    total_b = sum(b["amount"] for b in bets["B"])
    msg = "📊 REKAP TARUHAN\n\n🔵 KECIL (K):\n"
    if bets["K"]:
        for b in bets["K"]:
            msg += f"  @{b['username']} {b['amount']:.2f}\n"
        msg += f"  Total: {total_k:.2f}\n\n"
    else:
        msg += "  (kosong)\n\n"
    msg += "🔴 BESAR (B):\n"
    if bets["B"]:
        for b in bets["B"]:
            msg += f"  @{b['username']} {b['amount']:.2f}\n"
        msg += f"  Total: {total_b:.2f}\n\n"
    else:
        msg += "  (kosong)\n\n"
    msg += f"Total semua: {total_k + total_b:.2f} Koin"
    await update.message.reply_text(msg)

# ==================== AUTO ROLL ON/OFF ====================
async def autoon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global auto_roll_enabled
    auto_roll_enabled = True
    await update.message.reply_text("✅ Auto roll diaktifkan!")

async def autooff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global auto_roll_enabled
    auto_roll_enabled = False
    await update.message.reply_text("❌ Auto roll dimatikan!")

# ==================== MAIN ====================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("setdana", setdana))
    app.add_handler(CommandHandler("lastwin", lastwin))
    app.add_handler(CommandHandler("bet", bet))
    app.add_handler(CommandHandler("rekap", rekap))
    app.add_handler(CommandHandler("roll", roll))
    app.add_handler(CommandHandler("deposit", deposit))
    app.add_handler(CommandHandler("withdraw", withdraw))
    app.add_handler(CommandHandler("cekwd", cekwd))
    app.add_handler(CommandHandler("confirm", confirm))
    app.add_handler(CommandHandler("reject", reject))
    app.add_handler(CommandHandler("confirmdeposit", confirmdeposit))
    app.add_handler(CommandHandler("autoon", autoon))
    app.add_handler(CommandHandler("autooff", autooff))
    app.add_handler(CallbackQueryHandler(kirim_bukti_callback, pattern="kirim_bukti"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_bukti))
    print("🤖 Bot dadu berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            saldo REAL DEFAULT 0,
            dana TEXT DEFAULT NULL,
            referral_code TEXT,
            referred_by INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS withdraw_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            dana TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS last_win (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            amount REAL,
            side TEXT,
            score TEXT,
            game INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS deposit_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# ==================== HELPER ====================
def get_user(user_id, username):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users (id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = c.fetchone()
    conn.close()
    return user

def update_saldo(user_id, amount):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET saldo = saldo + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def add_history(user_id, typ, amount, desc=""):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO history (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
        (user_id, typ, amount, desc),
    )
    conn.commit()
    conn.close()

def save_last_win(user_id, username, amount, side, score):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as total FROM last_win")
    total = c.fetchone()
    game_num = total["total"] + 1
    c.execute(
        "INSERT INTO last_win (user_id, username, amount, side, score, game) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, amount, side, score, game_num),
    )
    conn.commit()
    conn.close()

def get_last_win():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM last_win ORDER BY created_at DESC LIMIT 1")
    res = c.fetchone()
    conn.close()
    return res

def get_leaderboard():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT username, saldo FROM users ORDER BY saldo DESC LIMIT 10")
    res = c.fetchall()
    conn.close()
    return res

def add_withdraw_request(user_id, amount, dana):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO withdraw_requests (user_id, amount, dana) VALUES (?, ?, ?)",
        (user_id, amount, dana),
    )
    conn.commit()
    conn.close()

def get_pending_wd():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT w.*, u.username FROM withdraw_requests w
        JOIN users u ON w.user_id = u.id
        WHERE w.status = 'pending'
    ''')
    res = c.fetchall()
    conn.close()
    return res

# ==================== DATA TARUHAN ====================
bets = {"K": [], "B": []}
auto_roll_enabled = True
user_states = {}

# ==================== COMMANDS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user(user.id, user.username)

    last = get_last_win()
    msg = f"🎲 Selamat datang {user.first_name}!\n\n"
    if last:
        msg += "𝗟𝗔𝗦𝗧 𝗪𝗜𝗡\n─────────────────\n"
        msg += f"𝗚{last['game']} : {last['side']} {last['score']} [ {last['amount']:.1f} ]\n─────────────────\n"
        msg += f"🏆 {last['side']} MENANG!\n\n"

    msg += (
        "📋 PERINTAH:\n"
        "/balance - Cek saldo\n"
        "/bet K/B [jumlah] - Pasang taruhan\n"
        "/rekap - Lihat total taruhan\n"
        "/deposit [jumlah] - Minta deposit QRIS\n"
        "/withdraw [jumlah] - Request WD\n"
        "/setdana [nomor] - Simpan nomor DANA\n"
        "/history - Riwayat transaksi\n"
        "/top - Leaderboard\n"
        "/referral - Kode referral\n"
        "/lastwin - Last win terakhir\n"
        "/autoon - Nyalakan auto roll\n"
        "/autooff - Matikan auto roll\n"
        "/help - Bantuan\n\n"
        "🎯 ADMIN ONLY:\n"
        "/roll - Roll manual\n"
        "/cekwd - Lihat WD pending\n"
        "/confirm @user [jumlah] - Konfirmasi WD\n"
        "/reject @user - Tolak WD\n"
        "/confirmdeposit @user [jumlah] - Konfirmasi deposit"
    )
    await update.message.reply_text(msg)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = get_user(user.id, user.username)
    await update.message.reply_text(
        f"💰 Saldo: {data['saldo']:.2f} Koin\n💵 Rp {data['saldo'] * KOIN_RATE:,.0f}"
    )

async def setdana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("❌ Contoh: /setdana 08123456789")
        return
    dana = context.args[0]
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET dana = ? WHERE id = ?", (dana, user.id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Nomor DANA: {dana}")

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_leaderboard()
    if not data:
        await update.message.reply_text("📭 Belum ada pemain.")
        return
    msg = "🏆 LEADERBOARD TOP 10\n\n"
    for i, u in enumerate(data, 1):
        msg += f"{i}. @{u['username']} - {u['saldo']:.2f} Koin\n"
    await update.message.reply_text(msg)

async def lastwin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last = get_last_win()
    if not last:
        await update.message.reply_text("📭 Belum ada kemenangan.")
        return
    await update.message.reply_text(
        f"𝗟𝗔𝗦𝗧 𝗪𝗜𝗡\n─────────────────\n"
        f"𝗚{last['game']} : {last['side']} {last['score']} [ {last['amount']:.1f} ]\n─────────────────\n"
        f"🏆 {last['side']} MENANG!"
    )

# ==================== BET ====================
async def bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) < 2:
        await update.message.reply_text("❌ Contoh: /bet K 0.5")
        return

    side = context.args[0].upper()
    if side not in ["K", "B"]:
        await update.message.reply_text("❌ Pilih K atau B!")
        return

    try:
        amount = float(context.args[1].replace(",", "."))
    except:
        await update.message.reply_text("❌ Jumlah harus angka!")
        return

    if amount < MIN_BET or amount > MAX_BET:
        await update.message.reply_text(f"❌ Min {MIN_BET} / Max {MAX_BET} Koin!")
        return

    user_data = get_user(user.id, user.username)
    if user_data["saldo"] < amount:
        await update.message.reply_text(f"❌ Saldo: {user_data['saldo']:.2f} Koin")
        return

    update_saldo(user.id, -amount)
    add_history(user.id, "bet", -amount, f"{side} {amount}")
    bets[side].append({"user_id": user.id, "username": user.username, "amount": amount})

    await update.message.reply_text(f"✅ Taruhan {side} {amount:.2f} Koin")

    # Auto roll
    total_k = sum(b["amount"] for b in bets["K"])
    total_b = sum(b["amount"] for b in bets["B"])
    total_all = total_k + total_b

    if auto_roll_enabled and total_all >= MIN_TOTAL_BET:
        selisih = abs(total_k - total_b)
        if selisih <= AUTO_ROLL_THRESHOLD:
            await update.message.reply_text(
                f"⚡ K {total_k:.2f} vs B {total_b:.2f} → roll dalam 3 detik..."
            )
            await asyncio.sleep(3)
            await auto_roll(update, context)
        else:
            await update.message.reply_text(f"📊 K {total_k:.2f} vs B {total_b:.2f} (selisih {selisih:.2f})")
    else:
        await update.message.reply_text(f"📊 Total: {total_all:.2f} Koin")

# ==================== AUTO ROLL ====================
async def auto_roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not bets["K"] and not bets["B"]:
        return

    total_k = sum(b["amount"] for b in bets["K"])
    total_b = sum(b["amount"] for b in bets["B"])

    # ============ RONDE 1 (M1) ============
    await update.message.reply_text("🎲 M1 123")
    await asyncio.sleep(1)
    d1 = random.randint(1, 6)
    d2 = random.randint(1, 6)
    total1 = d1 + d2
    if total1 <= 6:
        hasil1 = "K"
        side1 = "KECIL"
    elif total1 >= 8:
        hasil1 = "B"
        side1 = "BESAR"
    else:
        hasil1 = "DRAW"
        side1 = "DRAW"
    await update.message.reply_text(f"🎲 Dadu M1: {d1} - {d2} (Total {total1}) → {side1}")

    # ============ RONDE 2 (M2) ============
    await update.message.reply_text("🎲 M2 123")
    await asyncio.sleep(1)
    d3 = random.randint(1, 6)
    d4 = random.randint(1, 6)
    total2 = d3 + d4
    if total2 <= 6:
        hasil2 = "K"
        side2 = "KECIL"
    elif total2 >= 8:
        hasil2 = "B"
        side2 = "BESAR"
    else:
        hasil2 = "DRAW"
        side2 = "DRAW"
    await update.message.reply_text(f"🎲 Dadu M2: {d3} - {d4} (Total {total2}) → {side2}")

    # ============ CEK SKOR SETELAH M2 ============
    skor = {"K": 0, "B": 0}
    if hasil1 == "K":
        skor["K"] += 1
    elif hasil1 == "B":
        skor["B"] += 1
    if hasil2 == "K":
        skor["K"] += 1
    elif hasil2 == "B":
        skor["B"] += 1

    # ============ KALAU 2-0 LANGSUNG SELESAI ============
    if skor["K"] == 2:
        winner_side = "KECIL"
        result = "K"
        score = "2-0"
    elif skor["B"] == 2:
        winner_side = "BESAR"
        result = "B"
        score = "2-0"
    else:
        # ============ SKOR 1-1 → M3 ============
        await update.message.reply_text("🎲 M3 123 (BABAK PENENTU!)")
        await asyncio.sleep(1)
        d5 = random.randint(1, 6)
        d6 = random.randint(1, 6)
        total3 = d5 + d6
        if total3 <= 6:
            hasil3 = "K"
            side3 = "KECIL"
        elif total3 >= 8:
            hasil3 = "B"
            side3 = "BESAR"
        else:
            hasil3 = "DRAW"
            side3 = "DRAW"
        await update.message.reply_text(f"🎲 Dadu M3: {d5} - {d6} (Total {total3}) → {side3}")

        if hasil3 == "K":
            skor["K"] += 1
        elif hasil3 == "B":
            skor["B"] += 1

        if skor["K"] > skor["B"]:
            winner_side = "KECIL"
            result = "K"
            score = "2-1"
        else:
            winner_side = "BESAR"
            result = "B"
            score = "2-1"

    # ============ PEMBAYARAN ============
    winner_amount = total_k if result == "K" else total_b
    winner_bets = bets["K"] if result == "K" else bets["B"]
    pot = winner_amount * (1 - FEE)

    msg = f"🎲 DUEL DADU\n"
    msg += f"Skor akhir: {score}\n"
    msg += f"🏆 {winner_side} MENANG!\n\n"
    msg += f"💰 Pot: {winner_amount:.2f} Koin\n"
    msg += f"🔧 Fee {FEE*100:.0f}%: {winner_amount*FEE:.2f}\n"
    msg += f"🏆 {len(winner_bets)} pemenang\n\n"

    for b in winner_bets:
        share = (b["amount"] / winner_amount) * pot
        update_saldo(b["user_id"], share)
        add_history(b["user_id"], "win", share, f"Win {winner_side} {score}")
        msg += f"  @{b['username']} +{share:.2f} Koin\n"

    await update.message.reply_text(msg)

    if winner_bets:
        w = winner_bets[0]
        save_last_win(w["user_id"], w["username"], w["amount"], winner_side, score)

    bets["K"].clear()
    bets["B"].clear()

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin!")
        return
    await auto_roll(update, context)

# ==================== DEPOSIT ====================
async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) < 1:
        await update.message.reply_text("❌ Contoh: /deposit 0.5")
        return
    try:
        amount = float(context.args[0].replace(",", "."))
    except:
        await update.message.reply_text("❌ Jumlah harus angka!")
        return
    if amount < MIN_BET:
        await update.message.reply_text(f"❌ Min deposit {MIN_BET} Koin!")
        return

    user_states[user.id] = {"deposit_amount": amount}
    keyboard = [[InlineKeyboardButton("📤 Kirim Bukti Transfer", callback_data="kirim_bukti")]]
    msg = f"💳 BAYAR KE QRIS\n💰 {amount} Koin (Rp {amount*KOIN_RATE:,.0f})\n📌 Klik tombol setelah transfer!"
    try:
        with open(QRIS_IMAGE_PATH, "rb") as f:
            await update.message.reply_photo(f, caption=msg, reply_markup=InlineKeyboardMarkup(keyboard))
    except:
        await update.message.reply_text(msg + "\n\n⚠️ QRIS tidak ditemukan!")

async def kirim_bukti_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    amount = user_states.get(user.id, {}).get("deposit_amount", 0)
    if not amount:
        await query.edit_message_text("❌ /deposit dulu!")
        return
    await query.edit_message_text(f"📤 Kirim FOTO BUKTI TRANSFER\n💰 {amount} Koin (Rp {amount*KOIN_RATE:,.0f})")
    user_states[user.id]["waiting_bukti"] = True

async def handle_bukti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    state = user_states.get(user.id, {})
    amount = state.get("deposit_amount", 0)
    if not state.get("waiting_bukti"):
        await update.message.reply_text("❌ /deposit dulu!")
        return
    if not update.message.photo:
        await update.message.reply_text("❌ Kirim FOTO!")
        return
    photo = update.message.photo[-1].file_id
    for admin_id in ADMIN_IDS:
        await context.bot.send_photo(
            admin_id,
            photo,
            caption=f"📥 BUKTI TRANSFER\n👤 @{user.username}\n💰 {amount} Koin\n/confirmdeposit @{user.username} {amount}"
        )
    await update.message.reply_text(f"✅ Bukti terkirim ke admin!\n💰 {amount} Koin")
    user_states[user.id] = {}

async def confirmdeposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /confirmdeposit @username 0.5")
        return
    username = context.args[0].replace("@", "")
    try:
        amount = float(context.args[1].replace(",", "."))
    except:
        await update.message.reply_text("❌ Jumlah harus angka!")
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    if not user:
        await update.message.reply_text(f"❌ @{username} tidak ditemukan!")
        return
    update_saldo(user["id"], amount)
    add_history(user["id"], "deposit", amount, f"Deposit {amount}")
    await update.message.reply_text(f"✅ Deposit @{username} +{amount:.2f} Koin")

# ==================== WITHDRAW ====================
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) < 1:
        await update.message.reply_text("❌ /withdraw 0.5")
        return
    try:
        amount = float(context.args[0].replace(",", "."))
    except:
        await update.message.reply_text("❌ Jumlah harus angka!")
        return
    if amount < WD_MIN:
        await update.message.reply_text(f"❌ Min WD {WD_MIN} Koin!")
        return
    user_data = get_user(user.id, user.username)
    if user_data["saldo"] < amount:
        await update.message.reply_text(f"❌ Saldo: {user_data['saldo']:.2f}")
        return
    if not user_data["dana"]:
        await update.message.reply_text("❌ /setdana dulu!")
        return
    add_withdraw_request(user.id, amount, user_data["dana"])
    await update.message.reply_text(f"✅ WD {amount:.2f} Koin → admin!")

async def cekwd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin!")
        return
    pending = get_pending_wd()
    if not pending:
        await update.message.reply_text("✅ Tidak ada WD pending.")
        return
    msg = "📤 LIST WD PENDING\n\n"
    for w in pending:
        msg += f"@{w['username']} - {w['amount']:.2f} Koin\nDANA: {w['dana']}\nID: {w['id']}\n---\n"
    await update.message.reply_text(msg)

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /confirm @user 0.5")
        return
    username = context.args[0].replace("@", "")
    try:
        amount = float(context.args[1].replace(",", "."))
    except:
        await update.message.reply_text("❌ Jumlah harus angka!")
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    if not user:
        await update.message.reply_text(f"❌ @{username} tidak ditemukan!")
        conn.close()
        return
    c.execute("SELECT * FROM withdraw_requests WHERE user_id = ? AND status = 'pending'", (user["id"],))
    wd = c.fetchone()
    if not wd:
        await update.message.reply_text(f"❌ Tidak ada WD pending untuk @{username}")
        conn.close()
        return
    c.execute("UPDATE withdraw_requests SET status = 'done' WHERE id = ?", (wd["id"],))
    conn.commit()
    conn.close()
    update_saldo(user["id"], -wd["amount"])
    add_history(user["id"], "withdraw", -wd["amount"], f"WD {wd['amount']}")
    await update.message.reply_text(f"✅ WD @{username} {wd['amount']:.2f} Koin selesai!")

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin!")
        return
    if len(context.args) < 1:
        await update.message.reply_text("❌ /reject @user")
        return
    username = context.args[0].replace("@", "")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    if not user:
        await update.message.reply_text(f"❌ @{username} tidak ditemukan!")
        conn.close()
        return
    c.execute("SELECT * FROM withdraw_requests WHERE user_id = ? AND status = 'pending'", (user["id"],))
    wd = c.fetchone()
    if not wd:
        await update.message.reply_text(f"❌ Tidak ada WD pending untuk @{username}")
        conn.close()
        return
    c.execute("UPDATE withdraw_requests SET status = 'rejected' WHERE id = ?", (wd["id"],))
    conn.commit()
    conn.close()
    update_saldo(user["id"], wd["amount"])
    add_history(user["id"], "reject", wd["amount"], f"WD ditolak {wd['amount']}")
    await update.message.reply_text(f"❌ WD @{username} {wd['amount']:.2f} Koin ditolak!")

# ==================== REKAP ====================
async def rekap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_k = sum(b["amount"] for b in bets["K"])
    total_b = sum(b["amount"] for b in bets["B"])
    msg = "📊 REKAP TARUHAN\n\n🔵 KECIL (K):\n"
    if bets["K"]:
        for b in bets["K"]:
            msg += f"  @{b['username']} {b['amount']:.2f}\n"
        msg += f"  Total: {total_k:.2f}\n\n"
    else:
        msg += "  (kosong)\n\n"
    msg += "🔴 BESAR (B):\n"
    if bets["B"]:
        for b in bets["B"]:
            msg += f"  @{b['username']} {b['amount']:.2f}\n"
        msg += f"  Total: {total_b:.2f}\n\n"
    else:
        msg += "  (kosong)\n\n"
    msg += f"Total semua: {total_k + total_b:.2f} Koin"
    await update.message.reply_text(msg)

# ==================== AUTO ROLL ON/OFF ====================
async def autoon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global auto_roll_enabled
    auto_roll_enabled = True
    await update.message.reply_text("✅ Auto roll diaktifkan!")

async def autooff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global auto_roll_enabled
    auto_roll_enabled = False
    await update.message.reply_text("❌ Auto roll dimatikan!")

# ==================== MAIN ====================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("setdana", setdana))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("lastwin", lastwin))
    app.add_handler(CommandHandler("bet", bet))
    app.add_handler(CommandHandler("rekap", rekap))
    app.add_handler(CommandHandler("roll", roll))
    app.add_handler(CommandHandler("deposit", deposit))
    app.add_handler(CommandHandler("withdraw", withdraw))
    app.add_handler(CommandHandler("cekwd", cekwd))
    app.add_handler(CommandHandler("confirm", confirm))
    app.add_handler(CommandHandler("reject", reject))
    app.add_handler(CommandHandler("confirmdeposit", confirmdeposit))
    app.add_handler(CommandHandler("autoon", autoon))
    app.add_handler(CommandHandler("autooff", autooff))
    app.add_handler(CallbackQueryHandler(kirim_bukti_callback, pattern="kirim_bukti"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_bukti))

    print("🤖 Bot dadu berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            saldo REAL DEFAULT 0,
            dana TEXT DEFAULT NULL,
            referral_code TEXT,
            referred_by INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS withdraw_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            dana TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS last_win (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            amount REAL,
            side TEXT,
            score TEXT,
            game INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS deposit_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# ==================== HELPER ====================
def get_user(user_id, username):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users (id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = c.fetchone()
    conn.close()
    return user

def update_saldo(user_id, amount):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET saldo = saldo + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def add_history(user_id, typ, amount, desc=""):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO history (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
        (user_id, typ, amount, desc),
    )
    conn.commit()
    conn.close()

def save_last_win(user_id, username, amount, side, score):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as total FROM last_win")
    total = c.fetchone()
    game_num = total["total"] + 1
    c.execute(
        "INSERT INTO last_win (user_id, username, amount, side, score, game) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, amount, side, score, game_num),
    )
    conn.commit()
    conn.close()

def get_last_win():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM last_win ORDER BY created_at DESC LIMIT 1")
    res = c.fetchone()
    conn.close()
    return res

def get_all_last_win():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM last_win ORDER BY created_at DESC LIMIT 16")
    res = c.fetchall()
    conn.close()
    return res

def get_leaderboard():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT username, saldo FROM users ORDER BY saldo DESC LIMIT 10")
    res = c.fetchall()
    conn.close()
    return res

def add_withdraw_request(user_id, amount, dana):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO withdraw_requests (user_id, amount, dana) VALUES (?, ?, ?)",
        (user_id, amount, dana),
    )
    conn.commit()
    conn.close()

def get_pending_wd():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT w.*, u.username FROM withdraw_requests w
        JOIN users u ON w.user_id = u.id
        WHERE w.status = 'pending'
    ''')
    res = c.fetchall()
    conn.close()
    return res

# ==================== DATA TARUHAN ====================
bets = {"K": [], "B": []}
auto_roll_enabled = True
user_states = {}

# ==================== COMMANDS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user(user.id, user.username)

    last = get_last_win()
    msg = f"🎲 Selamat datang {user.first_name}!\n\n"
    if last:
        msg += "𝗟𝗔𝗦𝗧 𝗪𝗜𝗡\n─────────────────\n"
        msg += f"𝗚{last['game']} : {last['side']} {last['score']} [ {last['amount']:.1f} ]\n─────────────────\n"
        msg += f"🏆 {last['side']} MENANG!\n\n"

    msg += (
        "📋 PERINTAH:\n"
        "/balance - Cek saldo\n"
        "/bet K/B [jumlah] - Pasang taruhan\n"
        "/rekap - Lihat total taruhan\n"
        "/deposit [jumlah] - Minta deposit QRIS\n"
        "/withdraw [jumlah] - Request WD\n"
        "/setdana [nomor] - Simpan nomor DANA\n"
        "/history - Riwayat transaksi\n"
        "/top - Leaderboard\n"
        "/referral - Kode referral\n"
        "/lastwin - Last win terakhir\n"
        "/autoon - Nyalakan auto roll\n"
        "/autooff - Matikan auto roll\n"
        "/help - Bantuan\n\n"
        "🎯 ADMIN ONLY:\n"
        "/roll - Roll manual\n"
        "/cekwd - Lihat WD pending\n"
        "/confirm @user [jumlah] - Konfirmasi WD\n"
        "/reject @user - Tolak WD\n"
        "/confirmdeposit @user [jumlah] - Konfirmasi deposit"
    )
    await update.message.reply_text(msg)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = get_user(user.id, user.username)
    await update.message.reply_text(
        f"💰 Saldo: {data['saldo']:.2f} Koin\n💵 Rp {data['saldo'] * KOIN_RATE:,.0f}"
    )

async def setdana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("❌ Contoh: /setdana 08123456789")
        return
    dana = context.args[0]
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET dana = ? WHERE id = ?", (dana, user.id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Nomor DANA: {dana}")

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_leaderboard()
    if not data:
        await update.message.reply_text("📭 Belum ada pemain.")
        return
    msg = "🏆 LEADERBOARD TOP 10\n\n"
    for i, u in enumerate(data, 1):
        msg += f"{i}. @{u['username']} - {u['saldo']:.2f} Koin\n"
    await update.message.reply_text(msg)

async def lastwin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last = get_last_win()
    if not last:
        await update.message.reply_text("📭 Belum ada kemenangan.")
        return
    await update.message.reply_text(
        f"𝗟𝗔𝗦𝗧 𝗪𝗜𝗡\n─────────────────\n"
        f"𝗚{last['game']} : {last['side']} {last['score']} [ {last['amount']:.1f} ]\n─────────────────\n"
        f"🏆 {last['side']} MENANG!"
    )

# ==================== BET ====================
async def bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) < 2:
        await update.message.reply_text("❌ Contoh: /bet K 0.5")
        return

    side = context.args[0].upper()
    if side not in ["K", "B"]:
        await update.message.reply_text("❌ Pilih K atau B!")
        return

    try:
        amount = float(context.args[1].replace(",", "."))
    except:
        await update.message.reply_text("❌ Jumlah harus angka!")
        return

    if amount < MIN_BET or amount > MAX_BET:
        await update.message.reply_text(f"❌ Min {MIN_BET} / Max {MAX_BET} Koin!")
        return

    user_data = get_user(user.id, user.username)
    if user_data["saldo"] < amount:
        await update.message.reply_text(f"❌ Saldo: {user_data['saldo']:.2f} Koin")
        return

    update_saldo(user.id, -amount)
    add_history(user.id, "bet", -amount, f"{side} {amount}")
    bets[side].append({"user_id": user.id, "username": user.username, "amount": amount})

    await update.message.reply_text(f"✅ Taruhan {side} {amount:.2f} Koin")

    # Auto roll
    total_k = sum(b["amount"] for b in bets["K"])
    total_b = sum(b["amount"] for b in bets["B"])
    total_all = total_k + total_b

    if auto_roll_enabled and total_all >= MIN_TOTAL_BET:
        selisih = abs(total_k - total_b)
        if selisih <= AUTO_ROLL_THRESHOLD:
            await update.message.reply_text(
                f"⚡ K {total_k:.2f} vs B {total_b:.2f} → roll dalam 3 detik..."
            )
            await asyncio.sleep(3)
            await auto_roll(update, context)
        else:
            await update.message.reply_text(f"📊 K {total_k:.2f} vs B {total_b:.2f} (selisih {selisih:.2f})")
    else:
        await update.message.reply_text(f"📊 Total: {total_all:.2f} Koin")

# ==================== AUTO ROLL ====================
async def auto_roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not bets["K"] and not bets["B"]:
        return

    total_k = sum(b["amount"] for b in bets["K"])
    total_b = sum(b["amount"] for b in bets["B"])

    d1 = random.randint(1, 6)
    d2 = random.randint(1, 6)
    total = d1 + d2

    if total <= 6:
        result, side_name = "K", "KECIL"
        score = "2-0"
    elif total >= 8:
        result, side_name = "B", "BESAR"
        score = "2-0"
    else:
        # DRAW (total 7) → roll ulang
        await update.message.reply_text(f"🎲 DRAW ({d1}-{d2}) → roll ulang...")
        await auto_roll(update, context)
        return

    winner_amount = total_k if result == "K" else total_b
    winner_bets = bets["K"] if result == "K" else bets["B"]
    pot = winner_amount * (1 - FEE)

    # Jackpot
    jackpot = 1 if d1 == d2 else 0

    msg = f"🎲 DUEL DADU\nDadu: {d1} - {d2}\nTotal: {total} | {side_name} MENANG!\n\n"
    msg += f"💰 Pot: {winner_amount:.2f} Koin\n"
    msg += f"🔧 Fee {FEE*100:.0f}%: {winner_amount*FEE:.2f}\n"
    if jackpot:
        msg += f"🎰 JACKPOT! x{JACKPOT_MULTIPLIER}\n"
    msg += f"🏆 {len(winner_bets)} pemenang\n\n"

    for b in winner_bets:
        share = (b["amount"] / winner_amount) * pot
        if jackpot:
            share *= JACKPOT_MULTIPLIER
        update_saldo(b["user_id"], share)
        add_history(b["user_id"], "win", share, f"Win {side_name}" + (" JACKPOT" if jackpot else ""))
        msg += f"  @{b['username']} +{share:.2f} Koin\n"

    await update.message.reply_text(msg)

    # Simpan last win
    if winner_bets:
        w = winner_bets[0]
        save_last_win(w["user_id"], w["username"], w["amount"], side_name, score)

    bets["K"].clear()
    bets["B"].clear()

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin!")
        return
    await auto_roll(update, context)

# ==================== DEPOSIT ====================
async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) < 1:
        await update.message.reply_text("❌ Contoh: /deposit 0.5")
        return
    try:
        amount = float(context.args[0].replace(",", "."))
    except:
        await update.message.reply_text("❌ Jumlah harus angka!")
        return
    if amount < MIN_BET:
        await update.message.reply_text(f"❌ Min deposit {MIN_BET} Koin!")
        return

    user_states[user.id] = {"deposit_amount": amount}
    keyboard = [[InlineKeyboardButton("📤 Kirim Bukti Transfer", callback_data="kirim_bukti")]]
    msg = f"💳 BAYAR KE QRIS\n💰 {amount} Koin (Rp {amount*KOIN_RATE:,.0f})\n📌 Klik tombol setelah transfer!"
    try:
        with open(QRIS_IMAGE_PATH, "rb") as f:
            await update.message.reply_photo(f, caption=msg, reply_markup=InlineKeyboardMarkup(keyboard))
    except:
        await update.message.reply_text(msg + "\n\n⚠️ QRIS tidak ditemukan!")

async def kirim_bukti_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = q.from_user
    amount = user_states.get(user.id, {}).get("deposit_amount", 0)
    if not amount:
        await q.edit_message_text("❌ /deposit dulu!")
        return
    await q.edit_message_text(f"📤 Kirim FOTO BUKTI TRANSFER\n💰 {amount} Koin (Rp {amount*KOIN_RATE:,.0f})")
    user_states[user.id]["waiting_bukti"] = True

async def handle_bukti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    state = user_states.get(user.id, {})
    amount = state.get("deposit_amount", 0)
    if not state.get("waiting_bukti"):
        await update.message.reply_text("❌ /deposit dulu!")
        return
    if not update.message.photo:
        await update.message.reply_text("❌ Kirim FOTO!")
        return
    photo = update.message.photo[-1].file_id
    for admin_id in ADMIN_IDS:
        await context.bot.send_photo(
            admin_id,
            photo,
            caption=f"📥 BUKTI TRANSFER\n👤 @{user.username}\n💰 {amount} Koin\n/confirmdeposit @{user.username} {amount}"
        )
    await update.message.reply_text(f"✅ Bukti terkirim ke admin!\n💰 {amount} Koin")
    user_states[user.id] = {}

async def confirmdeposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /confirmdeposit @username 0.5")
        return
    username = context.args[0].replace("@", "")
    try:
        amount = float(context.args[1].replace(",", "."))
    except:
        await update.message.reply_text("❌ Jumlah harus angka!")
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    if not user:
        await update.message.reply_text(f"❌ @{username} tidak ditemukan!")
        return
    update_saldo(user["id"], amount)
    add_history(user["id"], "deposit", amount, f"Deposit {amount}")
    await update.message.reply_text(f"✅ Deposit @{username} +{amount:.2f} Koin")

# ==================== WITHDRAW ====================
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) < 1:
        await update.message.reply_text("❌ /withdraw 0.5")
        return
    try:
        amount = float(context.args[0].replace(",", "."))
    except:
        await update.message.reply_text("❌ Jumlah harus angka!")
        return
    if amount < WD_MIN:
        await update.message.reply_text(f"❌ Min WD {WD_MIN} Koin!")
        return
    user_data = get_user(user.id, user.username)
    if user_data["saldo"] < amount:
        await update.message.reply_text(f"❌ Saldo: {user_data['saldo']:.2f}")
        return
    if not user_data["dana"]:
        await update.message.reply_text("❌ /setdana dulu!")
        return
    add_withdraw_request(user.id, amount, user_data["dana"])
    await update.message.reply_text(f"✅ WD {amount:.2f} Koin → admin!")

async def cekwd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin!")
        return
    pending = get_pending_wd()
    if not pending:
        await update.message.reply_text("✅ Tidak ada WD pending.")
        return
    msg = "📤 LIST WD PENDING\n\n"
    for w in pending:
        msg += f"@{w['username']} - {w['amount']:.2f} Koin\nDANA: {w['dana']}\nID: {w['id']}\n---\n"
    await update.message.reply_text(msg)

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /confirm @user 0.5")
        return
    username = context.args[0].replace("@", "")
    try:
        amount = float(context.args[1].replace(",", "."))
    except:
        await update.message.reply_text("❌ Jumlah harus angka!")
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    if not user:
        await update.message.reply_text(f"❌ @{username} tidak ditemukan!")
        conn.close()
        return
    c.execute("SELECT * FROM withdraw_requests WHERE user_id = ? AND status = 'pending'", (user["id"],))
    wd = c.fetchone()
    if not wd:
        await update.message.reply_text(f"❌ Tidak ada WD pending untuk @{username}")
        conn.close()
        return
    c.execute("UPDATE withdraw_requests SET status = 'done' WHERE id = ?", (wd["id"],))
    conn.commit()
    conn.close()
    update_saldo(user["id"], -wd["amount"])
    add_history(user["id"], "withdraw", -wd["amount"], f"WD {wd['amount']}")
    await update.message.reply_text(f"✅ WD @{username} {wd['amount']:.2f} Koin selesai!")

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin!")
        return
    if len(context.args) < 1:
        await update.message.reply_text("❌ /reject @user")
        return
    username = context.args[0].replace("@", "")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    if not user:
        await update.message.reply_text(f"❌ @{username} tidak ditemukan!")
        conn.close()
        return
    c.execute("SELECT * FROM withdraw_requests WHERE user_id = ? AND status = 'pending'", (user["id"],))
    wd = c.fetchone()
    if not wd:
        await update.message.reply_text(f"❌ Tidak ada WD pending untuk @{username}")
        conn.close()
        return
    c.execute("UPDATE withdraw_requests SET status = 'rejected' WHERE id = ?", (wd["id"],))
    conn.commit()
    conn.close()
    update_saldo(user["id"], wd["amount"])
    add_history(user["id"], "reject", wd["amount"], f"WD ditolak {wd['amount']}")
    await update.message.reply_text(f"❌ WD @{username} {wd['amount']:.2f} Koin ditolak!")

# ==================== REKAP ====================
async def rekap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_k = sum(b["amount"] for b in bets["K"])
    total_b = sum(b["amount"] for b in bets["B"])
    msg = "📊 REKAP TARUHAN\n\n🔵 KECIL (K):\n"
    if bets["K"]:
        for b in bets["K"]:
            msg += f"  @{b['username']} {b['amount']:.2f}\n"
        msg += f"  Total: {total_k:.2f}\n\n"
    else:
        msg += "  (kosong)\n\n"
    msg += "🔴 BESAR (B):\n"
    if bets["B"]:
        for b in bets["B"]:
            msg += f"  @{b['username']} {b['amount']:.2f}\n"
        msg += f"  Total: {total_b:.2f}\n\n"
    else:
        msg += "  (kosong)\n\n"
    msg += f"Total semua: {total_k + total_b:.2f} Koin"
    await update.message.reply_text(msg)

# ==================== AUTO ROLL ON/OFF ====================
async def autoon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global auto_roll_enabled
    auto_roll_enabled = True
    await update.message.reply_text("✅ Auto roll diaktifkan!")

async def autooff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global auto_roll_enabled
    auto_roll_enabled = False
    await update.message.reply_text("❌ Auto roll dimatikan!")

# ==================== MAIN ====================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("setdana", setdana))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("lastwin", lastwin))
    app.add_handler(CommandHandler("bet", bet))
    app.add_handler(CommandHandler("rekap", rekap))
    app.add_handler(CommandHandler("roll", roll))
    app.add_handler(CommandHandler("deposit", deposit))
    app.add_handler(CommandHandler("withdraw", withdraw))
    app.add_handler(CommandHandler("cekwd", cekwd))
    app.add_handler(CommandHandler("confirm", confirm))
    app.add_handler(CommandHandler("reject", reject))
    app.add_handler(CommandHandler("confirmdeposit", confirmdeposit))
    app.add_handler(CommandHandler("autoon", autoon))
    app.add_handler(CommandHandler("autooff", autooff))
    app.add_handler(CallbackQueryHandler(kirim_bukti_callback, pattern="kirim_bukti"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_bukti))

    print("🤖 Bot dadu berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
