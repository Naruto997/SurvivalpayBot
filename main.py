from keep_alive import keep_alive
keep_alive()  # start server first

print("Bot polling started...")
bot.infinity_polling()




# main.py
import os
import json
import random
import time
import threading
from datetime import datetime, timezone
import telebot
from telebot import types
from keep_alive import run as run_webserver

DB_PATH = "db.json"

# helper: load/save DB
def load_db():
    if not os.path.exists(DB_PATH):
        with open(DB_PATH, "w") as f:
            f.write(json.dumps({
                "users": {}, "profiles": {}, "wallets": {},
                "earnings": [], "transactions": [], "withdraw_requests": [],
                "admin": {"admin_id": None}
            }))
    with open(DB_PATH, "r") as f:
        return json.load(f)

def save_db(db):
    with open(DB_PATH, "w") as f:
        json.dump(db, f, indent=2)

db = load_db()

# get token from env
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    print("ERROR: set TELEGRAM_TOKEN in env")
    raise SystemExit

bot = telebot.TeleBot(TOKEN, parse_mode=None)

# helper to ensure user exists
def ensure_user(uid, username):
    uid = str(uid)
    changed = False
    if uid not in db["users"]:
        db["users"][uid] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_banned": False,
            "honor_score": 100,
            "last_honor_recovery": None
        }
        changed = True
    if uid not in db["profiles"]:
        db["profiles"][uid] = {
            "username": username or f"user{uid}",
            "level": 1,
            "exp": 0,
            "banner": "default_banner.png",
            "avatar": ""
        }
        changed = True
    if uid not in db["wallets"]:
        db["wallets"][uid] = {
            "gold": 0,
            "diamonds": 0,
            "balance_usd": 0.0,
            "mined_at": None
        }
        changed = True
    if changed:
        save_db(db)

# small anti-spam: min seconds between plays
MIN_SECONDS_BETWEEN_PLAYS = 10
last_play = {}

# simplified match simulation based on your description
def simulate_match(uid, mode):
    # return dict: gold_earned, diamonds_earned, result, notes
    base = random.randint(8, 12)  # base earning
    gold = 0
    diamonds = 0
    notes = []
    result = "lose"

    if mode == "survival":
        # survive chance: 60% if not entering red zone
        survive = random.random() < 0.6
        hits = random.randint(0,4)
        if survive and hits <= 3:
            result = "win"
            gold = base + max(0, 5 - hits)  # fewer hits => bonus
            notes.append(f"Survived with {hits} hits.")
        else:
            result = "dead"
            gold = random.randint(1,4)
            notes.append(f"Failed. You took {hits} hits.")
    elif mode == "offensive":
        # count hits you deal (earn per hit)
        hits = random.randint(0, 8)
        result = "win" if hits > 0 else "lose"
        gold = base + hits * 2
        notes.append(f"You landed {hits} hits.")
    elif mode == "defense":
        # you can block up to 6 hits, but earn less
        blocked = random.randint(0,6)
        hits_taken = random.randint(0,6)
        if hits_taken <= 6:
            result = "win"
            gold = base + blocked
        else:
            result = "dead"
            gold = random.randint(1,5)
        notes.append(f"Blocked {blocked}, taken {hits_taken}.")
    elif mode == "rage":
        # you must kill >=1 machine to earn; kills are harder
        kills = sum(1 for _ in range(random.randint(1,5)) if random.random() < 0.3)
        if kills >= 1:
            result = "win"
            gold = base + kills * 5
            # diamonds: gain 1 diamond only after killing 2 machines
            if kills >= 2:
                diamonds = 1
            notes.append(f"Killed {kills} machines.")
        else:
            result = "lose"
            gold = random.randint(0,3)
            notes.append("Couldn't kill any machines.")
    elif mode == "ninja":
        # more hiding, a bit more gold
        hidden_time = random.randint(1,10)
        if hidden_time <= 10:
            result = "win"
            gold = base + 5
            notes.append(f"Hidden for {hidden_time}s, escaped detection.")
        else:
            result = "dead"
            gold = random.randint(1,3)
            notes.append("Trapped for too long.")
    # cap earnings
    gold = max(0, min(gold, 50))
    return {"gold": gold, "diamonds": diamonds, "result": result, "notes": "; ".join(notes)}

