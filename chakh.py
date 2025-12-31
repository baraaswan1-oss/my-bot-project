import logging
import os
import datetime
import asyncio
import psycopg2
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
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

# --- إعدادات الأمان والهوية ---
# توكن البوت الخاص بك
BOT_TOKEN = "7259081589:AAFLxrqldS6XyhrMwoDAHM9GIR1nZWZ9SFc"
# المعرف الخاص بك (المالك)
OWNER_ID = 6018370288  
# المعرف الفائق
SUPER_ADMIN_ID = 7289362045  

# إعداد السجلات (Logging) لمراقبة الأداء والأخطاء
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- نظام إبقاء البوت حياً (Health Check) ---
# هذا الجزء ضروري للمنصات السحابية لمنع إغلاق الخدمة تلقائياً
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is active and running!")

    def log_message(self, format, *args):
        return # منع إغراق السجلات بطلبات الـ Health Check

def run_health_server():
    # المنصات السحابية تستخدم المنفذ 7860 أو المتغير PORT
    port = int(os.environ.get("PORT", 7860))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# --- إدارة قاعدة البيانات (Supabase/PostgreSQL) ---
def get_db_connection():
    # استخدام تفاصيل الاتصال المباشرة لتجنب أخطاء المتغيرات البيئية ورموز كلمة المرور
    return psycopg2.connect(
        host="db.wwxsgddxilprofweergb.supabase.co",
        database="postgres",
        user="postgres",
        password="ha72$th!bU@cXUd",
        port="5432"
    )

