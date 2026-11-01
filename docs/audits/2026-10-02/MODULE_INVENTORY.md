# Python module inventory

Source revision: `bac72593964c5e7218b009824f7146998b6cdfaa`. All 132 source modules are inventoried below. Coverage is statement coverage from the fresh Python 3.12 core run; real Linux training is a separate check. Symbols are top-level functions/classes, not every method. Inventory membership does not certify absence of defects. Full SHA-256 hashes are in [source-inventory.json](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/source-inventory.json).

Interpret this alongside [the detailed audit](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/REPORT.md).


## src/moro

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |

## src/moro/analytics

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/analytics/__init__.py) | 6 | 100.0% | Package declarations / no top-level callable |
| [schema.py](/Users/mac/Dev/MoroAI/moro/src/moro/analytics/schema.py) | 281 | 95.2% | [initialize_experiment_db](/Users/mac/Dev/MoroAI/moro/src/moro/analytics/schema.py:257), [get_experiment_db](/Users/mac/Dev/MoroAI/moro/src/moro/analytics/schema.py:271) |
| [tracker.py](/Users/mac/Dev/MoroAI/moro/src/moro/analytics/tracker.py) | 759 | 79.4% | [ExperimentTracker](/Users/mac/Dev/MoroAI/moro/src/moro/analytics/tracker.py:19) |
| [visualizations.py](/Users/mac/Dev/MoroAI/moro/src/moro/analytics/visualizations.py) | 353 | 59.8% | [VisualAnalyticsEngine](/Users/mac/Dev/MoroAI/moro/src/moro/analytics/visualizations.py:16) |

## src/moro/cli

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |
| [analytics.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/analytics.py) | 335 | 77.6% | [_get_tracker](/Users/mac/Dev/MoroAI/moro/src/moro/cli/analytics.py:27), [analytics_list](/Users/mac/Dev/MoroAI/moro/src/moro/cli/analytics.py:34), [analytics_show](/Users/mac/Dev/MoroAI/moro/src/moro/cli/analytics.py:100), [analytics_compare](/Users/mac/Dev/MoroAI/moro/src/moro/cli/analytics.py:151), [analytics_trend](/Users/mac/Dev/MoroAI/moro/src/moro/cli/analytics.py:237), [analytics_recommend](/Users/mac/Dev/MoroAI/moro/src/moro/cli/analytics.py:288) |
| [dashboard.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/dashboard.py) | 164 | 30.5% | [dashboard_default](/Users/mac/Dev/MoroAI/moro/src/moro/cli/dashboard.py:31), [dashboard_serve](/Users/mac/Dev/MoroAI/moro/src/moro/cli/dashboard.py:55), [dashboard_build](/Users/mac/Dev/MoroAI/moro/src/moro/cli/dashboard.py:131), [dashboard_status](/Users/mac/Dev/MoroAI/moro/src/moro/cli/dashboard.py:146) |
| [data.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/data.py) | 358 | 76.7% | [build_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/data.py:18), [report_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/data.py:173), [inspect_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/data.py:270) |
| [deploy.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/deploy.py) | 63 | 84.2% | [deploy_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/deploy.py:14) |
| [diagnose.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/diagnose.py) | 170 | 79.8% | [_extract_error_from_log](/Users/mac/Dev/MoroAI/moro/src/moro/cli/diagnose.py:17), [diagnose_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/diagnose.py:58) |
| [doctor.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/doctor.py) | 92 | 76.8% | [doctor_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/doctor.py:13) |
| [eval.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/eval.py) | 491 | 37.4% | [eval_run_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/eval.py:20), [eval_report_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/eval.py:129), [list_evaluations](/Users/mac/Dev/MoroAI/moro/src/moro/cli/eval.py:162), [compare_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/eval.py:191), [perturb_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/eval.py:334) |
| [export.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/export.py) | 215 | 72.5% | [export_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/export.py:25) |
| [flywheel.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/flywheel.py) | 247 | 65.8% | [_get_db_path](/Users/mac/Dev/MoroAI/moro/src/moro/cli/flywheel.py:35), [flywheel_status](/Users/mac/Dev/MoroAI/moro/src/moro/cli/flywheel.py:45), [flywheel_ingest](/Users/mac/Dev/MoroAI/moro/src/moro/cli/flywheel.py:79), [flywheel_run](/Users/mac/Dev/MoroAI/moro/src/moro/cli/flywheel.py:105), [flywheel_history](/Users/mac/Dev/MoroAI/moro/src/moro/cli/flywheel.py:172), [flywheel_serve](/Users/mac/Dev/MoroAI/moro/src/moro/cli/flywheel.py:214) |
| [guard.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/guard.py) | 247 | 75.8% | [_resolve_target_file](/Users/mac/Dev/MoroAI/moro/src/moro/cli/guard.py:32), [scan_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/guard.py:52), [redact_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/guard.py:157), [check_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/guard.py:218) |
| [hooks.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/hooks.py) | 249 | 64.2% | [install_hooks](/Users/mac/Dev/MoroAI/moro/src/moro/cli/hooks.py:36), [check_hooks](/Users/mac/Dev/MoroAI/moro/src/moro/cli/hooks.py:137), [uninstall_hooks](/Users/mac/Dev/MoroAI/moro/src/moro/cli/hooks.py:220) |
| [import_data.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/import_data.py) | 127 | 64.1% | [import_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/import_data.py:15) |
| [init.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/init.py) | 93 | 76.2% | [sanitize_project_name](/Users/mac/Dev/MoroAI/moro/src/moro/cli/init.py:18), [init_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/init.py:25) |
| [recipe.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/recipe.py) | 216 | 89.3% | [suggest_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/recipe.py:22), [apply_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/recipe.py:151) |
| [registry.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/registry.py) | 138 | 27.9% | [list_models_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/registry.py:25), [show_model_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/registry.py:69), [promote_model_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/registry.py:107), [delete_model_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/registry.py:126) |
| [runs.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/runs.py) | 205 | 83.6% | [project_runs](/Users/mac/Dev/MoroAI/moro/src/moro/cli/runs.py:17), [_format_dt](/Users/mac/Dev/MoroAI/moro/src/moro/cli/runs.py:33), [_status_color](/Users/mac/Dev/MoroAI/moro/src/moro/cli/runs.py:43), [list_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/runs.py:54), [show_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/runs.py:110), [compare_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/runs.py:159) |
| [services.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/services.py) | 136 | 31.9% | [services_status_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/services.py:25), [services_start_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/services.py:60), [services_stop_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/services.py:79), [services_restart_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/services.py:98), [services_supervise_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/services.py:116), [services_logs_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/services.py:126) |
| [status.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/status.py) | 104 | 79.3% | [status_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/status.py:13) |
| [train.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/train.py) | 275 | 84.2% | [train_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/train.py:21) |
| [ui.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/ui.py) | 38 | 31.6% | [ui_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/ui.py:15) |
| [validate.py](/Users/mac/Dev/MoroAI/moro/src/moro/cli/validate.py) | 91 | 24.0% | [validate_command](/Users/mac/Dev/MoroAI/moro/src/moro/cli/validate.py:22) |

