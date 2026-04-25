from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from media_offline_database.artifacts import write_keyless_smoke_artifact
from media_offline_database.settings import Settings
from media_offline_database.sources import SourceRole

app = typer.Typer(help="Media Offline Database dataset compiler.")
console = Console()
DEFAULT_SMOKE_OUTPUT_DIR = Path(".mod/out/keyless-smoke")
SmokeOutputDirOption = Annotated[
    Path,
    typer.Option(
        "--output-dir",
        help="Directory where the keyless smoke artifact should be written.",
    ),
]


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


@app.command()
def smoke_artifact(
    output_dir: SmokeOutputDirOption = DEFAULT_SMOKE_OUTPUT_DIR,
) -> None:
    """Generate a tiny Parquet artifact without credentials or network access."""

    manifest_path = write_keyless_smoke_artifact(output_dir)
    console.print({"manifest": str(manifest_path)})
