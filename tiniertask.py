import tkinter as tk
from tkinter import messagebox, filedialog
import time
import threading
import subprocess

# We'll use pynput for recording/playing macros
from pynput import mouse, keyboard
from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Controller as KeyboardController, Key

# ---------- Global Variables ----------
recording_events = []
is_recording = False
start_time = 0.0

playback_speed = 1.0      # default 1x
playback_repeats = 1      # default 1 time
use_hotkey = False        # whether to enable a global F8 hotkey

mouse_listener = None
keyboard_listener = None

mouse_controller = MouseController()
keyboard_controller = KeyboardController()

root = None
btn_rec = None

# ---------- FUNCTIONS FOR DRAWING COLORED ICONS ----------
def create_solid_icon(hex_color="#FF0000"):
    """
    Creates a small 16x16 solid-colored PhotoImage.
    No base64 or external image file needed—avoids CRC/ASCII issues.
    """
    icon = tk.PhotoImage(width=16, height=16)
    for x in range(16):
        for y in range(16):
            icon.put(hex_color, (x, y))
    return icon

# ---------- Recording Callbacks ----------
def on_mouse_move(x, y):
    if is_recording:
        now = time.time() - start_time
        recording_events.append(('mmove', x, y, now))

def on_mouse_click(x, y, button, pressed):
    if is_recording:
        now = time.time() - start_time
        recording_events.append(('mclick', x, y, button.name, pressed, now))

def on_keyboard_press(key):
    if is_recording:
        now = time.time() - start_time
        try:
            recording_events.append(('kdown', key.char, now))
        except AttributeError:
            recording_events.append(('kdown', str(key), now))

def on_keyboard_release(key):
    if is_recording:
        now = time.time() - start_time
        try:
            recording_events.append(('kup', key.char, now))
        except AttributeError:
            recording_events.append(('kup', str(key), now))

# ---------- Start / Stop Recording ----------
def start_recording():
    global is_recording, recording_events, start_time
    global mouse_listener, keyboard_listener

    if is_recording:
        return  # already recording

    recording_events.clear()
    is_recording = True
    start_time = time.time()

    # Create new listeners
    mouse_listener = mouse.Listener(on_move=on_mouse_move,
                                    on_click=on_mouse_click)
    keyboard_listener = keyboard.Listener(on_press=on_keyboard_press,
                                          on_release=on_keyboard_release)
    mouse_listener.start()
    keyboard_listener.start()

def stop_recording():
    global is_recording, mouse_listener, keyboard_listener
    if not is_recording:
        return
    is_recording = False

    if mouse_listener and mouse_listener.running:
        mouse_listener.stop()
    if keyboard_listener and keyboard_listener.running:
        keyboard_listener.stop()

    mouse_listener = None
    keyboard_listener = None

def toggle_recording():
    global is_recording
    if not is_recording:
        start_recording()
        btn_rec.config(text="Stop", image=stop_icon)
    else:
        stop_recording()
        btn_rec.config(text="Rec", image=rec_icon)

# ---------- Playback Logic ----------
def play_recording():
    if is_recording:
        messagebox.showwarning("Error", "Cannot play while recording!")
        return
    if not recording_events:
        messagebox.showwarning("No Macro", "No recorded events to play.")
        return

    # Play in a separate thread so UI doesn't freeze
    th = threading.Thread(target=_play_thread)
    th.daemon = True
    th.start()

def _play_thread():
    global playback_speed, playback_repeats

    for _ in range(playback_repeats):
        for i in range(len(recording_events) - 1):
            event = recording_events[i]
            next_event = recording_events[i + 1]
            current_time = event[-1]
            next_time = next_event[-1]
            delay = (next_time - current_time) / playback_speed
            if delay > 0:
                time.sleep(delay)
            replay_event(event)

        # Replay the last event
        replay_event(recording_events[-1])

def replay_event(event):
    etype = event[0]
    if etype == 'mmove':
        _, x, y, _ = event
        mouse_controller.position = (x, y)

    elif etype == 'mclick':
        _, x, y, button_name, pressed, _ = event
        mouse_controller.position = (x, y)
        btn = Button.left if button_name == 'left' else Button.right
        if pressed:
            mouse_controller.press(btn)
        else:
            mouse_controller.release(btn)

    elif etype == 'kdown':
        _, keyval, _ = event
        press_key(keyval, press=True)

    elif etype == 'kup':
        _, keyval, _ = event
        press_key(keyval, press=False)

def press_key(keyval, press=True):
    from pynput.keyboard import Controller as KbController, Key
    kb = KbController()
    if len(keyval) == 1:
        # single character
        if press:
            kb.press(keyval)
        else:
            kb.release(keyval)
    else:
        # possibly 'Key.enter', 'Key.space', etc.
        try:
            key_obj = getattr(Key, keyval.replace("Key.", ""))
            if press:
                kb.press(key_obj)
            else:
                kb.release(key_obj)
        except AttributeError:
            pass

# ---------- Open / Save Macros ----------
def open_macro():
    global recording_events
    filename = filedialog.askopenfilename(
        title="Open Macro",
        filetypes=[("Macro Files", "*.macro"), ("All Files", "*.*")]
    )
    if not filename:
        return

    try:
        new_events = []
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # parse each line as a tuple
            tup = tuple(eval(p) for p in line.split(','))
            new_events.append(tup)
        recording_events = new_events
        messagebox.showinfo("Macro Loaded", f"Loaded {len(new_events)} events.")
    except Exception as e:
        messagebox.showerror("Error", f"Could not open macro: {e}")

