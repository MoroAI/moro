"""
MoroAI Runtime Orchestrator.

The central engine that coordinates all MoroAI subsystems
and manages the complete execution lifecycle.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

console = Console()
logger = logging.getLogger("moro.runtime")


# ===================================================================
# EXECUTION LIFECYCLE STATES
# ===================================================================


class ExecutionState(str, Enum):
    """States of the execution lifecycle."""

    INITIALIZING = "initializing"
    CONFIGURING = "configuring"
    VALIDATING = "validating"
    EXECUTING = "executing"
    MONITORING = "monitoring"
    COMPLETING = "completing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionPhase(str, Enum):
    """Phases of a complete MoroAI execution."""

    DATA_COMPILATION = "data_compilation"
    RECIPE_GENERATION = "recipe_generation"
    TRAINING = "training"
    EVALUATION = "evaluation"
    RELEASE = "release"
    DEPLOYMENT = "deployment"
    FEEDBACK_PROCESSING = "feedback_processing"


# ===================================================================
# EXECUTION CONTEXT
# ===================================================================


class ExecutionContext:
    """Carries all state through an execution lifecycle.

    This is the single source of truth for what is happening
    during any MoroAI operation.
    """

    def __init__(
        self,
        execution_id: str,
        project_root: Path,
        phase: ExecutionPhase,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.execution_id = execution_id
        self.project_root = Path(project_root)
        self.phase = phase
        self.config: dict[str, Any] = config or {}

        # State
        self.state = ExecutionState.INITIALIZING
        self.started_at = datetime.now(timezone.utc)
        self.completed_at: datetime | None = None
        self.error: Exception | None = None

        # Results
        self.results: dict[str, Any] = {}
        self.artifacts: list[Path] = []
        self.metrics: dict[str, float] = {}

        # Subsystem references (injected by orchestrator)
        self.state_manager = None
        self.experiment_tracker = None
        self.service_orchestrator = None

        # Callbacks
        self._progress_callbacks: list[Callable[[ExecutionContext, str, float | None], None]] = []
        self._error_callbacks: list[Callable[[ExecutionContext, Exception], None]] = []

    def add_progress_callback(self, callback: Callable) -> None:
        """Register a callback for progress updates."""
        self._progress_callbacks.append(callback)

    def add_error_callback(self, callback: Callable) -> None:
        """Register a callback for error notifications."""
        self._error_callbacks.append(callback)

    def report_progress(self, message: str, percentage: float | None = None) -> None:
        """Report progress to all registered callbacks."""
        for callback in self._progress_callbacks:
            try:
                callback(self, message, percentage)
            except Exception:
                pass

    def report_error(self, error: Exception) -> None:
        """Report an error to all registered callbacks."""
        for callback in self._error_callbacks:
            try:
                callback(self, error)
            except Exception:
                pass

    def complete(self, results: dict[str, Any] | None = None) -> None:
        """Mark execution as completed."""
        self.state = ExecutionState.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        if results:
            self.results.update(results)

    def fail(self, error: Exception) -> None:
        """Mark execution as failed."""
        self.state = ExecutionState.FAILED
        self.completed_at = datetime.now(timezone.utc)
        self.error = error
        self.report_error(error)

    @property
    def duration_seconds(self) -> float:
        """Get execution duration in seconds."""
        end = self.completed_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Serialize context to dictionary."""
        return {
            "execution_id": self.execution_id,
            "phase": self.phase.value,
            "state": self.state.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "results": self.results,
            "artifacts": [str(a) for a in self.artifacts],
            "metrics": self.metrics,
            "error": str(self.error) if self.error else None,
        }


# ===================================================================
# RUNTIME ORCHESTRATOR
# ===================================================================