# helper to create earning record & credit wallet (auto)
def record_earn_and_credit(uid, mode, gold, diamonds, result):
    uid = str(uid)
    rec = {
        "user_id": uid,
        "match_id": f"m_{int(time.time()*1000)}",
        "mode": mode,
        "gold_earned": int(gold),
        "diamonds_earned": int(diamonds),
        "result": result,
        "verified": True,   # small prototype: auto-verify
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    db["earnings"].append(rec)
    # transactions log
    tx = {
        "user_id": uid,
        "type": "earn",
        "gold_delta": int(gold),
        "diamonds_delta": int(diamonds),
        "amount_usd": 0.0,
        "status": "completed",
        "meta": {"mode": mode, "match_id": rec["match_id"]},
        "created_at": rec["created_at"]
    }
    db["transactions"].append(tx)
    # credit
    db["wallets"][uid]["gold"] += int(gold)
    db["wallets"][uid]["diamonds"] += int(diamonds)
    save_db(db)
    return rec, tx

# keyboard for main menu
def main_menu_markup():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("/play", "/wallet", "/profile")
    kb.row("/withdraw", "/earnings")
    return kb

@bot.message_handler(commands=["start"])
def cmd_start(message):
    uid = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    ensure_user(uid, username)
    bot.send_message(uid, f"Welcome {username}! This is SurvivalPay (prototype). Use the menu below.", reply_markup=main_menu_markup())

@bot.message_handler(commands=["profile"])
def cmd_profile(message):
    uid = str(message.from_user.id)
    if uid not in db["profiles"]:
        ensure_user(uid, message.from_user.username)
    p = db["profiles"][uid]
    u = db["users"][uid]
    txt = f"Username: {p['username']}\nLevel: {p['level']} (EXP: {p['exp']})\nHonor: {u['honor_score']}\nJoined: {u['created_at']}"
    bot.send_message(message.chat.id, txt)

@bot.message_handler(commands=["wallet"])
def cmd_wallet(message):
    uid = str(message.from_user.id)
    if uid not in db["wallets"]:
        ensure_user(uid, message.from_user.username)
    w = db["wallets"][uid]
    txt = f"Gold: {w['gold']}  |  Diamonds: {w['diamonds']}\nUSD Balance: ${w['balance_usd']:.2f}"
    bot.send_message(message.chat.id, txt)

@bot.message_handler(commands=["play"])
def cmd_play(message):
    uid = str(message.from_user.id)
    if db["users"].get(uid, {}).get("is_banned"):
        bot.send_message(message.chat.id, "Your account is banned.")
        return
    kb = types.InlineKeyboardMarkup()
    modes = ["survival", "offensive", "defense", "rage", "ninja"]
    for m in modes:
        kb.add(types.InlineKeyboardButton(text=m.capitalize(), callback_data=f"mode:{m}"))
    bot.send_message(message.chat.id, "Choose a mode:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mode:"))
def handle_mode(call):
    mode = call.data.split(":",1)[1]
    uid = call.from_user.id
    now = time.time()
    last = last_play.get(uid, 0)
    if now - last < MIN_SECONDS_BETWEEN_PLAYS:
        bot.answer_callback_query(call.id, "You are playing too fast. Wait a bit.")
        return
    last_play[uid] = now
    # simulate match
    res = simulate_match(uid, mode)
    rec, tx = record_earn_and_credit(uid, mode, res["gold"], res["diamonds"], res["result"])
    text = f"Mode: {mode}\nResult: {res['result']}\nGold earned: {res['gold']}\nDiamonds earned: {res['diamonds']}\nNotes: {res['notes']}\n\nYour wallet updated."
    bot.send_message(call.message.chat.id, text)

@bot.message_handler(commands=["earnings"])
def cmd_earnings(message):
    uid = str(message.from_user.id)
    user_earnings = [e for e in db["earnings"] if e["user_id"] == uid]
    if not user_earnings:
        bot.send_message(message.chat.id, "No earnings found yet.")
        return
    lines = []
    for e in sorted(user_earnings, key=lambda x: x["created_at"], reverse=True)[:10]:
        lines.append(f"{e['created_at'][:19]} | {e['mode']} | G:{e['gold_earned']} D:{e['diamonds_earned']} | {e['result']}")
    bot.send_message(message.chat.id, "Recent earnings:\n" + "\n".join(lines))

