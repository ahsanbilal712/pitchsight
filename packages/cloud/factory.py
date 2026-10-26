"""Factories the services call at start-up: Azure implementations when WHYLINE_CLOUD=1 and configured,
the local ones otherwise."""

from __future__ import annotations

import logging

from cloud.settings import cloud_enabled, settings

log = logging.getLogger("whyline.cloud")


def make_blackboard():
    if cloud_enabled() and settings().has_cosmos:
        from cloud.cosmos_blackboard import CosmosBlackboard

        log.info("blackboard: Cosmos DB %s/%s", settings().cosmos_database, settings().cosmos_blackboard_container)
        return CosmosBlackboard()
    from blackboard import SqliteBlackboard

    return SqliteBlackboard()


def make_checkpoint_storage(local_dir):
    """Workflow checkpoints: CosmosCheckpointStorage in Azure (resume survives a container restart),
    FileCheckpointStorage(local_dir) locally."""
    if cloud_enabled() and settings().has_cosmos:
        from agent_framework_azure_cosmos import CosmosCheckpointStorage

        from cloud.settings import async_credential

        s = settings()
        log.info("checkpoints: Cosmos DB %s/%s", s.cosmos_database, s.cosmos_checkpoint_container)
        return CosmosCheckpointStorage(endpoint=s.cosmos_endpoint, database_name=s.cosmos_database,
                                       container_name=s.cosmos_checkpoint_container, credential=async_credential())
    from agent_framework import FileCheckpointStorage

    return FileCheckpointStorage(local_dir)


def make_cue_publisher():
    if cloud_enabled() and settings().has_webpubsub:
        from cloud.pubsub import WebPubSubCuePublisher

        log.info("cues: Web PubSub hub %s", settings().webpubsub_hub)
        return WebPubSubCuePublisher()
    from cloud.pubsub import NullCuePublisher

    return NullCuePublisher()