## src/moro/config

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/config/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |
| [loader.py](/Users/mac/Dev/MoroAI/moro/src/moro/config/loader.py) | 44 | 89.3% | [load_config](/Users/mac/Dev/MoroAI/moro/src/moro/config/loader.py:10) |
| [models.py](/Users/mac/Dev/MoroAI/moro/src/moro/config/models.py) | 141 | 97.9% | [StrictConfig](/Users/mac/Dev/MoroAI/moro/src/moro/config/models.py:16), [ProjectConfig](/Users/mac/Dev/MoroAI/moro/src/moro/config/models.py:20), [DatasetConfig](/Users/mac/Dev/MoroAI/moro/src/moro/config/models.py:26), [ModelConfig](/Users/mac/Dev/MoroAI/moro/src/moro/config/models.py:52), [AdapterConfig](/Users/mac/Dev/MoroAI/moro/src/moro/config/models.py:59), [TrainingConfig](/Users/mac/Dev/MoroAI/moro/src/moro/config/models.py:72), [EvalSuiteRef](/Users/mac/Dev/MoroAI/moro/src/moro/config/models.py:97), [EvalConfig](/Users/mac/Dev/MoroAI/moro/src/moro/config/models.py:102), [ReleaseRequirements](/Users/mac/Dev/MoroAI/moro/src/moro/config/models.py:108), [ReleaseConfig](/Users/mac/Dev/MoroAI/moro/src/moro/config/models.py:118), [MoroConfig](/Users/mac/Dev/MoroAI/moro/src/moro/config/models.py:127) |

## src/moro/core

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/core/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |
| [errors.py](/Users/mac/Dev/MoroAI/moro/src/moro/core/errors.py) | 34 | 100.0% | [MoroError](/Users/mac/Dev/MoroAI/moro/src/moro/core/errors.py:1), [ProjectError](/Users/mac/Dev/MoroAI/moro/src/moro/core/errors.py:5), [ConfigError](/Users/mac/Dev/MoroAI/moro/src/moro/core/errors.py:9), [DatasetError](/Users/mac/Dev/MoroAI/moro/src/moro/core/errors.py:13), [DependencyError](/Users/mac/Dev/MoroAI/moro/src/moro/core/errors.py:17), [TrainingError](/Users/mac/Dev/MoroAI/moro/src/moro/core/errors.py:21), [ExportError](/Users/mac/Dev/MoroAI/moro/src/moro/core/errors.py:25), [EvalError](/Users/mac/Dev/MoroAI/moro/src/moro/core/errors.py:29), [RecipeError](/Users/mac/Dev/MoroAI/moro/src/moro/core/errors.py:33) |
| [hashing.py](/Users/mac/Dev/MoroAI/moro/src/moro/core/hashing.py) | 86 | 96.4% | [sha256_file](/Users/mac/Dev/MoroAI/moro/src/moro/core/hashing.py:9), [sha256_text](/Users/mac/Dev/MoroAI/moro/src/moro/core/hashing.py:24), [_snapshot_fields](/Users/mac/Dev/MoroAI/moro/src/moro/core/hashing.py:29), [config_snapshot_hash](/Users/mac/Dev/MoroAI/moro/src/moro/core/hashing.py:49), [matches_config_snapshot](/Users/mac/Dev/MoroAI/moro/src/moro/core/hashing.py:61), [sha256_directory](/Users/mac/Dev/MoroAI/moro/src/moro/core/hashing.py:75) |
| [ids.py](/Users/mac/Dev/MoroAI/moro/src/moro/core/ids.py) | 16 | 100.0% | [new_id](/Users/mac/Dev/MoroAI/moro/src/moro/core/ids.py:5) |
| [logging.py](/Users/mac/Dev/MoroAI/moro/src/moro/core/logging.py) | 44 | 0.0% | [info](/Users/mac/Dev/MoroAI/moro/src/moro/core/logging.py:12), [success](/Users/mac/Dev/MoroAI/moro/src/moro/core/logging.py:17), [warning](/Users/mac/Dev/MoroAI/moro/src/moro/core/logging.py:22), [error](/Users/mac/Dev/MoroAI/moro/src/moro/core/logging.py:27), [step](/Users/mac/Dev/MoroAI/moro/src/moro/core/logging.py:32), [dim](/Users/mac/Dev/MoroAI/moro/src/moro/core/logging.py:37), [get_console](/Users/mac/Dev/MoroAI/moro/src/moro/core/logging.py:42) |
| [paths.py](/Users/mac/Dev/MoroAI/moro/src/moro/core/paths.py) | 65 | 100.0% | [find_project_root](/Users/mac/Dev/MoroAI/moro/src/moro/core/paths.py:21), [project_dirs](/Users/mac/Dev/MoroAI/moro/src/moro/core/paths.py:35), [ensure_project_dirs](/Users/mac/Dev/MoroAI/moro/src/moro/core/paths.py:55) |
| [project.py](/Users/mac/Dev/MoroAI/moro/src/moro/core/project.py) | 30 | 92.3% | [require_project_root](/Users/mac/Dev/MoroAI/moro/src/moro/core/project.py:9), [load_project_config](/Users/mac/Dev/MoroAI/moro/src/moro/core/project.py:24) |

