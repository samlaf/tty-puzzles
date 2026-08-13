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

The first three puzzles all live in `LFLAG`, which isn't an accident. `IFLAG`
and `OFLAG` only substitute one byte for another; `LFLAG` holds the policy —
who owns a keystroke, the kernel or you. It's also the only order that's
observable: in canonical mode the line discipline hands you a finished line no
matter what `ICRNL` is doing, so puzzles 5 and 6 stay invisible until 2 lands.

**1. `disable_echo`** — turn off `ECHO`. Note what *doesn't* change: the
keystrokes still reach the program. Echo is a display decision, and switching
it off is the entirety of `getpass`.

**2. `disable_line_buffering`** — turn off `ICANON`, then set `VMIN`/`VTIME` to
say when a read is satisfied. Two things break at once: reads no longer wait
for Return, and backspace stops working, because the edit buffer you just threw
away was the thing erasing characters. `0x7f` is now yours to interpret.

**3. `disable_signal_chars`** — turn off `ISIG`. A byte matching `VINTR` is
acted on and *discarded*; with the flag off, `0x03` is ordinary input. Same
flag governs `VQUIT` (`0x1c`) and `VSUSP` (`0x1a`).

**3b. `disable_signal_flush`** — interception and *flushing the queues* are two
separate consequences of the same character. `NOFLSH` unpicks them: leave
`ISIG` on, and INTR discards nothing but itself. This is why Ctrl-C wipes a
half-typed shell command. Note the direction — you set a bit to switch a
behaviour off, because the flag is named for the absence.

**4. `disable_flow_control`** — turn off `IXON`. `0x13` halts all output until
`0x11` releases it, and neither byte is delivered. It's the answer to every
terminal that ever "froze". Note the geography: the flag lives in `IFLAG`,
because what's watched is *input* — even though what it controls is output.

**4b. `disable_extended_chars`** — turn off `IEXTEN`. Ctrl-V takes the next
byte literally and Ctrl-O discards output, and both survive `ICANON` and `ISIG`
going down. There is no `OPOST`-style master switch over input; `IEXTEN` masters
only this annex, which is why raw mode collects flags one at a time.

**5. `disable_cr_translation`** — turn off `ICRNL`. The test to sit with is the
canonical one: with line buffering still on, Return stops ending the line,
because the delimiter is `\n` and nothing is making one. Ctrl-J still works.

**6. `disable_output_processing`** — turn off `OPOST`. Its main tenant is
`ONLCR`, which rewrites every `\n` into `\r\n`. With it off, output staircases
off the right edge. `OPOST` is the master switch over all output rewriting.

**7. `make_raw` and `raw_mode`** — puzzles 1–6 assembled, then a context
manager, because a raw terminal is a held resource: save the attributes,
restore them in a `finally`, and the test crashes on purpose to check you meant
it. Skip it and your first uncaught exception leaves the shell with no echo.
(Blind-type `reset`, press Return.)

## Part 2 — building it back

Nothing here switches those services back on. From now on you *are* them —
userspace code on the program side of a terminal your own `make_raw` stripped
bare. These are the first puzzles whose before-tests need earlier work.

**8. `echo_back`** — given the bytes a read returned, produce the bytes to
write so typing shows up. Mostly the bytes themselves. The wrinkle is Return:
it arrives as `\r` and nothing appends the line feed for you, so reaching the
next line is `\r\n` and both bytes are yours.

**9. `LineEditor`** — canonical mode, rebuilt. `feed(byte)` returns bytes to
echo now and, on Return, the finished line. Backspace has to shrink the buffer
*and* clean the screen: `\b` alone only moves the cursor, so wiping a character
is the three-byte dance `\b` space `\b`. Ctrl-U is the same dance for the whole
line. When it passes, re-read `test_P02_before_backspace_never_reaches_the_program` —
same assertion, except now the someone implementing backspace is you.

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
