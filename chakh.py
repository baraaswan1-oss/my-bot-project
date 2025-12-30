import logging
import os
import datetime
import asyncio
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# --- إعدادات الاتصال السحابي (بياناتك الخاصة) ---
BOT_TOKEN = "7259081589:AAFLxrqldS6XyhrMwoDAHM9GIR1nZWZ9SFc"
# الرابط مدمج مع كلمة المرور التي زودتني بها
DATABASE_URL = "postgresql://postgres:ha72$th!bU@cXUd@db.wwxsgddxilprofweergb.supabase.co:5432/postgres"

OWNER_ID = 6018370288  
SUPER_ADMIN_ID = 7289362045  

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS structure 
                   (id SERIAL PRIMARY KEY, parent_id INTEGER, label TEXT, content TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS admins 
                   (user_id BIGINT PRIMARY KEY, username TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
                   (user_id BIGINT PRIMARY KEY, join_date TEXT)''')
    
    cur.execute("INSERT INTO admins (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (OWNER_ID, "المالك (براء)"))
    cur.execute("INSERT INTO admins (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (SUPER_ADMIN_ID, "المشرف الفائق"))
    
    cur.execute("SELECT id FROM structure WHERE id=1")
    if not cur.fetchone():
        cur.execute("INSERT INTO structure (id, parent_id, label, content) VALUES (1, 0, 'الرئيسية', '<b>مرحباً بك في بوت الدروس الشرعية</b>')")
    conn.commit()
    cur.close()
    conn.close()

def db_query(query, params=(), fetchone=False, commit=False):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        if commit: conn.commit()
        if fetchone: return cur.fetchone()
        try: return cur.fetchall()
        except: return None
    finally:
        cur.close()
        conn.close()

def is_admin(user_id):
    res = db_query("SELECT user_id FROM admins WHERE user_id=%s", (user_id,), fetchone=True)
    return res is not None

def get_reply_keyboard(parent_id):
    children = db_query("SELECT label FROM structure WHERE parent_id=%s", (parent_id,))
    kb = [[label[0]] for label in children]
    if parent_id != 1: kb.append(["🔙 عودة"])
    kb.append(["🔍 بحث", "🏠 الرئيسية"])
    kb.append(["🚀 تشغيل البوت"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    today = datetime.date.today().isoformat()
    db_query("INSERT INTO users (user_id, join_date) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (uid, today), commit=True)
    node = db_query("SELECT content FROM structure WHERE id=1", fetchone=True)
    context.user_data['current_node'] = 1
    context.user_data['act'] = None 
    await update.message.reply_text(node[0], reply_markup=get_reply_keyboard(1), parse_mode=ParseMode.HTML)
    if is_admin(uid):
        total_users = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
        daily_users = db_query("SELECT COUNT(*) FROM users WHERE join_date=%s", (today,), fetchone=True)[0]
        txt = f"🔧 <b>لوحة الإدارة السحابية</b>\n👤 المشتركين: {total_users}\n📅 جدد اليوم: {daily_users}"
        kb = [[InlineKeyboardButton("🛠 إدارة الأقسام", callback_data="manage_1")],
              [InlineKeyboardButton("📢 إذاعة للكل", callback_data="p_bc")]]
        if uid in [OWNER_ID, SUPER_ADMIN_ID]:
            kb.append([InlineKeyboardButton("👥 إدارة المشرفين", callback_data="admin_list")])
        await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    if not is_admin(uid): return
    await query.answer()
    if query.data == "admin_list":
        ads = db_query("SELECT user_id, username FROM admins")
        txt = "👥 <b>قائمة المشرفين:</b>\n\n"
        kb = []
        for a in ads:
            if a[0] == OWNER_ID:
                txt += f"👑 {a[1]} (مالك)\n"
                continue
            kb.append([InlineKeyboardButton(f"🗑 حذف {a[1]}", callback_data=f"del_adm_{a[0]}")])
        kb.append([InlineKeyboardButton("➕ إضافة مشرف جديد", callback_data="p_add_adm")])
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    elif query.data == "p_bc":
        context.user_data['act'] = 'bc'
        await query.edit_message_text("✍️ أرسل رسالة الإذاعة الآن:")
    elif query.data == "p_add_adm":
        context.user_data['act'] = 'a_adm'
        await query.edit_message_text("✍️ أرسل ID المشرف الجديد:")
    elif query.data.startswith("del_adm_"):
        target_id = int(query.data.split("_")[2])
        if target_id == OWNER_ID: return
        db_query("DELETE FROM admins WHERE user_id=%s", (target_id,), commit=True)
        await query.message.reply_text("✅ تم حذف المشرف.")
    elif query.data.startswith("manage_"):
        nid = int(query.data.split("_")[1])
        n = db_query("SELECT * FROM structure WHERE id=%s", (nid,), fetchone=True)
        if not n: return
        ch = db_query("SELECT id, label FROM structure WHERE parent_id=%s", (nid,))
        txt = f"⚙️ <b>إدارة: {n[2]}</b>\n\n{n[3]}"
        kb = [[InlineKeyboardButton(f"📁 {c[1]}", callback_data=f"manage_{c[0]}")] for c in ch]
        kb.append([InlineKeyboardButton("📝 نص", callback_data=f"e_t_{nid}"), InlineKeyboardButton("✏️ اسم", callback_data=f"e_l_{nid}")])
        kb.append([InlineKeyboardButton("➕ زر فرعي", callback_data=f"a_b_{nid}")])
        if nid != 1:
            kb.append([InlineKeyboardButton("🗑 حذف", callback_data=f"c_d_{nid}"), InlineKeyboardButton("🔙 عودة", callback_data=f"manage_{n[1]}")])
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    elif query.data.startswith("a_b_"):
        context.user_data.update({'act': 'add', 'pid': query.data.split("_")[3]})
        await query.edit_message_text("✍️ اسم الزر الجديد:")
    elif query.data.startswith("e_t_"):
        context.user_data.update({'act': 'txt', 'nid': query.data.split("_")[3]})
        await query.edit_message_text("✍️ النص الجديد:")
    elif query.data.startswith("e_l_"):
        context.user_data.update({'act': 'lbl', 'nid': query.data.split("_")[3]})
        await query.edit_message_text("✍️ الاسم الجديد:")
    elif query.data.startswith("c_d_"):
        nid = query.data.split("_")[2]
        kb = [[InlineKeyboardButton("✅ حذف", callback_data=f"x_d_{nid}"), InlineKeyboardButton("❌ تراجع", callback_data=f"manage_{nid}")]]
        await query.edit_message_text("⚠️ متأكد؟ سيتم حذف الفرع بالكامل!", reply_markup=InlineKeyboardMarkup(kb))
    elif query.data.startswith("x_d_"):
        nid = int(query.data.split("_")[2])
        db_query("DELETE FROM structure WHERE id=%s OR parent_id=%s", (nid, nid), commit=True)
        await query.message.reply_text("✅ تم الحذف.")
        await start(update, context)

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    curr = context.user_data.get('current_node', 1)
    act = context.user_data.get('act')
    if text in ["🚀 تشغيل البوت", "🏠 الرئيسية"]:
        context.user_data['act'] = None
        await start(update, context)
        return
    if text == "🔍 بحث":
        context.user_data['act'] = 'search'
        await update.message.reply_text("✍️ أرسل كلمة البحث:")
        return
    if text == "🔙 عودة":
        n = db_query("SELECT parent_id FROM structure WHERE id=%s", (curr,), fetchone=True)
        p_id = n[0] if (n and n[0] != 0) else 1
        context.user_data['current_node'] = p_id
        node = db_query("SELECT content FROM structure WHERE id=%s", (p_id,), fetchone=True)
        await update.message.reply_text(node[0], reply_markup=get_reply_keyboard(p_id), parse_mode=ParseMode.HTML)
        return
    if act == 'search':
        results = db_query("SELECT id, label FROM structure WHERE label ILIKE %s LIMIT 10", (f"%{text}%",))
        if not results: await update.message.reply_text("❌ لا توجد نتائج.")
        else:
            kb = [[InlineKeyboardButton(r[1], callback_data=f"go_{r[0]}")] for r in results]
            await update.message.reply_text("🔍 النتائج:", reply_markup=InlineKeyboardMarkup(kb))
        context.user_data['act'] = None
        return
    if act == 'bc' and is_admin(uid):
        users = db_query("SELECT user_id FROM users")
        await update.message.reply_text(f"⏳ إرسال لـ {len(users)}...")
        count = 0
        for u in users:
            try:
                await context.bot.send_message(u[0], text)
                count += 1
                await asyncio.sleep(0.05)
            except: pass
        await update.message.reply_text(f"✅ تم الإرسال لـ {count}.")
        context.user_data['act'] = None
        return
    node_info = db_query("SELECT id, content FROM structure WHERE parent_id=%s AND label=%s", (curr, text), fetchone=True)
    if node_info:
        context.user_data['current_node'] = node_info[0]
        await update.message.reply_text(node_info[1], reply_markup=get_reply_keyboard(node_info[0]), parse_mode=ParseMode.HTML)
        return
    if not is_admin(uid) or not act: return
    if act == 'a_adm' and uid in [OWNER_ID, SUPER_ADMIN_ID]:
        try:
            db_query("INSERT INTO admins (user_id, username) VALUES (%s, %s) ON CONFLICT DO NOTHING", (int(text), f"مشرف_{text}"), commit=True)
            await update.message.reply_text("✅ تمت إضافة المشرف.")
        except: await update.message.reply_text("❌ ID غير صحيح.")
    elif act == 'add':
        db_query("INSERT INTO structure (parent_id, label, content) VALUES (%s, %s, %s)", (context.user_data['pid'], text, "محتوى جديد"), commit=True)
        await update.message.reply_text("✅ أضيف الزر.")
    elif act == 'txt':
        db_query("UPDATE structure SET content=%s WHERE id=%s", (text, context.user_data['nid']), commit=True)
        await update.message.reply_text("✅ تم تحديث النص.")
    elif act == 'lbl':
        db_query("UPDATE structure SET label=%s WHERE id=%s", (text, context.user_data['nid']), commit=True)
        await update.message.reply_text("✅ تم تحديث الاسم.")
    context.user_data['act'] = None

async def go_to_node(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    nid = int(query.data.split("_")[1])
    n = db_query("SELECT content FROM structure WHERE id=%s", (nid,), fetchone=True)
    if n:
        context.user_data['current_node'] = nid
        await query.message.reply_text(n[0], reply_markup=get_reply_keyboard(nid), parse_mode=ParseMode.HTML)
    await query.answer()

if __name__ == '__main__':
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(go_to_node, pattern="^go_"))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_msg))
    print("البوت السحابي يعمل الآن...")
    app.run_polling()
