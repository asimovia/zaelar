"""connectors/email/attachments.py — files carried by an outgoing mail, for a new message and for a reply alike.

Its own module because `mailbox.py` is over the architecture ratchet's ceiling. A path that cannot be read fails
the send rather than dropping the file in silence: a mail announcing an invoice that arrives without it is the
failure this exists to avoid.
"""
from __future__ import annotations

import mimetypes
import os
from email.mime.application import MIMEApplication


def display_name(path: str) -> str:
    """The name the recipient sees: the original one, without the prefix the widget's data dir stored it under
    (`eml_<uid>_<n>_` for a mail attachment, `up_<random>_` for a file the operator uploaded)."""
    name = os.path.basename(str(path))
    if name.startswith("eml_") and name.count("_") >= 3:
        return name.split("_", 3)[-1]
    if name.startswith("up_") and name.count("_") >= 2:
        return name.split("_", 2)[-1]
    return name


def attach(msg, paths) -> str | None:
    """Attach each file to the multipart `msg`. Returns an error sentence, or None when every file went in."""
    for path in paths or []:
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as e:
            return f"no puedo leer el adjunto {os.path.basename(str(path))}: {e}"
        name = display_name(path)
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        part = MIMEApplication(data, _subtype=ctype.split("/", 1)[1])
        part.add_header("Content-Disposition", "attachment", filename=name)
        msg.attach(part)
    return None
