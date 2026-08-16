"""The pty rig every puzzle is checked against. You don't edit this file.

A `Pty` holds both ends of a real pseudo-terminal, so the kernel's line
discipline does the actual work -- nothing here simulates it. Holding both
ends at once is what makes it testable, and is what you never do in real life:

    master  the screen-and-keyboard end   ->  press(), screen()
    slave   the program end               ->  delivered(), emit()

Bytes you `press()` cross the line discipline before a program on the slave
can read them. Bytes a program `emit()`s cross it again on the way to the
screen. Every flag in this ladder changes one of those two journeys -- which
is exactly why both ends have to be observable for the change to be visible.

`screen()` and `delivered()` return b"" when nothing arrives within `TIMEOUT`.
That's the assertion most puzzles need: not "the wrong bytes came out" but
"nothing came out at all, because the kernel is still holding it."

A fresh pty does not start in the same state on every platform, so every `Pty`
is stamped with the explicit cooked baseline below before any puzzle sees it.
See COOKED_FLAGS for what that means and why.

Master and slave are POSIX's names for a pty's two ends -- newer documentation
sometimes says primary/subsidiary, but the C API is still ptsname, grantpt,
unlockpt. The slave is the end that carries the termios flags.

These ptys also have no controlling terminal. POSIX delivers INTR's SIGINT to
the tty's foreground process group, not to whoever typed it, and no session
ever attaches to a pty opened here -- so puzzles can press all the ^C they
want without your shell hearing any of it.
"""

import os
import pty
import select
import sys
import termios

# Index names for the seven-element list termios.tcgetattr returns. The stdlib
# puts these in `tty`, not `termios`, which is easy to trip over.
from tty import CC, CFLAG, IFLAG, ISPEED, LFLAG, OFLAG, OSPEED  # noqa: F401

import tracing

TIMEOUT = 0.25
"""Long enough that a slow machine won't produce a false 'nothing arrived'."""


# --- the cooked baseline ----------------------------------------------------
#
# "An ordinary cooked tty" has to mean the same thing on every machine or
# the puzzles aren't about the flags any more, they're about your kernel. It
# does not: a fresh pty on macOS and on Linux disagree on ten flags, and two of
# those disagreements are load-bearing here.
#
#   IXANY   on (macOS) / off (Linux).  With it set, *any* byte restarts output
#           after Ctrl-S -- so the flow-control puzzle's "Ctrl-Q is the key you
#           needed" is only true where it's clear. Pinned off.
#   ECHOK   off (macOS) / on (Linux).  This is the kernel's echo for the KILL
#           character, which is precisely what the LineEditor puzzle rebuilds.
#           Pinned off, leaving ECHOKE to erase the line visually -- the
#           behaviour a modern tty shows.
#
# The rest (BRKINT, IMAXBEL, HUPCL, ...) have nothing to say on a pty and are
# pinned only so that "untouched" is one state rather than two.
#
# Names, not numbers: the constants are not portable *values* either, and the
# c_cc indices are wildly different -- VINTR is 8 on macOS and 0 on Linux,
# VMIN is 16 there and 6 here. Anything absent on a platform is skipped, and
# "platform" includes the Python version: 3.14 on macOS names VSTATUS and
# VDSUSP where 3.12 does not.

COOKED_FLAGS = {
    IFLAG: {
        "BRKINT": True, "ICRNL": True, "IXON": True,
        "IGNBRK": False, "IGNPAR": False, "PARMRK": False, "INPCK": False,
        "ISTRIP": False, "INLCR": False, "IGNCR": False, "IXOFF": False,
        "IXANY": False, "IMAXBEL": False,
        # IUTF8 makes the kernel's ERASE delete a whole multi-byte character
        # rather than one byte -- which is the behaviour the LineEditor puzzle
        # reimplements. Pinned off so backspace means one byte everywhere.
        "IUTF8": False,
    },
    OFLAG: {
        "OPOST": True, "ONLCR": True,
        "OCRNL": False, "ONOCR": False, "ONLRET": False, "OFILL": False,
        "OFDEL": False, "OXTABS": False,
    },
    CFLAG: {
        "CREAD": True,
        "CSTOPB": False, "PARENB": False, "PARODD": False, "HUPCL": False,
        "CLOCAL": False, "CRTSCTS": False,
    },
    LFLAG: {
        "ICANON": True, "ECHO": True, "ECHOE": True, "ECHOKE": True,
        "ECHOCTL": True, "ISIG": True, "IEXTEN": True,
        "ECHOK": False, "ECHONL": False, "ECHOPRT": False, "NOFLSH": False,
        "TOSTOP": False, "FLUSHO": False, "PENDIN": False, "ALTWERASE": False,
        "EXTPROC": False,
    },
}

COOKED_CC = {
    "VINTR": 0x03,    # ^C
    "VQUIT": 0x1C,    # ^\
    "VERASE": 0x7F,   # ^?
    "VKILL": 0x15,    # ^U
    "VEOF": 0x04,     # ^D
    "VWERASE": 0x17,  # ^W
    "VREPRINT": 0x12, # ^R
    "VSTART": 0x11,   # ^Q
    "VSTOP": 0x13,    # ^S
    "VSUSP": 0x1A,    # ^Z
    "VLNEXT": 0x16,   # ^V
    "VDISCARD": 0x0F, # ^O
    "VMIN": 1,
    "VTIME": 0,
}