def save_macro():
    if not recording_events:
        messagebox.showwarning("No Macro", "No recorded events to save.")
        return

    filename = filedialog.asksaveasfilename(
        defaultextension=".macro",
        filetypes=[("Macro Files", "*.macro"), ("All Files", "*.*")]
    )
    if not filename:
        return
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            for evt in recording_events:
                line = ",".join(repr(e) for e in evt)
                f.write(line + "\n")
        messagebox.showinfo("Saved", f"Macro saved to {filename}")
    except Exception as e:
        messagebox.showerror("Error", f"Could not save macro: {e}")

# ---------- Build .exe ----------
def build_exe():
    ans = messagebox.askyesno(
        "Build .exe",
        "This will run PyInstaller (must be installed) and create an .exe.\nContinue?"
    )
    if not ans:
        return
    try:
        subprocess.run(["pyinstaller", "--onefile", "--noconsole", __file__], check=True)
        messagebox.showinfo("Build Complete", "Check the 'dist' folder for your new .exe")
    except subprocess.CalledProcessError as e:
        messagebox.showerror("Error", f"PyInstaller failed:\n{e}")

# ---------- Preferences ----------
def show_prefs():
    pref_win = tk.Toplevel(root)
    pref_win.title("Preferences")
    pref_win.resizable(False, False)

    tk.Label(pref_win, text="Playback Speed (1.0 = normal):").grid(row=0, column=0, padx=5, pady=5, sticky="e")
    speed_entry = tk.Entry(pref_win, width=10)
    speed_entry.insert(0, str(playback_speed))
    speed_entry.grid(row=0, column=1, padx=5, pady=5)

    tk.Label(pref_win, text="Repeat Count:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
    repeat_entry = tk.Entry(pref_win, width=10)
    repeat_entry.insert(0, str(playback_repeats))
    repeat_entry.grid(row=1, column=1, padx=5, pady=5)

    hotkey_var = tk.BooleanVar(value=use_hotkey)
    hotkey_check = tk.Checkbutton(pref_win, text="Enable F8 for Start/Stop", variable=hotkey_var)
    hotkey_check.grid(row=2, column=0, columnspan=2, padx=5, pady=5)

    def save_prefs():
        global playback_speed, playback_repeats, use_hotkey
        try:
            ps = float(speed_entry.get())
            rp = int(repeat_entry.get())
            if ps <= 0 or rp <= 0:
                raise ValueError
            playback_speed = ps
            playback_repeats = rp

            old_hotkey = use_hotkey
            use_hotkey = hotkey_var.get()
            if use_hotkey != old_hotkey:
                if use_hotkey:
                    register_global_hotkey()
                else:
                    unregister_global_hotkey()

            messagebox.showinfo("Saved", "Preferences updated.")
            pref_win.destroy()
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numeric values.")

    tk.Button(pref_win, text="OK", command=save_prefs).grid(row=3, column=0, columnspan=2, pady=5)

# ---------- Optional Global Hotkey (F8) ----------
def register_global_hotkey():
    def on_hotkey_press(key):
        if key == Key.f8:
            root.after(0, toggle_recording)

    global global_hotkey_listener
    global_hotkey_listener = keyboard.Listener(on_press=on_hotkey_press)
    global_hotkey_listener.start()

def unregister_global_hotkey():
    global global_hotkey_listener
    if 'global_hotkey_listener' in globals() and global_hotkey_listener is not None:
        global_hotkey_listener.stop()
        global_hotkey_listener = None

# ---------- Main GUI ----------
def main():
    global root, btn_rec
    global rec_icon, stop_icon

    root = tk.Tk()
    root.title("Replica")
    root.resizable(False, False)

    # Create color icons with different background colors
    open_icon  = create_solid_icon("#008000")  # green
    save_icon  = create_solid_icon("#000080")  # navy
    rec_icon_  = create_solid_icon("#FF0000")  # bright red
    stop_icon_ = create_solid_icon("#800000")  # maroon
    play_icon  = create_solid_icon("#008080")  # teal
    exe_icon   = create_solid_icon("#800080")  # purple
    prefs_icon = create_solid_icon("#808000")  # olive

    # Keep references so we can toggle them
    rec_icon  = rec_icon_
    stop_icon = stop_icon_

    toolbar = tk.Frame(root, padx=5, pady=5)
    toolbar.pack()

    # Buttons with placeholders + text
    btn_open = tk.Button(toolbar, image=open_icon, text="Open", compound="top", command=open_macro, bd=1)
    btn_open.image = open_icon
    btn_open.grid(row=0, column=0, padx=2)

    btn_save = tk.Button(toolbar, image=save_icon, text="Save", compound="top", command=save_macro, bd=1)
    btn_save.image = save_icon
    btn_save.grid(row=0, column=1, padx=2)

    btn_rec_ = tk.Button(toolbar, image=rec_icon, text="Rec", compound="top", command=toggle_recording, bd=1)
    btn_rec_.image = rec_icon
    btn_rec_.grid(row=0, column=2, padx=2)
    btn_rec = btn_rec_

    btn_play = tk.Button(toolbar, image=play_icon, text="Play", compound="top", command=play_recording, bd=1)
    btn_play.image = play_icon
    btn_play.grid(row=0, column=3, padx=2)

    btn_exe = tk.Button(toolbar, image=exe_icon, text=".exe", compound="top", command=build_exe, bd=1)
    btn_exe.image = exe_icon
    btn_exe.grid(row=0, column=4, padx=2)

    btn_prefs = tk.Button(toolbar, image=prefs_icon, text="Prefs", compound="top", command=show_prefs, bd=1)
    btn_prefs.image = prefs_icon
    btn_prefs.grid(row=0, column=5, padx=2)

    root.mainloop()

if __name__ == "__main__":
    main()

