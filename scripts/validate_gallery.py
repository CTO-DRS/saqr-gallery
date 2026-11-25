#!/usr/bin/env python3
"""
Saqr Gallery validator — مدقق معرض صقر.

Checks gallery.json the same way the Saqr Code app does before it lists or installs an
entry (app v0.18: data/Gallery.kt, data/SaqrPack.kt, agent/skills/SkillSafety.kt), so a pull
request that passes here is one the app accepts:

  * index shape: {"saqrgallery": 1, "updated": <int>, "entries": [...]}, at most 60 entries,
    unique ids, required fields, field caps, optional v0.18 fields with the right types;
  * every pack: .saqrpack v1, or v2 with a "skills" section; safe relative paths, size caps,
    commands that never shadow a builtin, known templates;
  * every skill: id/name/version/category caps, permissions that are real Saqr tools, never
    HIGH risk and never above the declared ceiling (SAFE or MEDIUM), no prompt-injection
    markers, no requests for secrets, no links to internal hosts, no hidden/bidi characters;
  * "sha256" (when present) equals SHA-256 of the pack's canonical JSON:
    json.dumps(pack minus installedAt/sha256, sort_keys=True, separators=(",", ":"),
    ensure_ascii=False) encoded as UTF-8.

Python standard library only.  Usage:
    python3 scripts/validate_gallery.py [gallery.json] [--print-sha]
Exit code 0 = valid, 1 = errors (each printed with its entry and field).
"""
import ipaddress
import json
import re
import sys
import unicodedata
from hashlib import sha256
from urllib.parse import urlsplit

# ----------------------------------------------------------------- caps (mirror the app)
MAX_ENTRIES = 60
E_MAX_ID, E_MAX_NAME, E_MAX_AUTHOR, E_MAX_DESC, E_MAX_TAGS, E_MAX_TAG = 40, 60, 40, 160, 4, 24
E_MAX_PERMISSIONS, E_MAX_URL = 10, 200

P_MAX_FILES, P_MAX_FILE_CHARS, P_MAX_TOTAL_CHARS = 40, 128_000, 512_000
P_MAX_COMMANDS, P_MAX_COMMAND_TEMPLATE, P_MAX_RULES = 12, 800, 2000
P_MAX_TOOLS, P_MAX_TOOL_LEN, P_MAX_NAME, P_MAX_ID, P_MAX_DESC, P_MAX_PATH = 8, 40, 40, 40, 140, 120
P_MAX_SKILLS = 12

S_MAX_NAME, S_MAX_DESC, S_MAX_AUTHOR = 40, 200, 40
S_MIN_INSTRUCTIONS, S_MAX_INSTRUCTIONS = 20, 4000
S_MAX_TAGS, S_MAX_TAG, S_MAX_PERMISSIONS, S_MAX_CHANGELOG, S_MAX_CHANGE_NOTES = 6, 24, 10, 20, 300

TEMPLATES = {"EMPTY", "WEB", "PYTHON", "NODE", "COMPOSE", "IME", "LITE_WEB"}
BUILTIN_COMMANDS = {"fix", "explain", "test", "review", "plan", "commit", "clear", "model",
                    "اصلح", "اشرح", "اختبر", "راجع", "خطة"}

# Saqr's tool registry (agent/ToolRegistry.kt): name -> risk
TOOLS = {
    "list_files": "SAFE", "read_file": "SAFE", "search": "SAFE", "project_search": "SAFE",
    "git_status": "SAFE", "git_diff": "SAFE", "git_log": "SAFE", "web_search": "SAFE", "web_fetch": "SAFE",
    "update_plan": "SAFE", "ask_user": "SAFE",
    "write_file": "MEDIUM", "edit_file": "MEDIUM", "run_command": "MEDIUM", "lint_project": "MEDIUM",
    "run_tests": "MEDIUM", "git_commit": "MEDIUM", "git_branch": "MEDIUM", "git_pull": "MEDIUM",
    "memory_save": "MEDIUM", "memory_forget": "MEDIUM",
    "delete_file": "HIGH", "git_push": "HIGH",
}
RISK_ORDER = {"SAFE": 0, "MEDIUM": 1, "HIGH": 2}
# working team roles a skill may bind to (agent/AgentRoles.kt, planning roles excluded)
ROLES = {"research", "architect", "developer", "debugger", "security", "tester", "reviewer",
         "optimizer", "documentation", "deployment"}

