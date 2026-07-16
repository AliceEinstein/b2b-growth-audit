"""Sanitization: per-run record-id hashing and value redaction.

Everything the LLM reads passes through here first. Raw values that look
like emails / phones / tokens are replaced with a redaction marker; long
free text is truncated. CRM field values are also explicitly marked as
untrusted data so they cannot be mistaken for instructions to the model.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from pathlib import Path
from typing import Any, Optional

from .safety import EMAIL_PATTERN, PHONE_PATTERN, TOKEN_PATTERNS

SALT_FILENAME = "run_salt.txt"  # lives in raw/ — local and gitignored
MAX_VALUE_LEN = 80
UNTRUSTED_VALUE_MARKER = "[CRM_FIELD_VALUE:UNTRUSTED_DATA_ONLY]"
CONTACT_IDENTITY_FIELDS = frozenset(
    {"email", "hs_additional_emails", "firstname", "lastname", "phone", "mobilephone"}
)

# CRM values are data, even when a user-entered note happens to contain
# instruction-shaped text. These patterns are deliberately conservative: a
# match suppresses the value from LLM-facing artifacts rather than trying to
# interpret or execute it.
PROMPT_INJECTION_PATTERNS = (
    re.compile(
        r"\b(ignore|disregard|forget|override)\b.{0,80}"
        r"\b(previous|prior|system|developer|assistant|instructions?|rules?)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(system|developer|assistant|user)\s*(message|prompt|instruction)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(run|execute|write|delete|send|call)\b.{0,60}"
        r"\b(command|script|file|api|crm|email|message)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    # Common Chinese instruction-shaped CRM text. This is a defense-in-depth
    # filter, not a language detector or an authorization boundary.
    re.compile(
        r"(忽略|无视|不理会|忘记|跳过).{0,30}"
        r"(之前|上文|系统|开发者|指令|规则|提示)",
        re.DOTALL,
    ),
    re.compile(
        r"(执行|运行|写入|删除|导出|发送|修改|更新|读取).{0,40}"
        r"(命令|脚本|文件|API|CRM|数据|联系人|属性|邮箱)",
        re.IGNORECASE | re.DOTALL,
    ),
    # High-frequency European-language variants; unknown languages remain
    # explicitly marked as untrusted and are never treated as instructions.
    re.compile(
        r"\b(ignora|ignorar|ignorez|negeer|ignoriere)\b.{0,80}"
        r"\b(instrucciones?|instructions?|instructies|anweisungen)\b",
        re.IGNORECASE | re.DOTALL,
    ),
)


def load_or_create_salt(run_dir: Path) -> str:
    """Per-run salt (PRD: never use a global salt)."""
    path = Path(run_dir) / "raw" / SALT_FILENAME
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    salt = secrets.token_hex(16)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(salt, encoding="utf-8")
    return salt


def hash_record_id(object_type: str, record_id: Any, salt: str) -> str:
    digest = hashlib.sha256(
        f"{object_type}:{record_id}:{salt}".encode("utf-8")
    ).hexdigest()
    return digest[:16]


def _looks_like_timestamp(value: str) -> bool:
    return bool(re.match(r"^\s*\d{4}-\d{2}-\d{2}", value))


def redact_value(value: Any) -> Optional[str]:
    """Redaction for sanitized artifacts. Conservative: prefer over-redaction."""
    if value is None:
        return None
    text = str(value)
    if EMAIL_PATTERN.search(text):
        return "[REDACTED:email]"
    for pattern in TOKEN_PATTERNS:
        if pattern.search(text):
            return "[REDACTED:token]"
    match = PHONE_PATTERN.search(text)
    if match is not None:
        digits = re.sub(r"\D", "", match.group())
        if len(digits) >= 9 and not _looks_like_timestamp(match.group()):
            return "[REDACTED:phone]"
    if len(text) > MAX_VALUE_LEN:
        return text[:MAX_VALUE_LEN] + "…"
    return text


def sanitize_untrusted_value(value: Any) -> Optional[str]:
    """Prepare a CRM value for an LLM-facing processed artifact.

    This is not an authorization boundary and does not make CRM content
    trustworthy. It is defense in depth: values are labelled as data, and
    instruction-shaped free text is removed completely. Identity fields are
    handled separately by the profiler and never pass their raw values here.
    """
    if value is None:
        return None
    text = str(value)
    if any(pattern.search(text) for pattern in PROMPT_INJECTION_PATTERNS):
        return "[REDACTED:untrusted_crm_text]"
    redacted = redact_value(value)
    if redacted is None or redacted.startswith("[REDACTED:"):
        return redacted
    return f"{UNTRUSTED_VALUE_MARKER} {redacted}"


def sanitize_evidence_value(
    object_type: str, field: Optional[str], value: Any
) -> Optional[str]:
    """Sanitize evidence values, suppressing contact identity fields by key."""
    if (
        object_type == "contacts"
        and field is not None
        and field.casefold() in CONTACT_IDENTITY_FIELDS
        and value not in (None, "")
    ):
        return "[REDACTED:identity]"
    return sanitize_untrusted_value(value)
