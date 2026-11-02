# خطوات نشر Glasscii

## 1. اختبار النسخة

شغّل اختبارات المشروع، ثم أعد بناء EXE من هذه النسخة لأن إصلاح اختيار الويدجت موجود بالكود وقد لا يكون موجودًا في EXE القديم. جرّب EXE على ويندوز، ويفضّل على جهاز آخر بلا Python. افحص الصورة وGIF والساعة والإطار المخفي والقوائم والأيقونة والخروج من قائمة النظام.

لا يحتوي أرشيف الكود على EXE جاهز؛ الملف الذي رفعته لم يُعد بناؤه هنا.

## 2. إنشاء المستودع

من GitHub اختر New repository، سمّه Glasscii، واختر Public إن أردته عامًا. يمكن استخدام الوصف:

> Turn images and GIFs into interactive ASCII art and glass desktop widgets for Windows.

ملف README جاهز ضمن المشروع، فلا تحتاج توليده من GitHub. اختر الرخصة التي تريدها قبل النشر إذا أردت منح الآخرين حقوق استخدام وتعديل وتوزيع الكود؛ لم تُضف رخصة بالنيابة عنك.

## 3. رفع الملفات

فك ضغط الأرشيف. ارفع **محتويات مجلد glass_ascii** إلى جذر المستودع، لا ملف ZIP نفسه. من Add file → Upload files اسحب الملفات والمجلدات. تأكد من رفع `.gitignore` أيضًا؛ قد يخفيه مستعرض الملفات.

لا ترفع `.venv` أو `.idea` أو `build` أو `dist` أو EXE إلى ملفات الكود. انتبه أن رفع الملفات عبر المتصفح لا يعتمد على `.gitignore` لاستثنائها تلقائيًا.

لرفع الملفات عبر Git بدل المتصفح، افتح Terminal داخل مجلد المشروع بعد تثبيت Git:

```powershell
git init
git add .
git commit -m "Initial public release"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/Glasscii.git
git push -u origin main
```

بدّل YOUR_USERNAME باسم حسابك، واستخدم هذا المسار لمستودع جديد وفارغ. لا تستخدم force push.

## 4. نشر أول إصدار

افتح Releases → Draft a new release. أنشئ tag باسم `v1.0.0` على الفرع main، واجعل العنوان `Glasscii v1.0.0`، وانسخ محتوى RELEASE_NOTES.md إلى الوصف. أرفق `dist/Glasscii.exe` الناتج من البناء الجديد، ثم Publish release.

## 5. اللمسات النهائية

أضف لقطة حقيقية للواجهة أو GIF قصير للمستودع، بعد التأكد من عدم ظهور معلومات شخصية. لم تُضف لقطة اصطناعية أو روابط تنزيل إلى مستودع غير معروف.

Topics مقترحة: `python`, `pyside6`, `ascii-art`, `desktop-widget`, `windows`, `halftone`.

## ملخص التغييرات في هذه الحزمة

- إضافة README إنكليزي وتعليمات عربية محدّثة وملف تجاهل Git ونص الإصدار.
- استثناء بيئة بايثون والملفات المولّدة وEXE من أرشيف الكود.
- إصلاح ربط إجراءات قائمة Widgets بمعرّف الويدجت الصحيح، مع استيعاب وسيط checked الذي ترسله QAction.
- الحفاظ على ألوان الواجهة وسلوك الرسم والإعدادات الموجودة في النسخة التي رفعتها.

ملاحظة مراجعة: `interaction.py` في النسخة المرفوعة لا يحتوي تحسينات تخزين الصورة المصغّرة وتنعيم الحركة حسب الزمن من التصحيح السابق؛ تُرك كما رفعته، ولم تُستبدل إعداداته ضمن تجهيز النشر.

المراجع: https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository
https://pyinstaller.org/en/stable/usage.html
