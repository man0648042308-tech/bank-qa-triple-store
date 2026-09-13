"""白名单打包Day37并逐项解压到内存校验；不打包环境、下载缓存或凭据。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

DIRECTORIES = (
    "src", "exercise05", "cypher", "infra", "scripts", "tests", "docs",
    "learning", "tools", "evidence",
)
ROOT_FILES = ("README.md", "Day37作业_提交版.md", "pyproject.toml", "uv.lock", ".gitignore")
SUFFIXES = {".py", ".ps1", ".cypher", ".md", ".yml", ".yaml", ".toml"}
EXCLUDED = {".venv", ".git", "__pycache__", ".pytest_cache", ".ruff_cache", "tmp", "build"}


def build(archive: Path, pdf: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    if archive.exists():
        raise FileExistsError("提交包已存在，请使用新文件名，保留旧包")
    if not pdf.resolve().is_relative_to(root / "output"):
        raise ValueError("PDF必须位于本项目output目录")
    if not (root / "evidence" / "验收记录.md").is_file():
        raise FileNotFoundError("真实验收记录缺失，停止打包")
    paths = [root / name for name in ROOT_FILES]
    paths.append(pdf)
    for name in DIRECTORIES:
        for path in (root / name).rglob("*"):
            relative = path.relative_to(root)
            if (
                path.is_file() and not path.is_symlink()
                and path.suffix in SUFFIXES
                and not any(part in EXCLUDED or part.endswith(".egg-info")
                            or part.startswith(".env") for part in relative.parts)
            ):
                paths.append(path)
    digests = {}
    archive.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive, "x", compression=ZIP_DEFLATED) as output:
        for path in sorted(set(paths)):
            relative = path.relative_to(root).as_posix()
            data = path.read_bytes()
            digests[relative] = hashlib.sha256(data).hexdigest()
            output.writestr(root.name + "/" + relative, data)
        output.writestr(root.name + "/MANIFEST_SHA256.json", json.dumps(
            digests, ensure_ascii=False, indent=2,
        ))
    with ZipFile(archive) as package:
        if package.testzip() is not None:
            raise RuntimeError("ZIP CRC校验失败")
        for name, digest in digests.items():
            data = package.read(root.name + "/" + name)
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError("ZIP逐项解压SHA256校验失败")
    print(json.dumps({
        "result": "SUBMISSION_ZIP_VERIFIED", "files": len(digests),
        "bytes": archive.stat().st_size,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    build(args.archive, args.pdf)
