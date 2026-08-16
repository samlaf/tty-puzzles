"""Tests for the tty puzzles. All fifteen.

    python3 test_puzzles.py        every puzzle
    python3 test_puzzles.py 2      just puzzle 2
    python3 test_puzzles.py 1 2 3  a range
    pytest test_puzzles.py -k P03  the same thing under pytest

From a notebook, import the runner instead:

    from test_puzzles import check
    check(2)

Each puzzle has a "before" test that passes on an untouched cooked tty
and an "after" test that only passes once your function has changed it. The
before tests never fail. They aren't checking your work -- they're a
description of the tty you already have, written as assertions.

Echo assertions use `in` rather than `==` where the exact echo of a control
byte is beside the point.
"""

import os
import signal
import termios
import tty
from contextlib import contextmanager

import puzzles
import tracing
from harness import CC, IFLAG, LFLAG, OFLAG, Pty, cc_value

# --- P1: ECHO -- the tty displays what you type -----------------------


def test_P01_before_a_cooked_tty_echoes():
    with Pty() as t:
        t.press(b"abc")
        assert b"abc" in t.screen()


def test_P01_after_the_screen_stays_silent():
    with Pty(puzzles.disable_echo) as t:
        t.press(b"hunter2")
        assert t.screen() == b""


def test_P01_the_program_still_gets_the_keystrokes():
    # Echo is display, not delivery. This is the whole of getpass().
    with Pty(puzzles.disable_echo) as t:
        t.press(b"hunter2\r")
        # \r arriving as \n is ICRNL, still on -- that's puzzle 5.
        assert t.delivered() == b"hunter2\n"


# --- P2: ICANON -- the tty buffers a line and edits it for you --------


def test_P02_before_nothing_is_delivered_until_enter():
    with Pty() as t:
        t.press(b"abc")
        assert t.delivered() == b""  # the line discipline is holding them
        t.press(b"\r")
        assert t.delivered() == b"abc\n"


def test_P02_before_backspace_never_reaches_the_program():
    # Someone implements backspace. In cooked mode it isn't you.
    with Pty() as t:
        t.press(b"ab\x7fc\r")
        assert t.delivered() == b"ac\n"


def test_P02_after_each_keystroke_arrives_alone():
    with Pty(puzzles.disable_line_buffering) as t:
        t.press(b"a")
        assert t.delivered() == b"a"


def test_P02_after_backspace_is_just_a_byte_you_must_handle():
    with Pty(puzzles.disable_line_buffering) as t:
        t.press(b"ab\x7f")
        assert t.delivered() == b"ab\x7f"


def test_P02_after_vmin_and_vtime_are_set_not_inherited():
    # A cooked tty already has VMIN=1, VTIME=0, so on one of those,
    # setting them is a no-op and clearing ICANON alone looks like a complete
    # answer. Hand the puzzle a tty someone else configured -- reads here
    # don't complete until four bytes arrive -- and it isn't.
    with Pty(puzzles.disable_line_buffering, preset={termios.VMIN: 4}) as t:
        t.press(b"a")
        assert t.delivered() == b"a"


# --- P3: ISIG -- the tty turns three bytes into signals ---------------


def test_P03_before_ctrl_c_takes_the_pending_line_with_it():
    # With ISIG set, a byte matching INTR does two separable things: it raises
    # SIGINT at the foreground process group, and -- unless NOFLSH is set, and
    # by default it isn't -- it flushes the input and output queues. So the
    # "a" typed before it never arrives either. This pty has no session, so
    # nothing is signalled here; the flush happens regardless, which is why
    # Ctrl-C wipes a half-typed shell line before any program has seen it.
    with Pty() as t:
        t.press(b"a\x03b\r")
        assert t.delivered() == b"b\n"


def test_P03_after_the_flush_stops_but_the_interception_does_not():
    # ISIG is still on here, so 0x03 is still swallowed -- only the "a" it used
    # to take with it survives. Two consequences of one character, unpicked.
    with Pty(puzzles.disable_signal_flush) as t:
        t.press(b"a\x03b\r")
        assert t.delivered() == b"ab\n"


def test_P03_after_ctrl_c_is_an_ordinary_byte():
    with Pty(puzzles.disable_signal_chars) as t:
        t.press(b"a\x03b\r")
        assert t.delivered() == b"a\x03b\n"


