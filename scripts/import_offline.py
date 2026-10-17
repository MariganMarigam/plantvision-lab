"""CLI shim: import externally captured frames (see plantvision.capture.import_offline)."""

from plantvision.capture.import_offline import main

if __name__ == "__main__":
    raise SystemExit(main())