class MoroRuntimeOrchestrator:
    """The central runtime orchestrator for MoroAI.

    Coordinates all subsystems and manages the complete
    execution lifecycle from data compilation to deployment.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)
        self._execution_history: list[ExecutionContext] = []
        self._active_executions: dict[str, ExecutionContext] = {}

        # Initialize subsystems lazily
        self._state_manager = None
        self._experiment_tracker = None
        self._service_orchestrator = None

        # Configuration
        self._config = self._load_config()

        logger.info(f"MoroRuntimeOrchestrator initialized for project: {project_root}")

    def _load_config(self) -> dict[str, Any]:
        """Load project configuration."""
        config_path = self.project_root / "moro.yaml"

        if config_path.exists():
            import yaml

            with open(config_path) as f:
                return yaml.safe_load(f) or {}

        return {}

    # ===================================================================
    # SUBSYSTEM ACCESSORS (Lazy Initialization)
    # ===================================================================

    @property
    def state_manager(self):
        """Get or create the state manager."""
        if self._state_manager is None:
            from moro.state.manager import StateManager

            self._state_manager = StateManager(self.project_root / ".moro" / "state.db")
        return self._state_manager

    @property
    def experiment_tracker(self):
        """Get or create the experiment tracker."""
        if self._experiment_tracker is None:
            from moro.analytics.tracker import ExperimentTracker

            self._experiment_tracker = ExperimentTracker(
                self.project_root / ".moro" / "analytics.db"
            )
        return self._experiment_tracker

    @property
    def service_orchestrator(self):
        """Get or create the service orchestrator."""
        if self._service_orchestrator is None:
            from moro.services.orchestrator import ServiceOrchestrator

            self._service_orchestrator = ServiceOrchestrator(
                self.project_root, self.project_root / ".moro" / "state.db"
            )
        return self._service_orchestrator

    # ===================================================================
    # EXECUTION LIFECYCLE
    # ===================================================================

    def create_execution(
        self,
        phase: ExecutionPhase,
        config: dict[str, Any] | None = None,
    ) -> ExecutionContext:
        """Create a new execution context.

        This is the entry point for any MoroAI operation.
        """
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"

        merged_config = dict(self._config)
        if config:
            merged_config.update(config)

        context = ExecutionContext(
            execution_id=execution_id,
            project_root=self.project_root,
            phase=phase,
            config=merged_config,
        )

        # Inject subsystem references
        context.state_manager = self.state_manager
        context.experiment_tracker = self.experiment_tracker
        context.service_orchestrator = self.service_orchestrator

        # Track execution
        self._active_executions[execution_id] = context
        self._execution_history.append(context)

        logger.info(f"Created execution {execution_id} for phase {phase.value}")

        return context

    async def execute_phase(
        self,
        context: ExecutionContext,
        phase_handler: Callable,
    ) -> dict[str, Any]:
        """Execute a single phase with full lifecycle management.

        This handles:
        - State transitions
        - Error handling and recovery
        - Progress reporting
        - Result collection
        """
        try:
            # Transition to executing
            context.state = ExecutionState.EXECUTING
            context.report_progress(f"Starting {context.phase.value}...")

            logger.info(
                f"Executing phase {context.phase.value} for execution {context.execution_id}"
            )

            # Execute the phase handler
            result = await phase_handler(context)

            # Transition to completing
            context.state = ExecutionState.COMPLETING
            context.report_progress(f"Completing {context.phase.value}...", 100)

            # Complete
            context.complete(result)

            logger.info(
                f"Completed phase {context.phase.value} for execution {context.execution_id}"
            )

            return result

        except Exception as e:
            logger.error(f"Failed phase {context.phase.value}: {e}")

            # Attempt recovery
            recovered = await self._attempt_recovery(context, e)

            if recovered:
                logger.info(f"Recovered from error in phase {context.phase.value}")
                return await self.execute_phase(context, phase_handler)
            else:
                context.fail(e)
                raise

    async def _attempt_recovery(
        self,
        context: ExecutionContext,
        error: Exception,
    ) -> bool:
        """Attempt to recover from an error.

        Returns True if recovery was successful and execution should retry.
        """
        error_type = type(error).__name__
        error_message = str(error).lower()

        logger.warning(f"Attempting recovery for error: {error_type} ({error})")

        # OOM errors: Reduce batch size and retry
        if "out of memory" in error_message or "oom" in error_message:
            logger.info("OOM detected. Reducing batch size and retrying...")

            if "batch_size" in context.config:
                current_batch = context.config.get("batch_size", 1)
                context.config["batch_size"] = max(1, current_batch // 2)
                return True

        # Timeout errors: Increase timeout and retry
        if "timeout" in error_message:
            logger.info("Timeout detected. Increasing timeout and retrying...")

            if "timeout" in context.config:
                context.config["timeout"] = context.config["timeout"] * 2
                return True

        # Connection errors: Wait and retry
        if "connection" in error_message or "refused" in error_message:
            logger.info("Connection error detected. Waiting 5 seconds and retrying...")
            await asyncio.sleep(5)
            return True

        # Unknown errors: No recovery
        logger.warning(f"No recovery strategy for error type: {error_type}")
        return False

    # ===================================================================
    # COMPLETE PIPELINE EXECUTION
    # ===================================================================

    async def run_complete_pipeline(
        self,
        data_source: Path | str,
        target_model: str,
        eval_suite: Path | str | None = None,
        deploy_target: str | None = None,
    ) -> dict[str, Any]:
        """Run the complete MoroAI pipeline from data to deployment.

        This is the central execution method coordinating all subsystems:
        1. Data Compilation
        2. Recipe Generation
        3. Training
        4. Evaluation
        5. Release
        6. Deployment (optional)
        """
        pipeline_id = f"pipeline_{uuid.uuid4().hex[:8]}"

        console.print(
            Panel(
                f"[bold cyan]MoroAI Complete Pipeline[/bold cyan]\n\n"
                f"Pipeline ID: {pipeline_id}\n"
                f"Data Source: {data_source}\n"
                f"Target Model: {target_model}\n"
                f"Deploy Target: {deploy_target or 'None'}",
                border_style="blue",
            )
        )

        results: dict[str, Any] = {
            "pipeline_id": pipeline_id,
            "phases": {},
            "success": False,
        }

        try:
            # Phase 1: Data Compilation
            console.print("\n[bold]Phase 1: Data Compilation[/bold]")

            data_context = self.create_execution(
                ExecutionPhase.DATA_COMPILATION, {"data_source": str(data_source)}
            )

            data_result = await self.execute_phase(data_context, self._phase_data_compilation)
            results["phases"]["data_compilation"] = data_result

            # Phase 2: Recipe Generation
            console.print("\n[bold]Phase 2: Recipe Generation[/bold]")

            recipe_context = self.create_execution(
                ExecutionPhase.RECIPE_GENERATION,
                {
                    "dataset_id": data_result.get("dataset_id"),
                    "target_model": target_model,
                },
            )

            recipe_result = await self.execute_phase(recipe_context, self._phase_recipe_generation)
            results["phases"]["recipe_generation"] = recipe_result

            # Phase 3: Training
            console.print("\n[bold]Phase 3: Training[/bold]")

            training_context = self.create_execution(
                ExecutionPhase.TRAINING,
                {
                    "dataset_id": data_result.get("dataset_id"),
                    "recipe": recipe_result,
                    "target_model": target_model,
                },
            )

            training_result = await self.execute_phase(training_context, self._phase_training)
            results["phases"]["training"] = training_result

            # Phase 4: Evaluation
            if eval_suite:
                console.print("\n[bold]Phase 4: Evaluation[/bold]")

                eval_context = self.create_execution(
                    ExecutionPhase.EVALUATION,
                    {
                        "training_run_id": training_result.get("experiment_id"),
                        "eval_suite": str(eval_suite),
                    },
                )

                eval_result = await self.execute_phase(eval_context, self._phase_evaluation)
                results["phases"]["evaluation"] = eval_result

            # Phase 5: Release
            console.print("\n[bold]Phase 5: Release[/bold]")

            release_context = self.create_execution(
                ExecutionPhase.RELEASE,
                {
                    "training_run_id": training_result.get("experiment_id"),
                    "eval_results": results["phases"].get("evaluation"),
                    "target_model": target_model,
                },
            )

            release_result = await self.execute_phase(release_context, self._phase_release)
            results["phases"]["release"] = release_result

            # Phase 6: Deployment (optional)
            if deploy_target:
                console.print(f"\n[bold]Phase 6: Deployment to {deploy_target}[/bold]")

                deploy_context = self.create_execution(
                    ExecutionPhase.DEPLOYMENT,
                    {
                        "release_id": release_result.get("release_id"),
                        "deploy_target": deploy_target,
                    },
                )

                deploy_result = await self.execute_phase(deploy_context, self._phase_deployment)
                results["phases"]["deployment"] = deploy_result

            # Pipeline complete
            results["success"] = True

            total_duration = sum(
                r.get("duration", 0) for r in results["phases"].values() if isinstance(r, dict)
            )

            console.print(
                Panel(
                    f"[bold green]✅ Pipeline Complete![/bold green]\n\n"
                    f"Pipeline ID: {pipeline_id}\n"
                    f"Duration: {total_duration:.1f}s\n"
                    f"Phases Completed: {len(results['phases'])}",
                    border_style="green",
                )
            )

        except Exception as e:
            results["success"] = False
            results["error"] = str(e)

            console.print(
                Panel(
                    f"[bold red]❌ Pipeline Failed[/bold red]\n\n"
                    f"Pipeline ID: {pipeline_id}\n"
                    f"Error: {str(e)}",
                    border_style="red",
                )
            )

        return results

    # ===================================================================
    # PHASE HANDLERS
    # ===================================================================

    async def _phase_data_compilation(self, context: ExecutionContext) -> dict[str, Any]:
        """Handle the data compilation phase."""
        start_time = time.time()

        data_source = Path(context.config["data_source"])

        context.report_progress("Loading data source...")

        # Import the data compiler
        from moro.data.compiler import DataCompiler

        compiler = DataCompiler(
            project_root=self.project_root,
            state_manager=self.state_manager,
        )

        context.report_progress("Compiling dataset...", 25)

        # Compile the dataset
        dataset_id = compiler.compile_dataset(
            source_path=data_source,
            config=context.config,
        )

        context.report_progress("Dataset compiled successfully", 100)

        duration = time.time() - start_time

        return {
            "dataset_id": dataset_id,
            "duration": duration,
            "status": "completed",
        }

    async def _phase_recipe_generation(self, context: ExecutionContext) -> dict[str, Any]:
        """Handle the recipe generation phase."""
        start_time = time.time()

        dataset_id = context.config.get("dataset_id")
        target_model = context.config.get("target_model")

        context.report_progress("Analyzing hardware...")

        # Import the recipe engine
        from moro.recipes.engine import RecipeEngine

        engine = RecipeEngine(
            project_root=self.project_root,
            state_manager=self.state_manager,
        )

        context.report_progress("Generating recipe...", 50)

        # Generate the recipe
        recipe = engine.generate_recipe(
            dataset_id=dataset_id,
            target_model=target_model,
        )

        context.report_progress("Recipe generated successfully", 100)

        duration = time.time() - start_time

        return {
            "recipe": recipe,
            "duration": duration,
            "status": "completed",
        }

    async def _phase_training(self, context: ExecutionContext) -> dict[str, Any]:
        """Handle the training phase."""
        start_time = time.time()

        dataset_id = context.config.get("dataset_id")
        recipe_input = context.config.get("recipe", {})
        recipe = recipe_input.get("recipe", recipe_input) if isinstance(recipe_input, dict) else {}

        target_model = context.config.get("target_model") or recipe.get("model_name") or "unknown"

        context.report_progress("Initializing training...")

        # Import the training runner
        from moro.training.runner import TrainingRunner

        runner = TrainingRunner(
            project_root=self.project_root,
            experiment_tracker=self.experiment_tracker,
        )

        # Create experiment
        experiment_id = self.experiment_tracker.create_experiment(
            name=f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            base_model=target_model,
            dataset_id=dataset_id,
        )

        context.report_progress("Starting training...", 10)

        try:
            # Run training
            result = await runner.run_training_async(
                experiment_id=experiment_id,
                dataset_id=dataset_id,
                recipe=recipe,
                progress_callback=lambda msg, pct: context.report_progress(msg, pct),
            )

            context.report_progress("Training completed successfully", 100)

            duration = time.time() - start_time

            return {
                "experiment_id": experiment_id,
                "final_loss": result.get("final_loss"),
                "peak_vram": result.get("peak_vram"),
                "duration": duration,
                "status": "completed",
            }

        except Exception as e:
            self.experiment_tracker.fail_experiment(experiment_id, str(e))
            raise

    async def _phase_evaluation(self, context: ExecutionContext) -> dict[str, Any]:
        """Handle the evaluation phase."""
        start_time = time.time()

        training_run_id = context.config.get("training_run_id")
        eval_suite_path = Path(context.config.get("eval_suite", "eval/test_suite.yaml"))

        context.report_progress("Loading evaluation suite...")

        # Import the eval harness
        from moro.eval.harness import EvalHarness

        harness = EvalHarness(
            project_root=self.project_root,
            experiment_tracker=self.experiment_tracker,
        )

        context.report_progress("Running evaluation...", 25)

        # Run evaluation
        eval_result = await harness.run_evaluation_async(
            experiment_id=training_run_id,
            eval_suite_path=eval_suite_path,
            progress_callback=lambda msg, pct: context.report_progress(msg, pct),
        )

        context.report_progress("Evaluation completed", 100)

        duration = time.time() - start_time

        return {
            "eval_id": eval_result.get("eval_id"),
            "pass_rate": eval_result.get("pass_rate"),
            "delta": eval_result.get("delta"),
            "duration": duration,
            "status": "completed",
        }

    async def _phase_release(self, context: ExecutionContext) -> dict[str, Any]:
        """Handle the release phase."""
        start_time = time.time()

        training_run_id = context.config.get("training_run_id")
        eval_results = context.config.get("eval_results", {})

        context.report_progress("Checking release gates...")

        # Import the release manager
        from moro.release.manager import ReleaseManager

        manager = ReleaseManager(
            project_root=self.project_root,
            state_manager=self.state_manager,
        )

        context.report_progress("Creating release...", 50)

        # Create release
        release_result = await manager.create_release_async(
            training_run_id=training_run_id,
            eval_results=eval_results,
            progress_callback=lambda msg, pct: context.report_progress(msg, pct),
        )

        context.report_progress("Release created successfully", 100)

        duration = time.time() - start_time

        return {
            "release_id": release_result.get("release_id"),
            "version": release_result.get("version"),
            "duration": duration,
            "status": "completed",
        }

    async def _phase_deployment(self, context: ExecutionContext) -> dict[str, Any]:
        """Handle the deployment phase."""
        start_time = time.time()

        release_id = context.config.get("release_id")
        deploy_target = context.config.get("deploy_target")

        context.report_progress(f"Preparing deployment to {deploy_target}...")

        # Import the deployment manager
        from moro.deploy.manager import DeploymentManager

        manager = DeploymentManager(
            project_root=self.project_root,
            state_manager=self.state_manager,
            service_orchestrator=self.service_orchestrator,
        )

        context.report_progress("Deploying...", 50)

        # Deploy
        deploy_result = await manager.deploy_async(
            release_id=release_id,
            target=deploy_target,
            progress_callback=lambda msg, pct: context.report_progress(msg, pct),
        )

        context.report_progress("Deployment completed", 100)

        duration = time.time() - start_time

        return {
            "deployment_id": deploy_result.get("deployment_id"),
            "endpoint": deploy_result.get("endpoint"),
            "duration": duration,
            "status": "completed",
        }

    # ===================================================================
    # SERVICE MANAGEMENT
    # ===================================================================

    async def start_all_services(self) -> dict[str, bool]:
        """Start all background services."""
        console.print("[cyan]Starting all services...[/cyan]")

        results: dict[str, bool] = {}

        # Start services in order of dependency
        service_order = ["ollama", "webhook", "gateway", "dashboard"]

        for service_name in service_order:
            try:
                success = self.service_orchestrator.start_service(service_name)
                results[service_name] = success

                if success:
                    console.print(f"  [green]✅ {service_name} started[/green]")
                else:
                    console.print(f"  [red]❌ {service_name} failed to start[/red]")

            except Exception as e:
                results[service_name] = False
                console.print(f"  [red]❌ {service_name} error: {e}[/red]")

        return results

    async def stop_all_services(self) -> dict[str, bool]:
        """Stop all background services."""
        console.print("[cyan]Stopping all services...[/cyan]")

        results = self.service_orchestrator.stop_all()

        for service_name, success in results.items():
            if success:
                console.print(f"  [green]✅ {service_name} stopped[/green]")
            else:
                console.print(f"  [red]❌ {service_name} failed to stop[/red]")

        return results

    # ===================================================================
    # HEALTH MONITORING
    # ===================================================================

    def get_system_health(self) -> dict[str, Any]:
        """Get complete system health status."""
        health: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "services": {},
            "database": {},
            "active_executions": len(self._active_executions),
            "total_executions": len(self._execution_history),
        }

        # Check services
        service_statuses = self.service_orchestrator.get_status()
        for status in service_statuses:
            health["services"][status["name"]] = {
                "running": status["running"],
                "healthy": status["healthy"],
                "pid": status.get("pid"),
            }

        # Check databases
        state_db = self.project_root / ".moro" / "state.db"
        analytics_db = self.project_root / ".moro" / "analytics.db"

        health["database"] = {
            "state_db_exists": state_db.exists(),
            "state_db_size_mb": (state_db.stat().st_size / (1024 * 1024))
            if state_db.exists()
            else 0,
            "analytics_db_exists": analytics_db.exists(),
            "analytics_db_size_mb": (analytics_db.stat().st_size / (1024 * 1024))
            if analytics_db.exists()
            else 0,
        }

        return health


# ===================================================================
# GLOBAL RUNTIME INSTANCE
# ===================================================================

_runtime: MoroRuntimeOrchestrator | None = None


def get_runtime(project_root: Path | None = None) -> MoroRuntimeOrchestrator:
    """Get or create the global runtime instance."""
    global _runtime

    if _runtime is None:
        if project_root is None:
            project_root = Path.cwd()

        _runtime = MoroRuntimeOrchestrator(project_root)

    return _runtime


def reset_runtime() -> None:
    """Reset the global runtime instance."""
    global _runtime
    _runtime = None