def test_P03_ctrl_backslash_and_ctrl_z_go_the_same_way():
    # QUIT (0x1c) and SUSP (0x1a) are intercepted by the same flag, and flush
    # the queues on the same terms as INTR -- so the "a" goes with them.
    with Pty() as t:
        t.press(b"a\x1c\x1ab\r")
        assert t.delivered() == b"b\n"
    with Pty(puzzles.disable_signal_chars) as t:
        t.press(b"a\x1c\x1ab\r")
        assert t.delivered() == b"a\x1c\x1ab\n"


# --- P4: IXON -- two bytes of input control all of the output --------------


def test_P04_before_ctrl_s_freezes_the_output():
    with Pty() as t:
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
    with Pty() as t:
        t.press(b"\x13")
        t.emit(b"data\n")
        assert t.screen() == b""
        t.press(b"z")  # an ordinary byte is not a thaw
        assert t.screen() == b""
        t.press(b"\x11")
        assert b"data" in t.screen()


def test_P04_before_the_flow_chars_never_reach_the_program():
    with Pty() as t:
        t.press(b"a\x13\x11b\r")
        assert t.delivered() == b"ab\n"


def test_P04_after_ctrl_s_is_an_ordinary_byte():
    with Pty(puzzles.disable_flow_control) as t:
        t.press(b"a\x13b\r")
        assert t.delivered() == b"a\x13b\n"


def test_P04_after_output_cannot_be_frozen():
    with Pty(puzzles.disable_flow_control) as t:
        t.press(b"\x13")
        t.screen()  # drain -- how a tty echoes a control byte varies
        t.emit(b"data\n")
        assert b"data" in t.screen()


def test_P04_after_a_nul_byte_cannot_freeze_output_either():
    # The tempting wrong answer: zero out VSTOP/VSTART instead of touching a
    # flag. But 0x00 doesn't mean "no character" -- _POSIX_VDISABLE is 0xff
    # on macOS (ask os.fpathconf(fd, "PC_VDISABLE")) -- so that answer leaves
    # flow control armed and listening for NUL. The spec says *nothing* you
    # type can pause output, and NUL is something you can type.
    with Pty(puzzles.disable_flow_control) as t:
        t.press(b"\x00")
        t.screen()  # drain any echo
        t.emit(b"data\n")
        assert b"data" in t.screen()


def test_P04_after_the_special_characters_are_untouched():
    # Same trap from the other side. Rebinding VSTOP/VSTART to any byte at
    # all still isn't switching the feature off -- and on a platform where
    # 0 happens to be _POSIX_VDISABLE it would even behave correctly, which
    # is why the behavioural test above isn't enough on its own. One bit,
    # in IFLAG; deciding what a byte means becomes your job at puzzle 9.
    with Pty() as t:
        before = t.mode()
        after = puzzles.disable_flow_control(t.mode())
    assert not after[IFLAG] & termios.IXON
    assert after[CC] == before[CC], "leave the special characters alone"


# --- P4b: IEXTEN -- the extended characters --------------------------------


def test_P04_before_ctrl_v_quotes_the_next_byte():
    # VLNEXT (^V, 0x16): "deliver the next byte literally." The quoted ^C is
    # spared both of puzzle 3's consequences -- no flush, and it arrives.
    with Pty() as t:
        t.press(b"a\x16\x03b\r")
        assert t.delivered() == b"a\x03b\n"


def test_P04_after_ctrl_v_is_an_ordinary_byte():
    with Pty(puzzles.disable_extended_chars) as t:
        t.press(b"a\x16b\r")
        assert t.delivered() == b"a\x16b\n"


# --- P5: ICRNL -- the Return key doesn't send the byte you think -----------


def test_P05_before_return_reaches_the_program_as_newline():
    # One keystroke, one byte, watched without canonical mode in the way:
    # you pressed \r and the program got \n.
    with Pty(puzzles.disable_line_buffering) as t:
        t.press(b"\r")
        assert t.delivered() == b"\n"


def test_P05_after_return_delivers_carriage_return():
    def configure(mode):
        return puzzles.disable_cr_translation(puzzles.disable_line_buffering(mode))

    with Pty(configure) as t:
        t.press(b"\r")
        assert t.delivered() == b"\r"