## src/moro/dashboard

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |

## src/moro/dashboard/api

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/__init__.py) | 3 | 100.0% | Package declarations / no top-level callable |
| [datasets.py](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/datasets.py) | 376 | 66.7% | [DatasetInfo](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/datasets.py:33), [DatasetUploadResponse](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/datasets.py:46), [DatasetPreview](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/datasets.py:56), [_find_dataset_file](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/datasets.py:71), [compile_dataset_sync](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/datasets.py:95), [list_datasets](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/datasets.py:116), [upload_dataset](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/datasets.py:185), [upload_multiple_datasets](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/datasets.py:228), [preview_dataset](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/datasets.py:277), [compile_dataset](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/datasets.py:347), [delete_dataset](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/datasets.py:366) |
| [deployment.py](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/deployment.py) | 200 | 68.5% | [DeploymentRequest](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/deployment.py:28), [DeploymentStatus](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/deployment.py:36), [_check_ollama](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/deployment.py:56), [get_deployment_status](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/deployment.py:77), [deploy_model](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/deployment.py:91), [undeploy_model](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/deployment.py:117), [list_ollama_models](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/deployment.py:126), [pull_ollama_model](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/deployment.py:132), [delete_ollama_model](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/deployment.py:147), [test_ollama_model](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/deployment.py:164) |
| [evaluation.py](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/evaluation.py) | 134 | 96.1% | [EvalRunRequest](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/evaluation.py:22), [EvalResultItem](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/evaluation.py:29), [list_evaluation_suites](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/evaluation.py:45), [run_evaluation](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/evaluation.py:66), [get_eval_results](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/evaluation.py:120) |
| [flywheel.py](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/flywheel.py) | 109 | 72.5% | [FlywheelCycleResponse](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/flywheel.py:22), [get_flywheel_status](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/flywheel.py:31), [trigger_flywheel_cycle](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/flywheel.py:58), [list_preference_pairs](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/flywheel.py:74) |
| [models.py](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/models.py) | 267 | 49.2% | [ModelInfo](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/models.py:30), [_get_models_from_releases](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/models.py:53), [list_models](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/models.py:104), [get_model](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/models.py:155), [promote_model](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/models.py:165), [archive_model](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/models.py:186), [delete_model](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/models.py:210), [compare_models](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/models.py:234) |
| [system.py](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/system.py) | 308 | 59.0% | [SystemHealth](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/system.py:33), [TerminalCommand](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/system.py:43), [TerminalResponse](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/system.py:50), [get_system_health](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/system.py:64), [get_services](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/system.py:141), [start_service](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/system.py:154), [stop_service](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/system.py:172), [execute_terminal_command](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/system.py:190), [get_config](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/system.py:236), [update_config](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/system.py:262), [ws_system_health](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/system.py:281), [ws_system_logs](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/system.py:294) |
| [training.py](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/training.py) | 333 | 65.9% | [TrainingConfig](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/training.py:32), [TrainingRun](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/training.py:46), [TrainingStartResponse](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/training.py:62), [_discover_filesystem_runs](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/training.py:78), [_simulate_training_worker](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/training.py:137), [list_training_runs](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/training.py:201), [get_training_run](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/training.py:218), [start_training](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/training.py:232), [stop_training](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/training.py:261), [cancel_training](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/training.py:276), [get_training_metrics](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/training.py:282), [get_gpu_status](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/training.py:307) |

## src/moro/dashboard

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [gateway.py](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/gateway.py) | 113 | 0.0% | [ChatMessage](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/gateway.py:36), [ChatCompletionRequest](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/gateway.py:41), [ChatCompletionResponse](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/gateway.py:49), [health_check](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/gateway.py:59), [list_models](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/gateway.py:70), [chat_completions](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/gateway.py:82) |
| [mission_control.py](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py) | 911 | 40.8% | [DockerConnector](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:38), [OllamaConnector](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:124), [DatabaseConnector](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:188), [TrainingMonitor](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:332), [FlywheelMonitor](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:366), [get_project_root](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:435), [startup](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:441), [serve_dashboard](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:457), [health_check](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:470), [system_overview](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:485), [state_nodes](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:511), [state_lineage](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:524), [registry_models_api](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:535), [registry_promote_model](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:541), [state_lineage_api](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:554), [services_status_api](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:560), [services_start_api](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:569), [services_stop_api](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:581), [docker_containers](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:593), [docker_start_container](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:601), [docker_stop_container](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:612), [docker_container_logs](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:623), [ollama_models](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:632), [ollama_model_info](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:638), [PromptPayload](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:646), [ollama_generate](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:652), [database_production_stats](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:659), [database_production_logs](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:665), [training_runs](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:671), [training_active](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:677), [flywheel_status](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:684), [CommandPayload](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:689), [terminal_execute](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:694), [_get_analytics_tracker](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:733), [_get_analytics_viz_engine](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:738), [analytics_experiments](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:743), [analytics_experiment_detail](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:751), [analytics_experiment_metrics](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:769), [analytics_compare](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:777), [analytics_loss_curves](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:787), [analytics_quality_trend](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:795), [analytics_heatmap](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:802), [analytics_resource_utilization](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:813), [analytics_output_comparison](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:820), [analytics_recommendations](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:832), [ws_system_metrics](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:845), [ws_training_telemetry](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:864), [ws_logs_stream](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:889) |
| [utils.py](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/utils.py) | 27 | 70.0% | [get_project_root](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/utils.py:14), [get_state_db_path](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/utils.py:20), [get_analytics_db_path](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/utils.py:25) |

