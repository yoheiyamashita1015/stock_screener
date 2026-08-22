"""ローカル/S3で同じキー構成を使う保存層。"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .config import BatchConfig


class Storage(ABC):
    @abstractmethod
    def exists(self, key: str) -> bool:
        pass

    @abstractmethod
    def read_bytes(self, key: str) -> bytes:
        pass

    @abstractmethod
    def write_bytes(self, key: str, data: bytes) -> None:
        pass

    @abstractmethod
    def list_keys(self, prefix: str) -> list[str]:
        pass

    @abstractmethod
    def last_modified(self, key: str) -> datetime | None:
        pass

    def read_json(self, key: str) -> Any:
        return json.loads(self.read_bytes(key).decode("utf-8"))

    def write_json(self, key: str, data: Any) -> None:
        payload = json.dumps(
            data, ensure_ascii=False, indent=2, allow_nan=False
        ).encode("utf-8")
        self.write_bytes(key, payload)


class LocalStorage(Storage):
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError(f"保存先の範囲外です: {key}")
        return path

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def read_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def write_bytes(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)

    def list_keys(self, prefix: str) -> list[str]:
        base = self._path(prefix)
        if not base.exists():
            return []
        if base.is_file():
            return [prefix]
        return sorted(
            path.relative_to(self.root).as_posix()
            for path in base.rglob("*")
            if path.is_file() and not path.name.endswith(".tmp")
        )

    def last_modified(self, key: str) -> datetime | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


class S3Storage(Storage):
    def __init__(self, bucket: str, prefix: str = ""):
        import boto3

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        # 明示的なアクセスキーは渡さず、ECS/LambdaのIAM Roleを利用します。
        self.client = boto3.client("s3")

    def _key(self, key: str) -> str:
        clean = key.strip("/")
        return f"{self.prefix}/{clean}" if self.prefix else clean

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def read_bytes(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
        return response["Body"].read()

    def write_bytes(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=data)

    def list_keys(self, prefix: str) -> list[str]:
        full_prefix = self._key(prefix)
        paginator = self.client.get_paginator("list_objects_v2")
        result = []
        root_prefix = f"{self.prefix}/" if self.prefix else ""
        for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix):
            for item in page.get("Contents", []):
                key = item["Key"]
                result.append(key[len(root_prefix):] if root_prefix else key)
        return sorted(result)

    def last_modified(self, key: str) -> datetime | None:
        from botocore.exceptions import ClientError

        try:
            response = self.client.head_object(Bucket=self.bucket, Key=self._key(key))
            return response["LastModified"]
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise


def create_storage(config: BatchConfig) -> Storage:
    if config.storage_mode == "s3":
        return S3Storage(config.s3_bucket_name, config.s3_prefix)
    return LocalStorage(config.local_data_dir)
