from __future__ import annotations

import argparse

from amspirit_debug_gui.app import DebugGuiApp


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="amspirit_debug_gui",
        description="Tkinter debug GUI for AMSpiriT Lite's embedded web server.",
    )
    ap.add_argument("--host", default="127.0.0.1", help="Debug server host (default: 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8765, help="Debug server port (default: 8765)")
    args = ap.parse_args()

    app = DebugGuiApp(host=args.host, port=args.port)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
