from __future__ import annotations

import typer
from rich.console import Console

from media_offline_database.settings import Settings
from media_offline_database.sources import SourceRole

app = typer.Typer(help="Media Offline Database dataset compiler.")
console = Console()


@app.callback()
def main() -> None:
    """Compile and validate open media discovery datasets."""


@app.command()
def doctor() -> None:
    """Print runtime configuration that is safe to display."""

    settings = Settings()
    console.print(
        {
            "env": settings.mod_env,
            "data_dir": str(settings.mod_data_dir),
            "cache_dir": str(settings.mod_cache_dir),
            "output_dir": str(settings.mod_output_dir),
            "source_roles": [role.value for role in SourceRole],
        }
    )
