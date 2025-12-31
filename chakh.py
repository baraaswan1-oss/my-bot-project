cat << 'EOF' > chakh.py
import logging
import sqlite3
import os
import datetime
import asyncio
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

# إعدادات البوت
BOT_TOKEN = "7259081589:AAFLxrqldS6XyhrMwoDAHM9GIR1nZWZ9SFc"
DB_PATH = 'bot_data.db'
OWNER_ID = 6018370288  # المالك (لا يمكن حذفه)
SUPER_ADMIN_ID = 7289362045  # المشرف الفائق (يستطيع إدارة المشرفين)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS structure 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, parent_id INTEGER, label TEXT, content TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS admins 
                      (user_id INTEGER PRIMARY KEY, username TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, join_date TEXT)''')
    
    # إضافة المالك والمشرف الفائق لقاعدة البيانات كمشرفين تلقائياً
    cursor.execute("INSERT OR IGNORE INTO admins (user_id, username) VALUES (?, ?)", (OWNER_ID, "المالك (براء)"))
    cursor.execute("INSERT OR IGNORE INTO admins (user_id, username) VALUES (?, ?)", (SUPER_ADMIN_ID, "المشرف الفائق"))
    
    cursor.execute("SELECT id FROM structure WHERE id=1")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO structure (id, parent_id, label, content) VALUES (1, 0, 'الرئيسية', '<b>مرحباً بك في بوت الدروس الشرعية</b>')")
    conn.commit()
    conn.close()

def db_query(query, params=(), fetchone=False, commit=False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        if commit: conn.commit()
        return cursor.fetchone() if fetchone else cursor.fetchall()
    finally:
        conn.close()

def is_admin(user_id):
    return db_query("SELECT user_id FROM admins WHERE user_id=?", (user_id,), fetchone=True) is not None

def can_manage_admins(user_id):
    return user_id == OWNER_ID or user_id == SUPER_ADMIN_ID

def get_reply_keyboard(parent_id):
    children = db_query("SELECT label FROM structure WHERE parent_id=?", (parent_id,))
    kb = [[label[0]] for label in children]
    if parent_id != 1: kb.append(["🔙 عودة"])
    kb.append(["🔍 بحث", "🏠 الرئيسية"])
    kb.append(["🚀 تشغيل البوت"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    today = datetime.date.today().isoformat()
    db_query("INSERT OR IGNORE INTO users (user_id, join_date) VALUES (?, ?)", (uid, today), commit=True)
    
    node = db_query("SELECT content FROM structure WHERE id=1", fetchone=True)
    context.user_data['current_node'] = 1
    context.user_data['act'] = None 

    await update.message.reply_text(node[0], reply_markup=get_reply_keyboard(1), parse_mode=ParseMode.HTML)
    
    if is_admin(uid):
        total_users = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
        daily_users = db_query("SELECT COUNT(*) FROM users WHERE join_date=?", (today,), fetchone=True)[0]
        txt = f"🔧 <b>لوحة الإدارة</b>\n👤 المشتركين: {total_users}\n📅 جدد اليوم: {daily_users}"
        kb = [[InlineKeyboardButton("🛠 إدارة الأقسام", callback_data="manage_1")],
              [InlineKeyboardButton("📢 إذاعة للكل", callback_data="p_bc")]]
        
        # إظهار زر المشرفين فقط لمن يملك الصلاحية
        if can_manage_admins(uid):
            kb.append([InlineKeyboardButton("👥 إدارة المشرفين", callback_data="admin_list")])
            
        await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    if not is_admin(uid): return
    await query.answer()
    
    if query.data == "admin_list":
        if not can_manage_admins(uid): return
        ads = db_query("SELECT user_id, username FROM admins")
        txt = "👥 <b>قائمة المشرفين:</b>\n\n"
        kb = []
        for a in ads:
            # منع إظهار زر الحذف للمالك الأصلي تحت أي ظرف
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
        if not can_manage_admins(uid): return
        context.user_data['act'] = 'a_adm'
        await query.edit_message_text("✍️ أرسل ID المشرف الجديد:")

    elif query.data.startswith("del_adm_"):
        if not can_manage_admins(uid): return
        target_id = int(query.data.split("_")[2])
        
        # حماية إضافية برمجياً: منع حذف المالك
        if target_id == OWNER_ID:
            await query.message.reply_text("❌ خطأ: لا يمكن حذف المالك الأساسي.")
            return
            
        db_query("DELETE FROM admins WHERE user_id=?", (target_id,), commit=True)
        await query.message.reply_text("✅ تم حذف المشرف.")

    elif query.data.startswith("manage_"):
        nid = int(query.data.split("_")[1])
        n = db_query("SELECT * FROM structure WHERE id=?", (nid,), fetchone=True)
        if not n: return
        ch = db_query("SELECT id, label FROM structure WHERE parent_id=?", (nid,))
        txt = f"⚙️ <b>إدارة: {n[2]}</b>\n\n{n[3]}"
        kb = [[InlineKeyboardButton(f"📁 {c[1]}", callback_data=f"manage_{c[0]}")] for c in ch]
        kb.append([InlineKeyboardButton("📝 نص", callback_data=f"e_t_{nid}"), InlineKeyboardButton("✏️ اسم", callback_data=f"e_l_{nid}")])
        kb.append([InlineKeyboardButton("➕ زر فرعي", callback_data=f"a_b_{nid}")])
        if nid != 1:
            kb.append([InlineKeyboardButton("🗑 حذف", callback_data=f"c_d_{nid}"), InlineKeyboardButton("🔙 عودة", callback_data=f"manage_{n[1]}")])
        else:
            kb.append([InlineKeyboardButton("📥 Backup", callback_data="bk_dn"), InlineKeyboardButton("📤 دمج .db", callback_data="bk_up_info")])
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

    elif query.data == "bk_dn":
        await query.message.reply_document(document=open(DB_PATH, 'rb'), filename="backup.db")
    elif query.data == "bk_up_info":
        await query.edit_message_text("📤 أرسل ملف .db للدمج..")
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
        db_query("DELETE FROM structure WHERE id=? OR parent_id=?", (nid, nid), commit=True)
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
        n = db_query("SELECT parent_id FROM structure WHERE id=?", (curr,), fetchone=True)
        p_id = n[0] if (n and n[0] != 0) else 1
        context.user_data['current_node'] = p_id
        node = db_query("SELECT content FROM structure WHERE id=?", (p_id,), fetchone=True)
        await update.message.reply_text(node[0], reply_markup=get_reply_keyboard(p_id), parse_mode=ParseMode.HTML)
        return
    if act == 'search':
        results = db_query("SELECT id, label FROM structure WHERE label LIKE ? LIMIT 10", (f"%{text}%",))
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
    node_info = db_query("SELECT id, content FROM structure WHERE parent_id=? AND label=?", (curr, text), fetchone=True)
    if node_info:
        context.user_data['current_node'] = node_info[0]
        await update.message.reply_text(node_info[1], reply_markup=get_reply_keyboard(node_info[0]), parse_mode=ParseMode.HTML)
        return
    if not is_admin(uid) or not act: return
    
    if act == 'a_adm' and can_manage_admins(uid):
        try:
            db_query("INSERT OR IGNORE INTO admins (user_id, username) VALUES (?, ?)", (int(text), f"مشرف_{text}"), commit=True)
            await update.message.reply_text("✅ تمت إضافة المشرف بنجاح.")
        except: await update.message.reply_text("❌ ID غير صحيح.")
    elif act == 'add':
        db_query("INSERT INTO structure (parent_id, label, content) VALUES (?, ?, ?)", (context.user_data['pid'], text, "محتوى جديد"), commit=True)
        await update.message.reply_text("✅ أضيف الزر.")
    elif act == 'txt':
        db_query("UPDATE structure SET content=? WHERE id=?", (text, context.user_data['nid']), commit=True)
        await update.message.reply_text("✅ تم تحديث النص.")
    elif act == 'lbl':
        db_query("UPDATE structure SET label=? WHERE id=?", (text, context.user_data['nid']), commit=True)
        await update.message.reply_text("✅ تم تحديث الاسم.")
    context.user_data['act'] = None

async def go_to_node(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    nid = int(query.data.split("_")[1])
    n = db_query("SELECT content FROM structure WHERE id=?", (nid,), fetchone=True)
    if n:
        context.user_data['current_node'] = nid
        await query.message.reply_text(n[0], reply_markup=get_reply_keyboard(nid), parse_mode=ParseMode.HTML)
    await query.answer()

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    f = await update.message.document.get_file()
    tmp = "tmp.db"
    await f.download_to_drive(tmp)
    try:
        c2 = sqlite3.connect(tmp); cur2 = c2.cursor()
        cur2.execute("SELECT parent_id, label, content FROM structure WHERE id > 1")
        rows = cur2.fetchall(); c2.close()
        for r in rows:
            if not db_query("SELECT id FROM structure WHERE parent_id=? AND label=?", (r[0], r[1]), fetchone=True):
                db_query("INSERT INTO structure (parent_id, label, content) VALUES (?, ?, ?)", r, commit=True)
        os.remove(tmp)
        await update.message.reply_text("✅ تم الدمج بنجاح.")
    except Exception as e: await update.message.reply_text(f"❌ خطأ في الدمج: {e}")

if __name__ == '__main__':
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(go_to_node, pattern="^go_"))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_msg))
    print("البوت يعمل بصلاحيات المشرف الفائق الجديدة...")
    app.run_polling()
EOF
python3 chakh.py
