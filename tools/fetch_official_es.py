"""从Elastic官方registry下载固定amd64镜像，逐层校验并生成OCI导入包。

仅用标准库。匿名registry令牌与CDN签名地址只在内存使用，不写入输出。
本工具不修改Docker配置，也不连接或修改其他项目的数据库。
"""

from __future__ import annotations

import hashlib
import json
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REFERENCE = "docker.elastic.co/elasticsearch/elasticsearch:8.18.0"
REGISTRY = "https://docker.elastic.co/v2/elasticsearch/elasticsearch"
MANIFEST_DIGEST = "aa388c8e3b1d6390683a543ae551c599bca2137a743c07c59828eaf803f7f710"
CDN = "docker-registry-production.d24a988e385e0074d717b6bdaea58f0d.r2.cloudflarestorage.com"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """手动处理重定向，避免向CDN转发registry认证头。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    destination = root / "tmp" / "es_official_transport_20260904"
    destination.mkdir(exist_ok=False)
    blob_dir = destination / "blobs" / "sha256"
    blob_dir.mkdir(parents=True)
    auth_url = (
        "https://docker-auth.elastic.co/auth?service=token-service"
        "&scope=repository:elasticsearch/elasticsearch:pull"
    )
    with urllib.request.urlopen(auth_url, timeout=30) as response:
        bearer = json.load(response)["token"]
    headers = {
        "Authorization": "Bearer " + bearer,
        "Accept": "application/vnd.docker.distribution.manifest.v2+json",
    }
    manifest_request = urllib.request.Request(
        REGISTRY + "/manifests/sha256:" + MANIFEST_DIGEST, headers=headers,
    )
    with urllib.request.urlopen(manifest_request, timeout=30) as response:
        raw_manifest = response.read()
    if hashlib.sha256(raw_manifest).hexdigest() != MANIFEST_DIGEST:
        raise RuntimeError("官方manifest SHA256与事先读取的固定摘要不符")
    manifest = json.loads(raw_manifest)
    (blob_dir / MANIFEST_DIGEST).write_bytes(raw_manifest)

    def download(descriptor):
        digest_type, digest = descriptor["digest"].split(":", 1)
        if digest_type != "sha256" or len(digest) != 64:
            raise RuntimeError("不支持的镜像摘要格式")
        request = urllib.request.Request(REGISTRY + "/blobs/" + descriptor["digest"])
        request.add_header("Authorization", "Bearer " + bearer)
        opener = urllib.request.build_opener(NoRedirect)
        try:
            stream = opener.open(request, timeout=45)
        except urllib.error.HTTPError as error:
            if error.code not in (301, 302, 303, 307, 308):
                raise RuntimeError(f"registry HTTP {error.code}") from None
            target = error.headers.get("Location", "")
            parsed = urllib.parse.urlsplit(target)
            if parsed.scheme != "https" or parsed.hostname != CDN:
                raise RuntimeError("官方响应的CDN主机不在已核对名单内") from None
            # 全新请求不带registry Authorization；签名地址不写日志、不存盘。
            stream = urllib.request.urlopen(target, timeout=45)
        expected_size = descriptor["size"]
        total = 0
        sha = hashlib.sha256()
        with stream, (blob_dir / digest).open("xb") as output:
            while chunk := stream.read(1024 * 1024):
                sha.update(chunk)
                output.write(chunk)
                total += len(chunk)
        if total != expected_size or sha.hexdigest() != digest:
            raise RuntimeError(f"镜像层校验失败 {digest[:12]}")
        print(f"BLOB_VERIFIED sha256={digest} bytes={total}", flush=True)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(download, [manifest["config"], *manifest["layers"]]))
    (destination / "oci-layout").write_text(
        '{"imageLayoutVersion":"1.0.0"}', encoding="utf-8",
    )
    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [{
            "mediaType": manifest["mediaType"],
            "digest": "sha256:" + MANIFEST_DIGEST,
            "size": len(raw_manifest),
            "platform": {"architecture": "amd64", "os": "linux"},
            "annotations": {
                "io.containerd.image.name": REFERENCE,
                "org.opencontainers.image.ref.name": REFERENCE,
            },
        }],
    }
    (destination / "index.json").write_text(json.dumps(index), encoding="utf-8")
    archive = root / "tmp" / "elasticsearch-8.18.0-official-amd64.tar"
    with tarfile.open(archive, "x") as output:
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                output.add(path, arcname=path.relative_to(destination).as_posix())
    with archive.open("rb") as source:
        archive_sha = hashlib.file_digest(source, "sha256").hexdigest()
    print(json.dumps({
        "result": "OFFICIAL_OCI_VERIFIED", "manifest": MANIFEST_DIGEST,
        "config": manifest["config"]["digest"], "layers": len(manifest["layers"]),
        "archive_sha256": archive_sha, "archive_bytes": archive.stat().st_size,
    }), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # 不输出可能包含CDN签名查询参数或临时认证数据的第三方异常文本。
        print(f"OFFICIAL_OCI_FAILED type={type(error).__name__}", flush=True)
        raise SystemExit(1) from None
