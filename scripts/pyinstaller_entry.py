"""PyInstaller entry point — bundles CLI + SDK into a single binary."""

from homecloud_cli.cli import main

if __name__ == "__main__":
    main()