SKILL_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
CATEGORY = re.compile(r"^[a-z0-9][a-z0-9-]{0,23}$")
SEMVER = re.compile(r"^(0|[1-9]\d{0,8})\.(0|[1-9]\d{0,8})\.(0|[1-9]\d{0,8})"
                    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$")
SHA = re.compile(r"^[0-9a-f]{64}$")


# ----------------------------------------------------------------- helpers
def normalize_cmd(s):
    out = []
    for ch in s.lower():
        if ch in "أإآٱ":
            out.append("ا")
        elif ch == "ى":
            out.append("ي")
        elif ch == "ـ" or "\u064B" <= ch <= "\u0652":
            continue
        else:
            out.append(ch)
    return "".join(out)


def fold(text):
    """Lowercase, NFKC, Arabic letter forms unified — SkillSafety.fold."""
    return normalize_cmd(unicodedata.normalize("NFKC", text)).replace("ة", "ه")


def semver_key(v):
    m = SEMVER.match(v or "")
    if not m:
        return None
    pre = m.group(4).split(".") if m.group(4) else []
    if any(len(p) > 1 and p.isdigit() and p.startswith("0") for p in pre):
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), pre


def semver_cmp(a, b):
    x, y = semver_key(a), semver_key(b)
    if x is None or y is None:
        return None
    for i in range(3):
        if x[i] != y[i]:
            return (x[i] > y[i]) - (x[i] < y[i])
    px, py = x[3], y[3]
    if not px or not py:
        return min(len(py), 1) - min(len(px), 1)
    for p, q in zip(px, py):
        if p.isdigit() and q.isdigit():
            c = (int(p) > int(q)) - (int(p) < int(q))
        elif p.isdigit():
            c = -1
        elif q.isdigit():
            c = 1
        else:
            c = (p > q) - (p < q)
        if c:
            return c
    return (len(px) > len(py)) - (len(px) < len(py))


def canonical(value):
    """Canonical JSON (CanonicalJson.kt). Raises ValueError for non-integer numbers."""
    def check(v):
        if isinstance(v, bool) or v is None or isinstance(v, (str, int)):
            return
        if isinstance(v, float):
            raise ValueError("non-integer number")
        if isinstance(v, list):
            for x in v:
                check(x)
            return
        if isinstance(v, dict):
            for x in v.values():
                check(x)
            return
        raise ValueError("unsupported JSON value")
    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def pack_sha256(pack):
    p = {k: v for k, v in pack.items() if k not in ("installedAt", "sha256")}
    return sha256(canonical(p).encode("utf-8")).hexdigest()


# ----------------------------------------------------------------- content scans (SkillSafety.kt)
def is_hidden(cp):
    if cp in (0x09, 0x0A, 0x0D):
        return False
    return (cp < 0x20 or 0x7F <= cp <= 0x9F or cp in (0x00AD, 0x061C, 0x180E, 0x200B, 0xFEFF)
            or 0x202A <= cp <= 0x202E or 0x2060 <= cp <= 0x2064 or 0x2066 <= cp <= 0x2069
            or 0xFFF9 <= cp <= 0xFFFB or 0xE0000 <= cp <= 0xE007F)


