"""Safely extract documentation metadata from Power BI PBIR report files."""

import json
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Set, Tuple
from zipfile import BadZipFile, ZipFile

from .tmdl_parser import (
    MAX_FILE_COUNT,
    MAX_UNCOMPRESSED_SIZE,
    MAX_ZIP_SIZE,
)


MAX_REPORT_TEXT_FILE_SIZE = 10 * 1024 * 1024
FIELD_KINDS = ("Column", "Measure", "HierarchyLevel")


def _get_report_root(file_name: str) -> Optional[str]:
    """Return the archive path representing one report folder."""

    parts = PurePosixPath(file_name).parts

    for index, part in enumerate(parts):
        if part.endswith(".Report"):
            return "/".join(parts[:index + 1])

    if "definition" in parts:
        definition_index = parts.index("definition")
        remaining_parts = parts[definition_index + 1:]

        if remaining_parts and remaining_parts[0] in {
            "pages",
            "bookmarks",
            "report.json",
            "version.json",
        }:
            return "/".join(parts[:definition_index])

    return None


def _is_report_definition_file(file_name: str) -> bool:
    """Identify report files needed for documentation."""

    file_path = PurePosixPath(file_name)
    report_root = _get_report_root(file_name)

    if report_root is None:
        return False

    if file_path.name == "definition.pbir":
        return True

    return (
        file_path.suffix.lower() == ".json"
        and "definition" in file_path.parts
    )


def load_report_files(zip_path: str) -> Dict[str, str]:
    """Safely load PBIR report-definition JSON from a project ZIP."""

    path = Path(zip_path)

    if not path.exists():
        raise ValueError("The ZIP file does not exist.")

    if path.stat().st_size > MAX_ZIP_SIZE:
        raise ValueError("The ZIP file exceeds the 25 MB limit.")

    try:
        with ZipFile(path, "r") as archive:
            file_entries = [
                entry
                for entry in archive.infolist()
                if not entry.is_dir()
            ]

            if len(file_entries) > MAX_FILE_COUNT:
                raise ValueError("The ZIP contains too many files.")

            total_size = sum(
                entry.file_size
                for entry in file_entries
            )

            if total_size > MAX_UNCOMPRESSED_SIZE:
                raise ValueError(
                    "The uncompressed content exceeds 100 MB."
                )

            report_files: Dict[str, str] = {}

            for entry in file_entries:
                raw_name = entry.filename

                if "\\" in raw_name:
                    raise ValueError(
                        "The ZIP contains an unsafe file path."
                    )

                member_path = PurePosixPath(raw_name)

                if (
                    member_path.is_absolute()
                    or ".." in member_path.parts
                ):
                    raise ValueError(
                        "The ZIP contains an unsafe file path."
                    )

                if "__MACOSX" in member_path.parts:
                    continue

                if member_path.name == ".DS_Store":
                    continue

                if not _is_report_definition_file(raw_name):
                    continue

                if entry.file_size > MAX_REPORT_TEXT_FILE_SIZE:
                    raise ValueError(
                        f"{raw_name} exceeds the 10 MB report-file limit."
                    )

                try:
                    content = archive.read(entry).decode("utf-8-sig")
                except UnicodeDecodeError as error:
                    raise ValueError(
                        f"{raw_name} is not valid UTF-8 text."
                    ) from error

                report_files[str(member_path)] = content

    except BadZipFile as error:
        raise ValueError(
            "The uploaded file is not a valid ZIP."
        ) from error

    return report_files


def _load_json(file_name: str, content: str) -> Dict[str, Any]:
    """Load a PBIR JSON object with a useful filename in any error."""

    try:
        value = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"{file_name} is not valid JSON."
        ) from error

    if not isinstance(value, dict):
        raise ValueError(f"{file_name} must contain a JSON object.")

    return value


