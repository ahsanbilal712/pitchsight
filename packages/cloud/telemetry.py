"""OpenTelemetry traces to Azure Monitor / Application Insights.

The newsroom already emits one span per agent hop through Agent Framework's observability; this wires the
exporter when APPLICATIONINSIGHTS_CONNECTION_STRING is set, so the agent graph shows up in the Application Map
and in Foundry's tracing view. Without the connection string it is a no-op.
"""

from __future__ import annotations

import logging

log = logging.getLogger("whyline.cloud")
_configured = False


def configure_telemetry(service_name: str) -> bool:
    global _configured
    if _configured:
        return True
    from cloud.settings import settings

    conn = settings().appinsights_connection_string
    if not conn:
        return False
    from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service_name,
                                                        "service.namespace": "pitchsight"}))
    provider.add_span_processor(BatchSpanProcessor(AzureMonitorTraceExporter(connection_string=conn)))
    trace.set_tracer_provider(provider)
    try:
        from agent_framework.observability import configure_otel_providers

        configure_otel_providers(enable_sensitive_data=False)
    except (ImportError, TypeError) as exc:  # older/newer observability API: the global provider still exports
        log.debug("agent framework observability not configured: %s", exc)
    _configured = True
    log.info("telemetry: %s exporting to Application Insights", service_name)
    return True
