# معرض صقر · Saqr Gallery

المعرض الرسمي لحزم المهارات (`.saqrpack`) لتطبيق **صقر كود** — قوالب وأوامر عربية يجلبها التطبيق مباشرة من هذا الملف (`gallery.json`)، والمساهمة هنا **طلب دمج (Pull Request)** واحد.

The official skill-pack gallery for **Saqr Code** — the app fetches `gallery.json` and lists every entry under Settings → معرض المجتمع; contributing is one pull request.

## كيف تساهم؟ · How to contribute

1. أضف مدخلًا جديدًا إلى مصفوفة `entries` في `gallery.json` (انسخ مدخلًا موجودًا وعدّله).
2. الحزمة نفسها تُوضع كائنًا في المفتاح `pack` بنفس مخطط `.saqrpack` (`saqrgallery` للفهرس = 1، و`saqrpack` للحزمة = 1).
3. افتح PR بعنوان واضح — سيُراجع ويُدمج، وسيظهر قالبك في كل نسخة التطبيق فور التحديث التالي.

1. Add a new entry to the `entries` array in `gallery.json` (copy an existing one and edit it).
2. Put the pack itself as an object under `pack`, following the `.saqrpack` schema (`saqrgallery: 1` for the index, `saqrpack: 1` for the pack).
3. Open a PR with a clear title — once merged, your template ships to every Saqr Code install on the next gallery refresh.

## قواعد الحزمة · Pack rules

- المسار النسبي فقط (لا مطلق ولا `..`)، وحجم الملفات ≤ 40 ملفًا، والقواعد ≤ 2000 حرف، والأوامر ≤ 12.
- أسماء الأوامر عربية أو لاتينية (`^[\p{L}\p{N}_-]{1,32}$`) ولا تظلل الأوامر المدمجة.
- الحزم غير الصالحة يتخطاها التطبيق بصمت — فاحص محليًا قبل الـPR.
- Relative paths only (no absolute, no `..`), ≤ 40 files, rules ≤ 2000 chars, ≤ 12 commands.
- Command names may be Arabic or Latin and must never shadow a builtin.
- Invalid packs are skipped silently by the app — validate locally before opening the PR.

## الترخيص · License

MIT — كما هو المشروع الأم [saqr-code](https://github.com/CTO-DRS/saqr-code-public).