## src/moro/data

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/data/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |
| [clean.py](/Users/mac/Dev/MoroAI/moro/src/moro/data/clean.py) | 224 | 92.7% | [_build_global_stats](/Users/mac/Dev/MoroAI/moro/src/moro/data/clean.py:36), [_load_domain_glossary](/Users/mac/Dev/MoroAI/moro/src/moro/data/clean.py:48), [_near_hash](/Users/mac/Dev/MoroAI/moro/src/moro/data/clean.py:69), [clean_rows](/Users/mac/Dev/MoroAI/moro/src/moro/data/clean.py:83) |
| [compiler.py](/Users/mac/Dev/MoroAI/moro/src/moro/data/compiler.py) | 107 | 87.8% | [DataCompiler](/Users/mac/Dev/MoroAI/moro/src/moro/data/compiler.py:18) |
| [ingest.py](/Users/mac/Dev/MoroAI/moro/src/moro/data/ingest.py) | 126 | 40.4% | [detect_format](/Users/mac/Dev/MoroAI/moro/src/moro/data/ingest.py:10), [read_raw_rows](/Users/mac/Dev/MoroAI/moro/src/moro/data/ingest.py:25), [_tag](/Users/mac/Dev/MoroAI/moro/src/moro/data/ingest.py:62), [_read_jsonl](/Users/mac/Dev/MoroAI/moro/src/moro/data/ingest.py:70), [_read_csv](/Users/mac/Dev/MoroAI/moro/src/moro/data/ingest.py:105), [_read_text](/Users/mac/Dev/MoroAI/moro/src/moro/data/ingest.py:116) |
| [models.py](/Users/mac/Dev/MoroAI/moro/src/moro/data/models.py) | 185 | 97.6% | [QualityScoreBreakdown](/Users/mac/Dev/MoroAI/moro/src/moro/data/models.py:20), [DomainQualityScores](/Users/mac/Dev/MoroAI/moro/src/moro/data/models.py:30), [InformationTheoreticMetrics](/Users/mac/Dev/MoroAI/moro/src/moro/data/models.py:38), [DatasetRowMetadata](/Users/mac/Dev/MoroAI/moro/src/moro/data/models.py:76), [DatasetMessage](/Users/mac/Dev/MoroAI/moro/src/moro/data/models.py:128), [DatasetRow](/Users/mac/Dev/MoroAI/moro/src/moro/data/models.py:133), [InvalidRow](/Users/mac/Dev/MoroAI/moro/src/moro/data/models.py:147), [DatasetStats](/Users/mac/Dev/MoroAI/moro/src/moro/data/models.py:159) |
| [normalize.py](/Users/mac/Dev/MoroAI/moro/src/moro/data/normalize.py) | 174 | 88.5% | [normalize_rows](/Users/mac/Dev/MoroAI/moro/src/moro/data/normalize.py:10), [_clean_raw](/Users/mac/Dev/MoroAI/moro/src/moro/data/normalize.py:73), [_make_row_id](/Users/mac/Dev/MoroAI/moro/src/moro/data/normalize.py:78), [_normalize_single_row](/Users/mac/Dev/MoroAI/moro/src/moro/data/normalize.py:87), [_parse_messages_list](/Users/mac/Dev/MoroAI/moro/src/moro/data/normalize.py:138), [_extract_prompt](/Users/mac/Dev/MoroAI/moro/src/moro/data/normalize.py:153), [_extract_completion](/Users/mac/Dev/MoroAI/moro/src/moro/data/normalize.py:161), [_text](/Users/mac/Dev/MoroAI/moro/src/moro/data/normalize.py:169) |
| [privacy.py](/Users/mac/Dev/MoroAI/moro/src/moro/data/privacy.py) | 123 | 78.0% | [scan_row](/Users/mac/Dev/MoroAI/moro/src/moro/data/privacy.py:44), [scan_rows](/Users/mac/Dev/MoroAI/moro/src/moro/data/privacy.py:59), [redact_text](/Users/mac/Dev/MoroAI/moro/src/moro/data/privacy.py:82), [redact_row](/Users/mac/Dev/MoroAI/moro/src/moro/data/privacy.py:97), [redact_rows](/Users/mac/Dev/MoroAI/moro/src/moro/data/privacy.py:113) |
| [quality.py](/Users/mac/Dev/MoroAI/moro/src/moro/data/quality.py) | 333 | 97.2% | [calculate_zlib_entropy](/Users/mac/Dev/MoroAI/moro/src/moro/data/quality.py:45), [calculate_domain_ppmi](/Users/mac/Dev/MoroAI/moro/src/moro/data/quality.py:66), [calculate_resnik_ic](/Users/mac/Dev/MoroAI/moro/src/moro/data/quality.py:86), [compute_basic_quality_breakdown](/Users/mac/Dev/MoroAI/moro/src/moro/data/quality.py:119), [classify_row](/Users/mac/Dev/MoroAI/moro/src/moro/data/quality.py:165), [approximate_token_count](/Users/mac/Dev/MoroAI/moro/src/moro/data/quality.py:217), [score_row](/Users/mac/Dev/MoroAI/moro/src/moro/data/quality.py:226), [score_row_epistemic](/Users/mac/Dev/MoroAI/moro/src/moro/data/quality.py:268) |
| [report.py](/Users/mac/Dev/MoroAI/moro/src/moro/data/report.py) | 104 | 80.4% | [compute_stats](/Users/mac/Dev/MoroAI/moro/src/moro/data/report.py:6) |
| [splitter.py](/Users/mac/Dev/MoroAI/moro/src/moro/data/splitter.py) | 58 | 93.3% | [split_rows](/Users/mac/Dev/MoroAI/moro/src/moro/data/splitter.py:8), [write_split](/Users/mac/Dev/MoroAI/moro/src/moro/data/splitter.py:51) |
| [versions.py](/Users/mac/Dev/MoroAI/moro/src/moro/data/versions.py) | 152 | 88.5% | [source_fingerprint](/Users/mac/Dev/MoroAI/moro/src/moro/data/versions.py:15), [build_key](/Users/mac/Dev/MoroAI/moro/src/moro/data/versions.py:20), [verify_snapshot](/Users/mac/Dev/MoroAI/moro/src/moro/data/versions.py:35), [select_snapshot](/Users/mac/Dev/MoroAI/moro/src/moro/data/versions.py:54), [publish_snapshot](/Users/mac/Dev/MoroAI/moro/src/moro/data/versions.py:78) |

