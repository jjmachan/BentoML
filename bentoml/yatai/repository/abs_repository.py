# Copyright 2019 Atalaya Tech, Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

# http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from dependency_injector.wiring import Provide, inject

from bentoml.configuration.containers import BentoMLContainer
from bentoml.exceptions import YataiRepositoryException
from bentoml.yatai.proto.repository_pb2 import BentoUri
from bentoml.yatai.repository.base_repository import BaseRepository

try:
    from azure.storage.blob import generate_blob_sas
except ImportError:
    raise YataiRepositoryException(
        "'azure-storage-blob' package is required for "
        "Azure Blob Storage repository. You can install it with pip:"
        "'pip install azure-storage-blob'"
    )


logger = logging.getLogger(__name__)


class ABSRepository(BaseRepository):
    @inject
    def __init__(
        self,
        base_url,
        expiration: int = Provide[
            BentoMLContainer.config.yatai.respository.abs.expiration
        ],
    ):
        self.uri_type = BentoUri.AZURE_BLOB_STORAGE
        self.expiration = expiration
        self.parsed_url = urlparse(base_url)
        self.storage_ac = self.parsed_url.netloc.split(".")[0]
        self.container_name = self.parsed_url.path.lstrip("/")

        # check auth
        self.abs_key = os.getenv("AZURE_STORAGE_KEY", None)
        if self.abs_key is None:
            raise YataiRepositoryException(
                "'AZURE_STORAGE_KEY' not provided. Please set this as env var"
            )

    def _generate_presigned_url(self, object_name, permissions):
        """
        permissions are strings which list all the permissions.
        eg: 'racwdl' -> [Read, Add, Create, Write, Delete, List]
        """
        # TODO use self.expiration
        sas_token = generate_blob_sas(
            self.storage_ac,
            self.container_name,
            object_name,
            account_key=self.abs_key,
            permission=permissions,
            expiry=datetime.now(timezone.utc) + timedelta(days=2),
        )
        signed_url = self.parsed_url._replace(
            query=sas_token, path="/".join([self.container_name, object_name])
        )

        return signed_url.geturl()

    def _get_object_name(self, bento_name, bento_version):
        return "/".join([bento_name, bento_version]) + ".tar.gz"

    def add(self, bento_name, bento_version):
        # Generate pre-signed SAS url for upload

        object_name = self._get_object_name(bento_name, bento_version)
        try:
            response = self._generate_presigned_url(object_name, "rw")
            logger.info("SAS generated!: {}".format(response))
        except Exception as e:
            raise YataiRepositoryException(
                "Not able to get pre-signed URL for Azure Blob Storage."
                " Error: {}".format(e)
            )
        return BentoUri(
            type=self.uri_type,
            uri=self.parsed_url._replace(
                path="/".join([self.container_name, object_name])
            ).geturl(),
            abs_presigned_url=response,
        )

    def get(self, bento_name, bento_version):
        object_name = self._get_object_name(bento_name, bento_version)

        import pdb; pdb.set_trace()
        try:
            response = self._generate_presigned_url(object_name, "r")
            return response
        except Exception:
            logger.error(
                "Failed generating presigned URL for downloading saved bundle"
                " from Azure Blob Storage, falling back to using blob path and"
                " client side credential for downloading with azure.blob.storage"
            )
            return self.parsed_url._replace(
                path="/".join([self.container_name, object_name])
            )

    def dangerously_delete(self, bento_name, bento_version):
        pass
