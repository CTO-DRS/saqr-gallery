# سجل التغييرات · Changelog

## ar-code-review — مراجعة الكود بالعربية

### 1.0.0
- الإصدار الأول: قائمة مراجعة من سبعة محاور (الصحة، الأمان، الأداء على الهواتف الضعيفة، الوضوح، الاختبارات، العربية وRTL، التوافق) مع مراجع `file:line` وحكم نهائي «جاهز للدمج» أو «يحتاج تعديلات».
- First release: a seven-point review checklist (correctness, security, low-end phone performance, clarity, tests, Arabic/RTL, compatibility) with `file:line` references and a final verdict.
- Permissions: read-only tools (`list_files`, `read_file`, `search`, `project_search`, `git_status`, `git_diff`, `git_log`), ceiling `SAFE`, bound to the `reviewer` role.

## ar-bug-hunter — صائد الأخطاء
### 1.0.0
- الإصدار الأول: إعادة إنتاج العطل ← سبب جذري ← اختبار يفشل ← أصغر إصلاح ← تحقق. First release. Role `debugger`, ceiling `MEDIUM`.

## ar-commit-writer — كاتب رسائل الإيداع
### 1.0.0
- الإصدار الأول: رسالة إيداع ثنائية اللغة من الفروقات الفعلية، قراءة فقط. First release. Role `developer`, ceiling `SAFE`.

## ar-readme-writer — كاتب README عربي
### 1.0.0
- الإصدار الأول: README ثنائي اللغة من ملفات المشروع دون اختلاق ميزات. First release. Role `developer`, ceiling `MEDIUM` (writes README.md only).

## ar-security-audit — تدقيق أمني عربي
### 1.0.0
- الإصدار الأول: تدقيق قراءة فقط بستة محاور وتقرير مرتب بالخطورة، دون طباعة قيم الأسرار. First release. Role `security`, ceiling `SAFE`.
