from __future__ import annotations

import json
from typing import Any

from core.connectors.base import validate_identifier
from core.schema_mapping.registry import TypeMappingRegistry
from core.audit_logger import audit_log


class AssessmentReport:
    def __init__(self) -> None:
        self.source_engine: str | None = None
        self.target_engine: str | None = None
        self.objects: list[dict[str, Any]] = []
        self.compatibility_issues: list[dict[str, Any]] = []
        self.size_warnings: list[dict[str, Any]] = []
        self.naming_collisions: list[dict[str, Any]] = []
        self.unsupported_types: list[dict[str, Any]] = []
        self.total_source_rows: int = 0
        self.estimated_total_size_bytes: int = 0
        self.compatible: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_engine": self.source_engine,
            "target_engine": self.target_engine,
            "objects": self.objects,
            "compatibility_issues": self.compatibility_issues,
            "size_warnings": self.size_warnings,
            "naming_collisions": self.naming_collisions,
            "unsupported_types": self.unsupported_types,
            "total_source_rows": self.total_source_rows,
            "estimated_total_size_bytes": self.estimated_total_size_bytes,
            "compatible": self.compatible,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


class AssessmentReportGenerator:
    def __init__(self, registry: TypeMappingRegistry) -> None:
        self._registry = registry

    def generate(
        self,
        source_engine: str,
        target_engine: str,
        source_connector: Any,
    ) -> AssessmentReport:
        report = AssessmentReport()
        report.source_engine = source_engine
        report.target_engine = target_engine

        objects = source_connector.list_objects()

        for obj_name in objects:
            validate_identifier(obj_name, "object")
            schema = source_connector.get_schema(obj_name)
            count = source_connector.get_object_count(obj_name)

            obj_report: dict[str, Any] = {
                "name": obj_name,
                "row_count": count,
                "columns": [],
            }

            report.total_source_rows += count

            for col in schema.columns:
                obj_report["columns"].append({
                    "name": col.name,
                    "source_type": col.source_type,
                    "nullable": col.nullable,
                    "size": col.size,
                })

                compatibility = self._registry.validate_compatibility(
                    source_engine, target_engine, col.source_type
                )

                if not compatibility["compatible"]:
                    report.compatibility_issues.append({
                        "object": obj_name,
                        "column": col.name,
                        "source_type": col.source_type,
                        "target_engine": target_engine,
                        "issue": compatibility.get("warning", "incompatible type"),
                    })
                    report.unsupported_types.append({
                        "object": obj_name,
                        "column": col.name,
                        "source_type": col.source_type,
                    })

                if target_engine in ("cosmos_mongo", "mongodb") and col.size is not None:
                    estimated_bytes = col.size * 3
                    if not self._registry.check_size_limit(target_engine, estimated_bytes):
                        report.size_warnings.append({
                            "object": obj_name,
                            "column": col.name,
                            "estimated_size_bytes": estimated_bytes,
                            "limit_mb": 2.0 if target_engine == "cosmos_mongo" else 16.0,
                        })

            report.objects.append(obj_report)

        report.compatible = (
            len(report.compatibility_issues) == 0
            and len(report.size_warnings) == 0
        )

        audit_log(
            phase="assessment",
            status="complete",
            details={
                "objects_assessed": len(objects),
                "compatible": report.compatible,
                "issues": len(report.compatibility_issues),
                "warnings": len(report.size_warnings),
            },
        )

        return report