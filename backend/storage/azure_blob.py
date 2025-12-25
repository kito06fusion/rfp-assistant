from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Optional, BinaryIO

from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from azure.core.exceptions import AzureError
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()


class AzureBlobStorage:
    #function to initialize Azure Blob storage client and container
    def __init__(
        self,
        connection_string: Optional[str] = None,
        container_name: str = "rag-indexes",
    ):
        self.connection_string = (
            connection_string
            or os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        )
        self.container_name = container_name
        self.blob_service_client: Optional[BlobServiceClient] = None
        self.container_client: Optional[ContainerClient] = None

        if self.connection_string:
            try:
                self.blob_service_client = BlobServiceClient.from_connection_string(
                    self.connection_string
                )
                self.container_client = self.blob_service_client.get_container_client(
                    self.container_name
                )
                try:
                    self.container_client.create_container()
                    logger.info(
                        "Created Azure Blob Storage container: %s", self.container_name
                    )
                except AzureError as e:
                    if "ContainerAlreadyExists" in str(e):
                        logger.debug(
                            "Azure Blob Storage container already exists: %s",
                            self.container_name,
                        )
                    else:
                        logger.warning(
                            "Failed to create/verify container: %s", str(e)
                        )
                        raise
                logger.info(
                    "Azure Blob Storage initialized (container: %s)", self.container_name
                )
            except Exception as e:
                logger.error(
                    "Failed to initialize Azure Blob Storage: %s", str(e)
                )
                raise
        else:
            logger.warning(
                "Azure Blob Storage connection string not provided. "
                "Set AZURE_STORAGE_CONNECTION_STRING environment variable to enable."
            )

    #function to check if Azure Blob storage client and container are available
    def is_available(self) -> bool:
        return self.blob_service_client is not None and self.container_client is not None

    #function to upload a file from disk to Azure Blob Storage
    def upload_file(
        self, blob_name: str, file_path: Path, overwrite: bool = True
    ) -> bool:
        if not self.is_available():
            logger.warning("Azure Blob Storage not available, cannot upload file")
            return False

        if not file_path.exists():
            logger.error("File does not exist: %s", file_path)
            return False

        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            with open(file_path, "rb") as data:
                blob_client.upload_blob(data, overwrite=overwrite)
            logger.info(
                "Uploaded file to Azure Blob Storage: %s -> %s/%s",
                file_path.name,
                self.container_name,
                blob_name,
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to upload file %s to Azure Blob Storage: %s",
                file_path,
                str(e),
            )
            return False

    #function to upload raw bytes as a blob to Azure Blob Storage
    def upload_bytes(
        self, blob_name: str, data: bytes, overwrite: bool = True
    ) -> bool:
        if not self.is_available():
            logger.warning("Azure Blob Storage not available, cannot upload bytes")
            return False

        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            blob_client.upload_blob(data, overwrite=overwrite)
            logger.info(
                "Uploaded bytes to Azure Blob Storage: %s/%s (%d bytes)",
                self.container_name,
                blob_name,
                len(data),
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to upload bytes to Azure Blob Storage blob %s: %s",
                blob_name,
                str(e),
            )
            return False

    #function to download a blob to a local file path
    def download_file(self, blob_name: str, file_path: Path) -> bool:
        if not self.is_available():
            logger.warning("Azure Blob Storage not available, cannot download file")
            return False

        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "wb") as download_file:
                download_file.write(blob_client.download_blob().readall())
            logger.info(
                "Downloaded file from Azure Blob Storage: %s/%s -> %s",
                self.container_name,
                blob_name,
                file_path,
            )
            return True
        except AzureError as e:
            if "BlobNotFound" in str(e) or "404" in str(e):
                logger.debug(
                    "Blob not found in Azure Blob Storage: %s/%s",
                    self.container_name,
                    blob_name,
                )
            else:
                logger.error(
                    "Failed to download file from Azure Blob Storage blob %s: %s",
                    blob_name,
                    str(e),
                )
            return False
        except Exception as e:
            logger.error(
                "Failed to download file from Azure Blob Storage blob %s: %s",
                blob_name,
                str(e),
            )
            return False

    #function to download raw bytes for a named blob
    def download_bytes(self, blob_name: str) -> Optional[bytes]:
        if not self.is_available():
            logger.warning("Azure Blob Storage not available, cannot download bytes")
            return None

        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            data = blob_client.download_blob().readall()
            logger.info(
                "Downloaded bytes from Azure Blob Storage: %s/%s (%d bytes)",
                self.container_name,
                blob_name,
                len(data),
            )
            return data
        except AzureError as e:
            if "BlobNotFound" in str(e) or "404" in str(e):
                logger.debug(
                    "Blob not found in Azure Blob Storage: %s/%s",
                    self.container_name,
                    blob_name,
                )
            else:
                logger.error(
                    "Failed to download bytes from Azure Blob Storage blob %s: %s",
                    blob_name,
                    str(e),
                )
            return None
        except Exception as e:
            logger.error(
                "Failed to download bytes from Azure Blob Storage blob %s: %s",
                blob_name,
                str(e),
            )
            return None

    #function to check whether a blob exists in the container
    def blob_exists(self, blob_name: str) -> bool:
        if not self.is_available():
            return False

        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            return blob_client.exists()
        except Exception as e:
            logger.error(
                "Failed to check blob existence in Azure Blob Storage: %s", str(e)
            )
            return False

    #function to delete a blob by name
    def delete_blob(self, blob_name: str) -> bool:
        if not self.is_available():
            logger.warning("Azure Blob Storage not available, cannot delete blob")
            return False

        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            blob_client.delete_blob()
            logger.info(
                "Deleted blob from Azure Blob Storage: %s/%s",
                self.container_name,
                blob_name,
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to delete blob from Azure Blob Storage: %s", str(e)
            )
            return False

    #function to list blob names optionally filtered by prefix
    def list_blobs(self, prefix: Optional[str] = None) -> list[str]:
        if not self.is_available():
            return []

        try:
            blobs = self.container_client.list_blobs(name_starts_with=prefix)
            return [blob.name for blob in blobs]
        except Exception as e:
            logger.error(
                "Failed to list blobs in Azure Blob Storage: %s", str(e)
            )
            return []
