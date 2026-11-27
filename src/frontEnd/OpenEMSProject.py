"""Project-local storage for openEMS solver runs."""
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile, mkdtemp


def write_json(path, data):
    temporary = NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                  delete=False)
    try:
        with temporary:
            json.dump(data, temporary, indent=2)
        os.replace(temporary.name, path)
    finally:
        Path(temporary.name).unlink(missing_ok=True)


class ProjectRuns:
    def __init__(self, project):
        self.project = Path(project).resolve()
        self.folder = self.project / "openems"
        self.runs = self.folder / "runs"

    def model_path(self, path):
        model = (self.project / path).resolve()
        model.relative_to(self.project)
        if self.runs.resolve() in model.parents:
            raise ValueError("Select the project model outside the run history.")
        return model

    def select(self, path):
        model = self.model_path(path)
        self.folder.mkdir(exist_ok=True)
        write_json(self.folder / "project.json", {
            "type": "xml", "path": model.relative_to(self.project).as_posix()})
        return model

    def selected(self):
        config = self.folder / "project.json"
        if config.exists():
            data = json.loads(config.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("type") != "xml" or not isinstance(data.get("path"), str):
                raise ValueError("Invalid openEMS project settings.")
            return self.model_path(data["path"])

    def prepare(self, model, tree):
        relative = model.relative_to(self.project)
        files = {model}
        for node in tree.iter():
            for key, name in node.attrib.items():
                if key.lower() in ("file", "filename") and name:
                    ref = Path(name)
                    source = self.model_path(model.parent / ref)
                    if ref.is_absolute() or not source.is_file():
                        raise ValueError(f"Use an existing project-relative input file: {name}")
                    files.add(source)
        self.runs.mkdir(parents=True, exist_ok=True)
        prefix = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_")
        run = Path(mkdtemp(prefix=prefix, dir=self.runs))
        try:
            for source in files:
                target = run / "work" / source.relative_to(self.project)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            (run / "solver.log").touch()
            write_json(run / "run.json", {"status": "Running", "model": relative.as_posix()})
        except Exception:
            shutil.rmtree(run)
            raise
        return run, run / "work" / relative
