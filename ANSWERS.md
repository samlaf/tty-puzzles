# Answers

Read a puzzle's entry only after you've made its tests pass, or after you've
been stuck long enough that the answer will actually stick.

## 1 — `disable_echo`

```python
def disable_echo(mode):
    mode[LFLAG] &= ~termios.ECHO
    return mode
```

**The thing to notice:** the delivery test still passes. Turning off `ECHO`
changes what the *screen* shows and nothing about what the program reads. Those
are two separate journeys through the line discipline, and most of these
puzzles are about keeping them apart in your head.

That one line is the whole mechanism behind `getpass` and behind every `sudo`
prompt you've ever typed into. There's no secret channel — the password takes
exactly the path a normal line takes, and the terminal just declines to print
it.

## 2 — `disable_line_buffering`

```python
def disable_line_buffering(mode):
    mode[LFLAG] &= ~termios.ICANON
    mode[CC][termios.VMIN] = 1
    mode[CC][termios.VTIME] = 0
    return mode
```

**The thing to notice:** `ICANON` alone isn't enough, and it's the half people
forget. Outside canonical mode, `VMIN` and `VTIME` define when a read is
satisfied, and they're a small matrix worth memorising:

| `VMIN` | `VTIME` | `read()` returns |
|---|---|---|
| `>0` | `0` | once at least `VMIN` bytes arrive; blocks indefinitely |
| `0` | `>0` | on the first byte, or after `VTIME` deciseconds — whichever first |
| `>0` | `>0` | on `VMIN` bytes, or `VTIME` after the *first* byte arrives |
| `0` | `0` | immediately, with whatever's there, possibly nothing |

`VMIN=1, VTIME=0` is what you want for a key reader: return the instant
anything is available, wait forever when nothing is. That row is what `setraw`
picks, and the `0/>0` row is one way to solve the lone-`ESC` problem at
puzzle 12.

**The second thing to notice:** the backspace test. Nothing in your function
mentions erasing, and yet `\x7f` started coming through as a byte. The line
discipline had been maintaining an edit buffer for you — accumulating the line,
applying `VERASE` and `VKILL`, releasing it on a delimiter — and canonical mode
*is* that buffer. Turn it off and you inherit the job. Puzzle 9 is where you do
it by hand.

## 3 — `disable_signal_chars`

```python
def disable_signal_chars(mode):
    mode[LFLAG] &= ~termios.ISIG
    return mode
```

**The thing to notice:** the before-test asserts that the byte *vanishes* — and
so does the `a` typed before it. With `ISIG` set, a byte matching `VINTR` is
acted on and discarded, so it never lands in anyone's read buffer. The signal
goes to the foreground process group of the terminal's session, which for a
bare `openpty()` with no session attached is nobody. The discard happens
regardless. Signal generation and byte consumption are separate consequences of
the same flag, and that's why the test is well-defined even with nothing on the
other end.

**The consequence:** in raw mode Ctrl-C cannot kill your program, because
nothing is watching for it any more. If you also crash without restoring the
terminal, you get a shell with echo off and no line editing, and no keystroke
will help you. Blind-type `reset` and press Return.

This is the argument for putting restoration in a `finally` — or better, a
context manager — before you write a single line of anything else. Puzzle 7.

## 3b — `disable_signal_flush`

```python
def disable_signal_flush(mode):
    mode[LFLAG] |= termios.NOFLSH
    return mode
```

**The thing to notice:** it's `|=`, not `&=~`. `NOFLSH` is a negative-sense
flag — it's named for what stops happening — so switching a behaviour off means
setting a bit. `termios` has a few of these (`NOFLSH`, `IGNBRK`, `IGNCR`,
`ONOCR`), and the double negative is worth reading slowly every time.

**The thing it separates:** `ISIG` was doing two jobs at once, and only one of
them is signalling. POSIX puts the second in a sentence you have to go looking
for — "if `NOFLSH` is not set, the input and output queues are flushed when
`INTR`, `QUIT`, or `SUSP` is generated" — and it's the job you feel every day.
When Ctrl-C erases a half-typed command, no program did that. The line
discipline threw its own queue away, before anyone read a byte.

**Where it goes next:** `cfmakeraw` clears `NOFLSH` along with the rest of
`LFLAG`, which looks like it re-enables flushing until you notice it clears
`ISIG` too. With no character being intercepted, there's nothing left to flush
on. Puzzle 7 is where you'll see that whole clause and have to decide which bits
are load-bearing.

## 4 — `disable_flow_control`

```python
def disable_flow_control(mode):
    mode[IFLAG] &= ~termios.IXON
    return mode
```

**The thing to notice:** this is the first step outside `LFLAG`, and the flag
sits on the *input* side even though the visible effect is on output. That's
the right way round once you see the mechanism: `IXON` doesn't change what
output does, it changes what two input bytes *mean* — watch for `VSTOP` and
`VSTART` in the keystroke stream, act, discard. The same consume-and-vanish
pattern as `ISIG`'s three characters at puzzle 3, pointed at a different
subsystem.