# withdraw flow
withdraw_state = {}

@bot.message_handler(commands=["withdraw"])
def cmd_withdraw(message):
    uid = str(message.from_user.id)
    w = db["wallets"].get(uid)
    if not w:
        ensure_user(message.from_user.id, message.from_user.username)
        w = db["wallets"][uid]
    # require at least 1 diamond
    if w["diamonds"] < 1:
        bot.send_message(message.chat.id, "Minimum 1 Diamond required to withdraw. You have: {}".format(w["diamonds"]))
        return
    msg = bot.send_message(message.chat.id, "Enter your payout wallet address or PayPal email (where we will send money):")
    bot.register_next_step_handler(msg, process_withdraw_address)

def process_withdraw_address(message):
    addr = message.text.strip()
    uid = str(message.from_user.id)
    w = db["wallets"][uid]
    # compute amount: 1 diamond = $1 (prototype) (you can change later)
    diamonds = w["diamonds"]
    usd_value = diamonds * 1.0  # adjust exchange rate here
    # store withdraw request
    req = {
        "id": f"wr_{int(time.time()*1000)}",
        "user_id": uid,
        "amount_usd": round(usd_value, 2),
        "wallet_address": addr,
        "fee_percent": 20.0,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    db["withdraw_requests"].append(req)
    save_db(db)
    bot.send_message(message.chat.id, f"Withdraw request created for ${req['amount_usd']:.2f}. Admin will review and pay you manually. Request id: {req['id']}")

# admin commands (simple)
def is_admin(user_id):
    admin_id = db.get("admin", {}).get("admin_id")
    try:
        return str(user_id) == str(admin_id)
    except:
        return False

@bot.message_handler(commands=["set_admin"])
def cmd_set_admin(message):
    # only allow if bot owner not set; or allow if current user is current admin
    uid = str(message.from_user.id)
    if db["admin"].get("admin_id") and not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "This command is admin-only.")
        return
    db["admin"]["admin_id"] = uid
    save_db(db)
    bot.send_message(message.chat.id, "You are now admin for this bot.")

@bot.message_handler(commands=["admin_withdraws"])
def cmd_admin_withdraws(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "Admin only.")
        return
    pending = [r for r in db["withdraw_requests"] if r["status"] == "pending"]
    if not pending:
        bot.send_message(message.chat.id, "No pending withdraws.")
        return
    lines = []
    for r in pending:
        lines.append(f"{r['id']} | user:{r['user_id']} | ${r['amount_usd']} | addr:{r['wallet_address']} | {r['created_at']}")
    bot.send_message(message.chat.id, "Pending withdraws:\n" + "\n".join(lines))

@bot.message_handler(commands=["approve_withdraw"])
def cmd_approve_withdraw(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "Admin only.")
        return
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "Usage: /approve_withdraw WR_ID")
        return
    rid = parts[1]
    for r in db["withdraw_requests"]:
        if r["id"] == rid and r["status"] == "pending":
            # mark as approved & paid (admin will perform manual external transfer)
            r["status"] = "paid"
            # apply fee: subtract from nothing here because we charged diamonds -> conversion model is simple
            # reset user's diamonds to 0 (they converted diamonds to withdraw)
            uid = r["user_id"]
            db["wallets"][uid]["diamonds"] = 0
            save_db(db)
            bot.send_message(message.chat.id, f"Withdraw {rid} marked as PAID. Don't forget to actually transfer the funds!")
            try:
                bot.send_message(int(uid), f"Your withdraw {rid} of ${r['amount_usd']} has been approved and marked PAID by admin.")
            except:
                pass
            return
    bot.send_message(message.chat.id, "Withdraw id not found or not pending.")

@bot.message_handler(commands=["help"])
def cmd_help(message):
    help_text = "/play - play a mode\n/wallet - show wallet\n/profile - profile\n/earnings - recent earnings\n/withdraw - request payout (min 1 diamond)\n\nAdmin commands:\n/set_admin - set yourself admin (first time)\n/admin_withdraws - list pending withdraws\n/approve_withdraw <id> - mark paid"
    bot.send_message(message.chat.id, help_text)

