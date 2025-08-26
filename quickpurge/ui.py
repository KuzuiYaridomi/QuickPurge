# quickpurge/ui.py
import os
import threading
import queue
import time
import PySimpleGUI as sg
import logging, traceback
from quickpurge import thumbnail


from quickpurge import database
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")


from .scanner import scan_folder, scan_entire_system
from .database import (
    get_all_duplicates,
    get_exclusions,
    add_exclusion,
    remove_exclusion,
    get_scan_history,
    clear_db,
    safe_get_all_duplicates,
)
from .safe_delete import safe_delete, permanent_delete, ARCHIVE_DIR, ensure_archive_folder
    


# =========================
# THEME
# =========================
sg.theme("DarkGrey14")
sg.set_options(font=("Segoe UI", 11), input_elements_background_color="#1b1b1b")

ACCENT_RED = "#e11d2e"
PANEL_BG = "#1a1a1a"
TEXT_DIM = "#c7c7c7"

TABLE_HEADERS = ["✔", "Name", "Size (bytes)", "Modified", "Path"]
# checkbox symbols (consistent text-friendly)
UNCHECK = "[ ]"
CHECK = "[✔]"


# ============== Helpers ==============


def popup_get_folders(parent=None):
    """
    Let the user add multiple folders using a small modal:
    - Click 'Add Folder' to pick one folder at a time (filedialog).
    - 'Remove Selected' removes from the list.
    - 'Done' returns the list; 'Cancel' returns [].
    """
    import tkinter as tk
    from tkinter import filedialog

    layout = [
        [sg.Text("Selected folders (added in order):")],
        [sg.Listbox(values=[], size=(60, 6), key="-FOLDERS-", enable_events=False)],
        [sg.Button("Add Folder"), sg.Button("Remove Selected"), sg.Push(), sg.Button("Done"), sg.Button("Cancel")]
    ]
    win = sg.Window("Select folders to scan", layout, modal=True, finalize=True)
    folders = []
    while True:
        ev, vals = win.read()
        if ev in (sg.WIN_CLOSED, "Cancel"):
            folders = []
            break
        if ev == "Add Folder":
            # Use Tk's folder dialog so look/feel is native
            root = tk.Tk()
            root.withdraw()
            path = filedialog.askdirectory(title="Select a folder")
            root.destroy()
            if path and path not in folders:
                folders.append(path)
                win["-FOLDERS-"].update(values=folders)
        elif ev == "Remove Selected":
            sel = vals.get("-FOLDERS-", [])
            if sel:
                for s in sel:
                    if s in folders:
                        folders.remove(s)
                win["-FOLDERS-"].update(values=folders)
        elif ev == "Done":
            break
    win.close()
    return folders



def _format_duplicates_rows(rows):
    table = []
    SEP = "\x1f"  # unit separator — used by DB GROUP_CONCAT
    for row in rows:
        try:
            if not row:
                continue
            # normalize: take last two fields as (joined_paths, size)
            if len(row) >= 2:
                joined_paths = row[-2]
                size = row[-1]
            else:
                continue
            if not joined_paths:
                continue

            # split on SEP, not comma
            paths = str(joined_paths).split(SEP)
            for p in paths:
                p = p.strip()
                if not p:
                    continue
                try:
                    stat = os.stat(p)
                    mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
                except Exception:
                    mtime_str = "-"
                name = os.path.basename(p)
                table.append([UNCHECK, name, size, mtime_str, p])
        except Exception:
            logging.exception("Error formatting DB row %r", row)
            continue
    return table





def _list_archive_files():
    files = []
    if os.path.isdir(ARCHIVE_DIR):
        for f in os.listdir(ARCHIVE_DIR):
            full = os.path.join(ARCHIVE_DIR, f)
            if os.path.isfile(full) and not f.endswith(".meta.json"):
                try:
                    files.append((f, os.path.getsize(full), full))
                except Exception:
                    files.append((f, 0, full))
    return files


