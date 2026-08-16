"""Render what happened to a byte on its way across the line discipline.

Every puzzle is a claim about one of two journeys:

    you typed     ->  [ line discipline ]  ->  the program read
    program wrote ->  [ line discipline ]  ->  the screen showed

A failing assertion tells you the second half was wrong. It doesn't show you
the first half, which is usually where the answer is. So `Pty` records every
leg of every journey, and the runner prints the record when a test fails.

Bytes are shown in caret notation, the same way `stty -a` prints them: ^C for
0x03, ^? for delete, ^M for the carriage return your Return key actually
sends. The line discipline's whole subject matter is bytes you can't see, so
printing them raw would defeat the point.
"""

CONTROL_NAMES = {
    0x00: "NUL", 0x03: "INTR", 0x04: "EOF", 0x08: "BS", 0x09: "TAB",
    0x0A: "LF", 0x0D: "CR", 0x0F: "DISCARD", 0x11: "START", 0x12: "REPRINT",
    0x13: "STOP", 0x15: "KILL", 0x16: "LNEXT", 0x17: "WERASE", 0x1A: "SUSP",
    0x1B: "ESC", 0x1C: "QUIT", 0x7F: "ERASE",
}


def caret(data: bytes) -> str:
    """Render bytes the way stty does: printable as-is, control as ^X."""
    out = []
    for byte in data:
        if byte == 0x7F:
            out.append("^?")
        elif byte < 0x20:
            out.append(f"^{chr(byte + 64)}")
        elif byte < 0x7F:
            out.append(chr(byte))
        else:
            out.append(f"\\x{byte:02x}")
    return "".join(out)


def hexes(data: bytes) -> str:
    return " ".join(f"{b:02x}" for b in data)


def names(data: bytes) -> str:
    """Name the control characters present, so ^U reads as KILL."""
    seen = []
    for byte in data:
        name = CONTROL_NAMES.get(byte)
        if name and name not in seen:
            seen.append(name)
    return " ".join(seen)


class Trace:
    """The ordered log of one Pty's traffic, both ends, both directions."""

    # (verb, arrow-label) -- the label says which leg of which journey this is.
    LABELS = {
        "press": "you typed",
        "delivered": "  -> the program read",
        "emit": "the program wrote",
        "screen": "  -> the screen showed",
    }

    def __init__(self, name=""):
        self.name = name
        self.events = []

    def record(self, verb: str, data: bytes, note: str = "") -> None:
        self.events.append((verb, data, note))

    def __bool__(self):
        return bool(self.events)

    def render(self, indent: str = "    ") -> str:
        if not self.events:
            return f"{indent}(no traffic recorded)"

        rows = []
        for verb, data, note in self.events:
            label = self.LABELS.get(verb, verb)
            if not data:
                shown = f"({note})" if note else "(nothing)"
                rows.append((label, shown, "", ""))
            else:
                rows.append((label, caret(data), hexes(data), names(data)))

        label_width = max(len(r[0]) for r in rows)
        shown_width = max(len(r[1]) for r in rows)

        lines = [f"{indent}-- trace {'-' * 52}"]
        for label, shown, hexed, named in rows:
            line = f"{indent}  {label:<{label_width}}  {shown:<{shown_width}}"
            if hexed:
                line += f"   {hexed}"
            if named:
                line += f"   [{named}]"
            lines.append(line.rstrip())
        lines.append(f"{indent}{'-' * 61}")
        return "\n".join(lines)


# The runner has no handle on the Pty a failing test built, so each Pty
# registers its trace here and the runner reads it back. Reset per test.
ACTIVE: list[Trace] = []


def reset() -> None:
    ACTIVE.clear()


def report(indent: str = "    ") -> str:
    return "\n\n".join(t.render(indent) for t in ACTIVE if t)