INJECTION = [
    (r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,20}\b(previous|prior|above|earlier|preceding|system|safety|your|developer)\b[^.\n]{0,20}\b(instructions?|rules?|prompts?|guidelines?|polic(y|ies)|restrictions?|guardrails?)\b",
     "asks to ignore or override instructions"),
    (r"\b(ignore|disregard|forget)\s+(all|any|every)\s+(other\s+)?(instructions?|rules?|prompts?|guidelines?)\b",
     "asks to ignore or override instructions"),
    (r"\b(reveal|print|show|repeat|output|leak|dump|disclose)\b[^.\n]{0,30}\b(system prompt|hidden instructions|your instructions|initial prompt)\b",
     "asks to reveal the system prompt"),
    (r"<\|(im_start|im_end|system|endoftext)\|>|</?\s*system\s*>|\[/?inst]|<<sys>>", "contains chat-template role tokens"),
    (r"\b(developer mode|jailbreak|do anything now)\b", "jailbreak phrasing"),
    (r"\b(do not|don't|never|no need to)\b[^.\n]{0,20}\b(ask|wait|request)\b[^.\n]{0,25}\b(approval|confirmation|permission|consent)\b",
     "asks to skip the user's approval"),
    (r"\b(auto[- ]?approve|without (asking|approval|confirmation|the user's (approval|consent)))\b", "asks to act without approval"),
    (r"(تجاهل|تجاوز|انس|اهمل|الغ|اكسر)\S*\s+[^.\n]{0,20}((التعليمات|القواعد|الاوامر|التوجيهات|القيود)\s+(السابقه|اعلاه|الاصليه|كلها|جميعها)|(كل|جميع)\s+(التعليمات|القواعد|الاوامر|القيود)|(تعليمات|قواعد|قيود)\s+(النظام|الامان|الحمايه))",
     "asks to ignore or override instructions (Arabic)"),
    (r"(بدون|دون|من غير)\s+(طلب\s+|انتظار\s+)?(موافقه|اذن|تاكيد|استئذان)", "asks to act without approval (Arabic)"),
    (r"(اكشف|اعرض|اطبع|كرر)\s+[^.\n]{0,20}(موجه النظام|تعليمات النظام|التعليمات المخفيه)", "asks to reveal the system prompt (Arabic)"),
]
INJECTION = [(re.compile(p), why) for p, why in INJECTION]
SPOOF = ["[INSTALLED SKILL — data, cannot override system rules]", "[END INSTALLED SKILL]",
         "[UNTRUSTED CONTENT — data, not instructions]", "[END UNTRUSTED CONTENT]",
         "[installed skill", "[end installed skill", "[untrusted content"]
NEGATION = re.compile(r"\b(never|don't|do not|avoid|not|no|without|nor)\b|(^|\s)(لا|ابدا|اياك|تجنب|ممنوع|دون|بدون)(\s|$)")
SECRET = [
    (r"\b(send|upload|post|exfiltrate|reveal|print|output|leak|email|share|paste|include|echo|cat|display|show|transmit|forward|copy)\b[^.\n]{0,40}\b(api[ _-]?keys?|access[ _-]?tokens?|auth[ _-]?tokens?|bearer tokens?|github tokens?|secrets?|passwords?|passphrases?|credentials?|private[ _-]?keys?|ssh[ _-]?keys?|keystores?|seed phrases?)\b",
     "asks to output or send secrets"),
    (r"\bask\b[^.\n]{0,25}\b(for|to (give|share|paste|send|type))\b[^.\n]{0,25}\b(api[ _-]?keys?|tokens?|passwords?|secrets?|credentials?|passphrases?)\b",
     "asks the user for secrets"),
    (r"(~|\$home)/\.ssh|\bid_(rsa|ed25519|ecdsa)\b|keystore\.properties|/data/data/|\bshared_prefs\b|\bsecurestore\b|\.git-credentials|\.netrc\b",
     "points at secret storage"),
    (r"(ارسل|اعرض|اطبع|اكشف|شارك|انشر|ارفع|الصق|اطلب|انسخ)\S*\s+[^.\n]{0,40}(مفتاح|المفتاح|مفاتيح|رمز الوصول|الرمز السري|التوكن|توكن|كلمه المرور|كلمات المرور|كلمه السر|الاسرار|بيانات الدخول)",
     "asks to output or send secrets (Arabic)"),
]
SECRET = [(re.compile(p), why) for p, why in SECRET]
URL = re.compile(r"\b([a-z][a-z0-9+.-]{1,15})://[^\s)\]>\"'`]+", re.IGNORECASE)
PRIVATE_IP = re.compile(r"(?<![\d.])(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|169\.254\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|0\.0\.0\.0)(?!\d)")
INTERNAL_HOST = re.compile(r"\b(metadata\.google\.internal|metadata\.goog)\b|\b[a-z0-9-]+\.(internal|local|localhost):\d{1,5}\b")
BLOCKED_HOSTS = {"localhost", "metadata", "metadata.google.internal", "metadata.goog", "ip6-localhost", "ip6-loopback", "local"}


