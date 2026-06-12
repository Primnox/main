# backend/backup_providers/s3.py
"""
S3-compatible provider — works with:
  • AWS S3               (leave endpoint_url blank)
  • Backblaze B2         endpoint_url = https://s3.us-west-002.backblazeb2.com
  • Cloudflare R2        endpoint_url = https://<account>.r2.cloudflarestorage.com
  • Wasabi               endpoint_url = https://s3.wasabisys.com
  • MinIO / any S3 fork  endpoint_url = http://localhost:9000
"""
from logger import get_logger

log = get_logger("backup.s3")


class S3Provider:
    def __init__(self, cfg: dict):
        self._bucket = cfg.get("bucket", "primnox-backup")
        self._prefix = cfg.get("prefix", "backups/")
        self._kwargs = {
            "aws_access_key_id":     cfg.get("access_key"),
            "aws_secret_access_key": cfg.get("secret_key"),
            "region_name":           cfg.get("region", "us-east-1"),
        }
        endpoint = cfg.get("endpoint_url", "").strip()
        if endpoint:
            self._kwargs["endpoint_url"] = endpoint

    def _client(self):
        try:
            import boto3
        except ImportError:
            raise RuntimeError("boto3 is not installed — run: pip install boto3")
        return boto3.client("s3", **self._kwargs)

    def upload(self, filename: str, data: bytes) -> None:
        key = self._prefix + filename
        log.info(f"S3 upload → s3://{self._bucket}/{key} ({len(data):,} bytes)")
        self._client().put_object(Bucket=self._bucket, Key=key, Body=data)

    def download(self, filename: str) -> bytes:
        key = self._prefix + filename
        log.info(f"S3 download ← s3://{self._bucket}/{key}")
        resp = self._client().get_object(Bucket=self._bucket, Key=key)
        return resp["Body"].read()

    def list_backups(self) -> list[dict]:
        resp = self._client().list_objects_v2(
            Bucket=self._bucket, Prefix=self._prefix
        )
        out = []
        for obj in resp.get("Contents", []):
            name = obj["Key"].removeprefix(self._prefix)
            if name.endswith(".prx"):
                out.append({
                    "name":      name,
                    "size":      obj["Size"],
                    "timestamp": obj["LastModified"].isoformat(),
                })
        return sorted(out, key=lambda x: x["timestamp"], reverse=True)

    def delete(self, filename: str) -> None:
        key = self._prefix + filename
        self._client().delete_object(Bucket=self._bucket, Key=key)
        log.info(f"S3 deleted: {key}")

    def test_connection(self) -> bool:
        try:
            self._client().head_bucket(Bucket=self._bucket)
            return True
        except Exception as e:
            log.warning(f"S3 connection test failed: {e}")
            return False
