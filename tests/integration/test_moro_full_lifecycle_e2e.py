"""
End-to-End Master Lifecycle Test for MoroAI.

Tests every single architectural component and CLI command in an integrated,
realistic workflow:
  1.  moro doctor
  2.  moro init
  3.  moro status
  4.  moro guard (scan, redact, check)
  5.  moro import
  6.  moro data build (with Epistemic Quality, PPMI, Resnik IC, MI Guard)
  7.  moro data report
  8.  moro data inspect
  9.  moro recipe suggest & apply (with Catastrophic Forgetting Auto-Ratio)
  10. moro hooks (install, check, uninstall)
  11. moro runs (list, show, compare)
  12. moro eval (perturb)
  13. moro export (adapter, ollama, gguf)
  14. moro diagnose
  15. moro flywheel (status, ingest, run cycle, DPO dataset generation, history)
"""

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from moro.main import app

runner = CliRunner()


def test_moro_full_lifecycle_master_e2e(tmp_path: Path, monkeypatch):
    project_dir = tmp_path / "quantum_foundry"

    # ---------------------------------------------------------
    # 1. moro doctor
    # ---------------------------------------------------------
    res_doc = runner.invoke(app, ["doctor"])
    assert res_doc.exit_code in (0, 1, 2, 3)
    assert "MoroAI Environment Check" in res_doc.stdout

    # ---------------------------------------------------------
    # 2. moro init
    # ---------------------------------------------------------
    res_init = runner.invoke(app, ["init", str(project_dir)])
    assert res_init.exit_code == 0
    assert (project_dir / "moro.yaml").exists()
    assert (project_dir / "data" / "raw").exists()
    assert (project_dir / "eval" / "support-golden-v1.yaml").exists()

    # Change working directory into the project directory
    monkeypatch.chdir(project_dir)

    # ---------------------------------------------------------
    # 3. moro status (initial)
    # ---------------------------------------------------------
    res_status = runner.invoke(app, ["status"])
    assert res_status.exit_code == 0
    assert "MoroAI Project Status" in res_status.stdout

    # ---------------------------------------------------------
    # 4. moro guard (scan, redact, check)
    # ---------------------------------------------------------
    dirty_file = project_dir / "dirty_data.jsonl"
    dirty_file.write_text(
        json.dumps(
            {
                "prompt": "Contact john.doe@example.com or use key sk-1234567890abcdef1234567890abcdef",
                "completion": "Call +1-555-019-2834 for support.",
            }
        )
        + "\n"
        + json.dumps(
            {
                "prompt": "Explain quantum entanglement.",
                "completion": "Quantum entanglement occurs when particles remain connected.",
            }
        )
        + "\n"
        + json.dumps(
            {
                "prompt": "What is quantum superposition?",
                "completion": "Superposition allows a quantum state to exist across linear combinations of basis states.",
            }
        )
        + "\n"
        + json.dumps(
            {
                "prompt": "Define quantum decoherence.",
                "completion": "Decoherence is the loss of quantum coherence due to environmental interaction.",
            }
        )
        + "\n"
        + json.dumps(
            {
                "prompt": "How does Shor's algorithm work?",
                "completion": "Shor's algorithm factors integers in polynomial time using quantum Fourier transforms.",
            }
        )
        + "\n"
    )

    # 4a. guard scan detects PII
    res_scan = runner.invoke(app, ["guard", "scan", str(dirty_file)])
    assert res_scan.exit_code == 0
    assert "Privacy Guard Alert" in res_scan.stdout
    assert "email" in res_scan.stdout

    # 4b. guard check fails because PII is present
    res_chk_fail = runner.invoke(app, ["guard", "check", str(dirty_file)])
    assert res_chk_fail.exit_code == 1

    # 4c. guard redact sanitizes the file
    clean_file = project_dir / "clean_data.jsonl"
    res_redact = runner.invoke(
        app, ["guard", "redact", str(dirty_file), "--output", str(clean_file)]
    )
    assert res_redact.exit_code == 0
    assert "Redacted" in res_redact.stdout

    # Verify clean_file passes guard check
    res_chk_pass = runner.invoke(app, ["guard", "check", str(clean_file)])
    assert res_chk_pass.exit_code == 0

    clean_content = clean_file.read_text()
    assert "[REDACTED_EMAIL]" in clean_content

    # ---------------------------------------------------------
    # 5. moro import
    # ---------------------------------------------------------
    res_import = runner.invoke(app, ["import", str(clean_file)])
    assert res_import.exit_code == 0
    assert "Registered dataset source" in res_import.stdout

    # ---------------------------------------------------------
    # 6. moro data build with Epistemic Quality, PPMI & MI Guard
    # ---------------------------------------------------------
    # Create a domain glossary
    glossary_file = project_dir / "domain_glossary.txt"
    glossary_file.write_text(
        "quantum\nentanglement\nsupremacy\nqubit\nhamiltonian\nsuperposition\n"
    )

    # Add an edge case row with high jargon density
    edge_file = project_dir / "edge_case.jsonl"
    edge_file.write_text(
        json.dumps(
            {
                "prompt": "Qubit Hamiltonian state.",
                "completion": "Superposition of qubit Hamiltonian yields quantum supremacy.",
            }
        )
        + "\n"
    )
    runner.invoke(app, ["import", str(edge_file)])

    # Update moro.yaml to point to the imported data and glossary file
    moro_yaml = project_dir / "moro.yaml"
    with open(moro_yaml) as f:
        cfg = yaml.safe_load(f)
    cfg.setdefault("dataset", {})["source"] = "data/raw/clean_data.jsonl"
    cfg["dataset"]["domain_glossary"] = "domain_glossary.txt"
    cfg.setdefault("release", {}).setdefault("require", {})["safety_pass"] = False
    with open(moro_yaml, "w") as f:
        yaml.safe_dump(cfg, f)

    res_build = runner.invoke(app, ["data", "build"])
    if res_build.exit_code != 0:
        print("DATA BUILD ERROR:", res_build.stdout)
    assert res_build.exit_code == 0
    assert "Dataset built successfully!" in res_build.stdout

    # Verify build artifacts
    versions_dir = project_dir / "data" / "versions"
    version_dirs = [d for d in versions_dir.iterdir() if d.is_dir()]
    assert len(version_dirs) >= 1
    latest_version = version_dirs[0]
    assert (latest_version / "train.jsonl").exists()
    assert (latest_version / "report.json").exists()

    with open(latest_version / "report.json") as f:
        stats = json.load(f)
        assert "classification_counts" in stats
        assert "avg_zlib_entropy" in stats
        assert "avg_ppmi" in stats

    # ---------------------------------------------------------
    # 7. moro data report
    # ---------------------------------------------------------
    res_report = runner.invoke(app, ["data", "report"])
    assert res_report.exit_code == 0
    assert "Dataset Quality Report" in res_report.stdout

    # ---------------------------------------------------------
    # 8. moro data inspect
    # ---------------------------------------------------------
    res_inspect = runner.invoke(app, ["data", "inspect", "--n", "2"])
    assert res_inspect.exit_code == 0
    assert "Row 1" in res_inspect.stdout or "Dataset:" in res_inspect.stdout

    # ---------------------------------------------------------
    # 9. moro recipe suggest & apply
    # ---------------------------------------------------------
    res_recipe = runner.invoke(app, ["recipe", "suggest", "--target-vram", "16.0"])
    assert res_recipe.exit_code == 0
    assert "Suggested Training Recipe" in res_recipe.stdout
    assert "domain_ratio" in res_recipe.stdout or "replay_ratio" in res_recipe.stdout

    # Apply recipe with -y
    res_apply = runner.invoke(app, ["recipe", "apply", "-y", "--target-vram", "16.0"])
    assert res_apply.exit_code == 0
    assert "updated" in res_apply.stdout

    # ---------------------------------------------------------
    # 10. moro hooks (install, check, uninstall)
    # ---------------------------------------------------------
    import subprocess

    subprocess.run(["git", "init"], cwd=str(project_dir), capture_output=True)
    res_hook_inst = runner.invoke(app, ["hooks", "install"])
    assert res_hook_inst.exit_code == 0
    assert "safety hooks installed" in res_hook_inst.stdout
    assert (project_dir / ".git" / "hooks" / "pre-commit").exists()

    res_hook_chk = runner.invoke(app, ["hooks", "check"])
    assert res_hook_chk.exit_code == 0

    res_hook_uninst = runner.invoke(app, ["hooks", "uninstall"])
    assert res_hook_uninst.exit_code == 0
    assert not (project_dir / ".git" / "hooks" / "pre-commit").exists()

    # ---------------------------------------------------------
    # 11. Training Registration & Runs Inspection
    # ---------------------------------------------------------
    from moro.config.loader import load_config
    from moro.core.hashing import sha256_text
    from moro.storage import db

    config = load_config(project_dir / "moro.yaml")
    conn = db.get_connection(project_dir)
    project_id = db.get_or_create_project(conn, config.project.name)

    run_dir_1 = project_dir / "runs" / "run_quantum_1"
    run_dir_1.mkdir(parents=True, exist_ok=True)
    (run_dir_1 / "config.json").write_text(config.model_dump_json(indent=2))

    run_1 = db.create_run(
        conn,
        project_id,
        sha256_text(config.model_dump_json()),
        config.model.name,
        config.model.quantization,
        str(run_dir_1),
        run_name="qwen-quantum-v1",
    )
    db.update_run_status(
        conn,
        run_1,
        "completed",
        train_loss=1.85,
        validation_loss=1.72,
        peak_vram_gb=4.2,
        tokens_per_sec=120.0,
    )

    run_dir_2 = project_dir / "runs" / "run_quantum_2"
    adapter_dir = run_dir_2 / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    (run_dir_2 / "config.json").write_text(config.model_dump_json(indent=2))
    (adapter_dir / "adapter_config.json").write_text(
        json.dumps(
            {
                "peft_type": "LORA",
                "r": 16,
                "base_model_name_or_path": config.model.name,
            }
        )
    )
    (adapter_dir / "adapter_model.safetensors").write_bytes(b"synthetic weights")

    run_2 = db.create_run(
        conn,
        project_id,
        sha256_text(config.model_dump_json()),
        config.model.name,
        config.model.quantization,
        str(run_dir_2),
        run_name="qwen-quantum-v2",
    )
    db.update_run_status(
        conn,
        run_2,
        "completed",
        train_loss=1.12,
        validation_loss=1.05,
        peak_vram_gb=5.1,
        tokens_per_sec=135.0,
    )
    conn.close()

    # 11a. moro runs list
    res_runs = runner.invoke(app, ["runs", "list"])
    assert res_runs.exit_code == 0
    assert run_1 in res_runs.stdout
    assert run_2 in res_runs.stdout

    # 11b. moro runs show
    res_show = runner.invoke(app, ["runs", "show", run_1])
    assert res_show.exit_code == 0
    assert "qwen-quantum-v1" in res_show.stdout

    # 11c. moro runs compare
    res_comp = runner.invoke(app, ["runs", "compare", run_1, run_2])
    assert res_comp.exit_code == 0

    # ---------------------------------------------------------
    # 12. moro eval perturb (Adversarial Robustness)
    # ---------------------------------------------------------
    suite_file = project_dir / "eval" / "quantum_eval.yaml"
    suite_data = {
        "name": "quantum_eval",
        "description": "Evaluation suite for quantum concepts",
        "cases": [
            {
                "id": "case_1",
                "messages": [{"role": "user", "content": "Define quantum superposition."}],
                "expect": {"contains": ["superposition"]},
            },
            {
                "id": "case_2",
                "messages": [{"role": "user", "content": "Explain quantum entanglement simply."}],
                "expect": {"contains": ["entanglement"]},
            },
        ],
    }
    with open(suite_file, "w") as f:
        yaml.safe_dump(suite_data, f)

    perturbed_out = project_dir / "eval" / "perturbed_suite.yaml"
    res_perturb = runner.invoke(
        app, ["eval", "perturb", str(suite_file), "--output", str(perturbed_out), "--seed", "42"]
    )
    assert res_perturb.exit_code == 0
    assert "Perturbed eval suite exported" in res_perturb.stdout
    assert perturbed_out.exists()

    # ---------------------------------------------------------
    # 13. moro export (adapter, ollama, gguf)
    # ---------------------------------------------------------
    export_out = project_dir / "export_artifacts"

    # 13a. Export adapter
    res_exp_ad = runner.invoke(
        app,
        [
            "export",
            "--run-id",
            run_2,
            "--format",
            "adapter",
            "--out",
            str(export_out / "adapter_run"),
        ],
    )
    assert res_exp_ad.exit_code == 0, f"EXPORT ADAPTER FAILED: {res_exp_ad.output}"
    assert (export_out / "adapter_run" / "adapter" / "adapter_config.json").exists()

    # 13b. Export ollama Modelfile
    res_exp_ol = runner.invoke(
        app,
        [
            "export",
            "--run-id",
            run_2,
            "--format",
            "ollama",
            "--out",
            str(export_out / "ollama_run"),
        ],
    )
    assert res_exp_ol.exit_code == 0, f"EXPORT OLLAMA FAILED: {res_exp_ol.output}"
    assert (export_out / "ollama_run" / "ollama_package" / "Modelfile").exists()

    # 13c. Export gguf script
    res_exp_gguf = runner.invoke(
        app,
        ["export", "--run-id", run_2, "--format", "gguf", "--out", str(export_out / "gguf_run")],
    )
    assert res_exp_gguf.exit_code in (0, 1, 3), f"EXPORT GGUF FAILED: {res_exp_gguf.output}"
    if res_exp_gguf.exit_code == 0:
        assert (export_out / "gguf_run" / "gguf" / "convert_to_gguf.sh").exists()
    elif res_exp_gguf.exit_code == 3:
        assert "Dependency error" in res_exp_gguf.output
    else:
        assert (
            "not available in the local cache" in res_exp_gguf.output
            or "Error:" in res_exp_gguf.output
        )

    # 14a. Diagnose completed run
    res_diag_comp = runner.invoke(app, ["diagnose", "--run-id", run_1])
    assert res_diag_comp.exit_code == 0, (
        f"DIAG COMP FAILED: {res_diag_comp.output}, exc={res_diag_comp.exception}"
    )
    assert "completed successfully" in res_diag_comp.stdout

    # 14b. Diagnose failed run with CUDA OOM
    conn = db.get_connection(project_dir)
    run_failed = db.create_run(
        conn,
        project_id,
        "hash_fail",
        config.model.name,
        config.model.quantization,
        str(project_dir / "runs" / "failed_run"),
        run_name="failed-oom-run",
    )
    db.update_run_status(
        conn,
        run_failed,
        "failed",
        error="CUDA out of memory. Tried to allocate 2.00 GiB (GPU 0; 7.93 GiB total capacity)",
    )
    conn.close()

    res_diag_fail = runner.invoke(app, ["diagnose", "--run-id", run_failed])
    assert res_diag_fail.exit_code == 0
    assert "GPU out of memory" in res_diag_fail.stdout or "OOM" in res_diag_fail.stdout
    assert "Recommended actions" in res_diag_fail.stdout

    # ---------------------------------------------------------
    # 15. moro flywheel (status, ingest, run, history)
    # ---------------------------------------------------------
    flywheel_db = project_dir / "production_logs.db"
    dpo_out = project_dir / "data" / "dpo_dataset"

    # 15a. Initial status
    res_fw_stat = runner.invoke(app, ["flywheel", "status", "--db", str(flywheel_db)])
    assert res_fw_stat.exit_code == 0
    assert "Pending Unprocessed Logs: 0" in res_fw_stat.stdout

    # 15b. Ingest production logs
    prod_logs = project_dir / "prod_traffic.jsonl"
    prod_logs.write_text(
        json.dumps(
            {
                "session_id": "sess-alpha",
                "prompt": "What is quantum tunneling?",
                "completion": "Quantum tunneling is magic.",
                "human_correction": "Quantum tunneling is a quantum mechanical phenomenon where a wavefunction can propagate through a potential barrier.",
            }
        )
        + "\n"
        + json.dumps(
            {
                "session_id": "sess-beta",
                "prompt": "Define a qubit.",
                "completion": "A qubit is the basic unit of quantum information, analogous to a classical bit.",
                "user_rating": 1.0,
            }
        )
        + "\n"
        + json.dumps(
            {
                "session_id": "sess-gamma",
                "prompt": "How to build a quantum computer?",
                "completion": "You need hardware.",
                "user_rating": 0.0,
            }
        )
        + "\n"
    )
    res_fw_ingest = runner.invoke(
        app, ["flywheel", "ingest", str(prod_logs), "--db", str(flywheel_db)]
    )
    assert res_fw_ingest.exit_code == 0
    assert "Ingested 3 production logs" in res_fw_ingest.stdout

    # 15c. Flywheel status shows 3 pending
    res_fw_stat2 = runner.invoke(app, ["flywheel", "status", "--db", str(flywheel_db)])
    assert "Pending Unprocessed Logs: 3" in res_fw_stat2.stdout

    # 15d. Execute continuous learning cycle
    res_fw_run = runner.invoke(
        app,
        [
            "flywheel",
            "run",
            "--db",
            str(flywheel_db),
            "--output-dir",
            str(dpo_out),
            "--min-pairs",
            "1",
        ],
    )
    assert res_fw_run.exit_code == 0
    assert "DPO Flywheel Cycle Completed" in res_fw_run.stdout
    assert "Preference Pairs Generated:" in res_fw_run.stdout

    # Verify DPO output files
    dpo_files = list(dpo_out.glob("dpo_*.jsonl"))
    assert len(dpo_files) > 0, f"No DPO dataset found in {dpo_out}"
    dpo_file = dpo_files[0]
    assert dpo_file.exists()

    with open(dpo_file) as f:
        lines = [json.loads(line) for line in f if line.strip()]
        assert len(lines) >= 2
        for pair in lines:
            assert "prompt" in pair
            assert "chosen" in pair
            assert "rejected" in pair
            assert "feedback_type" in pair

    # 15e. History shows completed epoch
    res_fw_hist = runner.invoke(app, ["flywheel", "history", "--db", str(flywheel_db)])
    assert res_fw_hist.exit_code == 0
    assert "completed" in res_fw_hist.stdout

    # ---------------------------------------------------------
    # 16. moro analytics (list, show, trend, recommend)
    # ---------------------------------------------------------
    from moro.analytics.tracker import ExperimentTracker

    analytics_tracker = ExperimentTracker(project_dir / ".moro" / "analytics.db")
    exp_master = analytics_tracker.create_experiment(
        name="master_lifecycle_run",
        base_model="Qwen/Qwen2.5-1.5B",
    )
    analytics_tracker.start_experiment(exp_master, {"learning_rate": 2e-4, "lora_r": 16})
    analytics_tracker.complete_experiment(
        exp_master,
        final_train_loss=1.25,
        final_eval_loss=1.35,
        eval_pass_rate=0.88,
        eval_delta=0.08,
    )

    exp_master2 = analytics_tracker.create_experiment(
        name="master_lifecycle_run_2",
        base_model="Qwen/Qwen2.5-1.5B",
    )
    analytics_tracker.start_experiment(exp_master2, {"learning_rate": 1e-4, "lora_r": 8})
    analytics_tracker.complete_experiment(
        exp_master2,
        final_train_loss=1.45,
        final_eval_loss=1.55,
        eval_pass_rate=0.80,
        eval_delta=0.03,
    )

    res_an_list = runner.invoke(app, ["analytics", "list"])
    assert res_an_list.exit_code == 0
    assert "MoroAI Experiments" in res_an_list.stdout

    res_an_show = runner.invoke(app, ["analytics", "show", exp_master])
    assert res_an_show.exit_code == 0
    assert exp_master in res_an_show.stdout

    res_an_trend = runner.invoke(app, ["analytics", "trend"])
    assert res_an_trend.exit_code == 0
    assert "Model Quality Trend" in res_an_trend.stdout

    res_an_rec = runner.invoke(app, ["analytics", "recommend"])
    assert res_an_rec.exit_code == 0
    assert "Experiment Recommendations" in res_an_rec.stdout