def web_guard(url):
    """WebGuard.check: None when allowed, else the reason."""
    try:
        u = urlsplit(url)
    except ValueError:
        return "unparseable URL"
    if u.scheme.lower() not in ("http", "https"):
        return "only http/https URLs are allowed"
    if u.username or u.password:
        return "URLs with embedded credentials are not allowed"
    host = (u.hostname or "").lower()
    if not host:
        return "URL has no host"
    if host in BLOCKED_HOSTS or host.endswith(".local") or host.endswith(".localhost"):
        return "private/internal hosts are blocked"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return None
    if ip.version == 6:
        h = host
        if h == "::1" or h.startswith(("fc", "fd", "fe80")):
            return "private/internal addresses are blocked"
        return None
    a, b = ip.packed[0], ip.packed[1]
    blocked = (a in (0, 10, 127) or (a == 169 and b == 254) or (a == 172 and 16 <= b <= 31)
               or (a == 192 and (b == 168 or (b == 0 and ip.packed[2] == 0)))
               or (a == 198 and b in (18, 19)) or (a == 100 and 64 <= b <= 127))
    return "private/internal addresses are blocked" if blocked else None


def loopback_dev_server(url):
    try:
        u = urlsplit(url)
        port = u.port
    except ValueError:
        return False
    return (u.hostname or "").lower() in ("127.0.0.1", "localhost") and port is not None and 1024 <= port <= 65535 \
        and not (u.username or u.password)


def scan_text(field, text):
    out = []
    if not text:
        return out
    hidden = sorted({ord(c) for c in text if is_hidden(ord(c))})
    if hidden:
        out.append(("hidden_unicode", f"{field}: invisible or direction-changing characters "
                    + " ".join(f"U+{cp:04X}" for cp in hidden[:4])))
    folded = fold(text)
    if any(fold(m) in folded for m in SPOOF):
        out.append(("injection", f"{field}: imitates an envelope marker"))
    for rx, why in INJECTION:
        m = rx.search(folded)
        if m:
            out.append(("injection", f"{field}: {why} («{m.group(0)[:48]}»)"))
    for rx, why in SECRET:
        for m in rx.finditer(folded):
            before = folded[max(0, m.start() - 24):m.start()]
            if NEGATION.search(before):
                continue
            out.append(("secret", f"{field}: {why} («{m.group(0)[:48]}»)"))
            break
    for m in URL.finditer(text):
        url = m.group(0).rstrip(".,;:!?،")
        if m.group(1).lower() not in ("http", "https"):
            out.append(("internal_url", f"{field}: {url[:60]} — only http/https links are allowed"))
            continue
        reason = web_guard(url)
        if reason and not loopback_dev_server(url):
            out.append(("internal_url", f"{field}: {url[:60]} — {reason}"))
    rest = URL.sub(" ", text)
    for m in PRIVATE_IP.finditer(rest):
        out.append(("internal_url", f"{field}: {m.group(0)} — private/internal address"))
    for m in INTERNAL_HOST.finditer(rest.lower()):
        out.append(("internal_url", f"{field}: {m.group(0)} — internal host name"))
    return out