def _restore_from_meta(full_archive_path):
    import json, shutil

    meta = full_archive_path + ".meta.json"
    if not os.path.exists(meta):
        return False, "No metadata to restore original path."
    try:
        with open(meta, "r", encoding="utf-8") as f:
            data = json.load(f)
        orig = data.get("original_path")
        if not orig:
            return False, "Missing original path in metadata."
        os.makedirs(os.path.dirname(orig), exist_ok=True)
        shutil.move(full_archive_path, orig)
        try:
            os.remove(meta)
        except Exception:
            pass
        return True, f"Restored to {orig}"
    except Exception as e:
        return False, str(e)


def refresh_duplicates(window, scan_id):
    """
    Update duplicates table for a given scan_id.
    If scan_id is falsy, don't query the DB — just clear the UI.
    """
    if not scan_id:
        # Don't call DB when no scan_id is available
        window["-DUP_COUNT-"].update("No scan yet")
        window["-TABLE-"].update(values=[])
        window["-DELETE-"].update(disabled=True)
        # SELECT_ALL should be disabled until we have rows
        if "-SELECT_ALL-" in window.AllKeysDict:
            window["-SELECT_ALL-"].update(disabled=True)
        return

    # when we have a valid scan_id, query the DB and render rows
    rows = safe_get_all_duplicates(scan_id)  # keep your DB function name (or safe_get_all_duplicates)
    table = _format_duplicates_rows(rows)
    window["-TABLE-"].update(values=table)
    window["-DUP_COUNT-"].update(f"{len(table)} duplicate files found")
    window["-DELETE-"].update(disabled=(len(table) == 0))
    if "-SELECT_ALL-" in window.AllKeysDict:
        window["-SELECT_ALL-"].update(disabled=(len(table) == 0))



# ============== Exclusion Rules ==============


def open_exclusion_rules(parent):
    current = get_exclusions()
    layout = [
        [
            sg.Text(
                "Exclude Folders from Scans",
                font=("Segoe UI Semibold", 13),
                background_color=PANEL_BG,
            )
        ],
        [
            sg.Listbox(
                values=current,
                size=(65, 12),
                key="-RULE_LIST-",
                background_color=PANEL_BG,
                text_color="white",
            )
        ],
        [
            sg.Input(
                key="-NEW_RULE-", expand_x=True, disabled=True, background_color=PANEL_BG
            ),
            sg.FolderBrowse(
                "Pick Folder", target="-NEW_RULE-", button_color=("white", ACCENT_RED)
            ),
            sg.Button("Add", button_color=("white", ACCENT_RED)),
        ],
        [
            sg.Button("Remove Selected", button_color=("white", ACCENT_RED)),
            sg.Push(),
            sg.Button("Close"),
        ],
    ]
    win = sg.Window(
        "Exclusion Rules",
        layout,
        modal=True,
        resizable=True,
        finalize=True,
        background_color=PANEL_BG,
    )
    while True:
        ev, vals = win.read()
        if ev in (sg.WIN_CLOSED, "Close"):
            break
        elif ev == "Add":
            path = (vals.get("-NEW_RULE-") or "").strip()
            if path:
                try:
                    add_exclusion(path)
                except Exception as e:
                    sg.popup_error(f"Could not add exclusion:\n{e}")
                win["-RULE_LIST-"].update(values=get_exclusions())
                win["-NEW_RULE-"].update("")
        elif ev == "Remove Selected":
            selected = vals.get("-RULE_LIST-", [])
            for rule in selected:
                try:
                    remove_exclusion(rule)
                except Exception:
                    pass
            win["-RULE_LIST-"].update(values=get_exclusions())
    win.close()
    try:
      parent.bring_to_front()
    except Exception:
        pass


# ============== Archive ==============


