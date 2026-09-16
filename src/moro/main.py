import typer

from moro import __version__
from moro.cli.data import app as data_app
from moro.cli.deploy import deploy_command
from moro.cli.diagnose import diagnose_command
from moro.cli.doctor import doctor_command
from moro.cli.eval import app as eval_app
from moro.cli.export import export_command
from moro.cli.import_data import import_command
from moro.cli.init import init_command
from moro.cli.recipe import app as recipe_app
from moro.cli.status import status_command
from moro.cli.train import train_command

app = typer.Typer(
    name="moro",
    help="MoroAI — local-first model adaptation foundry.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)


@app.callback()
def main() -> None:
    """
    MoroAI CLI.

    Build, evaluate, and deploy local models from private data.
    """
    pass


# ── Core project commands ────────────────────────────────────────────────────
app.command(name="init", help="Initialize a new MoroAI project.")(init_command)
app.command(name="status", help="Show current project status.")(status_command)

# ── Environment ──────────────────────────────────────────────────────────────
app.command(name="doctor", help="Check environment and hardware readiness.")(doctor_command)

# ── Data ─────────────────────────────────────────────────────────────────────
app.command(name="import", help="Import raw dataset files into the project.")(import_command)
app.add_typer(data_app, name="data")

# ── Recipe ───────────────────────────────────────────────────────────────────
app.add_typer(recipe_app, name="recipe")

# ── Training ─────────────────────────────────────────────────────────────────
app.command(name="train", help="Run fine-tuning.")(train_command)

# ── Evaluation ───────────────────────────────────────────────────────────────
app.add_typer(eval_app, name="eval")

# ── Export & Deploy ──────────────────────────────────────────────────────────
app.command(name="export", help="Export run artifacts.")(export_command)
app.command(name="deploy", help="Prepare local deployment artifacts.")(deploy_command)

# ── Diagnostics ──────────────────────────────────────────────────────────────
app.command(name="diagnose", help="Diagnose failures and suggest fixes.")(diagnose_command)


# ── Version ──────────────────────────────────────────────────────────────────
@app.command(name="version", help="Show MoroAI version.")
def version_command() -> None:
    typer.echo(f"moro {__version__}")


if __name__ == "__main__":
    app()
