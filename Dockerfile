FROM python:3.10

# إنشاء مجلد العمل
WORKDIR /code

# نسخ ملف المتطلبات وتثبيتها
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# نسخ كل ملفات البوت
COPY . .

# تشغيل البوت
CMD ["python", "chakh.py"]