**The archaeology:** a VT100 at 9600 baud genuinely couldn't keep up, and
XOFF/XON was the terminal's way of saying "hold on" — sent automatically by
the hardware, not typed. Nothing has needed it for decades, but it defaults on,
so its main modern effect is stealing two keystrokes: an accidental Ctrl-S
still hangs a terminal today, and readline's forward history search
(`Ctrl-S`, the mirror of `Ctrl-R`) never reaches bash until `stty -ixon`.

**The sibling:** `IXOFF` is the same protocol facing the other way — your
computer telling the *keyboard* side to pause. It defaults off, which is why
you've never met it.

**The cousin that isn't in the tests by accident:** `IXANY`. With it set, *any*
byte restarts stopped output, not just `VSTART` — so "Ctrl-Q is the key you
need" quietly stops being true. It's on by default on macOS and off on Linux,
which is why `harness.apply_cooked` pins it off: otherwise this puzzle would
mean two different things depending on whose machine ran it.

## 4b — `disable_extended_chars`

```python
def disable_extended_chars(mode):
    mode[LFLAG] &= ~termios.IEXTEN
    return mode
```

**The thing to notice:** these characters survive things you'd expect to kill
them. `IEXTEN` gates the implementation-defined extras POSIX declined to
standardize — `VLNEXT` (Ctrl-V, quote the next byte), `VDISCARD` (Ctrl-O, throw
output away), `VWERASE` (Ctrl-W, erase a word), `VREPRINT` (Ctrl-R, redraw the
pending line) — and they don't all answer to the same thing. Ctrl-W and Ctrl-R
need the canonical edit buffer, so puzzle 2 already took them. Ctrl-V and
Ctrl-O need nothing but `IEXTEN`, so they walk straight through `ICANON` and
`ISIG` both going down. Clear `ISIG` and quote a `^C` with `^V` and you'll find
the `^V` still being eaten by a kernel you thought you'd disarmed.

**Why that matters more than it looks:** `VDISCARD` is a real footgun. Ctrl-O
tells the line discipline to throw away everything the program writes, silently,
with no error and no indication anywhere. A TUI that "freezes" the instant
someone fat-fingers Ctrl-O, and recovers just as mysteriously on the next
Ctrl-O, is this flag. Raw mode has to clear `IEXTEN` for that reason alone.

**The shape it reveals:** there is no `OPOST`-style master switch over input.
`OPOST` gates every output rewrite at once (puzzle 6), but on the way in,
translation (`ICRNL`), editing (`ICANON`), signalling (`ISIG`) and this annex
(`IEXTEN`) each hold their own bit. That asymmetry is exactly why raw mode is a
list of flags rather than a single one, and why `cfmakeraw` is six lines
instead of two.

**A portability note you can see in the harness:** BSD puts more in this annex
than Linux does — `VSTATUS` (Ctrl-T, print a status line) and `VDSUSP` (Ctrl-Y,
delayed suspend) are macOS extras. Whether Python even *names* them depends on
your interpreter version, not just your OS, so `apply_cooked` disables whatever
it can name and the puzzles avoid pressing them.

## 5 — `disable_cr_translation`

```python
def disable_cr_translation(mode):
    mode[IFLAG] &= ~termios.ICRNL
    return mode
```

**The thing to notice:** the canonical-mode test. Everyone expects "Return now
delivers `\r`"; almost nobody expects "Return stops ending the line." But
canonical mode's delimiters are `\n`, `EOF` and the (normally unset) `EOL`
characters — Return was only ever ending lines because `ICRNL` forged a `\n`
before the line discipline looked. Turn the forgery off and Enter becomes an
ordinary printing key. This is also the diagnosis when a terminal appears to
ignore Enter entirely: some program died and left `ICRNL` off — `stty sane` is
undoing exactly this.

**The wider family:** `INLCR` (the reverse forgery) and `IGNCR` (drop `\r`
outright) live in the same field, and `OPOST`'s `ONLCR` at puzzle 6 is the
output-side mirror. The terminal world simply never agreed on what "end of
line" is — which is why raw-mode key readers accept `\r` *and* `\n` for Enter,
and why the network protocols born on real terminals (HTTP, SMTP) pin it to
`\r\n` and end the argument.

## 6 — `disable_output_processing`

```python
def disable_output_processing(mode):
    mode[OFLAG] &= ~termios.OPOST
    return mode
```

**The thing to notice:** you cleared the master switch, not the rule. `ONLCR`
is the tenant doing the `\n` → `\r\n` rewriting, and it's still set — but with
`OPOST` off the kernel never consults `OFLAG`'s rules at all. Output is the
only direction with such a switch; input flags apply one by one. `cfmakeraw`
does the same thing: one bit, and the whole output pipeline steps aside.

**The consequence you'll feel:** every `print()` in a raw-mode program
staircases, because Python is still ending lines with a lone `\n` and nobody
upgrades it any more. That's why TUI code writes `\r\n` explicitly, or better,
stops thinking in lines and starts thinking in cursor positions — which is
what escape sequences are for, at puzzle 14.