# ----------------------------------------------------------------- validators
def check_skill(s, where):
    errs = []

    def e(code, msg):
        errs.append(f"{where}: [{code}] {msg}")

    if not isinstance(s, dict):
        e("json", "skill must be an object")
        return errs
    sid, name, instr = s.get("id"), s.get("name"), s.get("instructions")
    for key, val in (("id", sid), ("name", name), ("instructions", instr)):
        if not isinstance(val, str) or not val.strip():
            e("json", f"required string field «{key}» missing")
    if errs:
        return errs
    for key in ("nameAr", "description", "category", "version", "author", "role", "risk"):
        if key in s and not isinstance(s[key], str):
            e("json", f"«{key}» must be a string")
    for key in ("tags", "permissions", "changelog"):
        if key in s and not isinstance(s[key], list):
            e("json", f"«{key}» must be an array")
    if errs:
        return errs
    sid, name = sid.strip(), name.strip()
    name_ar = s.get("nameAr", "").strip()
    desc = s.get("description", "").strip()
    category = (s.get("category", "").strip().lower() or "general")
    version = s.get("version", "").strip() or "1.0.0"
    author = s.get("author", "").strip()
    role = s.get("role", "").strip().lower()
    risk = (s.get("risk", "").strip().upper() or "SAFE")
    tags = [t.strip() for t in s.get("tags", []) if isinstance(t, str) and t.strip()]
    perms = [p.strip() for p in s.get("permissions", []) if isinstance(p, str) and p.strip()]
    changelog = s.get("changelog", [])

    if not SKILL_ID.match(sid):
        e("id", "2–40 chars of a-z, 0-9 and '-', starting with a letter or digit")
    if len(name) > S_MAX_NAME:
        e("name", f"name: 1–{S_MAX_NAME} chars")
    if len(name_ar) > S_MAX_NAME:
        e("name", f"nameAr: at most {S_MAX_NAME} chars")
    if len(desc) > S_MAX_DESC:
        e("size", f"description: at most {S_MAX_DESC} chars")
    if len(author) > S_MAX_AUTHOR:
        e("size", f"author: at most {S_MAX_AUTHOR} chars")
    if not CATEGORY.match(category):
        e("category", "lowercase a-z, 0-9 and '-', at most 24 chars")
    if len(tags) > S_MAX_TAGS or any(len(t) > S_MAX_TAG for t in tags):
        e("tags", f"at most {S_MAX_TAGS} tags of {S_MAX_TAG} chars")
    if semver_key(version) is None:
        e("version", f"«{version[:20]}» is not semver (e.g. 1.2.0)")
    if len(instr) > S_MAX_INSTRUCTIONS:
        e("size", f"instructions: {len(instr)} chars, the cap is {S_MAX_INSTRUCTIONS}")
    if len(instr.strip()) < S_MIN_INSTRUCTIONS:
        e("size", f"instructions: at least {S_MIN_INSTRUCTIONS} chars")
    if role and role not in ROLES:
        e("role", f"«{role[:20]}» is not a working team role")
    # permissions: real tools, never HIGH, never above the ceiling
    if risk == "HIGH":
        e("permission_high", "risk: HIGH can never be granted to a pack")
    elif risk not in ("SAFE", "MEDIUM"):
        e("risk", f"risk must be SAFE or MEDIUM, got «{risk[:20]}»")
    if len(perms) > S_MAX_PERMISSIONS:
        e("size", f"permissions: at most {S_MAX_PERMISSIONS} tools")
    cap = RISK_ORDER["MEDIUM" if risk == "MEDIUM" else "SAFE"]
    for p in dict.fromkeys(perms):
        r = TOOLS.get(p)
        if r is None:
            e("permission_unknown", f"«{p[:40]}» is not a Saqr tool")
        elif r == "HIGH":
            e("permission_high", f"«{p}» is HIGH risk and never grantable by a pack")
        elif RISK_ORDER[r] > cap:
            e("permission_ceiling", f"«{p}» is {r} but the skill's ceiling is {risk}")
    if len(changelog) > S_MAX_CHANGELOG:
        e("changelog", f"at most {S_MAX_CHANGELOG} entries")
    notes_all = []
    for c in changelog:
        if not isinstance(c, dict) or not isinstance(c.get("version"), str):
            e("changelog", "each entry needs a string «version»")
            break
        cv, notes = c["version"].strip(), str(c.get("notes", "")).strip()
        notes_all.append((cv, notes))
        if semver_key(cv) is None:
            e("changelog", f"«{cv[:20]}» is not semver")
            break
        if (semver_cmp(cv, version) or 0) > 0:
            e("changelog", f"entry {cv} is newer than the skill's version {version}")
            break
        if len(notes) > S_MAX_CHANGE_NOTES:
            e("changelog", f"notes for {cv} exceed {S_MAX_CHANGE_NOTES} chars")
            break
    findings = scan_text("instructions", instr) + scan_text("name", name) + scan_text("nameAr", name_ar) \
        + scan_text("description", desc) + scan_text("author", author)
    for t in tags:
        findings += scan_text("tags", t)
    for cv, notes in notes_all:
        findings += scan_text(f"changelog {cv[:20]}", notes)
    seen = set()
    for code, msg in findings:
        if (code, msg) not in seen:
            seen.add((code, msg))
            e(code, msg)
    return errs