def test_P05_after_return_no_longer_ends_a_canonical_line():
    # Line buffering left ON this time. The line discipline's delimiter is
    # \n, and with the translation off nothing you press makes one -- so
    # Enter stops ending the line. Ctrl-J (a literal \n) still does.
    with Pty(puzzles.disable_cr_translation) as t:
        t.press(b"abc\r")
        assert t.delivered() == b""
        t.press(b"\n")
        assert t.delivered() == b"abc\r\n"


# --- P6: OPOST -- the kernel rewrites output too ---------------------------


def test_P06_before_newline_grows_a_carriage_return_on_the_way_out():
    with Pty() as t:
        t.emit(b"one\ntwo\n")
        assert t.screen() == b"one\r\ntwo\r\n"


def test_P06_after_output_crosses_verbatim():
    with Pty(puzzles.disable_output_processing) as t:
        t.emit(b"one\ntwo\n")
        assert t.screen() == b"one\ntwo\n"


def test_P06_after_the_master_switch_is_off_not_just_one_tenant():
    # ONLCR is the only rewrite armed on a cooked tty, so clearing it
    # alone looks like a complete answer to the test above. Arm a different
    # tenant first -- OCRNL rewrites \r into \n on the way out -- and ask
    # again. OPOST is the master switch: with it off, nothing rewrites.
    def configure(mode):
        mode[OFLAG] |= termios.OCRNL
        return puzzles.disable_output_processing(mode)

    with Pty(configure) as t:
        t.emit(b"down\rhome")
        assert t.screen() == b"down\rhome"


# --- P7: make_raw -- the whole descent in one function ---------------------


def test_P07_raw_input_arrives_byte_for_byte():
    with Pty(puzzles.make_raw) as t:
        t.press(b"a\x03\x13\x1a\r\x7f")
        assert t.delivered() == b"a\x03\x13\x1a\r\x7f"


def test_P07_raw_has_no_extended_characters_either():
    # IEXTEN's tenants survive ICANON and ISIG: ^V still quotes, and ^O
    # (VDISCARD) still throws all output away -- a TUI that "freezes" the
    # moment someone fat-fingers Ctrl-O, with no error anywhere. Raw means
    # IEXTEN is off too, and both are bytes.
    with Pty(puzzles.make_raw) as t:
        t.press(b"\x16a")
        assert t.delivered() == b"\x16a"
    with Pty(puzzles.make_raw) as t:
        t.press(b"\x0f")
        t.delivered()  # drain
        t.emit(b"after")
        assert b"after" in t.screen()


def test_P07_raw_echoes_nothing():
    with Pty(puzzles.make_raw) as t:
        t.press(b"hunter2\r")
        assert t.screen() == b""


def test_P07_raw_output_crosses_verbatim():
    with Pty(puzzles.make_raw) as t:
        t.emit(b"one\ntwo")
        assert t.screen() == b"one\ntwo"


def test_P07_raw_survives_someone_elses_vmin():
    # Same trap as puzzle 2: raw mode is a *destination*, not a diff against
    # the defaults, so it has to set VMIN/VTIME no matter what it was handed.
    with Pty(puzzles.make_raw, preset={termios.VMIN: 4, termios.VTIME: 5}) as t:
        t.press(b"a")
        assert t.delivered() == b"a"


def test_P07_matches_the_stdlib_where_it_counts():
    # tty.setraw is cfmakeraw plus apply. It also clears BRKINT, ISTRIP and
    # PARENB and sets CS8 -- serial-line hygiene with nothing to show on a
    # pty -- so compare only the bits this ladder is about.
    with Pty() as t:
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
    # RuntimeError subclass), and an untouched tty passes "unchanged"
    # vacuously -- the puzzle would look done before it was started.
    class AppBlewUp(Exception):
        pass

    with Pty() as t:
        before = t.mode()
        try:
            with puzzles.raw_mode(t.slave):
                t.press(b"a")
                assert t.delivered() == b"a"  # raw inside the block
                raise AppBlewUp("the app blew up mid-frame")
        except AppBlewUp:
            pass
        after = t.mode()
        # PENDIN is not configuration. The BSD kernel raises it on any switch
        # back into canonical mode -- "typeahead may be pending; re-edit it at
        # the next read" -- and lowers it again on its own. Your restore did
        # not put it there and cannot keep it out; assert on the bits you own.
        after[LFLAG] &= ~termios.PENDIN
        assert after == before
        t.press(b"ab\x7fc\r")
        assert t.delivered() == b"ac\n"  # cooked again: the kernel edits


