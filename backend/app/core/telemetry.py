"""OpenTelemetry setup — optional; auto-disabled if package/endpoint unavailable."""
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


def setup_telemetry(app) -> None:
    """Enable OTEL only if endpoint is configured AND package is available."""
    if not settings.OTEL_ENDPOINT:
        logger.info("telemetry.disabled_no_endpoint")
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": "aegis-backend"}))
        provider.add_span_processor(BatchSpanProcessor(
            OTLPSpanExporter(endpoint=settings.OTEL_ENDPOINT, insecure=True)
        ))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        logger.info("telemetry.enabled", endpoint=settings.OTEL_ENDPOINT)
    except ImportError:
        logger.info("telemetry.disabled_package_missing")
    except Exception as e:
        logger.warning("telemetry.disabled_error", error=str(e))
