# tty-puzzles

Take a terminal apart one flag at a time, then build it back in userspace.

Your terminal does a startling amount of work for you. It shows you what you
type. It lets you fix a typo before the program sees the line. It turns three
bytes into signals. It translates your Return key. None of that is the terminal
*emulator* and none of it is your program — it's the kernel's **line
discipline**, and every part of it is a flag you can switch off.

Nine puzzles. The first seven switch a service off and watch what breaks; the
last two make you the service. Fill in `puzzles.py` until the tests pass.

> The long-form writeup lives in the blog series. This file is the spec.

## Running it

```bash
python3 test_puzzles.py        # every puzzle
python3 test_puzzles.py 2      # just puzzle 2
python3 test_puzzles.py 1 2 3  # a range
pytest test_puzzles.py -k P03  # same thing under pytest
```

In a notebook, hand the runner your own cells instead of the stub file:

```python
!git clone -q https://github.com/samlaf/tty-puzzles.git
%cd tty-puzzles
import sys; sys.modules["puzzles"] = sys.modules["__main__"]

from test_puzzles import check
check(1)
```

Edit `puzzles.py` only. `harness.py`, `tracing.py` and `test_puzzles.py` are
the rig.

`ANSWERS.md` has a worked solution and a discussion for every puzzle. Read an
entry after you've made its tests pass, or after you've been stuck long enough
that the answer will actually stick.

## How the tests can possibly work

Terminal behaviour looks untestable — the answer is "what a human sees". It
isn't, because of `openpty()`. A pty is a pair of fds with a real line
discipline between them: the master is the screen-and-keyboard end, the slave
is the program end. Normally one process holds each. Here the test holds both,
so "what the screen shows" and "what the program reads" are two byte strings
you can assert on.

```
   press()  ─────►┐                    ┌────►  delivered()
                  │  line discipline   │
   screen() ◄─────┘   (the flags)      └─────  emit()
        master                          slave
```

`screen()` and `delivered()` return `b""` when nothing arrives within a quarter
second. That's the assertion most puzzles need — not "the wrong bytes came out"
but "nothing came out, because the kernel is still holding it".

When a test fails, the runner prints every leg of the journey in caret
notation, so you can see where the bytes changed:

```
    -- trace ----------------------------------------------------
      you typed               ab^?              61 62 7f   [ERASE]
        -> the program read   (nothing within 0.25s)
      the program wrote       one^Jtwo^J        6f 6e 65 0a 74 77 6f 0a   [LF]
        -> the screen showed  one^M^Jtwo^M^J    6f 6e 65 0d 0a ...   [CR LF]
```

## The map

Everything lives in the seven-element list `termios.tcgetattr(fd)` returns.
Index it with the names in `tty` (`tty.LFLAG`, not `termios.LFLAG` — the
constants aren't where you'd guess).

| Field | What it governs | Flags in this ladder |
|---|---|---|
| `IFLAG` | bytes on the way in | `ICRNL`, `IXON` |
| `OFLAG` | bytes on the way out | `OPOST` |
| `CFLAG` | baud, character size, parity | — |
| `LFLAG` | echo, line editing, signals | `ECHO`, `ICANON`, `ISIG`, `NOFLSH`, `IEXTEN` |
| `CC` | which byte means what | `VMIN`, `VTIME`, `VERASE`, `VKILL`, `VINTR` |

Clear a flag with `mode[LFLAG] &= ~termios.ECHO`; set one with `|=`.

Index `CC` with the constants, never a literal: the slots sit in different
places on different systems. `VINTR` is index 8 on macOS and 0 on Linux;
`VMIN` is 16 there and 6 here.

## Part 1 — the descent

Each puzzle switches off one service and asks what it was worth. The specs are
below; the reasoning — why this order, what each service was doing for you — is
in [Take a terminal apart, then build it back][post], and the worked solutions
are in `ANSWERS.md`.

**1. `disable_echo`** — turn off `ECHO`. The keystrokes must still reach the
program: this is display only.

**2. `disable_line_buffering`** — turn off `ICANON`, then set `VMIN` and
`VTIME` in `mode[CC]` to say when a read is satisfied: return as soon as at
least one byte is available, never time out.
**Warning:** a cooked terminal already has `VMIN=1, VTIME=0`, so clearing
`ICANON` alone looks like a complete answer. One test hands you a terminal
someone else configured.