# --- P8: echo, reimplemented ------------------------------------------------


def test_P08_before_nobody_echoes_on_a_raw_tty():
    with Pty(puzzles.make_raw) as t:
        t.press(b"hi")
        assert t.delivered() == b"hi"
        assert t.screen() == b""


def test_P08_after_the_program_echoes_instead():
    with Pty(puzzles.make_raw) as t:
        t.press(b"hi")
        t.emit(puzzles.echo_back(t.delivered()))
        assert t.screen() == b"hi"


def test_P08_return_takes_two_bytes_now():
    # Enter arrives as \r (puzzle 5 undid the translation) and nothing will
    # append the line feed for you (puzzle 6). Both bytes are yours.
    with Pty(puzzles.make_raw) as t:
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


def test_P09_the_editor_drives_a_real_tty():
    # The whole loop on a live pty: raw keystrokes in, your echo out.
    with Pty(puzzles.make_raw) as t:
        t.press(b"ls -x\x7fl\r")
        echoed, lines = feed_all(puzzles.LineEditor(), t.delivered())
        t.emit(echoed)
        assert lines == [b"ls -l\n"]
        assert t.screen() == b"ls -x" + b"\x08 \x08" + b"l\r\n"


# --- P10: your own interrupt --------------------------------------------------


def test_P10_before_a_raw_tty_lets_ctrl_c_through_untouched():
    # Puzzle 3's before-test, inverted: no flush, no signal, no meaning. The
    # byte arrives like any other, and giving it a meaning back is app code.
    with Pty(puzzles.make_raw) as t:
        t.press(b"abc\x03ok\r")
        assert t.delivered() == b"abc\x03ok\r"


def test_P10_after_ctrl_c_raises():
    editor = puzzles.InterruptingEditor()
    feed_all(editor, b"abc")
    try:
        editor.feed(b"\x03")
    except KeyboardInterrupt:
        return
    raise AssertionError("0x03 should raise KeyboardInterrupt")


def test_P10_after_the_flush_is_yours_too():
    # The kernel discarded the pending line on INTR -- puzzle 3's before-test
    # watched the "a" vanish. Your editor reproduces that: what was typed
    # before the ^C never becomes a line.
    editor = puzzles.InterruptingEditor()
    feed_all(editor, b"abc")
    try:
        editor.feed(b"\x03")
    except KeyboardInterrupt:
        pass
    echoed, lines = feed_all(editor, b"ok\r")
    assert lines == [b"ok\n"]


def test_P10_after_every_other_byte_is_still_puzzle_9():
    echoed, lines = feed_all(puzzles.InterruptingEditor(), b"ab\x7fc\r")
    assert lines == [b"ac\n"]
    assert echoed == b"ab\x08 \x08c\r\n"


def test_P10_the_read_loop_decides_what_interrupt_means():
    # The point of owning the byte: ^C doesn't have to kill anyone. Bash
    # treats it as "abandon this line" -- catch, show ^C, start over. An
    # uncaught raise is Python's default death. Both are correct; the policy
    # moved from the kernel to you.
    with Pty(puzzles.make_raw) as t:
        t.press(b"abc\x03ok\r")
        editor = puzzles.InterruptingEditor()
        echoed, lines = bytearray(), []
        data = t.delivered()
        for i in range(len(data)):
            try:
                echo, line = editor.feed(data[i : i + 1])
            except KeyboardInterrupt:
                echoed += b"^C\r\n"
                continue
            echoed += echo
            if line is not None:
                lines.append(line)
        t.emit(bytes(echoed))
        assert lines == [b"ok\n"]
        assert t.screen() == b"abc^C\r\nok\r\n"


# --- P11: the window size -----------------------------------------------------


def test_P11_before_the_size_lives_in_the_pty_not_the_fd():
    # A fresh pty has no size at all -- (0, 0) -- until someone says
    # otherwise; on a real terminal the emulator declares it at startup and
    # again on every resize. One size, stored in the pty itself: set at the
    # master, visible at the slave.
    with Pty() as t:
        assert termios.tcgetwinsize(t.slave) == (0, 0)
        termios.tcsetwinsize(t.master, (24, 80))
        assert termios.tcgetwinsize(t.slave) == (24, 80)


