"""Tests for the tty puzzles. Fifteen planned; nine written so far.

    python3 test_puzzles.py        every puzzle
    python3 test_puzzles.py 2      just puzzle 2
    python3 test_puzzles.py 1 2 3  a range
    pytest test_puzzles.py -k P03  the same thing under pytest

From a notebook, import the runner instead:

    from test_puzzles import check
    check(2)

Each puzzle has a "before" test that passes on an untouched cooked terminal
and an "after" test that only passes once your function has changed it. The
before tests never fail. They aren't checking your work -- they're a
description of the terminal you already have, written as assertions.

Echo assertions use `in` rather than `==` where the exact echo of a control
byte is beside the point.
"""

import termios
import tty

import puzzles
import tracing
from harness import CC, IFLAG, LFLAG, OFLAG, Terminal, cc_value

# --- P1: ECHO -- the terminal displays what you type -----------------------


def test_P01_before_a_cooked_terminal_echoes():
    with Terminal() as t:
        t.press(b"abc")
        assert b"abc" in t.screen()


def test_P01_after_the_screen_stays_silent():
    with Terminal(puzzles.disable_echo) as t:
        t.press(b"hunter2")
        assert t.screen() == b""


def test_P01_the_program_still_gets_the_keystrokes():
    # Echo is display, not delivery. This is the whole of getpass().
    with Terminal(puzzles.disable_echo) as t:
        t.press(b"hunter2\r")
        # \r arriving as \n is ICRNL, still on -- that's puzzle 5.
        assert t.delivered() == b"hunter2\n"


# --- P2: ICANON -- the terminal buffers a line and edits it for you --------


def test_P02_before_nothing_is_delivered_until_enter():
    with Terminal() as t:
        t.press(b"abc")
        assert t.delivered() == b""  # the line discipline is holding them
        t.press(b"\r")
        assert t.delivered() == b"abc\n"


def test_P02_before_backspace_never_reaches_the_program():
    # Someone implements backspace. In cooked mode it isn't you.
    with Terminal() as t:
        t.press(b"ab\x7fc\r")
        assert t.delivered() == b"ac\n"


def test_P02_after_each_keystroke_arrives_alone():
    with Terminal(puzzles.disable_line_buffering) as t:
        t.press(b"a")
        assert t.delivered() == b"a"


def test_P02_after_backspace_is_just_a_byte_you_must_handle():
    with Terminal(puzzles.disable_line_buffering) as t:
        t.press(b"ab\x7f")
        assert t.delivered() == b"ab\x7f"


def test_P02_after_vmin_and_vtime_are_set_not_inherited():
    # A cooked terminal already has VMIN=1, VTIME=0, so on one of those,
    # setting them is a no-op and clearing ICANON alone looks like a complete
    # answer. Hand the puzzle a terminal someone else configured -- reads here
    # don't complete until four bytes arrive -- and it isn't.
    with Terminal(puzzles.disable_line_buffering, preset={termios.VMIN: 4}) as t:
        t.press(b"a")
        assert t.delivered() == b"a"


# --- P3: ISIG -- the terminal turns three bytes into signals ---------------


def test_P03_before_ctrl_c_takes_the_pending_line_with_it():
    # With ISIG set, a byte matching INTR does two separable things: it raises
    # SIGINT at the foreground process group, and -- unless NOFLSH is set, and
    # by default it isn't -- it flushes the input and output queues. So the
    # "a" typed before it never arrives either. This pty has no session, so
    # nothing is signalled here; the flush happens regardless, which is why
    # Ctrl-C wipes a half-typed shell line before any program has seen it.
    with Terminal() as t:
        t.press(b"a\x03b\r")
        assert t.delivered() == b"b\n"


def test_P03_after_the_flush_stops_but_the_interception_does_not():
    # ISIG is still on here, so 0x03 is still swallowed -- only the "a" it used
    # to take with it survives. Two consequences of one character, unpicked.
    with Terminal(puzzles.disable_signal_flush) as t:
        t.press(b"a\x03b\r")
        assert t.delivered() == b"ab\n"