## src/moro/deploy

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/deploy/__init__.py) | 5 | 0.0% | Package declarations / no top-level callable |
| [manager.py](/Users/mac/Dev/MoroAI/moro/src/moro/deploy/manager.py) | 93 | 0.0% | [DeploymentManager](/Users/mac/Dev/MoroAI/moro/src/moro/deploy/manager.py:21) |

## src/moro/diagnose

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/diagnose/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |
| [analyzer.py](/Users/mac/Dev/MoroAI/moro/src/moro/diagnose/analyzer.py) | 104 | 100.0% | [analyze_error](/Users/mac/Dev/MoroAI/moro/src/moro/diagnose/analyzer.py:73) |

## src/moro/eval

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/eval/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |
| [compare.py](/Users/mac/Dev/MoroAI/moro/src/moro/eval/compare.py) | 122 | 91.2% | [compare_eval](/Users/mac/Dev/MoroAI/moro/src/moro/eval/compare.py:16), [_compute_delta](/Users/mac/Dev/MoroAI/moro/src/moro/eval/compare.py:66), [_summarize_delta](/Users/mac/Dev/MoroAI/moro/src/moro/eval/compare.py:112) |
| [harness.py](/Users/mac/Dev/MoroAI/moro/src/moro/eval/harness.py) | 143 | 89.9% | [EvalHarness](/Users/mac/Dev/MoroAI/moro/src/moro/eval/harness.py:22) |
| [loader.py](/Users/mac/Dev/MoroAI/moro/src/moro/eval/loader.py) | 87 | 76.4% | [load_suite](/Users/mac/Dev/MoroAI/moro/src/moro/eval/loader.py:11) |
| [models.py](/Users/mac/Dev/MoroAI/moro/src/moro/eval/models.py) | 66 | 100.0% | [EvalMessage](/Users/mac/Dev/MoroAI/moro/src/moro/eval/models.py:9), [EvalExpect](/Users/mac/Dev/MoroAI/moro/src/moro/eval/models.py:16), [EvalCase](/Users/mac/Dev/MoroAI/moro/src/moro/eval/models.py:25), [EvalSuite](/Users/mac/Dev/MoroAI/moro/src/moro/eval/models.py:34), [CaseScore](/Users/mac/Dev/MoroAI/moro/src/moro/eval/models.py:43), [EvalResult](/Users/mac/Dev/MoroAI/moro/src/moro/eval/models.py:51) |
| [perturbations.py](/Users/mac/Dev/MoroAI/moro/src/moro/eval/perturbations.py) | 168 | 100.0% | [PerturbationEngine](/Users/mac/Dev/MoroAI/moro/src/moro/eval/perturbations.py:50) |
| [robustness.py](/Users/mac/Dev/MoroAI/moro/src/moro/eval/robustness.py) | 329 | 91.9% | [CaseRobustnessResult](/Users/mac/Dev/MoroAI/moro/src/moro/eval/robustness.py:27), [RobustnessReport](/Users/mac/Dev/MoroAI/moro/src/moro/eval/robustness.py:58), [compute_case_robustness](/Users/mac/Dev/MoroAI/moro/src/moro/eval/robustness.py:111), [compute_robustness_report](/Users/mac/Dev/MoroAI/moro/src/moro/eval/robustness.py:134), [compute_robustness_score](/Users/mac/Dev/MoroAI/moro/src/moro/eval/robustness.py:152), [create_perturbed_suite](/Users/mac/Dev/MoroAI/moro/src/moro/eval/robustness.py:180), [evaluate_robustness](/Users/mac/Dev/MoroAI/moro/src/moro/eval/robustness.py:234) |
| [runner.py](/Users/mac/Dev/MoroAI/moro/src/moro/eval/runner.py) | 140 | 63.0% | [_load_generator](/Users/mac/Dev/MoroAI/moro/src/moro/eval/runner.py:15), [_generate_response](/Users/mac/Dev/MoroAI/moro/src/moro/eval/runner.py:49), [run_suite](/Users/mac/Dev/MoroAI/moro/src/moro/eval/runner.py:57) |
| [scorers.py](/Users/mac/Dev/MoroAI/moro/src/moro/eval/scorers.py) | 87 | 66.0% | [score_case](/Users/mac/Dev/MoroAI/moro/src/moro/eval/scorers.py:12) |

