# =========================================================================
#  BOOT SEQUENCE  —  INSTRUCTORS: PASTE STUDENT CODE HERE
#  Replace the contents of this function with the student's Module 4 code
#  (sections 1 and 2 only — the boot animation and personality prompt).
#  The main loop handles the conversation automatically.
#
#  Section 2 (the personality) is sent to the instructor's computer when the
#  Pi starts and becomes this Pi's personality in the editor.  Leave it empty
#  ("") to use whatever personality is set on the computer instead.
#
#  Helpers you can use:
#      set_led_func("on" | "off" | "blink" | "breathe")   button light
#      play_note_func("C", 0.5)    note name or minor chord ("Am"); "" = rest
#      turn_on_led_func("red" | "green" | "off")          external LEDs
#      say_func("Hello!")          speak out loud
# =========================================================================


def run_boot_sequence(set_led_func, play_note_func, turn_on_led_func, say_func):
    """Runs the startup animation and returns the bot personality prompt."""

    # 1. Boot Sequence Animation  (Futurama theme, simplified)
    set_led_func("blink")

    # Riff 1 — repeated notes, then a step down and back up
    turn_on_led_func("green")
    play_note_func("E", 0.15)
    play_note_func("E", 0.15)
    play_note_func("E", 0.15)
    play_note_func("E", 0.15)
    play_note_func("D", 0.15)
    play_note_func("E", 0.4)

    # Riff 2 — same pattern, higher
    turn_on_led_func("red")
    play_note_func("G", 0.15)
    play_note_func("G", 0.15)
    play_note_func("G", 0.15)
    play_note_func("G", 0.15)
    play_note_func("F#", 0.15)
    play_note_func("G", 0.4)

    # Riff 3 — higher again
    turn_on_led_func("green")
    play_note_func("A", 0.15)
    play_note_func("A", 0.15)
    play_note_func("A", 0.15)
    play_note_func("A", 0.15)
    play_note_func("G", 0.15)
    play_note_func("A", 0.4)

    # Run back down to finish
    turn_on_led_func("red")
    play_note_func("B", 0.2)
    play_note_func("A", 0.2)
    play_note_func("G", 0.2)
    play_note_func("F#", 0.2)
    play_note_func("E", 0.6)

    turn_on_led_func("off")
    set_led_func("on")

    # 2. Personality System Prompt Definition
    #    Leave empty to use the personality set on the computer.
    personality_prompt = """
    """


# =========================================================================
# REPLACE THE CODE ABOVE, BE CAREFUL OF THE TAB AT THE BEGINNING
# =========================================================================

    say_func("All systems online.")
    turn_on_led_func("green")

    return personality_prompt