def test_P03_after_ctrl_c_is_an_ordinary_byte():
    with Terminal(puzzles.disable_signal_chars) as t:
        t.press(b"a\x03b\r")
        assert t.delivered() == b"a\x03b\n"


def test_P03_ctrl_backslash_and_ctrl_z_go_the_same_way():
    # QUIT (0x1c) and SUSP (0x1a) are intercepted by the same flag, and flush
    # the queues on the same terms as INTR -- so the "a" goes with them.
    with Terminal() as t:
        t.press(b"a\x1c\x1ab\r")
        assert t.delivered() == b"b\n"
    with Terminal(puzzles.disable_signal_chars) as t:
        t.press(b"a\x1c\x1ab\r")
        assert t.delivered() == b"a\x1c\x1ab\n"


# --- P4: IXON -- two bytes of input control all of the output --------------


def test_P04_before_ctrl_s_freezes_the_terminal():
    with Terminal() as t:
        t.press(b"\x13")
        assert t.screen() == b""  # consumed by flow control, not even echoed
        t.emit(b"data\n")
        assert t.screen() == b""  # the kernel is holding the output queue
        t.press(b"\x11")
        assert b"data" in t.screen()  # Ctrl-Q lets it go


def test_P04_before_only_ctrl_q_thaws_it():
    # The claim worth testing is that START is *the* key, not just any key.
    # It is only true where IXANY is clear -- with IXANY set, which is the
    # macOS default, any byte at all restarts output. The cooked baseline
    # pins it off so this puzzle means the same thing everywhere.
    with Terminal() as t:
        t.press(b"\x13")
        t.emit(b"data\n")
        assert t.screen() == b""
        t.press(b"z")  # an ordinary byte is not a thaw
        assert t.screen() == b""
        t.press(b"\x11")
        assert b"data" in t.screen()


def test_P04_before_the_flow_chars_never_reach_the_program():
    with Terminal() as t:
        t.press(b"a\x13\x11b\r")
        assert t.delivered() == b"ab\n"


def test_P04_after_ctrl_s_is_an_ordinary_byte():
    with Terminal(puzzles.disable_flow_control) as t:
        t.press(b"a\x13b\r")
        assert t.delivered() == b"a\x13b\n"


def test_P04_after_output_cannot_be_frozen():
    with Terminal(puzzles.disable_flow_control) as t:
        t.press(b"\x13")
        t.screen()  # drain -- how a terminal echoes a control byte varies
        t.emit(b"data\n")
        assert b"data" in t.screen()


def test_P04_after_a_nul_byte_cannot_freeze_output_either():
    # The tempting wrong answer: zero out VSTOP/VSTART instead of touching a
    # flag. But 0x00 doesn't mean "no character" -- _POSIX_VDISABLE is 0xff
    # on macOS (ask os.fpathconf(fd, "PC_VDISABLE")) -- so that answer leaves
    # flow control armed and listening for NUL. The spec says *nothing* you
    # type can pause output, and NUL is something you can type.
    with Terminal(puzzles.disable_flow_control) as t:
        t.press(b"\x00")
        t.screen()  # drain any echo
        t.emit(b"data\n")
        assert b"data" in t.screen()


def test_P04_after_the_control_characters_are_untouched():
    # Same trap from the other side. Rebinding VSTOP/VSTART to any byte at
    # all still isn't switching the feature off -- and on a platform where
    # 0 happens to be _POSIX_VDISABLE it would even behave correctly, which
    # is why the behavioural test above isn't enough on its own. One bit,
    # in IFLAG; the CC table is puzzle 9's business.
    with Terminal() as t:
        before = t.mode()
        after = puzzles.disable_flow_control(t.mode())
    assert not after[IFLAG] & termios.IXON
    assert after[CC] == before[CC], "leave the control characters alone"


# --- P4b: IEXTEN -- the deluxe special characters --------------------------


