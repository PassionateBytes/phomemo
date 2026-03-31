"""CLI entry point for phomemo-tui (stub — full implementation in later task)."""

from __future__ import annotations


def main() -> None:
    """Launch the Phomemo TUI."""
    from phomemo_tui.app import PhomemoApp

    PhomemoApp().run()
