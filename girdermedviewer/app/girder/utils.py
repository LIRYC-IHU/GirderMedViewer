from contextlib import contextmanager
from datetime import datetime
from enum import Enum
import logging
import os
import sys
from tempfile import TemporaryDirectory

logging.basicConfig(stream=sys.stdout)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def format_date(date_str, format):
    return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%f+00:00").strftime(format)


class CacheMode(Enum):
    No = "No"
    Session = "Session"
    Permanent = "Permanent"


class FileDownloader:
    def __init__(self, girder_client, temp_dir=None, cache_mode=CacheMode.No):
        """
        :example:
        ```
        girder_client = GirderClient(apiUrl="http://localhost:8080/api/v1")
        girder_client.authenticate(apiKey="my_key")
        downloader = FileDownloader(girder_client, cache_mode=CacheMode.Session)
        with downloader.download_file(file) as file_path:
            ...
        ```
        """
        self.temp_dir_path = temp_dir
        if not self.temp_dir_path:
            self.temporary_directory = TemporaryDirectory()
            self.temp_dir_path = self.temporary_directory.name
            if cache_mode == CacheMode.Permanent:
                raise Exception("A directory must be provided if cache mode is Permanent")
        self.girder_client = girder_client
        self.cache = cache_mode

    def __del__(self):
        if self.cache == CacheMode.Session:
            self.clear_cache()

    def get_item_files(self, item):
        return self.girder_client.listFile(item["_id"])

    def get_item_inherited_metadata(self, item):
        parent_folder = self.girder_client.getFolder(item["folderId"])
        metadata = parent_folder["meta"]
        # Fetch metadata of all parents
        while parent_folder["parentId"] != item["baseParentId"]:
            parent_folder = self.girder_client.getFolder(parent_folder["parentId"])
            metadata.update(parent_folder["meta"])
        return metadata

    @contextmanager
    def download_file(self, file):
        """
        :param forced_cache can be used to override the cache mode for a specific file
        """
        file_path = os.path.join(self.temp_dir_path, file['_id'], file["name"])
        if not os.path.exists(file_path):
            logger.debug(f"Downloading {file_path}")
            self.girder_client.downloadFile(
                file["_id"],
                file_path
            )
            logger.debug(f"Downloaded {file_path}")
        try:
            yield file_path
        finally:
            if self.cache == CacheMode.No:
                self.clear_cache(file)

    def clear_cache(self, file=None):
        if file is not None:
            file_path = os.path.join(self.temp_dir_path, file['_id'], file["name"])
            os.remove(file_path)
        else:
            self.temp_dir_path.cleanup()