def test_P04_before_ctrl_v_quotes_the_next_byte():
    # VLNEXT (^V, 0x16): "deliver the next byte literally." The quoted ^C is
    # spared both of puzzle 3's consequences -- no flush, and it arrives.
    with Terminal() as t:
        t.press(b"a\x16\x03b\r")
        assert t.delivered() == b"a\x03b\n"


def test_P04_after_ctrl_v_is_an_ordinary_byte():
    with Terminal(puzzles.disable_extended_chars) as t:
        t.press(b"a\x16b\r")
        assert t.delivered() == b"a\x16b\n"


# --- P5: ICRNL -- the Return key doesn't send the byte you think -----------


def test_P05_before_return_reaches_the_program_as_newline():
    # One keystroke, one byte, watched without canonical mode in the way:
    # you pressed \r and the program got \n.
    with Terminal(puzzles.disable_line_buffering) as t:
        t.press(b"\r")
        assert t.delivered() == b"\n"


def test_P05_after_return_delivers_carriage_return():
    def configure(mode):
        return puzzles.disable_cr_translation(puzzles.disable_line_buffering(mode))

    with Terminal(configure) as t:
        t.press(b"\r")
        assert t.delivered() == b"\r"


def test_P05_after_return_no_longer_ends_a_canonical_line():
    # Line buffering left ON this time. The line discipline's delimiter is
    # \n, and with the translation off nothing you press makes one -- so
    # Enter stops ending the line. Ctrl-J (a literal \n) still does.
    with Terminal(puzzles.disable_cr_translation) as t:
        t.press(b"abc\r")
        assert t.delivered() == b""
        t.press(b"\n")
        assert t.delivered() == b"abc\r\n"


# --- P6: OPOST -- the kernel rewrites output too ---------------------------


def test_P06_before_newline_grows_a_carriage_return_on_the_way_out():
    with Terminal() as t:
        t.emit(b"one\ntwo\n")
        assert t.screen() == b"one\r\ntwo\r\n"


def test_P06_after_output_crosses_verbatim():
    with Terminal(puzzles.disable_output_processing) as t:
        t.emit(b"one\ntwo\n")
        assert t.screen() == b"one\ntwo\n"


def test_P06_after_the_master_switch_is_off_not_just_one_tenant():
    # ONLCR is the only rewrite armed on a cooked terminal, so clearing it
    # alone looks like a complete answer to the test above. Arm a different
    # tenant first -- OCRNL rewrites \r into \n on the way out -- and ask
    # again. OPOST is the master switch: with it off, nothing rewrites.
    def configure(mode):
        mode[OFLAG] |= termios.OCRNL
        return puzzles.disable_output_processing(mode)

    with Terminal(configure) as t:
        t.emit(b"down\rhome")
        assert t.screen() == b"down\rhome"


# --- P7: make_raw -- the whole descent in one function ---------------------


def test_P07_raw_input_arrives_byte_for_byte():
    with Terminal(puzzles.make_raw) as t:
        t.press(b"a\x03\x13\x1a\r\x7f")
        assert t.delivered() == b"a\x03\x13\x1a\r\x7f"


def test_P07_raw_has_no_deluxe_characters_either():
    # IEXTEN's tenants survive ICANON and ISIG: ^V still quotes, and ^O
    # (VDISCARD) still throws all output away -- a TUI that "freezes" the
    # moment someone fat-fingers Ctrl-O, with no error anywhere. Raw means
    # IEXTEN is off too, and both are bytes.
    with Terminal(puzzles.make_raw) as t:
        t.press(b"\x16a")
        assert t.delivered() == b"\x16a"
    with Terminal(puzzles.make_raw) as t:
        t.press(b"\x0f")
        t.delivered()  # drain
        t.emit(b"after")
        assert b"after" in t.screen()


def test_P07_raw_echoes_nothing():
    with Terminal(puzzles.make_raw) as t:
        t.press(b"hunter2\r")
        assert t.screen() == b""