def _find_source_entity(value: Any) -> str:
    """Find the semantic-model entity referenced inside a PBIR expression."""

    if isinstance(value, dict):
        source_ref = value.get("SourceRef")

        if isinstance(source_ref, dict):
            entity = source_ref.get("Entity")

            if isinstance(entity, str):
                return entity

        for child in value.values():
            entity = _find_source_entity(child)

            if entity:
                return entity

    elif isinstance(value, list):
        for child in value:
            entity = _find_source_entity(child)

            if entity:
                return entity

    return ""


def _parse_direct_field(
    field_kind: str,
    field_value: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Convert a PBIR column, measure, or hierarchy level to metadata."""

    table_name = _find_source_entity(field_value.get("Expression", {}))
    object_name = (
        field_value.get("Property")
        or field_value.get("Level")
        or field_value.get("Hierarchy")
    )

    if not isinstance(object_name, str):
        return None

    return {
        "type": field_kind[0].lower() + field_kind[1:],
        "table": table_name,
        "name": object_name,
    }


def extract_field_references(value: Any) -> List[Dict[str, Any]]:
    """Recursively extract model references without retaining literal values."""

    references: List[Dict[str, Any]] = []

    if isinstance(value, dict):
        aggregation = value.get("Aggregation")

        if isinstance(aggregation, dict):
            aggregation_references = extract_field_references(
                aggregation.get("Expression", {})
            )

            for reference in aggregation_references:
                reference["aggregationFunctionCode"] = aggregation.get(
                    "Function"
                )

            return aggregation_references

        for field_kind in FIELD_KINDS:
            field_value = value.get(field_kind)

            if isinstance(field_value, dict):
                reference = _parse_direct_field(
                    field_kind,
                    field_value,
                )

                return [reference] if reference else []

        for child in value.values():
            references.extend(extract_field_references(child))

    elif isinstance(value, list):
        for child in value:
            references.extend(extract_field_references(child))

    return _deduplicate_references(references)


def _deduplicate_references(
    references: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Remove duplicate semantic references while preserving their order."""

    unique_references = []
    seen: Set[Tuple[Any, ...]] = set()

    for reference in references:
        key = (
            reference.get("role"),
            reference.get("type"),
            reference.get("table"),
            reference.get("name"),
            reference.get("aggregationFunctionCode"),
            reference.get("direction"),
        )

        if key in seen:
            continue

        seen.add(key)
        unique_references.append(reference)

    return unique_references


def _clean_literal_text(value: Any) -> str:
    """Normalize a visible title literal without evaluating it."""

    if not isinstance(value, str):
        return ""

    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")

    return value


def _find_first_literal(value: Any) -> str:
    """Find a visible title literal in a small formatting object."""

    if isinstance(value, dict):
        literal = value.get("Literal")

        if isinstance(literal, dict) and "Value" in literal:
            return _clean_literal_text(literal.get("Value"))

        for child in value.values():
            result = _find_first_literal(child)

            if result:
                return result

    elif isinstance(value, list):
        for child in value:
            result = _find_first_literal(child)

            if result:
                return result

    return ""


def _extract_visual_title(visual: Dict[str, Any]) -> str:
    """Extract a configured visual title, excluding unrelated formatting."""

    container_objects = visual.get("visualContainerObjects", {})

    if not isinstance(container_objects, dict):
        return ""

    for title_item in container_objects.get("title", []):
        if not isinstance(title_item, dict):
            continue

        properties = title_item.get("properties", {})

        if not isinstance(properties, dict):
            continue

        title = _find_first_literal(properties.get("text", {}))

        if title:
            return title[:500]

    return ""


def _extract_textbox_text(visual: Dict[str, Any]) -> str:
    """Extract visible text from a text-box visual."""

    objects = visual.get("objects", {})

    if not isinstance(objects, dict):
        return ""

    text_values = []

    for general_item in objects.get("general", []):
        if not isinstance(general_item, dict):
            continue

        properties = general_item.get("properties", {})

        if not isinstance(properties, dict):
            continue

        for paragraph in properties.get("paragraphs", []):
            if not isinstance(paragraph, dict):
                continue

            for text_run in paragraph.get("textRuns", []):
                if not isinstance(text_run, dict):
                    continue

                value = text_run.get("value")

                if isinstance(value, str):
                    text_values.append(value)

    return " ".join(text_values).strip()[:1000]


def _extract_query_fields(visual: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract fields and their visual data roles from queryState."""

    query = visual.get("query", {})

    if not isinstance(query, dict):
        return []

    query_state = query.get("queryState", {})

    if not isinstance(query_state, dict):
        return []

    references = []

    for role, role_config in query_state.items():
        if not isinstance(role_config, dict):
            continue

        for projection in role_config.get("projections", []):
            if not isinstance(projection, dict):
                continue

            projection_references = extract_field_references(
                projection.get("field", {})
            )

            for reference in projection_references:
                reference["role"] = role

                if "active" in projection:
                    reference["active"] = bool(
                        projection.get("active")
                    )

            references.extend(projection_references)

    return _deduplicate_references(references)


def _extract_sort_fields(visual: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract visual sort fields without retaining query literals."""

    query = visual.get("query", {})

    if not isinstance(query, dict):
        return []

    sort_definition = query.get("sortDefinition", {})

    if not isinstance(sort_definition, dict):
        return []

    references = []

    for sort_item in sort_definition.get("sort", []):
        if not isinstance(sort_item, dict):
            continue

        sort_references = extract_field_references(
            sort_item.get("field", {})
        )

        for reference in sort_references:
            reference["direction"] = sort_item.get("direction", "")

        references.extend(sort_references)

    return _deduplicate_references(references)


def _extract_filters(filter_config: Any) -> List[Dict[str, Any]]:
    """Extract filter fields and types while deliberately dropping values."""

    if not isinstance(filter_config, dict):
        return []

    filters = []

    for filter_item in filter_config.get("filters", []):
        if not isinstance(filter_item, dict):
            continue

        filters.append({
            "type": filter_item.get("type", ""),
            "howCreated": filter_item.get("howCreated", ""),
            "fields": extract_field_references(filter_item),
            "selectedValuesRedacted": "filter" in filter_item,
        })

    return filters


def _build_model_index(
    tables: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Set[str]]]:
    """Create a lookup used to connect visual fields to model objects."""

    model_index = {}

    for table_name, table in tables.items():
        model_index[table_name] = {
            "column": {
                column["name"]
                for column in table.get("columns", [])
            },
            "measure": {
                measure["name"]
                for measure in table.get("measures", [])
            },
        }

    return model_index


def _annotate_model_matches(
    references: List[Dict[str, Any]],
    model_index: Dict[str, Dict[str, Set[str]]],
) -> None:
    """Mark whether a visual field exists in the uploaded semantic model."""

    for reference in references:
        table_name = reference.get("table", "")
        object_name = reference.get("name", "")
        object_type = reference.get("type", "")
        table_index = model_index.get(table_name)

        if table_index is None:
            reference["modelMatch"] = False
        elif object_type in {"column", "measure"}:
            reference["modelMatch"] = (
                object_name in table_index[object_type]
            )
        else:
            reference["modelMatch"] = True


def _parse_visual(
    file_name: str,
    content: str,
    model_index: Dict[str, Dict[str, Set[str]]],
) -> Dict[str, Any]:
    """Parse one PBIR visual into a compact documentation object."""

    data = _load_json(file_name, content)
    visual = data.get("visual", {})

    if not isinstance(visual, dict):
        visual = {}

    fields = _extract_query_fields(visual)
    sort_fields = _extract_sort_fields(visual)
    filters = _extract_filters(data.get("filterConfig"))

    _annotate_model_matches(fields, model_index)
    _annotate_model_matches(sort_fields, model_index)

    for filter_item in filters:
        _annotate_model_matches(
            filter_item["fields"],
            model_index,
        )

    visual_type = visual.get("visualType")

    if not isinstance(visual_type, str):
        visual_type = "groupOrContainer"

    return {
        "type": visual_type,
        "title": _extract_visual_title(visual),
        "visibleText": _extract_textbox_text(visual),
        "fields": fields,
        "sort": sort_fields,
        "filters": filters,
        "filterCount": len(filters),
    }


def _get_relative_name(file_name: str, report_root: str) -> str:
    """Return a path relative to its .Report folder."""

    if not report_root:
        return file_name

    prefix = f"{report_root}/"

    if file_name.startswith(prefix):
        return file_name[len(prefix):]

    return file_name


def _get_report_name(report_root: str) -> str:
    """Create a readable report name from its folder name."""

    if not report_root:
        return "Power BI Report"

    folder_name = PurePosixPath(report_root).name

    if folder_name.endswith(".Report"):
        return folder_name[:-len(".Report")]

    return folder_name


def _parse_report(
    report_root: str,
    report_files: Dict[str, str],
    model_index: Dict[str, Dict[str, Set[str]]],
) -> Dict[str, Any]:
    """Parse one report folder from normalized archive files."""

    relative_files = {
        _get_relative_name(file_name, report_root): (
            file_name,
            content,
        )
        for file_name, content in report_files.items()
        if _get_report_root(file_name) == report_root
    }
    definition_data: Dict[str, Any] = {}
    definition_entry = relative_files.get("definition.pbir")

    if definition_entry is not None:
        definition_data = _load_json(*definition_entry)

    report_data: Dict[str, Any] = {}
    report_entry = relative_files.get("definition/report.json")

    if report_entry is not None:
        report_data = _load_json(*report_entry)

    pages_metadata: Dict[str, Any] = {}
    pages_entry = relative_files.get("definition/pages/pages.json")

    if pages_entry is not None:
        pages_metadata = _load_json(*pages_entry)

    page_order = pages_metadata.get("pageOrder", [])
    page_order_lookup = {
        page_name: index
        for index, page_name in enumerate(page_order)
        if isinstance(page_name, str)
    }
    page_entries = []

    for relative_name, entry in relative_files.items():
        relative_path = PurePosixPath(relative_name)

        if (
            len(relative_path.parts) == 4
            and relative_path.parts[:2] == ("definition", "pages")
            and relative_path.name == "page.json"
        ):
            page_entries.append((relative_name, entry))

    pages = []

    for relative_name, (file_name, content) in page_entries:
        page_data = _load_json(file_name, content)
        page_name = page_data.get(
            "name",
            PurePosixPath(relative_name).parent.name,
        )
        visual_prefix = (
            f"definition/pages/{page_name}/visuals/"
        )
        visuals = []

        for visual_relative_name, visual_entry in relative_files.items():
            if (
                visual_relative_name.startswith(visual_prefix)
                and visual_relative_name.endswith("/visual.json")
            ):
                visuals.append(_parse_visual(
                    visual_entry[0],
                    visual_entry[1],
                    model_index,
                ))

        visuals.sort(
            key=lambda item: (
                item.get("type", ""),
                item.get("title", ""),
                item.get("visibleText", ""),
            )
        )
        page_filters = _extract_filters(
            page_data.get("filterConfig")
        )

        for filter_item in page_filters:
            _annotate_model_matches(
                filter_item["fields"],
                model_index,
            )

        drillthrough_fields = extract_field_references(
            page_data.get("pageBinding", {})
        )
        _annotate_model_matches(
            drillthrough_fields,
            model_index,
        )

        pages.append({
            "displayName": page_data.get("displayName") or "Unnamed page",
            "order": page_order_lookup.get(
                page_name,
                len(page_order_lookup),
            ) + 1,
            "isActive": page_name == pages_metadata.get(
                "activePageName"
            ),
            "visibility": page_data.get(
                "visibility",
                "AlwaysVisible",
            ),
            "width": page_data.get("width"),
            "height": page_data.get("height"),
            "filters": page_filters,
            "filterCount": len(page_filters),
            "drillthroughFields": drillthrough_fields,
            "visuals": visuals,
            "visualCount": len(visuals),
            "dataVisualCount": sum(
                1
                for visual_item in visuals
                if visual_item["fields"]
            ),
        })

    pages.sort(
        key=lambda item: (
            item["order"],
            item["displayName"],
        )
    )
    bookmarks = []

    for relative_name, (file_name, content) in relative_files.items():
        if not relative_name.endswith(".bookmark.json"):
            continue

        bookmark_data = _load_json(file_name, content)
        options = bookmark_data.get("options", {})

        if not isinstance(options, dict):
            options = {}

        target_visuals = options.get("targetVisualNames", [])

        bookmarks.append({
            "displayName": (
                bookmark_data.get("displayName") or "Bookmark"
            ),
            "targetVisualCount": (
                len(target_visuals)
                if isinstance(target_visuals, list)
                else 0
            ),
        })

    bookmarks.sort(
        key=lambda item: item["displayName"]
    )
    dataset_reference = definition_data.get("datasetReference", {})
    semantic_model_reference = ""

    if isinstance(dataset_reference, dict):
        by_path = dataset_reference.get("byPath", {})

        if isinstance(by_path, dict):
            reference_path = by_path.get("path")

            if isinstance(reference_path, str):
                semantic_model_reference = PurePosixPath(
                    reference_path
                ).name

    settings = report_data.get("settings", {})

    if not isinstance(settings, dict):
        settings = {}

    theme_collection = report_data.get("themeCollection", {})
    theme_names = []

    if isinstance(theme_collection, dict):
        for theme in theme_collection.values():
            if isinstance(theme, dict):
                theme_name = theme.get("name")

                if isinstance(theme_name, str):
                    theme_names.append(theme_name)

    report_filters = _extract_filters(
        report_data.get("filterConfig")
    )

    for filter_item in report_filters:
        _annotate_model_matches(
            filter_item["fields"],
            model_index,
        )

    all_visuals = [
        visual
        for page in pages
        for visual in page["visuals"]
    ]
    unresolved_references = [
        reference
        for visual in all_visuals
        for reference in visual["fields"]
        if reference.get("modelMatch") is False
    ]

    return {
        "name": _get_report_name(report_root),
        "semanticModelReference": semantic_model_reference,
        "themes": sorted(set(theme_names)),
        "layoutOptimization": report_data.get(
            "layoutOptimization",
            "",
        ),
        "exportDataMode": settings.get("exportDataMode", ""),
        "filters": report_filters,
        "filterCount": len(report_filters),
        "pages": pages,
        "bookmarks": bookmarks,
        "statistics": {
            "pageCount": len(pages),
            "visualCount": len(all_visuals),
            "dataVisualCount": sum(
                1
                for visual in all_visuals
                if visual["fields"]
            ),
            "bookmarkCount": len(bookmarks),
            "unresolvedFieldReferenceCount": len(
                unresolved_references
            ),
        },
        "sanitization": {
            "filterSelectionValuesExcluded": True,
            "bookmarkExplorationStateExcluded": True,
            "visualImagesAndResourceContentExcluded": True,
        },
    }


def get_report_metadata(
    report_files: Dict[str, str],
    tables: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Parse every PBIR report found in the uploaded project ZIP."""

    report_roots = sorted({
        report_root
        for file_name in report_files
        if (report_root := _get_report_root(file_name)) is not None
    })
    model_index = _build_model_index(tables)

    return [
        _parse_report(
            report_root,
            report_files,
            model_index,
        )
        for report_root in report_roots
    ]