def open_archive(parent):
    ensure_archive_folder()

    def refresh(tbl):
        files = _list_archive_files()
        tbl.update(values=[(f, sz, p) for f, sz, p in files])

    headings = ["File", "Size", "Full Path"]
    layout = [
        [sg.Text("Archive", font=("Segoe UI Semibold", 13), background_color=PANEL_BG)],
        [
            sg.Table(
                values=[],
                headings=headings,
                key="-ARCHIVE_TABLE-",
                expand_x=True,
                expand_y=True,
                justification="left",
                background_color=PANEL_BG,
                text_color="white",
                select_mode=sg.TABLE_SELECT_MODE_EXTENDED,
            )
        ],
        [
            sg.Button("Open Folder", button_color=("white", ACCENT_RED)),
            sg.Button("Restore Selected", button_color=("white", ACCENT_RED)),
            sg.Button("Restore All", button_color=("white", ACCENT_RED)),
            sg.Button(
                "Permanently Delete Selected", button_color=("white", ACCENT_RED)
            ),
            sg.Button("Delete All", button_color=("white", ACCENT_RED)),
            sg.Push(),
            sg.Button("Close"),
        ],
    ]
    win = sg.Window(
        "QuickPurge Archive",
        layout,
        modal=True,
        resizable=True,
        finalize=True,
        size=(1000, 500),
        background_color=PANEL_BG,
    )
    refresh(win["-ARCHIVE_TABLE-"])
    while True:
        ev, vals = win.read()
        if ev in (sg.WIN_CLOSED, "Close"):
            break
        elif ev == "Open Folder":
            ensure_archive_folder()
            try:
                os.startfile(ARCHIVE_DIR)
            except Exception:
                sg.popup_error(f"Could not open: {ARCHIVE_DIR}")
        elif ev in ("Permanently Delete Selected", "Restore Selected"):
            rows = vals.get("-ARCHIVE_TABLE-", [])
            if not rows:
                continue
            data = win["-ARCHIVE_TABLE-"].get()
            for idx in rows:
                _, _, full = data[idx]
                if ev == "Permanently Delete Selected":
                    try:
                        permanent_delete(full)
                        meta = full + ".meta.json"
                        if os.path.exists(meta):
                            os.remove(meta)
                    except Exception as e:
                        sg.popup_error(f"Delete failed for {full}:\n{e}")
                else:
                    ok, msg = _restore_from_meta(full)
                    if not ok:
                        sg.popup_error(
                            f"Restore failed for {os.path.basename(full)}:\n{msg}"
                        )
            refresh(win["-ARCHIVE_TABLE-"])
        elif ev == "Delete All":
            data = win["-ARCHIVE_TABLE-"].get()
            if data and sg.popup_ok_cancel(
                "Permanently delete ALL archived files?"
            ) == "OK":
                for _, _, full in data:
                    try:
                        permanent_delete(full)
                        meta = full + ".meta.json"
                        if os.path.exists(meta):
                            os.remove(meta)
                    except Exception:
                        pass
                refresh(win["-ARCHIVE_TABLE-"])
        elif ev == "Restore All":
            data = win["-ARCHIVE_TABLE-"].get()
            for _, _, full in data:
                _restore_from_meta(full)
            refresh(win["-ARCHIVE_TABLE-"])
    win.close()
    parent.bring_to_front()


# ============== Progress Window ==============


def _make_progress_window():
    canvas_size = (220, 220)
    layout = [
        [
            sg.Text(
                "Scanning...",
                font=("Segoe UI Semibold", 16),
                text_color="white",
                background_color=PANEL_BG,
            )
        ],
        [sg.Canvas(size=canvas_size, key="-CANVAS-", background_color=PANEL_BG)],
        [
            sg.Text(
                "Preparing...",
                key="-SUBTITLE-",
                size=(50, 1),
                text_color=TEXT_DIM,
                background_color=PANEL_BG,
            )
        ],
        [sg.ProgressBar(100, orientation="h", size=(40, 20), key="-PB-")],
        [
            sg.Button("Cancel Scan", key="-CANCEL-", button_color=("white", ACCENT_RED)),
            sg.Push(),
            sg.Button("Hide"),
        ],
    ]
    win = sg.Window(
        "QuickPurge Monitor",
        layout,
        finalize=True,
        modal=False,
        element_justification="center",
        keep_on_top=True,
        background_color=PANEL_BG,
        alpha_channel=0.95,  # translucent
    )
    canvas = win["-CANVAS-"].TKCanvas

    import tkinter as tk

    size = 200
    x0, y0 = 10, 10
    x1, y1 = x0 + size, y0 + size
    canvas.create_oval(x0, y0, x1, y1, outline="#333333", width=6)
    arc = canvas.create_arc(
        x0,
        y0,
        x1,
        y1,
        start=90,
        extent=0,
        style=tk.ARC,
        outline=ACCENT_RED,
        width=6,
    )
    return win, canvas, arc