def test_P07_raw_output_crosses_verbatim():
    with Terminal(puzzles.make_raw) as t:
        t.emit(b"one\ntwo")
        assert t.screen() == b"one\ntwo"


def test_P07_raw_survives_someone_elses_vmin():
    # Same trap as puzzle 2: raw mode is a *destination*, not a diff against
    # the defaults, so it has to set VMIN/VTIME no matter what it was handed.
    with Terminal(puzzles.make_raw, preset={termios.VMIN: 4, termios.VTIME: 5}) as t:
        t.press(b"a")
        assert t.delivered() == b"a"


def test_P07_matches_the_stdlib_where_it_counts():
    # tty.setraw is cfmakeraw plus apply. It also clears BRKINT, ISTRIP and
    # PARENB and sets CS8 -- serial-line hygiene with nothing to show on a
    # pty -- so compare only the bits this ladder is about.
    with Terminal() as t:
        yours = puzzles.make_raw(t.mode())
        tty.setraw(t.slave)
        theirs = t.mode()
    # Report every disagreeing flag by name and in one go. This test writes no
    # bytes, so there is no trace to fall back on -- the message is the only
    # diagnostic there is.
    differences = []
    for field, name in [
        (IFLAG, "IXON"),
        (IFLAG, "ICRNL"),
        (OFLAG, "OPOST"),
        (LFLAG, "ECHO"),
        (LFLAG, "ICANON"),
        (LFLAG, "ISIG"),
        (LFLAG, "IEXTEN"),  # puzzle 4b: not hygiene, ^V/^O are live
        (LFLAG, "NOFLSH"),  # setraw leaves it: nothing to flush, ISIG off
    ]:
        bit = getattr(termios, name)
        mine, stdlib = bool(yours[field] & bit), bool(theirs[field] & bit)
        if mine != stdlib:
            differences.append(
                f"      {name:<8} yours={'on' if mine else 'off':<3} "
                f"tty.setraw={'on' if stdlib else 'off'}"
            )
    assert not differences, "make_raw disagrees with tty.setraw:\n" + "\n".join(
        differences
    )
    # cc_value, not a bare index: CPython hands back VMIN/VTIME as ints only
    # when ICANON is clear, and `yours` was built from a cooked mode where
    # they are still one-byte bytes objects.
    assert cc_value(yours, "VMIN") == cc_value(theirs, "VMIN")
    assert cc_value(yours, "VTIME") == cc_value(theirs, "VTIME")


def test_P07_raw_mode_restores_after_a_crash():
    # The crash must be a bespoke exception: catching RuntimeError here would
    # also swallow the NotImplementedError of an unwritten raw_mode (it's a
    # RuntimeError subclass), and an untouched terminal passes "unchanged"
    # vacuously -- the puzzle would look done before it was started.
    class AppBlewUp(Exception):
        pass

    with Terminal() as t:
        before = t.mode()
        try:
            with puzzles.raw_mode(t.slave):
                t.press(b"a")
                assert t.delivered() == b"a"  # raw inside the block
                raise AppBlewUp("the app blew up mid-frame")
        except AppBlewUp:
            pass
        assert t.mode() == before
        t.press(b"ab\x7fc\r")
        assert t.delivered() == b"ac\n"  # cooked again: the kernel edits


# --- P8: echo, reimplemented ------------------------------------------------


def test_P08_before_nobody_echoes_on_a_raw_terminal():
    with Terminal(puzzles.make_raw) as t:
        t.press(b"hi")
        assert t.delivered() == b"hi"
        assert t.screen() == b""


def test_P08_after_the_program_echoes_instead():
    with Terminal(puzzles.make_raw) as t:
        t.press(b"hi")
        t.emit(puzzles.echo_back(t.delivered()))
        assert t.screen() == b"hi"


def test_P08_return_takes_two_bytes_now():
    # Enter arrives as \r (puzzle 5 undid the translation) and nothing will
    # append the line feed for you (puzzle 6). Both bytes are yours.
    with Terminal(puzzles.make_raw) as t:
        t.press(b"one\rtwo")
        t.emit(puzzles.echo_back(t.delivered()))
        assert t.screen() == b"one\r\ntwo"


