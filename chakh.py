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

# --- الإعدادات الأساسية ---
BOT_TOKEN = "7259081589:AAFLxrqldS6XyhrMwoDAHM9GIR1nZWZ9SFc"
OWNER_ID = 6018370288  
SUPER_ADMIN_ID = 7289362045  

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def get_db_connection():
    return psycopg2.connect(
        host="db.wwxsgddxilprofweergb.supabase.co",
        database="postgres",
        user="postgres",
        password="ha72$th!bU@cXUd",
        port="5432"
    )

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

def is_admin(user_id):
    res = db_query("SELECT user_id FROM admins WHERE user_id=%s", (user_id,), fetchone=True)
    return res is not None

def get_reply_keyboard(parent_id):
    children = db_query("SELECT label FROM structure WHERE parent_id=%s", (parent_id,))
    kb = [[label[0]] for label in children]
    if parent_id != 1: kb.append(["🔙 عودة"])
    kb.append(["🔍 بحث", "🏠 الرئيسية"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    db_query("INSERT INTO users (user_id, join_date) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (uid, datetime.date.today().isoformat()), commit=True)
    node = db_query("SELECT content FROM structure WHERE id=1", fetchone=True)
    context.user_data['current_node'] = 1
    context.user_data['act'] = None 
    
    await update.message.reply_text(node[0], reply_markup=get_reply_keyboard(1), parse_mode=ParseMode.HTML)
    
    if is_admin(uid):
        total_users = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
        txt = f"🔧 <b>لوحة الإدارة السحابية</b>\n👤 عدد المشتركين: {total_users}"
        kb = [[InlineKeyboardButton("🛠 إدارة الأقسام", callback_data="manage_1")],
              [InlineKeyboardButton("📢 إذاعة للكل", callback_data="p_bc")]]
        await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    if not is_admin(uid): 
        await query.answer("عذراً، لست مسؤولاً.", show_alert=True)
        return
    
    await query.answer() # لإيقاف تحميل الزر عند المستخدم
    data = query.data

    if data.startswith("manage_"):
        nid = int(data.split("_")[1])
        n = db_query("SELECT * FROM structure WHERE id=%s", (nid,), fetchone=True)
        if not n: return
        ch = db_query("SELECT id, label FROM structure WHERE parent_id=%s", (nid,))
        txt = f"⚙️ <b>إدارة القسم: {n[2]}</b>\n\nالمحتوى الحالي:\n{n[3]}"
        kb = [[InlineKeyboardButton(f"📁 {c[1]}", callback_data=f"manage_{c[0]}")] for c in ch]
        kb.append([InlineKeyboardButton("📝 تعديل النص", callback_data=f"e_t_{nid}"), InlineKeyboardButton("✏️ تعديل الاسم", callback_data=f"e_l_{nid}")])
        kb.append([InlineKeyboardButton("➕ إضافة زر فرعي", callback_data=f"a_b_{nid}")])
        if nid != 1:
            kb.append([InlineKeyboardButton("🗑 حذف القسم", callback_data=f"c_d_{nid}")])
        kb.append([InlineKeyboardButton("🔙 عودة للخلف", callback_data=f"manage_{n[1]}")])
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

    elif data == "p_bc":
        context.user_data['act'] = 'bc'
        await query.edit_message_text("✍️ أرسل رسالة الإذاعة الآن (نص أو وسائط):")

    elif data.startswith("a_b_"):
        context.user_data.update({'act': 'add', 'pid': data.split("_")[2]})
        await query.edit_message_text("✍️ أرسل اسم الزر الجديد:")

    elif data.startswith("e_t_"):
        context.user_data.update({'act': 'txt', 'nid': data.split("_")[2]})
        await query.edit_message_text("✍️ أرسل النص (المحتوى) الجديد للقسم:")

    elif data.startswith("e_l_"):
        context.user_data.update({'act': 'lbl', 'nid': data.split("_")[2]})
        await query.edit_message_text("✍️ أرسل الاسم الجديد للزر:")

    elif data.startswith("c_d_"):
        nid = data.split("_")[2]
        kb = [[InlineKeyboardButton("✅ نعم، احذف", callback_data=f"confirm_del_{nid}"), InlineKeyboardButton("❌ تراجع", callback_data=f"manage_{nid}")]]
        await query.edit_message_text("⚠️ هل أنت متأكد؟ حذف هذا القسم سيحذف كل ما بداخله!", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("confirm_del_"):
        nid = int(data.split("_")[2])
        db_query("DELETE FROM structure WHERE id=%s OR parent_id=%s", (nid, nid), commit=True)
        await query.message.reply_text("✅ تم حذف القسم بنجاح.")
        # العودة للرئيسية بعد الحذف
        n = db_query("SELECT content FROM structure WHERE id=1", fetchone=True)
        await query.message.reply_text(n[0], reply_markup=get_reply_keyboard(1), parse_mode=ParseMode.HTML)

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    curr = context.user_data.get('current_node', 1)
    act = context.user_data.get('act')

    if text == "🏠 الرئيسية":
        context.user_data['act'] = None
        await start(update, context)
        return

    if text == "🔙 عودة":
        n = db_query("SELECT parent_id FROM structure WHERE id=%s", (curr,), fetchone=True)
        p_id = n[0] if (n and n[0] != 0) else 1
        context.user_data['current_node'] = p_id
        node = db_query("SELECT content FROM structure WHERE id=%s", (p_id,), fetchone=True)
        await update.message.reply_text(node[0], reply_markup=get_reply_keyboard(p_id), parse_mode=ParseMode.HTML)
        return

    # معالجة ضغطات أزرار المستخدم العادية
    node_info = db_query("SELECT id, content FROM structure WHERE parent_id=%s AND label=%s", (curr, text), fetchone=True)
    if node_info:
        context.user_data['current_node'] = node_info[0]
        await update.message.reply_text(node_info[1], reply_markup=get_reply_keyboard(node_info[0]), parse_mode=ParseMode.HTML)
        return

    # معالجة مدخلات الإدارة
    if not is_admin(uid) or not act: return

    if act == 'add':
        db_query("INSERT INTO structure (parent_id, label, content) VALUES (%s, %s, %s)", (context.user_data['pid'], text, "محتوى تجريبي.. قم بتعديله من لوحة الإدارة"), commit=True)
        await update.message.reply_text(f"✅ تم إضافة الزر '{text}' بنجاح.")
    elif act == 'txt':
        db_query("UPDATE structure SET content=%s WHERE id=%s", (text, context.user_data['nid']), commit=True)
        await update.message.reply_text("✅ تم تحديث نص القسم.")
    elif act == 'lbl':
        db_query("UPDATE structure SET label=%s WHERE id=%s", (text, context.user_data['nid']), commit=True)
        await update.message.reply_text("✅ تم تغيير اسم الزر.")
    elif act == 'bc':
        users = db_query("SELECT user_id FROM users")
        await update.message.reply_text(f"⏳ جاري الإذاعة لـ {len(users)} مشترك...")
        count = 0
        for u in users:
            try:
                await context.bot.send_message(u[0], text)
                count += 1
                await asyncio.sleep(0.05)
            except: pass
        await update.message.reply_text(f"✅ تمت الإذاعة بنجاح لـ {count} شخص.")

    context.user_data['act'] = None

if __name__ == '__main__':
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # الترتيب مهم جداً هنا
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_msg))
    
    print("البوت السحابي يعمل الآن بكفاءة...")
    app.run_polling()
