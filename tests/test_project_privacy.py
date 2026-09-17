import subprocess

from typer.testing import CliRunner

from moro.main import app


def test_initialized_project_git_ignores_private_inputs(tmp_path):
    root = tmp_path / "private-project"
    result = CliRunner().invoke(app, ["init", str(root)])
    assert result.exit_code == 0, result.output
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    paths = ["data/raw/customer.jsonl", "data/raw/nested/notes.txt", ".env", ".env.production",
             "weights/adapter_model.safetensors", "weights/pytorch_model.bin", "model.gguf"]
    result = subprocess.run(["git", "check-ignore", "--stdin"], cwd=root,
                            input="\n".join(paths) + "\n", text=True, capture_output=True)
    assert result.returncode == 0
    assert set(result.stdout.splitlines()) == set(paths)
    visible = subprocess.run(["git", "check-ignore", "--stdin"], cwd=root,
                             input="moro.yaml\neval/support-golden-v1.yaml\ndata/raw/.gitkeep\n",
                             text=True, capture_output=True)
    assert visible.returncode == 1
    assert not visible.stdout