def db_query(query, params=(), fetchone=False, commit=False):
    """دالة موحدة لتنفيذ الاستعلامات لضمان إغلاق الاتصال دائماً"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        if commit:
            conn.commit()
        if fetchone:
            return cur.fetchone()
        try:
            return cur.fetchall()
        except:
            return None
    except Exception as e:
        logger.error(f"Database Error: {e}")
        return None
    finally:
        cur.close()
        conn.close()

def init_db():
    """تجهيز الجداول الأساسية عند بدء التشغيل"""
    conn = get_db_connection()
    cur = conn.cursor()
    # جدول الهيكل الشجري للأقسام
    cur.execute('''CREATE TABLE IF NOT EXISTS structure 
                   (id SERIAL PRIMARY KEY, parent_id INTEGER, label TEXT, content TEXT)''')
    # جدول المشرفين
    cur.execute('''CREATE TABLE IF NOT EXISTS admins 
                   (user_id BIGINT PRIMARY KEY, username TEXT)''')
    # جدول المستخدمين للإذاعة
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
                   (user_id BIGINT PRIMARY KEY, join_date TEXT)''')
    
    # إضافة المالك والمشرف تلقائياً
    cur.execute("INSERT INTO admins (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (OWNER_ID, "المالك الرئيسي"))
    cur.execute("INSERT INTO admins (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (SUPER_ADMIN_ID, "المشرف الفائق"))
    
    # التأكد من وجود العقدة الرئيسية (الصفحة الرئيسية)
    cur.execute("SELECT id FROM structure WHERE id=1")
    if not cur.fetchone():
        cur.execute("INSERT INTO structure (id, parent_id, label, content) VALUES (1, 0, 'الرئيسية', '<b>🌿 مرحباً بك في بوت الدروس الشرعية</b>\n\nاستخدم الأزرار أدناه للتنقل بين الأقسام.')")
    
    conn.commit()
    cur.close()
    conn.close()

# --- وظائف التحقق المساعدة ---
def is_admin(user_id):
    res = db_query("SELECT user_id FROM admins WHERE user_id=%s", (user_id,), fetchone=True)
    return res is not None

def get_reply_keyboard(parent_id):
    """إنشاء لوحة الأزرار بناءً على الأقسام الفرعية في قاعدة البيانات"""
    children = db_query("SELECT label FROM structure WHERE parent_id=%s ORDER BY id ASC", (parent_id,))
    kb = [[label[0]] for label in children]
    if parent_id != 1:
        kb.append(["🔙 عودة"])
    kb.append(["🔍 بحث", "🏠 الرئيسية"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# --- معالجات الأوامر والرسائل ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # تسجيل المستخدم الجديد
    db_query("INSERT INTO users (user_id, join_date) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", 
             (uid, datetime.date.today().isoformat()), commit=True)
    
    node = db_query("SELECT content FROM structure WHERE id=1", fetchone=True)
    context.user_data['current_node'] = 1
    context.user_data['act'] = None 
    
    await update.message.reply_text(
        node[0], 
        reply_markup=get_reply_keyboard(1), 
        parse_mode=ParseMode.HTML
    )
    
    # إذا كان المستخدم مسؤولاً، نعرض له لوحة التحكم الإضافية
    if is_admin(uid):
        total_users = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
        txt = f"⚙️ <b>لوحة تحكم المسؤول</b>\n👤 عدد المشتركين الكلي: {total_users}"
        kb = [
            [InlineKeyboardButton("📁 إدارة الأقسام", callback_data="manage_1")],
            [InlineKeyboardButton("📢 إذاعة (Broadcast)", callback_data="p_bc")]
        ]
        await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة ضغطات أزرار Inline (لوحة الإدارة)"""
    query = update.callback_query
    uid = query.from_user.id
    
    if not is_admin(uid): 
        await query.answer("عذراً، هذه القائمة للمسؤولين فقط.", show_alert=True)
        return
    
    await query.answer()
    data = query.data

    if data.startswith("manage_"):
        nid = int(data.split("_")[1])
        n = db_query("SELECT * FROM structure WHERE id=%s", (nid,), fetchone=True)
        if not n: return
        
        ch = db_query("SELECT id, label FROM structure WHERE parent_id=%s ORDER BY id ASC", (nid,))
        txt = f"🛠 <b>إدارة: {n[2]}</b>\n\nالنص الحالي:\n{n[3]}"
        
        kb = [[InlineKeyboardButton(f"📂 {c[1]}", callback_data=f"manage_{c[0]}")] for c in ch]
        kb.append([
            InlineKeyboardButton("📝 تعديل النص", callback_data=f"edit_text_{nid}"),
            InlineKeyboardButton("✏️ تعديل الاسم", callback_data=f"edit_label_{nid}")
        ])
        kb.append([InlineKeyboardButton("➕ إضافة فرع جديد", callback_data=f"add_child_{nid}")])
        
        if nid != 1:
            kb.append([InlineKeyboardButton("🗑 حذف هذا القسم", callback_data=f"confirm_delete_{nid}")])
            kb.append([InlineKeyboardButton("🔙 عودة للقسم الأعلى", callback_data=f"manage_{n[1]}")])
        else:
            kb.append([InlineKeyboardButton("❌ إغلاق", callback_data="close_admin")])
            
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

    elif data == "p_bc":
        context.user_data['act'] = 'broadcast'
        await query.message.reply_text("📣 أرسل الرسالة التي تريد إذاعتها لجميع المستخدمين الآن:")

    elif data.startswith("add_child_"):
        context.user_data.update({'act': 'add_node', 'parent_id': data.split("_")[2]})
        await query.message.reply_text("✍️ أرسل الآن اسم الزر (القسم) الجديد:")

    elif data.startswith("edit_text_"):
        context.user_data.update({'act': 'edit_text', 'node_id': data.split("_")[2]})
        await query.message.reply_text("✍️ أرسل النص الجديد للقسم (يدعم HTML):")

    elif data.startswith("edit_label_"):
        context.user_data.update({'act': 'edit_label', 'node_id': data.split("_")[2]})
        await query.message.reply_text("✍️ أرسل الاسم الجديد للزر:")

    elif data.startswith("confirm_delete_"):
        nid = data.split("_")[2]
        kb = [
            [InlineKeyboardButton("✅ تأكيد الحذف النهائي", callback_data=f"do_delete_{nid}")],
            [InlineKeyboardButton("❌ تراجع", callback_data=f"manage_{nid}")]
        ]
        await query.edit_message_text("⚠️ هل أنت متأكد؟ سيتم حذف هذا القسم وجميع فروعه نهائياً!", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("do_delete_"):
        nid = int(data.split("_")[2])
        db_query("DELETE FROM structure WHERE id=%s OR parent_id=%s", (nid, nid), commit=True)
        await query.message.reply_text("✅ تم الحذف بنجاح.")
        await start(update, context)

    elif data == "close_admin":
        await query.message.delete()

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة جميع الرسائل النصية (التنقل + مدخلات الإدارة)"""
    uid = update.effective_user.id
    text = update.message.text
    curr_node = context.user_data.get('current_node', 1)
    action = context.user_data.get('act')

    # الأوامر الثابتة
    if text == "🏠 الرئيسية":
        context.user_data['act'] = None
        await start(update, context)
        return

    if text == "🔍 بحث":
        context.user_data['act'] = 'search'
        await update.message.reply_text("🔍 أرسل الكلمة التي تريد البحث عنها في أسماء الأقسام:")
        return

    if text == "🔙 عودة":
        n = db_query("SELECT parent_id FROM structure WHERE id=%s", (curr_node,), fetchone=True)
        parent_id = n[0] if (n and n[0] != 0) else 1
        context.user_data['current_node'] = parent_id
        node_data = db_query("SELECT content FROM structure WHERE id=%s", (parent_id,), fetchone=True)
        await update.message.reply_text(node_data[0], reply_markup=get_reply_keyboard(parent_id), parse_mode=ParseMode.HTML)
        return

    # معالجة التنقل بين الأقسام (للمستخدم العادي والمسؤول)
    target_node = db_query("SELECT id, content FROM structure WHERE parent_id=%s AND label=%s", (curr_node, text), fetchone=True)
    if target_node:
        context.user_data['current_node'] = target_node[0]
        await update.message.reply_text(
            target_node[1], 
            reply_markup=get_reply_keyboard(target_node[0]), 
            parse_mode=ParseMode.HTML
        )
        return

    # معالجة عمليات الإدارة والبحث (State Management)
    if action:
        if action == 'search':
            results = db_query("SELECT id, label FROM structure WHERE label ILIKE %s LIMIT 8", (f"%{text}%",))
            if not results:
                await update.message.reply_text("❌ لم يتم العثور على أقسام بهذا الاسم.")
            else:
                kb = [[InlineKeyboardButton(r[1], callback_data=f"go_{r[0]}")] for r in results]
                await update.message.reply_text("📂 الأقسام التي تم العثور عليها:", reply_markup=InlineKeyboardMarkup(kb))
            context.user_data['act'] = None
            
        elif action == 'broadcast' and is_admin(uid):
            all_users = db_query("SELECT user_id FROM users")
            await update.message.reply_text(f"⏳ جاري بدء الإذاعة لـ {len(all_users)} مستخدم...")
            count = 0
            for user in all_users:
                try:
                    await context.bot.send_message(user[0], text)
                    count += 1
                    await asyncio.sleep(0.05) # تجنب الحظر من تليجرام
                except: continue
            await update.message.reply_text(f"✅ تمت الإذاعة بنجاح لـ {count} مستخدم.")
            context.user_data['act'] = None

        elif is_admin(uid):
            if action == 'add_node':
                p_id = context.user_data['parent_id']
                db_query("INSERT INTO structure (parent_id, label, content) VALUES (%s, %s, %s)", 
                         (p_id, text, "محتوى جديد.. اضغط تعديل النص لتغييره."), commit=True)
                await update.message.reply_text(f"✅ تم إنشاء القسم '{text}' بنجاح.")
            elif action == 'edit_text':
                n_id = context.user_data['node_id']
                db_query("UPDATE structure SET content=%s WHERE id=%s", (text, n_id), commit=True)
                await update.message.reply_text("✅ تم تحديث نص القسم.")
            elif action == 'edit_label':
                n_id = context.user_data['node_id']
                db_query("UPDATE structure SET label=%s WHERE id=%s", (text, n_id), commit=True)
                await update.message.reply_text("✅ تم تحديث اسم الزر.")
            context.user_data['act'] = None

async def jump_to_node(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دالة للانتقال المباشر لعقدة معينة (تستخدم في نتائج البحث)"""
    query = update.callback_query
    node_id = int(query.data.split("_")[1])
    node_data = db_query("SELECT content FROM structure WHERE id=%s", (node_id,), fetchone=True)
    if node_data:
        context.user_data['current_node'] = node_id
        await query.message.reply_text(
            node_data[0], 
            reply_markup=get_reply_keyboard(node_id), 
            parse_mode=ParseMode.HTML
        )
    await query.answer()

# --- الإقلاع والتشغيل ---

if __name__ == '__main__':
    # 1. تشغيل سيرفر الـ Health Check في خيط منفصل (Thread)
    threading.Thread(target=run_health_server, daemon=True).start()
    
    # 2. تهيئة قاعدة البيانات
    init_db()
    
    # 3. بناء تطبيق التليجرام
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # 4. إضافة المعالجات (Handlers) - الترتيب مهم
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(jump_to_node, pattern="^go_"))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_msg))
    
    print("🚀 البوت يعمل الآن بنظام الحماية السحابية 24/7...")
    app.run_polling()
