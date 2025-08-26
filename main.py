# main.py
import os
import time
import logging
import sqlite3
import PySimpleGUI as sg
from quickpurge.exclusion_rules import should_exclude

# Import your package modules
from quickpurge import database, utils, ui, thumbnail   # ✅ added thumbnail
from quickpurge.safe_delete import ensure_archive_folder
from quickpurge.database import DB_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def show_loading_screen():
    sg.theme("DarkGrey14")

    layout = [
        [
            sg.Push(background_color="gray"),
            sg.Text(
                "QUICK",
                font=("Helvetica", 38, "bold"),
                text_color="black",
                background_color="gray",
                key="-TITLE1-",
            ),
            sg.Text(
                "PURGE",
                font=("Helvetica", 38, "bold"),
                text_color="red",
                background_color="gray",
                key="-TITLE2-",
            ),
            sg.Push(background_color="gray"),
        ],
        [
            sg.Push(background_color="gray"),
            sg.ProgressBar(100, orientation="h", size=(40, 20), key="-PROGRESS-", bar_color=("red", "black")),
            sg.Push(background_color="gray"),
        ],
    ]

    window = sg.Window(
        "QuickPurge Loading",
        layout,
        finalize=True,
        element_justification="center",
        background_color="gray",
        no_titlebar=True,
        size=(600, 220),
        icon=thumbnail.get_app_icon(),   # ✅ added icon here
    )

    progress_bar = window["-PROGRESS-"]
    total_duration = 3.0  # seconds total for loading (shorter)
    fade_duration = 0.8
    start_time = time.time()

    while True:
        now = time.time()
        elapsed = now - start_time
        if elapsed > total_duration:
            elapsed = total_duration

        progress = int((elapsed / total_duration) * 100)
        progress_bar.UpdateBar(progress)

        # optional fade
        fade_start = total_duration - fade_duration
        if elapsed >= fade_start:
            fade_progress = (elapsed - fade_start) / fade_duration
            alpha = max(0.0, min(1.0, fade_progress))
            try:
                window.TKroot.attributes("-alpha", alpha)
            except Exception:
                pass

        event, _ = window.read(timeout=100)
        if event in (sg.WIN_CLOSED, "Exit"):
            window.close()
            return

        if elapsed >= total_duration:
            break

    try:
        window.TKroot.attributes("-alpha", 1.0)
    except Exception:
        pass

    window.close()


def check_db_integrity(db_path):
    """Run PRAGMA integrity_check() and return (True, "ok") if ok else (False, details)."""
    try:
        if not os.path.exists(db_path):
            # No DB -> treat as OK (will be created by init_db)
            return True, "no_db"
        conn = sqlite3.connect(db_path, timeout=10)
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        rows = cur.fetchall()
        conn.close()
        # integrity_check returns [('ok',)]
        if rows and rows[0][0] == "ok":
            return True, "ok"
        return False, rows
    except Exception as e:
        logging.exception("DB integrity check failed: %s", e)
        return False, str(e)


def initialize():
    """
    Initialization logic:
     - create app archive folder using same helper as rest of app
     - initialize DB schema
     - verify DB integrity and offer to reset it if corrupted
     - clear transient duplicates so UI starts fresh (keeps scan history)
     - log app start
    """
    # ensure archive exists (same folder used by safe_delete)
    try:
        ensure_archive_folder()
    except Exception as e:
        logging.warning("Could not ensure archive folder: %s", e)

    # check DB integrity before init
    try:
        ok, info = check_db_integrity(DB_PATH)
        if not ok:
            # Ask user whether to rename/reset DB (preserve copy as .corrupt.bak)
            msg = (
                "The database file appears to be corrupt or inconsistent.\n\n"
                "If you choose Yes, the current DB will be renamed to:\n"
                f"{DB_PATH}.corrupt.bak\n\n"
                "A fresh database will be created and the app will start with an empty history.\n\n"
                "If you choose No, the app will still attempt to initialize (may fail).\n\n"
                "Proceed and reset the DB?"
            )
            answer = sg.popup_yes_no(msg, title="Database corruption detected", keep_on_top=True)
            if answer == "Yes":
                try:
                    bak = DB_PATH + ".corrupt.bak"
                    # rename (move) the file out of the way
                    if os.path.exists(DB_PATH):
                        os.replace(DB_PATH, bak)
                        logging.info("Renamed corrupt DB to %s", bak)
                except Exception as e:
                    logging.exception("Failed to rename corrupt DB: %s", e)
            else:
                logging.warning("User chose not to reset corrupt DB; continuing and hoping for best.")

        # Initialize/create DB schema (safe to call repeatedly)
        database.init_db()
    except Exception as e:
        logging.exception("Database initialization failed: %s", e)
        sg.popup_error(f"Database initialization failed:\n{e}", keep_on_top=True)

    # Ensure the transient duplicates table is empty at startup so UI is ready for a fresh scan.
    # This preserves the scans history while clearing any leftover duplicate rows that caused
    # previous 'expected 2 values' problems when old rows lingered.
    try:
        database.clear_duplicates()
        logging.debug("Cleared transient duplicates table at startup.")
    except Exception as e:
        logging.exception("Failed to clear duplicates at startup: %s", e)

    utils.log("QuickPurge started.")


def main():
    # show a brief loading screen
    try:
        show_loading_screen()
    except Exception:
        # fail gracefully; don't block app start for loading screen issues
        logging.debug("Loading screen failed or was closed.")

    initialize()

    # run the UI (blocks until user exits)
    try:
        ui.run()
        
    except Exception as e:
        logging.exception("Unhandled exception in UI.run(): %s", e)
        sg.popup_error(f"Fatal error in UI:\n{e}", keep_on_top=True)
        


if __name__ == "__main__":
    main()