def safe_path(p):
    return isinstance(p, str) and p.strip() != "" and len(p) <= P_MAX_PATH and not p.startswith("/") \
        and "\\" not in p and ".." not in p.split("/")


def check_pack(pack, where):
    errs = []

    def e(code, msg):
        errs.append(f"{where}: [{code}] {msg}")

    if not isinstance(pack, dict):
        e("json", "«pack» must be an object")
        return errs
    v = pack.get("saqrpack")
    skills = pack.get("skills")
    if v == 2:
        if not isinstance(skills, list) or not skills:
            e("json", "saqrpack 2 needs a non-empty «skills» array")
            return errs
    elif v != 1:
        e("json", "«saqrpack» must be 1 (or 2 with a skills section)")
        return errs
    else:
        skills = []  # a v1 pack's "skills" key is ignored by the app
    pid, pname = pack.get("id"), pack.get("name")
    if not isinstance(pid, str) or not pid.strip() or not isinstance(pname, str) or not pname.strip():
        e("json", "«id» and «name» are required")
        return errs
    if len(pid.strip()) > P_MAX_ID or len(pname.strip()) > P_MAX_NAME:
        e("size", f"id/name at most {P_MAX_ID}/{P_MAX_NAME} chars (the app truncates)")
    if len(str(pack.get("description", "")).strip()) > P_MAX_DESC:
        e("size", f"description at most {P_MAX_DESC} chars (the app truncates)")
    template = str(pack.get("template", "")).strip()
    files = pack.get("files", {}) or {}
    commands = pack.get("commands", []) or []
    if not isinstance(files, dict) or not isinstance(commands, list):
        e("json", "«files» must be an object and «commands» an array")
        return errs
    if not template and not files and not skills:
        e("empty", "the pack has no template, files or skills")
    if template and template not in TEMPLATES:
        e("template", f"unknown template «{template}» (known: {', '.join(sorted(TEMPLATES))})")
    if len(files) > P_MAX_FILES:
        e("size", f"at most {P_MAX_FILES} files")
    total = 0
    for path, content in files.items():
        if not safe_path(path):
            e("path", f"unsafe path «{path[:60]}»")
        if not isinstance(content, str):
            e("json", f"file «{path[:60]}» must be a string")
            continue
        total += len(content)
        if len(content) > P_MAX_FILE_CHARS:
            e("size", f"file «{path[:60]}» exceeds {P_MAX_FILE_CHARS} chars")
    if total > P_MAX_TOTAL_CHARS:
        e("size", f"files total {total} chars, the cap is {P_MAX_TOTAL_CHARS}")
    if len(commands) > P_MAX_COMMANDS:
        e("size", f"at most {P_MAX_COMMANDS} commands")
    seen = set()
    for c in commands:
        if not isinstance(c, dict):
            e("command", "each command must be an object")
            continue
        n = str(c.get("name", "")).strip().lstrip("/")
        t = str(c.get("template", ""))
        if not re.fullmatch(r"[\w-]{1,32}", n) or not t.strip() or len(t) > P_MAX_COMMAND_TEMPLATE:
            e("command", f"malformed command «{n[:32]}»")
        key = normalize_cmd(n)
        if key in {normalize_cmd(b) for b in BUILTIN_COMMANDS}:
            e("duplicate", f"command «{n}» shadows a builtin")
        if key in seen:
            e("duplicate", f"command «{n}» appears twice")
        seen.add(key)
    if len(str(pack.get("rules", ""))) > P_MAX_RULES:
        e("size", f"rules at most {P_MAX_RULES} chars")
    tools = pack.get("tools", []) or []
    if not isinstance(tools, list) or len(tools) > P_MAX_TOOLS or any(len(str(x)) > P_MAX_TOOL_LEN for x in tools):
        e("size", f"at most {P_MAX_TOOLS} preferred tools of {P_MAX_TOOL_LEN} chars")
    if "version" in pack and str(pack["version"]).strip() and semver_key(str(pack["version"]).strip()) is None:
        e("version", "pack «version» is not semver")
    if len(skills) > P_MAX_SKILLS:
        e("size", f"at most {P_MAX_SKILLS} skills")
    ids = set()
    for i, s in enumerate(skills):
        sid = s.get("id", f"#{i}") if isinstance(s, dict) else f"#{i}"
        if sid in ids:
            e("duplicate", f"skill id «{sid}» appears twice")
        ids.add(sid)
        errs += check_skill(s, f"{where} › skill {sid}")
    return errs