def test_P11_after_your_ioctl_agrees_with_the_wrapper():
    with Pty() as t:
        termios.tcsetwinsize(t.master, (24, 80))
        assert puzzles.window_size(t.slave) == (24, 80)
        termios.tcsetwinsize(t.master, (50, 132))
        assert puzzles.window_size(t.slave) == (50, 132)
        assert puzzles.window_size(t.slave) == termios.tcgetwinsize(t.slave)


def test_P11_after_sigwinch_is_the_whole_notification():
    with Pty() as t:
        termios.tcsetwinsize(t.master, (24, 80))
        seen = []
        previous = puzzles.watch_resize(t.slave, seen.append)
        try:
            termios.tcsetwinsize(t.master, (50, 132))
            # The kernel just raised SIGWINCH at this pty's foreground
            # process group -- which, as with puzzle 3's SIGINT, is nobody:
            # no session ever attached here. Deliver it by hand.
            assert seen == []
            os.kill(os.getpid(), signal.SIGWINCH)
            assert seen == [(50, 132)]
        finally:
            signal.signal(signal.SIGWINCH, previous)


# --- Part 3: above the fd -----------------------------------------------------
#
# From here on the kernel is a bystander: the tty is raw, and every byte in
# either direction is a conversation with the terminal emulator. No emulator
# sits on this rig's master, so the tests assert on the bytes themselves --
# which is all the kernel ever forwarded anyway.

# --- P12: escape sequences in -------------------------------------------------


def decode_all(decoder, data):
    """Push data through the decoder a byte at a time; collect finished keys."""
    keys = []
    for i in range(len(data)):
        key = decoder.feed(data[i : i + 1])
        if key is not None:
            keys.append(key)
    return keys


def test_P12_before_an_arrow_is_three_bytes():
    # The emulator speaks first: one keypress, three bytes, and the raw tty
    # forwards them untouched. Control arrives in the same stream as text --
    # in-band -- and pulling them apart again is now your job.
    with Pty(puzzles.make_raw) as t:
        t.press(b"\x1b[A")
        assert t.delivered() == b"\x1b[A"


def test_P12_after_arrows_decode_to_names():
    keys = decode_all(puzzles.KeyDecoder(), b"\x1b[A\x1b[B\x1b[C\x1b[D")
    assert keys == ["up", "down", "right", "left"]


def test_P12_after_plain_bytes_pass_through_as_text():
    assert decode_all(puzzles.KeyDecoder(), b"ab") == [b"a", b"b"]


def test_P12_after_text_and_sequences_interleave():
    assert decode_all(puzzles.KeyDecoder(), b"a\x1b[Ab") == [b"a", "up", b"b"]


def test_P12_after_delete_takes_a_parameter_byte():
    # \x1b[3~: the final byte ~ closes many keys, and the parameter bytes
    # before it are what tell them apart. This is why the grammar is worth
    # implementing over a lookup table of three-byte strings.
    assert decode_all(puzzles.KeyDecoder(), b"\x1b[3~") == ["delete"]


def test_P12_after_an_unknown_sequence_is_swallowed_whole():
    # \x1b[5~ is Page Up, which this decoder doesn't name. The wrong failure
    # mode is leaking "5~" into the text: knowing where a sequence *ends* is
    # half of why you parsed it.
    assert decode_all(puzzles.KeyDecoder(), b"a\x1b[5~b") == [b"a", b"b"]


def test_P12_after_a_lone_escape_never_resolves():
    # Not a bug -- an honest answer. No *byte* distinguishes the Escape key
    # from the front of an arrow; only time can, and time is puzzle 13.
    assert puzzles.KeyDecoder().feed(b"\x1b") is None


# --- P13: the lone ESC -- the seam puzzle ---------------------------------------


@contextmanager
def deadline(seconds, hint):
    """Fail a test instead of hanging it.

    Puzzles 13 and 15 are the first whose *wrong* answers can block forever
    on a read, and a hung suite teaches nothing -- so these tests run under
    an alarm that turns "never returned" into a failure with a hint.
    """

    def expired(signum, frame):
        raise AssertionError(hint)

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def test_P13_before_no_byte_tells_the_two_apart():
    with Pty(puzzles.make_raw) as t:
        t.press(b"\x1b")
        escape_key = t.delivered()
        t.press(b"\x1b[A")
        arrow = t.delivered()
        assert arrow.startswith(escape_key)  # identical prefix; only time differs


