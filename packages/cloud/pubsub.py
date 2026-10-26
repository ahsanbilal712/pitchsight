"""Cue fan-out through Azure Web PubSub (ADR-009): CueBus publishes each delivered cue to the hub, and the
screens on Static Web Apps subscribe with a client token from `GET /cues/negotiate`. Locally the api's
WebSocket forwarder does the same job, so this publisher is only built when WHYLINE_CLOUD=1."""

from __future__ import annotations

import json
import logging

log = logging.getLogger("whyline.cloud")


class WebPubSubCuePublisher:
    def __init__(self, client=None, *, hub: str | None = None) -> None:
        from cloud.settings import settings

        s = settings()
        self.hub = hub or s.webpubsub_hub
        if client is None:
            from azure.messaging.webpubsubservice import WebPubSubServiceClient

            if s.webpubsub_endpoint:
                from cloud.settings import credential

                client = WebPubSubServiceClient(endpoint=s.webpubsub_endpoint, hub=self.hub, credential=credential())
            else:
                client = WebPubSubServiceClient.from_connection_string(s.webpubsub_connection_string, hub=self.hub)
        self._client = client

    def publish(self, cue: dict) -> None:
        """Send to the match group (one group per match_id); a delivery failure never blocks the newsroom."""
        group = str(cue.get("match_id") or "all")
        try:
            self._client.send_to_group(group, json.dumps({"type": "cue", "data": cue}, separators=(",", ":")),
                                       content_type="application/json")
        except Exception as exc:  # noqa: BLE001 - the blackboard copy is the source of truth
            log.warning("web pubsub publish failed for cue %s: %s", cue.get("cue_id"), exc)

    def client_url(self, user_id: str | None = None, match_id: str | None = None, minutes: int = 60) -> str:
        """A short-lived subscriber URL for a screen: joins the match group read-only."""
        groups = [match_id] if match_id else None
        token = self._client.get_client_access_token(user_id=user_id, minutes_to_expire=minutes,
                                                     roles=[f"webpubsub.joinLeaveGroup.{match_id}"] if match_id
                                                     else None, groups=groups)
        return token["url"]


class NullCuePublisher:
    """Local runs: the api's blackboard forwarder already streams cues over its own WebSocket."""

    def publish(self, cue: dict) -> None:
        return None