def _update_circle(canvas, arc_id, percent):
    extent = -360 * max(0, min(1, percent))
    canvas.itemconfig(arc_id, extent=extent)


# ============== Duplicate History ==============


def open_history(parent):
    rows = get_scan_history(limit=50)
    layout = [
        [
            sg.Text(
                "Duplicate Files History",
                font=("Segoe UI Semibold", 13),
                background_color=PANEL_BG,
            )
        ],
        [
            sg.Table(
                values=[
                    (r[0], time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r[1])))
                    for r in rows
                ],
                headings=["Scan ID", "Timestamp"],
                key="-HIST_TABLE-",
                expand_x=True,
                expand_y=True,
                justification="left",
                background_color=PANEL_BG,
                text_color="white",
            )
        ],
        [sg.Button("Close")],
    ]
    win = sg.Window(
        "Scan History",
        layout,
        modal=True,
        finalize=True,
        size=(600, 400),
        background_color=PANEL_BG,
        alpha_channel=0.95,
    )
    while True:
        ev, _ = win.read()
        if ev in (sg.WIN_CLOSED, "Close"):
            break
    win.close()
    parent.bring_to_front()


# ============== Main ==============


def run():
    from typing import Optional
    current_scan_id: Optional[int] = None
    progress_q = queue.Queue()
    cancel_flag = {"cancel": False}

    header_row = [
        sg.Text(
            "QuickPurge — Duplicate Finder",
            font=("Segoe UI Semibold", 18),
            text_color="white",
            background_color=PANEL_BG,
        )
    ]

    action_row = [
        sg.Button("Select Folders", key="-SELECT_FOLDER-", button_color=("white", ACCENT_RED)),
        sg.Button("Scan Entire System", key="-SCAN_ALL-", button_color=("white", ACCENT_RED)),
        sg.Text(
            "0 duplicate files found",
            key="-DUP_COUNT-",
            text_color=TEXT_DIM,
            background_color=PANEL_BG,
        ),
    ]

    table = sg.Table(
        values=[],
        headings=TABLE_HEADERS,
        key="-TABLE-",
        auto_size_columns=False,
        col_widths=[4, 26, 12, 19, 60],
        justification="left",
        num_rows=18,
        expand_x=True,
        expand_y=True,
        background_color=PANEL_BG,
        text_color="white",
        alternating_row_color="#151515",
        select_mode=sg.TABLE_SELECT_MODE_EXTENDED,
        enable_events=True,
    )

    bottom_row = [
        sg.Button("Select All", key="-SELECT_ALL-", button_color=("white", ACCENT_RED), disabled=True),
        sg.Button("Deselect All", key="-DESELECT_ALL-", button_color=("white", ACCENT_RED), disabled=True),
        sg.Button("Delete Selected", key="-DELETE-", button_color=("white", ACCENT_RED), disabled=True),
    ]

    sidebar = [
        [sg.Button("Duplicate Files", key="-MENU_DUP-", size=(20, 1))],
        [sg.Button("Exclusion Rules", key="-MENU_RULES-", size=(20, 1))],
        [sg.Button("Archive", key="-MENU_ARCHIVE-", size=(20, 1))],
        [sg.Button("History", key="-MENU_HISTORY-", size=(20, 1))],
        [sg.Button("Help", key="-MENU_HELP-", size=(20, 1))],
    ]

    layout = [
        [
            sg.Column(
                sidebar,
                vertical_alignment="top",
                background_color=PANEL_BG,
                pad=((0, 10), (0, 0)),
            ),
            sg.VSeparator(),
            sg.Column(
                [header_row, action_row, [table], bottom_row],
                expand_x=True,
                expand_y=True,
                background_color=PANEL_BG,
                pad=(0, 0),
            ),
        ]
    ]

    window = sg.Window(
        "QuickPurge",
        layout,
        finalize=True,
        resizable=True,
        background_color=PANEL_BG,
        alpha_channel=0.95,  # translucent
        icon=thumbnail.get_app_icon(),
    )
    progress_win = None
    progress_canvas = None
    progress_arc = None

    def on_progress(info: dict):
        progress_q.put(info)

    def run_scan(folder: str = None, full: bool = False):
        nonlocal current_scan_id
        cancel_flag["cancel"] = False

        # tell the main thread to clear/reset the UI before scanning
        progress_q.put({"stage": "reset_ui"})

        try:
          if full:
            current_scan_id = scan_entire_system(
                on_progress=on_progress, cancel_flag=cancel_flag
            )
          else:
            current_scan_id = scan_folder(
                folder, on_progress=on_progress, cancel_flag=cancel_flag
            )
        except Exception as e:
          progress_q.put({"stage": "error", "message": str(e)})
        # NOTE: NO LOCAL DONE.


    REFRESH_MS = 120
    while True:
        event, values = window.read(timeout=REFRESH_MS)
        if event in (sg.WIN_CLOSED, "Exit"):
            break

        if event == "-SELECT_FOLDER-":
            folders = popup_get_folders()
            if not folders:
                continue
            
            # --- PROTECTED FOLDER CHECK ---- 
            from .exclusion_rules import should_exclude
            bad = [f for f in folders if should_exclude(f)]
            if bad:
                ok = sg.popup_yes_no(
                    "You selected one or more protected/system folders:\n\n"
                    + "\n".join(bad[:6])
                    + ("\n\n...and more" if len(bad) > 6 else "")
                    + "\n\nScanning or deleting files in system/program folders is risky.\nContinue?",
                    title="Warning - Protected folders",
                    keep_on_top=True,   
                )
                if ok != "Yes":
                    continue

            # --- END PROTECTED FOLDER CHECK ---

            if progress_win is None:
                progress_win, progress_canvas, progress_arc = _make_progress_window()
            progress_win.bring_to_front()
            threading.Thread(target=run_scan, args=(folders, False), daemon=True).start()

        elif event == "-SCAN_ALL-":
            ok = sg.popup_yes_no(
                "Warning: Scanning your entire system may include system and program files.\n"
                "Deleting duplicates from these locations can cause Windows or applications to stop working.\n"
                "We recommend only scanning personal folders (Documents, Downloads, Pictures, Videos, Music).\n\n"
                "Do you want to continue?",
                title="Scan Entire Sytem",
                keep_on_top=True,
            )
            if ok != "Yes":
                continue

            if progress_win is None:
                progress_win, progress_canvas, progress_Arc = _make_progress_window()
            progress_win.bring_to_front()
            threading.Thread(target=run_scan, kwargs={"full": True}, daemon=True).start()
            
                
        elif event == "-MENU_RULES-":
            open_exclusion_rules(window)
        elif event == "-MENU_ARCHIVE-":
            open_archive(window)
        elif event == "-MENU_HELP-":
            sg.popup_scrolled(
                "QuickPurge Help",
                "• Select a folder or use 'Scan Entire System' to start.\n"
                "• Duplicates appear live in the table as they’re found.\n"
                "• 'Delete Selected' moves checked files into the Archive.\n"
                "• Use 'Archive' to permanently delete or restore.\n"
                "• Use 'Exclusion Rules' to skip folders or paths.\n"
                "• Use 'History' to see past scans.\n\n"
                "— Built by Muzammil Pasha aka Kuzui Yaridomi —",
                title="Help",
                size=(70, 20),
            )
            window.bring_to_front()
        elif event == "-MENU_DUP-":
            refresh_duplicates(window, current_scan_id)
        elif event == "-MENU_HISTORY-":
            open_history(window)


        # Table click → toggle checkbox
        if event == "-TABLE-":
            selected = values.get("-TABLE-", [])
            if selected:
                data = window["-TABLE-"].get()
                for i in selected:
                    row = data[i]
                    row[0] = CHECK if row[0] == UNCHECK else UNCHECK
                window["-TABLE-"].update(values=data)

                # Enable/disable select/deselect depending on content
                checked = any(r[0] == CHECK for r in data)
                window["-DELETE-"].update(disabled=not checked)
                window["-SELECT_ALL-"].update(disabled=(len(data) == 0))
                window["-DESELECT_ALL-"].update(disabled=(not checked))
        
        # Select All (toggle behavior): if all checked -> deselect all, else select all
        elif event == "-SELECT_ALL-":
            data = window["-TABLE-"].get()
            if not data:
                continue
                # if every row already checked -> uncheck all (toggle)
            if all(row[0] == CHECK for row in data):
                new_data = [[UNCHECK] + row[1:] for row in data]
            else:
                new_data = [[CHECK] + row[1:] for row in data]
            window["-TABLE-"].update(values=new_data)
            checked = any(r[0] == CHECK for r in new_data)
            window["-DELETE-"].update(disabled=not checked)
            window["-DESELECT_ALL-"].update(disabled=(not checked))

        # Deselect All explicit button
        elif event == "-DESELECT_ALL-":
            data = window["-TABLE-"].get()
            if not data:
                continue
            new_data = [[UNCHECK] + row[1:] for row in data]
            window["-TABLE-"].update(values=new_data)
            window["-DELETE-"].update(disabled=True)
            window["-DESELECT_ALL-"].update(disabled=True)
            window["-SELECT_ALL-"].update(disabled=(len(new_data) == 0))

        # Delete Selected (archive checked rows)
        elif event == "-DELETE-":
            data = window["-TABLE-"].get()
            to_delete = [row[-1] for row in data if row[0] == CHECK]
            if to_delete:
                for path in to_delete:
                    try:
                        safe_delete(path)
                        database.remove_duplicate_by_path(current_scan_id, path)
                    except Exception as e:
                        sg.popup_error(f"Failed to archive {path}:\n{e}")
                sg.popup("Checked files moved to archive.")
                refresh_duplicates(window, current_scan_id)
            # after delete, disable delete / deselect if nothing left
            window["-DELETE-"].update(disabled=True)
            window["-DESELECT_ALL-"].update(disabled=True)
            window["-SELECT_ALL-"].update(disabled=False)
         

        # progress window events (non-blocking)
        if progress_win is not None:
            ev2, _ = progress_win.read(timeout=0)
            if ev2 == "-CANCEL-":
                cancel_flag["cancel"] = True
            elif ev2 == "Hide":
                progress_win.hide()

        # Drain progress queue and update UI elements
        while True:
            try:
                info = progress_q.get_nowait()
            except queue.Empty:
                break

            stage = info.get("stage")

            if stage == "reset_ui":
              window["-TABLE-"].update(values=[])
              window["-DUP_COUNT-"].update("Scanning...")
              window["-DELETE-"].update(disabled=True)
              window["-SELECT_ALL-"].update(disabled=True)
              window["-DESELECT_ALL-"].update(disabled=True)

            elif stage == "error":
                sg.popup_error(f"Scan failed: {info.get('message')}")
                continue

            elif stage == "done":
                      # final refresh of duplicates table
                if current_scan_id:
                    try:
                      refresh_duplicates(window, current_scan_id)
                    except Exception as e:
                      print("final refresh failed:", e)

                # close progress window
                if progress_win is not None:
                    sg.popup_no_titlebar(
                        "Scan completed.", keep_on_top=True, auto_close=True, auto_close_duration=2
                    )
                    try:
                        progress_win.close()
                    except Exception:
                        pass
                    progress_win = progress_canvas = progress_arc = None

                # refresh history list
                try:
                    _ = get_scan_history(limit=50)
                except Exception as e:
                    print("Couldnt refresh history:", e)



                 
                       
                    

            # refresh history tab after scan
            try:
                rows = get_scan_history(limit=50)
            except Exception as e:
                print("Couldn't refresh history:", e)

            # Read progress numbers (fallback defaults)
            total = max(1, int(info.get("total_files", 1)))
            done = int(info.get("files_scanned", 0))
            pct = done / total if total else 0.0

            # update progress visuals
            if progress_win is not None and progress_arc:
                try:
                    _update_circle(progress_canvas, progress_arc, pct)
                    progress_win["-PB-"].update_bar(int(pct * 100))
                except Exception:
                    pass

                sub = info.get("path") or ""
                if sub:
                    try:
                        progress_win["-SUBTITLE-"].update(f"Scanning: {sub[:80]}")
                    except Exception:
                        pass

            # live-refresh duplicates table if we have a scan id
            if current_scan_id:
                try:
                    refresh_duplicates(window, current_scan_id)
                except Exception as e:
                    try:
                        from .utils import log
                        log(f"refresh_duplicates error: {e}")
                    except Exception:
                        print("refresh_duplicates error:", e)


    # End main event loop; close window
    window.close()


if __name__ == "__main__":
    run()







