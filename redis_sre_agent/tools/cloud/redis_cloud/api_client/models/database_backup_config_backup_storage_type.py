from enum import Enum


class DatabaseBackupConfigBackupStorageType(str, Enum):
    AWS_S3 = "aws-s3"
    AZURE_BLOB_STORAGE = "azure-blob-storage"
    FTP = "ftp"
    GOOGLE_BLOB_STORAGE = "google-blob-storage"
    HTTP = "http"
    REDIS = "redis"

    def __str__(self) -> str:
        return str(self.value)