## src/moro/export

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/export/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |
| [eligibility.py](/Users/mac/Dev/MoroAI/moro/src/moro/export/eligibility.py) | 95 | 92.4% | [ExportRun](/Users/mac/Dev/MoroAI/moro/src/moro/export/eligibility.py:19), [validate_adapter](/Users/mac/Dev/MoroAI/moro/src/moro/export/eligibility.py:30), [resolve_export_run](/Users/mac/Dev/MoroAI/moro/src/moro/export/eligibility.py:52) |
| [gates.py](/Users/mac/Dev/MoroAI/moro/src/moro/export/gates.py) | 119 | 86.3% | [check_release_requirements](/Users/mac/Dev/MoroAI/moro/src/moro/export/gates.py:15), [write_gate_report](/Users/mac/Dev/MoroAI/moro/src/moro/export/gates.py:118) |
| [gguf.py](/Users/mac/Dev/MoroAI/moro/src/moro/export/gguf.py) | 141 | 64.7% | [write_gguf_script](/Users/mac/Dev/MoroAI/moro/src/moro/export/gguf.py:17), [convert_to_gguf_direct](/Users/mac/Dev/MoroAI/moro/src/moro/export/gguf.py:85) |
| [manifest.py](/Users/mac/Dev/MoroAI/moro/src/moro/export/manifest.py) | 175 | 95.2% | [export_adapter](/Users/mac/Dev/MoroAI/moro/src/moro/export/manifest.py:18), [generate_manifest](/Users/mac/Dev/MoroAI/moro/src/moro/export/manifest.py:62), [write_manifest](/Users/mac/Dev/MoroAI/moro/src/moro/export/manifest.py:99), [generate_model_card](/Users/mac/Dev/MoroAI/moro/src/moro/export/manifest.py:108), [write_model_card](/Users/mac/Dev/MoroAI/moro/src/moro/export/manifest.py:169) |
| [merge.py](/Users/mac/Dev/MoroAI/moro/src/moro/export/merge.py) | 96 | 21.1% | [merge_adapter_into_base](/Users/mac/Dev/MoroAI/moro/src/moro/export/merge.py:15) |
| [ollama.py](/Users/mac/Dev/MoroAI/moro/src/moro/export/ollama.py) | 72 | 77.8% | [generate_ollama_package](/Users/mac/Dev/MoroAI/moro/src/moro/export/ollama.py:12) |
| [paths.py](/Users/mac/Dev/MoroAI/moro/src/moro/export/paths.py) | 28 | 88.9% | [deployment_directory](/Users/mac/Dev/MoroAI/moro/src/moro/export/paths.py:9) |

## src/moro/flywheel

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/__init__.py) | 49 | 100.0% | Package declarations / no top-level callable |
| [architecture.py](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/architecture.py) | 70 | 100.0% | [AbstractLogIngestor](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/architecture.py:13), [AbstractPreferenceExtractor](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/architecture.py:37), [AbstractSyntheticGenerator](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/architecture.py:46), [AbstractDPOTrainerBridge](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/architecture.py:55), [AbstractDeploymentGate](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/architecture.py:64) |

## src/moro/flywheel/extractors

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/extractors/__init__.py) | 5 | 100.0% | Package declarations / no top-level callable |
| [deterministic_extractor.py](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/extractors/deterministic_extractor.py) | 171 | 89.0% | [DeterministicPreferenceExtractor](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/extractors/deterministic_extractor.py:17) |

## src/moro/flywheel/generators

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/generators/__init__.py) | 8 | 100.0% | Package declarations / no top-level callable |
| [grounded_generator.py](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/generators/grounded_generator.py) | 120 | 56.5% | [OllamaGroundedGenerator](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/generators/grounded_generator.py:17), [DeterministicGroundedGenerator](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/generators/grounded_generator.py:90) |

## src/moro/flywheel/ingestors

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/ingestors/__init__.py) | 5 | 100.0% | Package declarations / no top-level callable |
| [sqlite_ingestor.py](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/ingestors/sqlite_ingestor.py) | 301 | 83.5% | [SQLiteLogIngestor](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/ingestors/sqlite_ingestor.py:20) |

## src/moro/flywheel

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [models.py](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/models.py) | 74 | 100.0% | [FeedbackType](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/models.py:15), [InferenceLogPayload](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/models.py:24), [PreferencePair](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/models.py:38), [FeedbackEntry](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/models.py:52), [RefinedTrainingPair](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/models.py:65) |
| [orchestrator.py](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/orchestrator.py) | 281 | 85.3% | [FlywheelConfig](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/orchestrator.py:32), [DPOExecutionSummary](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/orchestrator.py:50), [MoroAIFlywheelOrchestrator](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/orchestrator.py:88), [FlywheelOrchestrator](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/orchestrator.py:243) |

## src/moro/flywheel/storage

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/storage/__init__.py) | 9 | 100.0% | Package declarations / no top-level callable |
| [schema.py](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/storage/schema.py) | 126 | 100.0% | [initialize_production_db](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/storage/schema.py:84), [get_production_db](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/storage/schema.py:99), [get_db_stats](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/storage/schema.py:107) |

