"""Reading a mail's HEADERS and plain text: names, addresses, the sender's authentication (V2-778 F1, 2026-10-01).

Moved out of `connectors/email/mailbox.py` (946 lines, over the 900 a new file may reach): pure functions over
header strings and message parts, with no IMAP or SMTP in them. `mailbox` imports every one back under its name.
"""
from __future__ import annotations

import re
from email.header import decode_header
from html.parser import HTMLParser


# Automatic senders — their mail is silently ignored (never a personal message to triage/reply to).
_NOREPLY_PATTERNS = (
    "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply",
    "mailer-daemon", "postmaster", "bounce", "notifications@",
    "automated@", "auto-confirm", "auto-reply", "automailer",
)


# RFC headers that reveal bulk/automatic email.
_AUTOMATED_HEADERS = {
    "Auto-Submitted": lambda v: v.lower() != "no",
    "Precedence": lambda v: v.lower() in {"bulk", "list", "junk"},
    "X-Auto-Response-Suppress": lambda v: bool(v),
    "List-Unsubscribe": lambda v: bool(v),
}


# ── Pure parsers (testable without network) ─────────────────────────────────────────────────────────────────────
def decode_header_value(raw: str) -> str:
    """Decode an RFC 2047 header (=?UTF-8?...) to plain text."""
    if not raw:
        return ""
    out = []
    for part, charset in decode_header(raw):
        if isinstance(part, bytes):
            out.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(part)
    return " ".join(out)


class _Text(HTMLParser):
    """Markup → the text a person reads: block ends become line breaks, <style>/<script>/<head> leave nothing
    behind (the regex version kept every CSS rule of a styled mail as text), entities are decoded by the parser."""

    _BREAK = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "table", "blockquote"}
    _SILENT = {"style", "script", "head", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._mute = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SILENT:
            self._mute += 1
        elif tag in self._BREAK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SILENT:
            self._mute = max(0, self._mute - 1)
        elif tag in self._BREAK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self._mute:
            self.out.append(data)


def strip_html(html: str) -> str:
    """Markup → plain text (the fallback when a mail has no text/plain part, or when its «plain» part is HTML)."""
    p = _Text()
    try:
        p.feed(html or "")
        p.close()
    except Exception:
        return html or ""
    lines = [" ".join(ln.split()) for ln in "".join(p.out).replace("\xa0", " ").splitlines()]
    out, blank = [], 0
    for ln in lines:
        blank = blank + 1 if not ln else 0
        if blank <= 1:
            out.append(ln)
    return "\n".join(out).strip()


def _looks_like_markup(txt: str) -> bool:
    """A text/plain part that is really HTML (some senders put their HTML there): it opens with a tag and most of it
    is markup. Measured on a confirmation mail that reached the card as `<div id="container" style=…`."""
    head = (txt or "").lstrip()
    return head.startswith("<") and len(strip_html(head)) < 0.6 * len(head)


def extract_text_body(msg) -> str:
    """Extract the text body from a possibly multipart email (prefer text/plain; fall back to text/html→text)."""
    if msg.is_multipart():
        for want_html in (False, True):
            for part in msg.walk():
                if "attachment" in str(part.get("Content-Disposition", "")):
                    continue
                ctype = part.get_content_type()
                if (ctype == "text/html") != want_html:
                    continue
                if ctype not in ("text/plain", "text/html"):
                    continue
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    txt = payload.decode(charset, errors="replace")
                    return strip_html(txt) if want_html or _looks_like_markup(txt) else txt
        return ""
    payload = msg.get_payload(decode=True)
    if not payload:
        return ""
    txt = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return strip_html(txt) if msg.get_content_type() == "text/html" or _looks_like_markup(txt) else txt


def extract_email_address(raw: str) -> str:
    """'Name <addr@x>' → 'addr@x' (lowercase)."""
    m = re.search(r"<([^>]+)>", raw or "")
    return (m.group(1) if m else (raw or "")).strip().lower()


def display_name(raw: str, fallback: str) -> str:
    """Visible sender name ('Name <addr>' → 'Name'), or fallback (the address)."""
    name = decode_header_value(raw or "")
    if "<" in name:
        name = name.split("<")[0].strip().strip('"')
    return name or fallback


def is_automated_sender(address: str, headers: dict) -> bool:
    """True if the email comes from an automatic/noreply sender or is marked as bulk by headers."""
    addr = (address or "").lower()
    if any(p in addr for p in _NOREPLY_PATTERNS):
        return True
    for header, check in _AUTOMATED_HEADERS.items():
        val = headers.get(header, "")
        if val and check(val):
            return True
    return False


# ── SPF/DKIM/DMARC verification (trust metadata) ────────────────────────────────────────────────────────────────
def _domain_of(address: str) -> str:
    _, _, domain = (address or "").rpartition("@")
    return domain.strip().lower()


def _domains_aligned(a: str, b: str) -> bool:
    a = (a or "").strip().lower().rstrip(".")
    b = (b or "").strip().lower().rstrip(".")
    if not a or not b:
        return False
    return a == b or a.endswith("." + b) or b.endswith("." + a)


_AUTH_METHOD_RE = re.compile(r"\b(dmarc|dkim|spf)\s*=\s*([a-z]+)", re.IGNORECASE)


_AUTH_PROP_RE = re.compile(
    r"\b(header\.from|header\.d|smtp\.mailfrom|smtp\.from|envelope-from)\s*=\s*([^\s;]+)", re.IGNORECASE)


def verify_sender_authentication(msg, from_addr: str) -> tuple[bool, str]:
    """Is the From: domain authenticated (SPF/DKIM/DMARC) according to the Authentication-Results header stamped by
    OUR receiving server? From: is forgeable; this is the only reliable indicator. Returns (ok, reason). Missing
    header → (False, 'no Authentication-Results') — blocks nothing, only marks metadata."""
    from_domain = _domain_of(from_addr)
    if not from_domain:
        return False, "missing From domain"
    headers = msg.get_all("Authentication-Results") or []
    if not headers:
        return False, "no Authentication-Results header"
    trusted = " ".join(str(headers[0]).split())        # receiver prepends it → FIRST one is trusted
    methods = {m.lower(): r.lower() for m, r in _AUTH_METHOD_RE.findall(trusted)}
    props = {p.lower(): v.strip().strip('"') for p, v in _AUTH_PROP_RE.findall(trusted)}
    if methods.get("dmarc") == "pass":
        return True, "dmarc=pass"
    if methods.get("spf") == "pass":
        spf = props.get("smtp.mailfrom") or props.get("smtp.from") or props.get("envelope-from") or ""
        if _domains_aligned(_domain_of(spf) if "@" in spf else spf, from_domain):
            return True, "spf=pass aligned"
    if methods.get("dkim") == "pass":
        dkim = props.get("header.d") or _domain_of(props.get("header.from", ""))
        if _domains_aligned(dkim, from_domain):
            return True, "dkim=pass aligned"
    return False, f"unauthenticated ({trusted[:80]})"