DISABLED_CC = [
    "VEOL", "VEOL2",     # extra line delimiters; canonical mode uses \n here
    "VDSUSP", "VSTATUS", # BSD extras: ^Y delayed-suspend, ^T status line
    "VSWTC", "VSWTCH",   # Linux shell-layer switch, undefined in practice
]
"""Special characters pinned to _POSIX_VDISABLE -- bound to no key at all.

These are the slots that exist on one platform and not the other, so leaving
them at their defaults makes "an untouched cooked tty" mean two different
things. Note the value used: _POSIX_VDISABLE is 0x00 on Linux and 0xff on
macOS, so it has to be asked for at runtime rather than written as a literal.
Setting one of these to 0 on macOS would *arm* it against the NUL byte instead
of disabling it -- the same trap the flow-control puzzle tests for.

Caveat worth knowing: this can only disable what the running Python names.
Python 3.12 on macOS doesn't expose VSTATUS, yet the kernel still has ^T bound
to c_cc[18] -- so on that interpreter, ^T remains live and unreachable. No
puzzle presses it, but don't add one that does.
"""


def vdisable(fd) -> int:
    """The value meaning "no key is bound to this", for this platform."""
    try:
        return os.fpathconf(fd, "PC_VDISABLE")
    except (OSError, ValueError):
        return 0xFF if sys.platform == "darwin" else 0x00


def apply_cooked(fd) -> None:
    """Stamp the explicit cooked baseline onto fd.

    This is what `stty sane` is: not a diff against what you have, but a named
    destination. Flags this platform doesn't define are skipped.
    """
    mode = termios.tcgetattr(fd)
    for field, wanted in COOKED_FLAGS.items():
        for name, on in wanted.items():
            bit = getattr(termios, name, None)
            if bit is None:
                continue
            if on:
                mode[field] |= bit
            else:
                mode[field] &= ~bit
    mode[CFLAG] = (mode[CFLAG] & ~termios.CSIZE) | termios.CS8
    bindings = dict(COOKED_CC)
    bindings.update(dict.fromkeys(DISABLED_CC, vdisable(fd)))
    for name, value in bindings.items():
        index = getattr(termios, name, None)
        if index is None or index >= len(mode[CC]):
            continue
        mode[CC][index] = value
    termios.tcsetattr(fd, termios.TCSANOW, mode)


def _read(fd, timeout, limit=4096):
    ready, _, _ = select.select([fd], [], [], timeout)
    return os.read(fd, limit) if ready else b""


class Pty:
    """Both ends of a pty, in cooked mode, then put into `configure`'s mode.

    `configure` is applied to the slave, which is the end carrying the termios
    flags. `Pty()` with no argument leaves an ordinary cooked tty there -- the
    state your shell hands every program it starts.

    `preset` writes special characters into the mode *after* the baseline and
    *before* `configure` sees it, standing in for a tty some earlier program
    left in a state of its own. A puzzle that only passes on a pristine pty
    hasn't really been tested: the whole point of tcgetattr/modify/tcsetattr is
    that you don't know what you're starting from.
    """

    def __init__(self, configure=None, preset=None):
        self.master, self.slave = pty.openpty()
        self.trace = tracing.Trace(getattr(configure, "__name__", "cooked"))
        tracing.ACTIVE.append(self.trace)
        try:
            apply_cooked(self.slave)
            if preset:
                mode = termios.tcgetattr(self.slave)
                for index, value in preset.items():
                    mode[CC][index] = value
                termios.tcsetattr(self.slave, termios.TCSANOW, mode)
            if configure is not None:
                mode = configure(termios.tcgetattr(self.slave))
                if mode is None:
                    raise AssertionError(
                        f"{configure.__name__} returned None; return the mode list"
                    )
                termios.tcsetattr(self.slave, termios.TCSANOW, mode)
        except BaseException:
            self.close()  # an unfinished puzzle shouldn't leak two fds per test
            raise

    # --- the screen-and-keyboard end -------------------------------------

    def press(self, data: bytes) -> None:
        """Type at the tty."""
        self.trace.record("press", data)
        os.write(self.master, data)

    def screen(self, timeout: float = TIMEOUT) -> bytes:
        """Bytes arriving at the screen -- echo and program output alike."""
        data = _read(self.master, timeout)
        self.trace.record("screen", data, f"nothing within {timeout}s")
        return data

    # --- the program end --------------------------------------------------

    def delivered(self, timeout: float = TIMEOUT) -> bytes:
        """Bytes a program reading this tty would get right now."""
        data = _read(self.slave, timeout)
        self.trace.record("delivered", data, f"nothing within {timeout}s")
        return data

    def emit(self, data: bytes) -> None:
        """Write output, as the program on the slave would."""
        self.trace.record("emit", data)
        os.write(self.slave, data)

    # --- misc -------------------------------------------------------------

    def mode(self):
        return termios.tcgetattr(self.slave)

    def close(self):
        for fd in (self.master, self.slave):
            try:
                os.close(fd)
            except OSError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def cc_value(mode, name: str) -> int:
    """Read a c_cc entry as an int, whatever shape the stdlib returned it in.

    CPython converts the VMIN and VTIME slots to integers only when ICANON is
    clear, and leaves them as one-byte bytes objects otherwise (historically
    those slots were the same storage as VEOF and VEOL). So the type of
    `mode[CC][termios.VMIN]` depends on a flag in the same struct, and any
    test comparing two modes has to normalise before it compares.
    """
    value = mode[CC][getattr(termios, name)]
    return value if isinstance(value, int) else ord(value)