## src/moro/flywheel/webhook

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/webhook/__init__.py) | 9 | 100.0% | Package declarations / no top-level callable |
| [receiver.py](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/webhook/receiver.py) | 231 | 76.2% | [WebhookConfig](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/webhook/receiver.py:21), [get_config](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/webhook/receiver.py:38), [set_config](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/webhook/receiver.py:45), [WebhookRequestHandler](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/webhook/receiver.py:50), [start_webhook_receiver](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/webhook/receiver.py:214) |

## src/moro/hardware

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/hardware/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |
| [detector.py](/Users/mac/Dev/MoroAI/moro/src/moro/hardware/detector.py) | 135 | 55.1% | [_get_vram_gb](/Users/mac/Dev/MoroAI/moro/src/moro/hardware/detector.py:11), [detect_hardware](/Users/mac/Dev/MoroAI/moro/src/moro/hardware/detector.py:48) |
| [profile.py](/Users/mac/Dev/MoroAI/moro/src/moro/hardware/profile.py) | 20 | 100.0% | [HardwareProfile](/Users/mac/Dev/MoroAI/moro/src/moro/hardware/profile.py:8) |

## src/moro

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [main.py](/Users/mac/Dev/MoroAI/moro/src/moro/main.py) | 121 | 93.0% | [version_callback](/Users/mac/Dev/MoroAI/moro/src/moro/main.py:35), [main](/Users/mac/Dev/MoroAI/moro/src/moro/main.py:42), [version_command](/Users/mac/Dev/MoroAI/moro/src/moro/main.py:116) |

## src/moro/models

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/models/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |
| [loading.py](/Users/mac/Dev/MoroAI/moro/src/moro/models/loading.py) | 34 | 90.9% | [resolve_model_reference](/Users/mac/Dev/MoroAI/moro/src/moro/models/loading.py:6), [model_load_options](/Users/mac/Dev/MoroAI/moro/src/moro/models/loading.py:31) |

## src/moro/recipes

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |
| [engine.py](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/engine.py) | 310 | 97.1% | [RecipeSuggestion](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/engine.py:19), [_get_target_modules](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/engine.py:56), [suggest_recipe](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/engine.py:66), [predict_peak_vram_gb](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/engine.py:219), [RecipeEngine](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/engine.py:255) |
| [mixing.py](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/mixing.py) | 139 | 100.0% | [MixingStrategy](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/mixing.py:29), [calculate_mixing_strategy](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/mixing.py:54), [estimate_jargon_divergence](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/mixing.py:122) |
| [presets.py](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/presets.py) | 155 | 93.9% | [RecipePreset](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/presets.py:15), [get_preset_for_vram](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/presets.py:142) |
| [rules.py](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/rules.py) | 65 | 100.0% | [infer_parameter_billions](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/rules.py:11), [estimate_memory](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/rules.py:37) |

## src/moro/registry

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/registry/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |
| [manager.py](/Users/mac/Dev/MoroAI/moro/src/moro/registry/manager.py) | 184 | 93.1% | [ModelRegistry](/Users/mac/Dev/MoroAI/moro/src/moro/registry/manager.py:19) |

## src/moro/release

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/release/__init__.py) | 5 | 100.0% | Package declarations / no top-level callable |
| [manager.py](/Users/mac/Dev/MoroAI/moro/src/moro/release/manager.py) | 132 | 98.2% | [ReleaseManager](/Users/mac/Dev/MoroAI/moro/src/moro/release/manager.py:22) |

## src/moro/runtime

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/runtime/__init__.py) | 19 | 100.0% | Package declarations / no top-level callable |
| [orchestrator.py](/Users/mac/Dev/MoroAI/moro/src/moro/runtime/orchestrator.py) | 871 | 73.8% | [ExecutionState](/Users/mac/Dev/MoroAI/moro/src/moro/runtime/orchestrator.py:32), [ExecutionPhase](/Users/mac/Dev/MoroAI/moro/src/moro/runtime/orchestrator.py:46), [ExecutionContext](/Users/mac/Dev/MoroAI/moro/src/moro/runtime/orchestrator.py:63), [MoroRuntimeOrchestrator](/Users/mac/Dev/MoroAI/moro/src/moro/runtime/orchestrator.py:167), [get_runtime](/Users/mac/Dev/MoroAI/moro/src/moro/runtime/orchestrator.py:855), [reset_runtime](/Users/mac/Dev/MoroAI/moro/src/moro/runtime/orchestrator.py:868) |

## src/moro/services

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/services/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |
| [orchestrator.py](/Users/mac/Dev/MoroAI/moro/src/moro/services/orchestrator.py) | 513 | 44.8% | [is_port_open](/Users/mac/Dev/MoroAI/moro/src/moro/services/orchestrator.py:28), [ServiceDefinition](/Users/mac/Dev/MoroAI/moro/src/moro/services/orchestrator.py:37), [ServiceStatusList](/Users/mac/Dev/MoroAI/moro/src/moro/services/orchestrator.py:65), [ServiceOrchestrator](/Users/mac/Dev/MoroAI/moro/src/moro/services/orchestrator.py:97) |

## src/moro/state

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/state/__init__.py) | 6 | 100.0% | Package declarations / no top-level callable |
| [manager.py](/Users/mac/Dev/MoroAI/moro/src/moro/state/manager.py) | 544 | 89.7% | [StateManager](/Users/mac/Dev/MoroAI/moro/src/moro/state/manager.py:25) |
| [schema.py](/Users/mac/Dev/MoroAI/moro/src/moro/state/schema.py) | 234 | 98.1% | [NodeType](/Users/mac/Dev/MoroAI/moro/src/moro/state/schema.py:15), [EdgeType](/Users/mac/Dev/MoroAI/moro/src/moro/state/schema.py:30), [NodeStatus](/Users/mac/Dev/MoroAI/moro/src/moro/state/schema.py:45), [initialize_state_db](/Users/mac/Dev/MoroAI/moro/src/moro/state/schema.py:205), [get_state_db](/Users/mac/Dev/MoroAI/moro/src/moro/state/schema.py:222) |