**3. `disable_signal_chars`** — turn off `ISIG`, so `0x03` becomes ordinary
input. The same flag governs `VQUIT` (`0x1c`) and `VSUSP` (`0x1a`).

**3b. `disable_signal_flush`** — leave `ISIG` on and stop INTR/QUIT/SUSP
discarding the queues.
**Warning:** you'll be *setting* a bit to switch a behaviour off, because the
flag is named for the absence.

**4. `disable_flow_control`** — stop `0x13` halting output and `0x11` releasing
it. One flag, and it isn't in the field the effect suggests.
**Warning:** rebinding `VSTOP`/`VSTART` is the tempting wrong answer — `0x00`
doesn't mean "no character", and two tests check for it.

**4b. `disable_extended_chars`** — turn off `IEXTEN`. Ctrl-V (`0x16`) and
Ctrl-O (`0x0f`) survive `ICANON` and `ISIG` both being off; one `LFLAG` bit
gates them.

**5. `disable_cr_translation`** — turn off `ICRNL`, so Return delivers `\r`.
**Warning:** with line buffering still on, Return then stops ending the line at
all — the delimiter is `\n` and nothing is making one. Ctrl-J still does.

**6. `disable_output_processing`** — turn off `OPOST`, so output crosses byte
for byte.
**Warning:** `ONLCR` is only the tenant. One test arms `OCRNL` as well, to
check you cleared the master switch rather than the one rule.

**7. `make_raw` and `raw_mode`** — puzzles 1–6 assembled, built from your own
earlier answers. Then `raw_mode(fd)`, a context manager that saves the
attributes before touching anything and restores them in a `finally`; the test
crashes on purpose inside the block.
**Warning:** leave `NOFLSH` out. With `ISIG` off, no byte is recognized as a
signal character, so there is no flush left to suppress — and the stdlib-diff
test compares that bit.

## Part 2 — building it back

Nothing here switches those services back on: you write them instead, as
userspace code on the program side of a terminal your own `make_raw` stripped
bare. These are the first puzzles whose before-tests need earlier work.

**8. `echo_back`** — given the bytes a read returned, produce the bytes to
write so the person typing sees them.
**Warning:** Return arrives as `\r` and nothing appends the line feed for you.
Both bytes are yours.

**9. `LineEditor`** — `feed(byte)` returns a pair: bytes to echo now, and the
finished line once the byte completes one (`None` otherwise), with `\n`
appended exactly as cooked mode delivered it in puzzle 2.

| byte | | behaviour |
|---|---|---|
| printable | | buffer it, echo it |
| `0x7f` | `VERASE` | drop the last buffered byte, wipe it from the screen; do nothing on an empty buffer |
| `0x15` | `VKILL` | erase the whole buffered line the same way |
| `0x0d` | Return | echo `\r\n`, deliver the line, start the next one |

**Warning:** `\b` alone only moves the cursor. Wiping a character is the
three-byte dance `\b` space `\b`.

[post]: https://samlaf.github.io/programming/take-a-terminal-apart-then-build-it-back.html

## Roadmap

10. Your own interrupt: `0x03` arrives, you decide what it means.
11. Decode escape sequences — `\x1b[A` and friends.
12. The lone-`ESC` ambiguity, resolved with `VTIME` or `select`.
13. `TIOCGWINSZ` and `SIGWINCH`: how big is the window, and when did it change.
14. Alternate screen, cursor hiding, teardown that survives an exception.
15. Put it together: a prompt built on nothing but what you wrote.

## Platform notes

Runs on macOS and Linux, Python 3.12+, with no dependencies — everything used
here is in the standard library. A fresh pty does **not** start in the
same state on both — they disagree on ten flags — so `harness.apply_cooked()`
stamps an explicit cooked baseline on every terminal before a puzzle sees it.
That's what `stty sane` is: a named destination, not a diff. Two of those
disagreements are load-bearing (`IXANY` and `ECHOK`); see `COOKED_FLAGS` in
`harness.py` for the reasoning.

To see your own platform's raw defaults, and what the baseline does to them:

```bash
python3 probe_defaults.py            # what your kernel hands you
python3 probe_defaults.py --cooked   # what every puzzle actually starts from
```

Which control characters exist turns out to be a *Python version* question, not
just an OS one — 3.14 on macOS exposes `VSTATUS` and `VDSUSP` where 3.12 does
not. The baseline skips whatever the running interpreter can't name.
