import typer

from moro import __version__
from moro.cli.analytics import analytics_app
from moro.cli.dashboard import dashboard_app
from moro.cli.data import app as data_app
from moro.cli.deploy import deploy_command
from moro.cli.diagnose import diagnose_command
from moro.cli.doctor import doctor_command
from moro.cli.eval import app as eval_app
from moro.cli.export import export_command
from moro.cli.flywheel import app as flywheel_app
from moro.cli.guard import app as guard_app
from moro.cli.hooks import hooks_app
from moro.cli.import_data import import_command
from moro.cli.init import init_command
from moro.cli.recipe import app as recipe_app
from moro.cli.registry import app as registry_app
from moro.cli.runs import app as runs_app
from moro.cli.services import app as services_app
from moro.cli.status import status_command
from moro.cli.train import train_command
from moro.cli.ui import ui_command
from moro.cli.validate import validate_command

app = typer.Typer(
    name="moro",
    help="MoroAI — local-first model adaptation foundry.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"moro {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show MoroAI version.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
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
app.add_typer(runs_app, name="runs")

# ── Evaluation ───────────────────────────────────────────────────────────────
app.add_typer(eval_app, name="eval")

# ── Export & Deploy ──────────────────────────────────────────────────────────
app.command(name="export", help="Export run artifacts.")(export_command)
app.command(name="deploy", help="Prepare local deployment artifacts.")(deploy_command)

# ── Diagnostics ──────────────────────────────────────────────────────────────
app.command(name="diagnose", help="Diagnose failures and suggest fixes.")(diagnose_command)

# ── Repository governance & DevSecOps ─────────────────────────────────────────
app.add_typer(hooks_app, name="hooks")
app.add_typer(guard_app, name="guard")

# ── Continuous Learning Flywheel ──────────────────────────────────────────────
app.add_typer(flywheel_app, name="flywheel")

# ── Pre-Flight Validation ───────────────────────────────────────────────────
app.command(name="validate", help="Run pre-flight validation on project config and environment.")(
    validate_command
)

# ── Model Registry ───────────────────────────────────────────────────────────
app.add_typer(registry_app, name="registry")

# ── Service Orchestrator ─────────────────────────────────────────────────────
app.add_typer(services_app, name="services")

# ── Experiment Tracking & Visual Analytics ────────────────────────────────────
app.add_typer(analytics_app, name="analytics")

# ── Mission Control Web Dashboard ─────────────────────────────────────────────
app.command(name="ui", help="Launch the MoroAI Mission Control Web Dashboard.")(ui_command)
app.add_typer(dashboard_app, name="dashboard")


# ── Version ──────────────────────────────────────────────────────────────────
@app.command(name="version", help="Show MoroAI version.")
def version_command() -> None:
    typer.echo(f"moro {__version__}")


if __name__ == "__main__":
    app()