## src/moro/storage

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/storage/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |
| [db.py](/Users/mac/Dev/MoroAI/moro/src/moro/storage/db.py) | 380 | 90.9% | [utcnow](/Users/mac/Dev/MoroAI/moro/src/moro/storage/db.py:11), [get_db_path](/Users/mac/Dev/MoroAI/moro/src/moro/storage/db.py:16), [get_connection](/Users/mac/Dev/MoroAI/moro/src/moro/storage/db.py:20), [ensure_schema](/Users/mac/Dev/MoroAI/moro/src/moro/storage/db.py:33), [get_or_create_project](/Users/mac/Dev/MoroAI/moro/src/moro/storage/db.py:129), [get_or_create_dataset_source](/Users/mac/Dev/MoroAI/moro/src/moro/storage/db.py:153), [add_dataset_version](/Users/mac/Dev/MoroAI/moro/src/moro/storage/db.py:191), [get_latest_dataset_version](/Users/mac/Dev/MoroAI/moro/src/moro/storage/db.py:220), [create_run](/Users/mac/Dev/MoroAI/moro/src/moro/storage/db.py:232), [update_run_status](/Users/mac/Dev/MoroAI/moro/src/moro/storage/db.py:266), [get_latest_run](/Users/mac/Dev/MoroAI/moro/src/moro/storage/db.py:304), [list_runs](/Users/mac/Dev/MoroAI/moro/src/moro/storage/db.py:311), [add_eval_run](/Users/mac/Dev/MoroAI/moro/src/moro/storage/db.py:323), [add_artifact](/Users/mac/Dev/MoroAI/moro/src/moro/storage/db.py:363) |
| [state_graph.py](/Users/mac/Dev/MoroAI/moro/src/moro/storage/state_graph.py) | 157 | 81.7% | [StateGraphManager](/Users/mac/Dev/MoroAI/moro/src/moro/storage/state_graph.py:19) |

## src/moro/templates

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/templates/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |
| [project.py](/Users/mac/Dev/MoroAI/moro/src/moro/templates/project.py) | 161 | 100.0% | [readme_template](/Users/mac/Dev/MoroAI/moro/src/moro/templates/project.py:32), [default_moro_yaml](/Users/mac/Dev/MoroAI/moro/src/moro/templates/project.py:65) |

## src/moro/training

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/training/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |
| [async_runner.py](/Users/mac/Dev/MoroAI/moro/src/moro/training/async_runner.py) | 97 | 89.5% | [AsyncTrainingRunner](/Users/mac/Dev/MoroAI/moro/src/moro/training/async_runner.py:20) |
| [backend.py](/Users/mac/Dev/MoroAI/moro/src/moro/training/backend.py) | 56 | 100.0% | [TrainingBackend](/Users/mac/Dev/MoroAI/moro/src/moro/training/backend.py:14) |
| [hf_backend.py](/Users/mac/Dev/MoroAI/moro/src/moro/training/hf_backend.py) | 405 | 65.3% | [_require_imports](/Users/mac/Dev/MoroAI/moro/src/moro/training/hf_backend.py:24), [HuggingFaceBackend](/Users/mac/Dev/MoroAI/moro/src/moro/training/hf_backend.py:42) |
| [recovery.py](/Users/mac/Dev/MoroAI/moro/src/moro/training/recovery.py) | 166 | 77.5% | [apply_oom_recovery_protocol](/Users/mac/Dev/MoroAI/moro/src/moro/training/recovery.py:30), [summarize_recovery](/Users/mac/Dev/MoroAI/moro/src/moro/training/recovery.py:159) |
| [runner.py](/Users/mac/Dev/MoroAI/moro/src/moro/training/runner.py) | 237 | 83.5% | [TrainingResult](/Users/mac/Dev/MoroAI/moro/src/moro/training/runner.py:21), [TrainingRunner](/Users/mac/Dev/MoroAI/moro/src/moro/training/runner.py:49) |

## src/moro/ui

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/ui/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |
| [server.py](/Users/mac/Dev/MoroAI/moro/src/moro/ui/server.py) | 1278 | 17.8% | [check_port_open](/Users/mac/Dev/MoroAI/moro/src/moro/ui/server.py:29), [get_local_services](/Users/mac/Dev/MoroAI/moro/src/moro/ui/server.py:37), [get_project_state](/Users/mac/Dev/MoroAI/moro/src/moro/ui/server.py:104), [query_ollama](/Users/mac/Dev/MoroAI/moro/src/moro/ui/server.py:193), [DashboardRequestHandler](/Users/mac/Dev/MoroAI/moro/src/moro/ui/server.py:209), [start_server](/Users/mac/Dev/MoroAI/moro/src/moro/ui/server.py:1264) |

## src/moro/validation

| Module | Lines | Coverage | Top-level symbols |
|---|---:|---:|---|
| [__init__.py](/Users/mac/Dev/MoroAI/moro/src/moro/validation/__init__.py) | 1 | 100.0% | Package declarations / no top-level callable |
| [engine.py](/Users/mac/Dev/MoroAI/moro/src/moro/validation/engine.py) | 237 | 82.9% | [ValidationCheck](/Users/mac/Dev/MoroAI/moro/src/moro/validation/engine.py:27), [ValidationReport](/Users/mac/Dev/MoroAI/moro/src/moro/validation/engine.py:33), [validate_project](/Users/mac/Dev/MoroAI/moro/src/moro/validation/engine.py:43) |