# --- P9: canonical mode, reimplemented --------------------------------------


def feed_all(editor, data):
    """Push data through the editor a byte at a time, as a read loop would."""
    echoed, lines = bytearray(), []
    for i in range(len(data)):
        echo, line = editor.feed(data[i : i + 1])
        echoed += echo
        if line is not None:
            lines.append(line)
    return bytes(echoed), lines


def test_P09_a_plain_line_echoes_and_delivers_like_cooked_mode():
    echoed, lines = feed_all(puzzles.LineEditor(), b"abc\r")
    assert echoed == b"abc\r\n"
    assert lines == [b"abc\n"]  # compare test_P02_before -- you're the kernel


def test_P09_backspace_edits_the_buffer_and_the_screen():
    # \b alone only moves the cursor; wiping a character is the three-byte
    # dance back-space-back.
    echoed, lines = feed_all(puzzles.LineEditor(), b"ab\x7fc\r")
    assert lines == [b"ac\n"]
    assert echoed == b"ab\x08 \x08c\r\n"


def test_P09_backspace_on_an_empty_line_does_nothing():
    echoed, lines = feed_all(puzzles.LineEditor(), b"\x7f\x7fa\r")
    assert lines == [b"a\n"]
    assert echoed == b"a\r\n"


def test_P09_ctrl_u_kills_the_whole_line():
    echoed, lines = feed_all(puzzles.LineEditor(), b"abcd\x15ok\r")
    assert lines == [b"ok\n"]
    assert echoed == b"abcd" + b"\x08 \x08" * 4 + b"ok\r\n"


def test_P09_the_editor_drives_a_real_terminal():
    # The whole loop on a live pty: raw keystrokes in, your echo out.
    with Terminal(puzzles.make_raw) as t:
        t.press(b"ls -x\x7fl\r")
        echoed, lines = feed_all(puzzles.LineEditor(), t.delivered())
        t.emit(echoed)
        assert lines == [b"ls -l\n"]
        assert t.screen() == b"ls -x" + b"\x08 \x08" + b"l\r\n"


# --- the runner -------------------------------------------------------------


def all_tests():
    """Every test, in the order it appears in this file.

    Definition order, not alphabetical: each puzzle's "before" test is written
    above its "after" test because that's the order they're meant to be read,
    and sorting by name would run them backwards.
    """
    tests = [v for k, v in globals().items() if k.startswith("test_P")]
    return sorted(tests, key=lambda f: f.__code__.co_firstlineno)


def check(*numbers, show_trace=True):
    """Run the tests for the given puzzle numbers, or all of them.

    Usable from a notebook cell as well as the command line:

        from test_puzzles import check
        check(4)

    Returns True when everything selected passed.
    """
    import traceback

    tests = all_tests()
    if numbers:
        wanted = tuple(f"test_P{int(n):02d}" for n in numbers)
        tests = [t for t in tests if t.__name__.startswith(wanted)]
    if not tests:
        print(f"no tests match {numbers}")
        return False

    todo = failed = 0
    for test in tests:
        tracing.reset()
        label = test.__name__.removeprefix("test_")
        try:
            test()
            print(f"  ok    {label}")
        except NotImplementedError:
            todo += 1
            print(f"  todo  {label}")
        except Exception:  # noqa: BLE001 -- report and keep going
            failed += 1
            print(f"  FAIL  {label}")
            if show_trace:
                report = tracing.report()
                if report:
                    print(report)
                print("    " + traceback.format_exc().strip().replace("\n", "\n    "))
                print()

    passed = len(tests) - failed - todo
    print(f"\n{passed}/{len(tests)} passed, {todo} not started")
    return failed == 0 and todo == 0


if __name__ == "__main__":
    import sys

    check(*[a for a in sys.argv[1:] if a.isdigit()])