def test_P13_after_a_sequence_reads_as_one_key():
    with Pty(puzzles.make_raw) as t:
        t.press(b"\x1b[A")
        with deadline(2, "read_key never returned for a complete sequence"):
            assert puzzles.read_key(t.slave) == "up"


def test_P13_after_a_lone_esc_becomes_the_escape_key():
    with Pty(puzzles.make_raw) as t:
        t.press(b"\x1b")
        with deadline(
            2, "read_key waited forever -- a lone ESC needs a timer: VTIME or select"
        ):
            assert puzzles.read_key(t.slave) == "esc"


def test_P13_after_ordinary_text_needs_no_timer():
    with Pty(puzzles.make_raw) as t:
        t.press(b"ab")
        with deadline(2, "read_key never returned for plain text"):
            assert puzzles.read_key(t.slave) == b"a"
            assert puzzles.read_key(t.slave) == b"b"


# --- P14: the alternate screen --------------------------------------------------


def test_P14_before_the_kernel_forwards_what_it_does_not_understand():
    # DEC private modes mean nothing below the fd. The line discipline
    # forwards them like any other bytes; the opinions all live in the
    # emulator -- which is exactly why this rig can only assert on bytes.
    with Pty(puzzles.make_raw) as t:
        t.emit(b"\x1b[?1049h")
        assert t.screen() == b"\x1b[?1049h"


def test_P14_after_entering_switches_and_hides():
    with Pty(puzzles.make_raw) as t:
        with puzzles.alt_screen(t.slave):
            assert t.screen() == b"\x1b[?1049h\x1b[?25l"
        assert t.screen() == b"\x1b[?25h\x1b[?1049l"  # reverse order, cursor first


def test_P14_after_teardown_survives_a_crash():
    # Same contract as raw_mode at puzzle 7: the give-back happens even when
    # the body dies. A TUI that skips it leaves its user staring at the
    # alternate screen, scrollback apparently gone.
    class AppBlewUp(Exception):
        pass

    with Pty(puzzles.make_raw) as t:
        try:
            with puzzles.alt_screen(t.slave):
                t.screen()  # drain the entry bytes
                raise AppBlewUp("mid-frame")
        except AppBlewUp:
            pass
        assert t.screen() == b"\x1b[?25h\x1b[?1049l"


# --- P15: the prompt ------------------------------------------------------------


def test_P15_before_a_raw_tty_gives_you_nothing():
    # Every service the ladder switched off, absent at once: no echo, no
    # editing, no line, no meaning for ^C. What arrives is the raw material
    # puzzles 8-13 turned back into services; this puzzle is their assembly.
    with Pty(puzzles.make_raw) as t:
        t.press(b"ls -x\x7fl\r")
        assert t.screen() == b""
        assert t.delivered() == b"ls -x\x7fl\r"


def test_P15_after_it_reads_like_a_shell():
    # The keystrokes are pressed before prompt() runs: the kernel queues
    # them, and the single-threaded rig then lets your read loop drain the
    # queue at its own pace.
    with Pty(puzzles.make_raw) as t:
        t.press(b"ls -x\x7fl\r")
        with deadline(2, "prompt never returned -- does your loop end the line on \\r?"):
            line = puzzles.prompt(t.slave)
        assert line == b"ls -l\n"
        assert t.screen() == b"$ ls -x\x08 \x08l\r\n"


def test_P15_after_arrows_leave_no_trace():
    # The in-band problem, closed: without puzzle 12 the Up key would spray
    # [A into the line and onto the screen both.
    with Pty(puzzles.make_raw) as t:
        t.press(b"ls\x1b[A\x1b[D -l\r")
        with deadline(2, "prompt never returned -- is the decoder eating sequences?"):
            line = puzzles.prompt(t.slave)
        assert line == b"ls -l\n"
        assert t.screen() == b"$ ls -l\r\n"


def test_P15_after_ctrl_c_interrupts_because_you_built_it():
    # Nothing in the kernel makes this happen any more -- ISIG is off. The
    # KeyboardInterrupt is your editor's, and the tty coming back safe is
    # your raw_mode's finally.
    with Pty(puzzles.make_raw) as t:
        t.press(b"oops\x03")
        interrupted = False
        try:
            with deadline(2, "prompt swallowed the interrupt"):
                puzzles.prompt(t.slave)
        except KeyboardInterrupt:
            interrupted = True
        assert interrupted
        assert t.screen() == b"$ oops"  # echoed before the interrupt unwound


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
