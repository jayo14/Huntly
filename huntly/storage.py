"""Neon Object Storage backend for Django.

S3-compatible storage that branches with the Neon Postgres branch. Neon
requires path-style addressing (SigV4 only), so the client is built with
``addressing_style="path"``. Credentials and endpoint come from the
AWS-standard env vars that ``neon env pull`` writes:

    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_ENDPOINT_URL_S3, AWS_REGION

The bucket is private, so ``url()`` returns a time-limited presigned GET URL
instead of a permanent public link.
"""

import os
from contextlib import contextmanager
from tempfile import NamedTemporaryFile

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
from django.utils.timezone import now

NEON_BUCKET_ENV = "S3_BUCKET"
NEON_DEFAULT_BUCKET = "assets"
PRESIGNED_URL_EXPIRES = int(os.environ.get("S3_PRESIGNED_URL_EXPIRES", "3600"))


class NeonStorageError(RuntimeError):
    """Raised when Neon Object Storage is not usable."""


def neon_storage_configured():
    """True when the env carries a Neon S3 endpoint and credentials."""
    return bool(
        os.environ.get("AWS_ENDPOINT_URL_S3")
        and os.environ.get("AWS_ACCESS_KEY_ID")
        and os.environ.get("AWS_SECRET_ACCESS_KEY")
    )


@deconstructible
class NeonS3Storage(Storage):
    """Django storage backed by a Neon Object Storage bucket."""

    def __init__(self, bucket=None, endpoint_url=None, region=None):
        self.bucket = bucket or os.environ.get(NEON_BUCKET_ENV, NEON_DEFAULT_BUCKET)
        self.endpoint_url = endpoint_url or os.environ.get("AWS_ENDPOINT_URL_S3")
        self.region = region or os.environ.get("AWS_REGION", "eu-central-1")
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if not neon_storage_configured():
                raise NeonStorageError(
                    "Neon Object Storage is not configured. Run `neon env pull` so "
                    "AWS_ENDPOINT_URL_S3, AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY "
                    "are set, or unset them to fall back to local media storage."
                )
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                region_name=self.region,
                # Neon Object Storage is path-style / SigV4 only.
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
            )
        return self._client

    def _open(self, name, mode="rb"):
        response = self.client.get_object(Bucket=self.bucket, Key=name)
        return ContentFile(response["Body"].read())

    def _save(self, name, content):
        body = content.read()
        self.client.put_object(
            Bucket=self.bucket,
            Key=name,
            Body=body,
            ContentType=getattr(content, "content_type", None)
            or self._guess_type(name),
            # Private bucket: serve through presigned URLs, so keep the object
            # out of intermediary caches.
            CacheControl="private, no-store",
        )
        return name

    def delete(self, name):
        self.client.delete_object(Bucket=self.bucket, Key=name)

    def exists(self, name):
        try:
            self.client.head_object(Bucket=self.bucket, Key=name)
            return True
        except Exception:
            return False

    def size(self, name):
        return self.client.head_object(Bucket=self.bucket, Key=name)["ContentLength"]

    def url(self, name):
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": name},
            ExpiresIn=PRESIGNED_URL_EXPIRES,
        )

    def listdir(self, path=""):
        prefix = f"{path.rstrip('/')}/" if path else ""
        paginator = self.client.get_paginator("list_objects_v2")
        directories, files = set(), []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix, Delimiter="/"):
            for common in page.get("CommonPrefixes", []):
                directories.add(common["Prefix"].rstrip("/").split("/")[-1])
            for item in page.get("Contents", []):
                files.append(item["Key"].split("/")[-1])
        return list(directories), files

    def modified_time(self, name):
        timestamp = self.client.head_object(Bucket=self.bucket, Key=name)["LastModified"]
        return timestamp

    def accessed_time(self, name):
        return self.modified_time(name)

    def get_accessed_time(self, name):
        return self.accessed_time(name)

    def get_modified_time(self, name):
        return self.modified_time(name)

    def path(self, name):
        raise NotImplementedError(
            "Neon Object Storage is remote; there is no local filesystem path. "
            "Use huntly.storage.local_file(field_file) to stage a temp copy."
        )

    @staticmethod
    def _guess_type(name):
        import mimetypes

        return mimetypes.guess_type(name)[0] or "application/octet-stream"


@contextmanager
def local_file(field_file):
    """Stage a stored file on local disk for readers that need a real path.

    The resume DOCX generator shells out to Node, which calls
    ``fs.readFileSync`` on ``passport_photo_path``. Remote objects have no
    local path, so download to a temp file, yield it, then clean up.

    Usage:
        with local_file(resume.passport_photo) as path:
            docx_data["passport_photo_path"] = path
            generate_docx(docx_data)
    """
    if not field_file:
        yield None
        return

    storage = field_file.storage
    name = field_file.name

    # FileSystemStorage already has a real path; avoid a needless download.
    if hasattr(storage, "path"):
        try:
            yield storage.path(name)
            return
        except (NotImplementedError, OSError):
            pass

    handle = NamedTemporaryFile(
        suffix=os.path.splitext(name)[1] or ".bin", delete=False
    )
    try:
        with storage.open(name, "rb") as source:
            for chunk in source.chunks():
                handle.write(chunk)
        handle.close()
        yield handle.name
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