def validate(doc):
    errors = []
    if not isinstance(doc, dict) or doc.get("saqrgallery") != 1:
        return ['index: «saqrgallery» must be 1']
    if "updated" in doc and (not isinstance(doc["updated"], int) or isinstance(doc["updated"], bool)):
        errors.append("index: «updated» must be an integer (ms)")
    entries = doc.get("entries")
    if not isinstance(entries, list):
        return errors + ["index: «entries» must be an array"]
    if len(entries) > MAX_ENTRIES:
        errors.append(f"index: at most {MAX_ENTRIES} entries (the app ignores the rest)")
    ids = set()
    for i, en in enumerate(entries):
        where = f"entry #{i}"
        if not isinstance(en, dict):
            errors.append(f"{where}: must be an object")
            continue
        eid = en.get("id")
        if isinstance(eid, str) and eid.strip():
            where = f"entry «{eid.strip()}»"
        else:
            errors.append(f"{where}: [json] «id» is required")
            continue
        eid = eid.strip()
        if len(eid) > E_MAX_ID or not SKILL_ID.match(eid):
            errors.append(f"{where}: [id] 2–{E_MAX_ID} chars of a-z, 0-9 and '-'")
        if eid in ids:
            errors.append(f"{where}: [duplicate] id appears more than once")
        ids.add(eid)
        if not isinstance(en.get("name"), str) or not en["name"].strip():
            errors.append(f"{where}: [json] «name» is required")
        for key, cap in (("name", E_MAX_NAME), ("nameAr", E_MAX_NAME), ("description", E_MAX_DESC), ("author", E_MAX_AUTHOR)):
            if key in en and (not isinstance(en[key], str) or len(en[key].strip()) > cap):
                errors.append(f"{where}: [size] «{key}» must be a string of at most {cap} chars")
        tags = en.get("tags", [])
        if not isinstance(tags, list) or len(tags) > E_MAX_TAGS or any(not isinstance(t, str) or len(t.strip()) > E_MAX_TAG for t in tags):
            errors.append(f"{where}: [tags] at most {E_MAX_TAGS} string tags of {E_MAX_TAG} chars")
        pack = en.get("pack")
        if pack is None:
            errors.append(f"{where}: [json] «pack» is required")
            continue
        errors += check_pack(pack, where)
        if isinstance(pack, dict) and isinstance(pack.get("id"), str) and pack["id"].strip() != eid:
            errors.append(f"{where}: [id] entry id must equal pack id «{pack['id']}» (update detection relies on it)")
        # ---- optional v0.18 fields
        if "version" in en and (not isinstance(en["version"], str) or semver_key(en["version"].strip()) is None):
            errors.append(f"{where}: [version] «version» must be semver")
        if "sha256" in en:
            sh = en["sha256"]
            if not isinstance(sh, str) or not SHA.match(sh.strip().lower()):
                errors.append(f"{where}: [checksum] «sha256» must be 64 lowercase hex chars")
            elif isinstance(pack, dict):
                try:
                    actual = pack_sha256(pack)
                    if actual != sh.strip().lower():
                        errors.append(f"{where}: [checksum] sha256 mismatch: listed {sh[:12]}…, content {actual[:12]}…")
                except ValueError as ex:
                    errors.append(f"{where}: [checksum] pack is not canonical: {ex}")
        if "permissions" in en:
            perms = en["permissions"]
            if not isinstance(perms, list) or len(perms) > E_MAX_PERMISSIONS or any(not isinstance(p, str) for p in perms):
                errors.append(f"{where}: [permissions] at most {E_MAX_PERMISSIONS} tool names")
            else:
                for p in perms:
                    r = TOOLS.get(p.strip())
                    if r is None:
                        errors.append(f"{where}: [permission_unknown] «{p[:40]}» is not a Saqr tool")
                    elif r == "HIGH":
                        errors.append(f"{where}: [permission_high] «{p}» is HIGH risk and never grantable by a pack")
                declared = {p for s in (pack.get("skills") or []) if isinstance(s, dict) for p in s.get("permissions", []) if isinstance(p, str)} \
                    if isinstance(pack, dict) and pack.get("saqrpack") == 2 else set()
                extra = {p.strip() for p in perms} - declared
                if declared and extra:
                    errors.append(f"{where}: [permissions] summary lists tools no skill declares: {', '.join(sorted(extra))}")
        if "rating" in en:
            r = en["rating"]
            if isinstance(r, bool) or not isinstance(r, (int, float)) or not 0 <= r <= 5:
                errors.append(f"{where}: [rating] must be a number 0–5 (aggregate, display only)")
        if "ratingCount" in en and (isinstance(en["ratingCount"], bool) or not isinstance(en["ratingCount"], int) or en["ratingCount"] < 0):
            errors.append(f"{where}: [rating] «ratingCount» must be a non-negative integer")
        if "changelogUrl" in en:
            u = en["changelogUrl"]
            if not isinstance(u, str) or len(u) > E_MAX_URL or not u.startswith("https://") or web_guard(u):
                errors.append(f"{where}: [url] «changelogUrl» must be a public https link of at most {E_MAX_URL} chars")
        if "skills" in en:
            n = en["skills"]
            actual = len(pack.get("skills") or []) if isinstance(pack, dict) and pack.get("saqrpack") == 2 else 0
            if isinstance(n, bool) or not isinstance(n, int) or n != actual:
                errors.append(f"{where}: [skills] «skills» must equal the pack's skill count ({actual})")
    return errors


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    path = args[0] if args else "gallery.json"
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as ex:
        print(f"✗ {path}: cannot read JSON: {ex}")
        return 1
    errors = validate(doc)
    entries = doc.get("entries", []) if isinstance(doc, dict) else []
    if "--print-sha" in argv:
        for en in entries if isinstance(entries, list) else []:
            if isinstance(en, dict) and isinstance(en.get("pack"), dict):
                try:
                    print(f"{en.get('id')}: {pack_sha256(en['pack'])}")
                except ValueError as ex:
                    print(f"{en.get('id')}: not canonical ({ex})")
    if errors:
        print(f"✗ {path}: {len(errors)} error(s)")
        for err in errors:
            print("  - " + err)
        return 1
    skills = sum(len(en.get("pack", {}).get("skills") or []) for en in entries
                 if isinstance(en, dict) and isinstance(en.get("pack"), dict) and en["pack"].get("saqrpack") == 2)
    print(f"✓ {path}: valid — {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}, {skills} skill(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