# run webserver in a thread (for UptimeRobot keep-alive)
t = threading.Thread(target=run_webserver)
t.daemon = True
t.start()

# start bot polling
print("Bot polling started...")
bot.infinity_polling()


# --- Deposit Requirement System ---

# Ensure deposit status is tracked in DB
def ensure_deposit_field(uid):
    uid = str(uid)
    if "deposit_paid" not in db["users"][uid]:
        db["users"][uid]["deposit_paid"] = False
        save_db(db)

# User command: deposit instructions
@bot.message_handler(commands=["deposit"])
def cmd_deposit(message):
    uid = str(message.from_user.id)
    ensure_user(uid, message.from_user.username)
    ensure_deposit_field(uid)
    bot.send_message(message.chat.id,
        "💰 To enable withdrawals, you must pay a $5 security deposit.\n\n"
        "Send $5 to this wallet or payment method:\n\n"
        "**Your Wallet Address or Payment Method Here**\n\n"
        "After payment, send /confirm_deposit to request approval.",
        parse_mode="Markdown"
    )

# User command: confirm deposit request
@bot.message_handler(commands=["confirm_deposit"])
def cmd_confirm_deposit(message):
    uid = str(message.from_user.id)
    ensure_user(uid, message.from_user.username)
    ensure_deposit_field(uid)

    if db["users"][uid]["deposit_paid"]:
        bot.send_message(message.chat.id, "✅ Your deposit is already confirmed. You can withdraw anytime.")
        return

    # Add request to pending deposits
    deposit_req = {
        "id": f"dep_{int(time.time()*1000)}",
        "user_id": uid,
        "username": message.from_user.username or message.from_user.first_name,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    if "deposit_requests" not in db:
        db["deposit_requests"] = []
    db["deposit_requests"].append(deposit_req)
    save_db(db)

    bot.send_message(message.chat.id, "📩 Your deposit confirmation request has been sent to the admin. Please wait for approval.")

# Admin command: view pending deposits
@bot.message_handler(commands=["admin_deposits"])
def cmd_admin_deposits(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "Admin only.")
        return
    pending = [r for r in db.get("deposit_requests", []) if r["status"] == "pending"]
    if not pending:
        bot.send_message(message.chat.id, "No pending deposit confirmations.")
        return
    lines = []
    for r in pending:
        lines.append(f"{r['id']} | user:{r['username']} ({r['user_id']}) | {r['created_at']}")
    bot.send_message(message.chat.id, "Pending deposit confirmations:\n" + "\n".join(lines))

# Admin command: approve deposit
@bot.message_handler(commands=["approve_deposit"])
def cmd_approve_deposit(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "Admin only.")
        return
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "Usage: /approve_deposit USER_ID")
        return
    uid = parts[1]
    if uid not in db["users"]:
        bot.send_message(message.chat.id, "User not found.")
        return

    # Mark deposit as paid
    db["users"][uid]["deposit_paid"] = True
    # Update deposit request status
    for r in db.get("deposit_requests", []):
        if r["user_id"] == uid and r["status"] == "pending":
            r["status"] = "approved"
    save_db(db)

    bot.send_message(message.chat.id, f"Deposit approved for user {uid}.")
    try:
        bot.send_message(int(uid), "Your $5 deposit has been approved. You can now withdraw your earnings.")
    except:
        pass

# --- Update Withdraw Command to Check Deposit ---
@bot.message_handler(commands=["withdraw"])
def cmd_withdraw(message):
    uid = str(message.from_user.id)
    ensure_user(uid, message.from_user.username)
    ensure_deposit_field(uid)

    if not db["users"][uid]["deposit_paid"]:
        bot.send_message(message.chat.id, "You must pay a $5 deposit before withdrawing. Use /deposit for instructions.")
        return

    w = db["wallets"].get(uid)
    if not w:
        ensure_user(message.from_user.id, message.from_user.username)
        w = db["wallets"][uid]
    if w["diamonds"] < 1:
        bot.send_message(message.chat.id, f"Minimum 1 Diamond required to withdraw. You have: {w['diamonds']}")
        return
    msg = bot.send_message(message.chat.id, "Enter your payout wallet address or PayPal email:")
    bot.register_next_step_handler(msg, process_withdraw_address)
    
