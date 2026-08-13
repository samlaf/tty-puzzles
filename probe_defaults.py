"""Dump the default termios state of a freshly-opened pty.

The ladder's before-tests describe "a cooked terminal you haven't touched".
That description has to hold on every platform, so first we need to know what
each platform actually hands us. Run this on macOS and on Linux and diff the
output: whatever differs is what the harness has to normalise.

    python3 probe_defaults.py
"""

import os
import platform
import pty
import sys
import termios
import tty

LFLAGS = [
    "ICANON", "ECHO", "ECHOE", "ECHOK", "ECHOKE", "ECHOCTL", "ECHONL",
    "ECHOPRT", "ISIG", "IEXTEN", "NOFLSH", "TOSTOP", "FLUSHO", "PENDIN",
    "ALTWERASE", "EXTPROC",
]
IFLAGS = [
    "IGNBRK", "BRKINT", "IGNPAR", "PARMRK", "INPCK", "ISTRIP", "INLCR",
    "IGNCR", "ICRNL", "IXON", "IXOFF", "IXANY", "IMAXBEL", "IUTF8",
]
OFLAGS = [
    "OPOST", "ONLCR", "OCRNL", "ONOCR", "ONLRET", "OFILL", "OFDEL",
    "OXTABS", "ONOEOT", "TAB3",
]
# CS5..CS8 are values of the CSIZE mask, not independent bits -- listing them
# as flags reports "CS6 CS7 on" for what is simply CS8. Reported separately.
CFLAGS = [
    "CSTOPB", "CREAD", "PARENB", "PARODD", "HUPCL", "CLOCAL", "CRTSCTS",
]
CCHARS = [
    "VINTR", "VQUIT", "VERASE", "VKILL", "VEOF", "VEOL", "VEOL2", "VWERASE",
    "VREPRINT", "VSTART", "VSTOP", "VSUSP", "VDSUSP", "VLNEXT", "VDISCARD",
    "VSTATUS", "VMIN", "VTIME", "VSWTC", "VSWTCH",
]


def show_bits(mode, field, names, label):
    """Print each flag as on/off, or absent if this platform lacks it."""
    print(f"{label} = {mode[field]:#010x}")
    on, off, absent = [], [], []
    for name in names:
        if not hasattr(termios, name):
            absent.append(name)
            continue
        bit = getattr(termios, name)
        # Skip masks (TAB3 on Linux, CSIZE): they aren't single flags.
        if bit.bit_count() != 1:
            continue
        (on if mode[field] & bit else off).append(name)
    print(f"  on     : {' '.join(on) or '-'}")
    print(f"  off    : {' '.join(off) or '-'}")
    print(f"  absent : {' '.join(absent) or '-'}")
    print()


def describe_char(value):
    """Render a control character the way stty does: ^C, ^?, <undef>.

    _POSIX_VDISABLE -- the value meaning "no key is bound to this" -- is 0x00
    on Linux and 0xff on macOS, so both have to read as undefined.
    """
    if not isinstance(value, int):
        value = ord(value)
    if value in (0x00, 0xFF):
        return "<undef>"
    if value == 0x7F:
        return "^?"
    if value < 0x20:
        return f"^{chr(value + 64)}"
    return repr(chr(value))


def main():
    cooked = "--cooked" in sys.argv
    print(f"python   : {sys.version.split()[0]}")
    print(f"platform : {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"baseline : {'apply_cooked() applied' if cooked else 'platform default'}")
    print()

    master, slave = pty.openpty()
    try:
        if cooked:
            import harness

            harness.apply_cooked(slave)
        mode = termios.tcgetattr(slave)
    finally:
        os.close(master)
        os.close(slave)

    show_bits(mode, tty.IFLAG, IFLAGS, "IFLAG")
    show_bits(mode, tty.OFLAG, OFLAGS, "OFLAG")
    show_bits(mode, tty.CFLAG, CFLAGS, "CFLAG")
    show_bits(mode, tty.LFLAG, LFLAGS, "LFLAG")

    csize = mode[tty.CFLAG] & termios.CSIZE
    width = {termios.CS5: "CS5", termios.CS6: "CS6",
             termios.CS7: "CS7", termios.CS8: "CS8"}.get(csize, hex(csize))
    print(f"CSIZE    = {width}")
    print(f"ISPEED   = {mode[tty.ISPEED]}   OSPEED = {mode[tty.OSPEED]}")
    print()

    print("control characters")
    cc = mode[tty.CC]
    for name in CCHARS:
        if not hasattr(termios, name):
            print(f"  {name:10s} absent on this platform")
            continue
        index = getattr(termios, name)
        if index >= len(cc):
            print(f"  {name:10s} index {index} out of range")
            continue
        value = cc[index]
        # VMIN and VTIME are counts, not keys.
        if name in ("VMIN", "VTIME"):
            print(f"  {name:10s} idx={index:<3d} {value}")
        else:
            print(f"  {name:10s} idx={index:<3d} {describe_char(value)}")


if __name__ == "__main__":
    main()