## 7 — `make_raw` and `raw_mode`

```python
def make_raw(mode):
    mode = disable_echo(mode)
    mode = disable_line_buffering(mode)
    mode = disable_signal_chars(mode)
    mode = disable_extended_chars(mode)
    mode = disable_flow_control(mode)
    mode = disable_cr_translation(mode)
    mode = disable_output_processing(mode)
    return mode


@contextmanager
def raw_mode(fd):
    saved = termios.tcgetattr(fd)
    termios.tcsetattr(fd, termios.TCSANOW, make_raw(termios.tcgetattr(fd)))
    try:
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, saved)
```

(with `from contextlib import contextmanager` at the top.)

**The thing to notice:** `tcgetattr` is called *twice*, and the second call is
not tidiness. `make_raw` mutates the list you hand it — every puzzle here does,
and so does `tty.setraw`. Feed it the list you saved and `saved` is raw too;
your `finally` runs, "restores", and the terminal stays broken. This is the
classic termios bug, and it's invisible until the one day you need the restore
to work.

**What is deliberately absent:** `disable_signal_flush`. Setting `NOFLSH` looks
like part of the bundle and isn't — with `ISIG` cleared, no byte is ever
recognized as `INTR`, `QUIT` or `SUSP` in the first place, so there is no flush
left to suppress. `tty.setraw` leaves the bit alone for the same reason, and
`test_P07_matches_the_stdlib_where_it_counts` compares it, so adding it here is
one of the two ways that test goes red. (The other is forgetting
`disable_extended_chars`, which is easy to do because puzzle 4b is a side
branch rather than a rung.)

**The diff against the stdlib:** `cfmakeraw` also clears `BRKINT`, `INPCK`,
`ISTRIP` and `PARENB` and sets `CS8` — break conditions, parity checking, and
seven-bit stripping. All of it is about the serial *wire*, which a pty doesn't
have, so no test in this rig can distinguish your version from the stdlib's.
That's the difference between "same behaviour here" and "same everywhere", and
production code should still clear the lot.

**One more choice worth knowing you made:** `TCSANOW` switches immediately;
`tty.setraw` defaults to `TCSAFLUSH`, which also throws away any input typed
before the switch — usually what you want on the way *in* (keystrokes typed at
the cooked prompt shouldn't leak into your raw reader), and `TCSADRAIN` is the
polite way *out* (let pending output finish printing first).

## 8 — `echo_back`

```python
def echo_back(data):
    return data.replace(b"\r", b"\r\n")
```

**The thing to notice:** how little there is. Echo always was just this — the
line discipline copying input to output — and the entire mystery of "why can I
see what I type" reduces to one `write()` someone does on your behalf. The
`\r` case is puzzles 5 and 6 sending you the bill at the same time: the key
arrives untranslated *and* nothing pads your output, so the newline you used
to get for free is now two bytes you write yourself.

**Where it stops being trivial:** echo `\x7f` and you'll print a control
character instead of erasing one — echoing and *editing* are different jobs,
and the kernel's `ECHOE` flag was quietly doing both. That's puzzle 9. And the
kernel's `ECHOCTL` was rendering other control bytes as `^C`-style pairs,
which is why they looked printable; try `echo_back(b"\x1b")` in a real
terminal and watch nothing appear.

## 9 — `LineEditor`

```python
class LineEditor:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, byte):
        if byte == b"\r":
            line = bytes(self.buffer) + b"\n"
            self.buffer.clear()
            return b"\r\n", line
        if byte == b"\x7f":
            if not self.buffer:
                return b"", None
            self.buffer.pop()
            return b"\x08 \x08", None
        if byte == b"\x15":
            wipe = b"\x08 \x08" * len(self.buffer)
            self.buffer.clear()
            return wipe, None
        self.buffer += byte
        return byte, None
```

**The thing to notice:** `\b \b`. Backspace the control character (`\x08`)
only moves the cursor left; the character it lands on stays on the screen. So
erasing is three bytes: step back, overwrite with a space, step back again.
That dance is exactly what the kernel's `ECHOE` flag performs when cooked mode
handles `VERASE`, and you've likely watched it thousands of times without
seeing three writes.

**The shape of the return value:** every keystroke produces two answers — what
the screen should show, what the program should eventually receive — and
they're independent. That's the harness diagram again: `feed()` *is* a line
discipline, with the same two arrows. Compare the puzzle 2 before-tests with
the puzzle 9 tests; several are byte-for-byte the same assertion, made against
your code instead of the kernel's.

**Where it breaks, on purpose:** one `\x7f` drops one *byte*. Type `é` (two
bytes in UTF-8) or a tab (one byte, several columns) and the screen and buffer
disagree. The kernel has the same problem — the `IUTF8` flag exists precisely
because "erase one character" and "erase one byte" stopped being the same
thing — and a real line editor tracks display width per character, which is
half of what makes readline nontrivial. (`apply_cooked` pins `IUTF8` off, so
the kernel in these puzzles is exactly as naive as your version.)
