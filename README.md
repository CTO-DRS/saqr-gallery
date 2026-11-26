# معرض صقر · Saqr Gallery

المعرض الرسمي لحزم المهارات (`.saqrpack`) لتطبيق **صقر كود** — قوالب وأوامر عربية يجلبها التطبيق مباشرة من هذا الملف (`gallery.json`)، والمساهمة هنا **طلب دمج (Pull Request)** واحد.

The official skill-pack gallery for **Saqr Code** — the app fetches `gallery.json` and lists every entry under Settings → معرض المجتمع; contributing is one pull request.

## كيف تساهم؟ · How to contribute

1. أضف مدخلًا جديدًا إلى مصفوفة `entries` في `gallery.json` (انسخ مدخلًا موجودًا وعدّله). معرّف المدخل `id` يساوي معرّف الحزمة.
2. الحزمة نفسها تُوضع كائنًا في المفتاح `pack` بنفس مخطط `.saqrpack`: `saqrpack: 1` لحزمة قالب/أوامر، و`saqrpack: 2` لحزمة فيها قسم `skills` (مهارات الوكيل — تطبيق صقر كود 0.18 فما فوق). الفهرس نفسه يبقى `saqrgallery: 1`.
3. شغّل المدقق محليًا — بلا اعتماديات، بايثون القياسية فقط:
   ```
   python3 scripts/validate_gallery.py gallery.json --print-sha
   ```
   وضع البصمة المطبوعة لمدخلك في الحقل `sha256` (اختياري لكنه مستحسن: التطبيق يرفض التثبيت إن لم تطابق المحتوى).
4. افتح PR بعنوان واضح. سير العمل `.github/workflows/validate.yml` يشغّل المدقق نفسه على كل طلب دمج (قد لا يعمل إن كانت دقائق GitHub Actions للحساب متوقفة — شغّله محليًا دائمًا).
5. عند تعديل مهارة: ارفع `version` (semver) وأضف مدخلًا في `changelog` — يرى المستخدم الفرق قبل التحديث.

1. Add a new entry to the `entries` array in `gallery.json` (copy an existing one). The entry `id` equals the pack `id`.
2. Put the pack itself as an object under `pack`, following the `.saqrpack` schema: `saqrpack: 1` for a template/commands pack, `saqrpack: 2` for a pack with a `skills` section (agent skills — Saqr Code 0.18+). The index stays `saqrgallery: 1`.
3. Validate locally (Python standard library only): `python3 scripts/validate_gallery.py gallery.json --print-sha`, and put your entry's printed hash in `sha256` (optional but recommended — the app refuses to install when it does not match).
4. Open a PR with a clear title. `.github/workflows/validate.yml` runs the same validator on every pull request (it may not run while the account's GitHub Actions minutes are unavailable — always run it locally).
5. When you change a skill, bump its `version` (semver) and add a `changelog` entry — users see the diff before they update.

### حقول اختيارية للمدخل · Optional entry fields (app 0.18+)
`version` (semver) · `sha256` (canonical pack hash) · `permissions` (tool names summary) · `rating` + `ratingCount` (an aggregate 0–5, display only — only if you really have one) · `changelogUrl` (public https) · `skills` (the pack's skill count). Older app versions ignore them.

## قواعد الحزمة · Pack rules

- المسار النسبي فقط (لا مطلق ولا `..`)، وحجم الملفات ≤ 40 ملفًا، والقواعد ≤ 2000 حرف، والأوامر ≤ 12، والمهارات ≤ 12.
- أسماء الأوامر عربية أو لاتينية (`^[\p{L}\p{N}_-]{1,32}$`) ولا تظلل الأوامر المدمجة.
- Relative paths only (no absolute, no `..`), ≤ 40 files, rules ≤ 2000 chars, ≤ 12 commands, ≤ 12 skills.
- Command names may be Arabic or Latin and must never shadow a builtin.
- Invalid packs are skipped by the app — the validator tells you why before you open the PR.

## قواعد المهارة · Skill rules

- `id` بأحرف لاتينية صغيرة وأرقام و`-`، والتعليمات بين 20 و4000 حرف، و`version` بصيغة semver.
- الصلاحيات أسماء أدوات صقر الحقيقية فقط، بسقف `SAFE` أو `MEDIUM`؛ الأدوات عالية الخطورة (`delete_file`، `git_push`) لا تُمنح لحزمة أبدًا.
- يُرفض: علامات حقن الأوامر («تجاهل التعليمات السابقة»، "ignore previous instructions"، رموز القوالب)، طلب الأسرار أو مفاتيح API، روابط لعناوين داخلية أو خاصة، والمحارف المخفية أو محارف اتجاه النص.
- `id`: lowercase latin, digits and `-`; instructions 20–4000 chars; `version` is semver.
- Permissions must be real Saqr tool names with a `SAFE` or `MEDIUM` ceiling; HIGH tools (`delete_file`, `git_push`) are never grantable by a pack.
- Refused: prompt-injection markers, requests for secrets/API keys, links to internal/private addresses, hidden or bidi-control characters. Full spec: `docs/SKILLS.md` in the Saqr Code app repository (v0.18).

## الترخيص · License

MIT — انظر [LICENSE](LICENSE) · See [LICENSE](LICENSE).
