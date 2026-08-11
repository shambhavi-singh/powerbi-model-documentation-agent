import argparse
from pathlib import Path, PurePosixPath
import re
import textwrap

from typing import Any, Dict, List
from zipfile import BadZipFile, ZipFile


MAX_ZIP_SIZE = 25 * 1024 * 1024
MAX_UNCOMPRESSED_SIZE = 100 * 1024 * 1024
MAX_FILE_COUNT = 5000
IDENTIFIER_PATTERN = r"'(?:[^']|'')*'|[^\s=]+"

TABLE_DECLARATION = re.compile(
    rf"^table\s+(?P<name>{IDENTIFIER_PATTERN})\s*$",
    re.MULTILINE,
)
COLUMN_DECLARATION = re.compile(
    (
        rf"^\tcolumn[ \t]+"
        rf"(?P<name>{IDENTIFIER_PATTERN})"
        rf"(?:[ \t]*=[ \t]*(?P<expression>.*))?[ \t]*$"
    ),
    re.MULTILINE,
)

MEASURE_DECLARATION = re.compile(
    (
        rf"^\tmeasure[ \t]+"
        rf"(?P<name>{IDENTIFIER_PATTERN})[ \t]*="
        rf"[ \t]*(?P<expression>.*)$"
    ),
    re.MULTILINE,
)

RELATIONSHIP_DECLARATION = re.compile(
    r"^relationship\s+(?P<name>.+?)\s*$"
)
ROLE_DECLARATION = re.compile(
    rf"^role\s+(?P<name>{IDENTIFIER_PATTERN})\s*$"
)
TABLE_PERMISSION_DECLARATION = re.compile(
    (
        rf"^\ttablePermission[ \t]+"
        rf"(?P<table>{IDENTIFIER_PATTERN})[ \t]*="
        rf"[ \t]*(?P<expression>.*)$"
    )
)
PERSPECTIVE_DECLARATION = re.compile(
    rf"^perspective\s+(?P<name>{IDENTIFIER_PATTERN})\s*$"
)
PERSPECTIVE_TABLE_DECLARATION = re.compile(
    rf"^\tperspectiveTable\s+(?P<name>{IDENTIFIER_PATTERN})\s*$"
)
EXPRESSION_DECLARATION = re.compile(
    rf"^expression\s+(?P<name>{IDENTIFIER_PATTERN})[ \t]*="
)

MEASURE_PROPERTY_PREFIXES = (
    "formatString:",
    "lineageTag:",
    "displayFolder:",
    "isHidden",
    "kpi",
    "annotation ",
    "changedProperty",
    "formatStringDefinition",
    "detailRowsDefinition",
)

COLUMN_PROPERTY_PREFIXES = (
    "dataType:",
    "formatString:",
    "lineageTag:",
    "summarizeBy:",
    "sourceColumn:",
    "sortByColumn:",
    "dataCategory:",
    "isHidden",
    "isKey",
    "isAvailableInMdx:",
    "annotation ",
    "changedProperty",
)


def clean_identifier(value: str) -> str:
    """Remove TMDL quotation marks from an object name."""

    value = value.strip()

    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")

    return value


def get_description_before(
    lines: List[str],
    declaration_index: int,
    indentation: str,
) -> str:
    """Read consecutive TMDL /// description lines before an object."""

    description_lines = []
    index = declaration_index - 1
    prefix = f"{indentation}///"

    while index >= 0 and lines[index].startswith(prefix):
        description_lines.insert(
            0,
            lines[index][len(prefix):].strip(),
        )
        index -= 1

    return " ".join(description_lines).strip()


def get_object_block(
    lines: List[str],
    declaration_index: int,
) -> List[str]:
    """Return one table-level object's declaration and property lines."""

    end_index = len(lines)

    for index in range(declaration_index + 1, len(lines)):
        line = lines[index]

        if (
            line.startswith("\t")
            and not line.startswith("\t\t")
            and line.strip()
        ):
            end_index = index
            break

    return lines[declaration_index:end_index]


def get_root_object_block(
    lines: List[str],
    declaration_index: int,
) -> List[str]:
    """Return a top-level TMDL object's declaration and child lines."""

    end_index = len(lines)

    for index in range(declaration_index + 1, len(lines)):
        line = lines[index]

        if line.strip() and not line.startswith(("\t", " ")):
            end_index = index
            break

    return lines[declaration_index:end_index]


def get_root_property_value(
    block: List[str],
    property_name: str,
    default: str = "",
) -> str:
    """Get a direct property from a top-level TMDL object block."""

    prefix = f"\t{property_name}:"

    for line in block[1:]:
        if line.startswith(prefix):
            return line[len(prefix):].strip()

    return default


def get_property_value(
    block: List[str],
    property_name: str,
    default: str = "",
) -> str:
    """Get a direct property from a column or measure block."""

    prefix = f"\t\t{property_name}:"

    for line in block[1:]:
        if line.startswith(prefix):
            return line[len(prefix):].strip()

    return default


def has_object_flag(
    block: List[str],
    flag_name: str,
) -> bool:
    """Check for a Boolean TMDL property written as a standalone flag."""

    expected_line = f"\t\t{flag_name}"

    return any(line.strip() == expected_line.strip() for line in block[1:])


def extract_measure_expression(
    declaration_match: re.Match,
    block: List[str],
) -> str:
    """Extract a single-line, multiline, or fenced DAX expression."""

    inline_expression = declaration_match.group("expression").strip()

    if inline_expression and inline_expression != "```":
        return inline_expression

    expression_lines = []

    for line in block[1:]:
        stripped_line = line.strip()

        if inline_expression == "```" and stripped_line == "```":
            break

        is_direct_property = (
            line.startswith("\t\t")
            and not line.startswith("\t\t\t")
            and stripped_line.startswith(MEASURE_PROPERTY_PREFIXES)
        )

        if is_direct_property:
            break

        expression_lines.append(line)

    expression = textwrap.dedent(
        "\n".join(expression_lines)
    ).strip()

    return expression


def extract_column_expression(
    declaration_match: re.Match,
    block: List[str],
) -> str:
    """Extract inline or multiline DAX for a calculated column."""

    declaration = declaration_match.group(0)

    if "=" not in declaration:
        return ""

    inline_expression = (
        declaration_match.group("expression") or ""
    ).strip()

    if inline_expression:
        return inline_expression

    expression_lines = []

    for line in block[1:]:
        stripped_line = line.strip()
        is_direct_property = (
            line.startswith("\t\t")
            and not line.startswith("\t\t\t")
            and stripped_line.startswith(COLUMN_PROPERTY_PREFIXES)
        )

        if is_direct_property:
            break

        expression_lines.append(line)

    return textwrap.dedent(
        "\n".join(expression_lines)
    ).strip()


def get_table_names(
    tmdl_files: Dict[str, str]
) -> List[str]:
    """Extract table names from all table TMDL files."""

    table_names = []

    for file_name, content in tmdl_files.items():
        file_path = PurePosixPath(file_name)

        if "tables" not in file_path.parts:
            continue

        match = TABLE_DECLARATION.search(content)

        if match is None:
            raise ValueError(
                f"No table declaration found in {file_name}."
            )

        table_name = clean_identifier(
            match.group("name")
        )

        table_names.append(table_name)

    return sorted(table_names)


def get_table_objects(
    tmdl_files: Dict[str, str]
) -> Dict[str, Dict[str, Any]]:
    """Extract descriptions, columns, and measures for every table."""

    table_objects = {}

    for file_name, content in sorted(
        tmdl_files.items()
    ):
        file_path = PurePosixPath(file_name)

        if "tables" not in file_path.parts:
            continue

        table_match = TABLE_DECLARATION.search(content)

        if table_match is None:
            raise ValueError(
                f"No table declaration found in {file_name}."
            )

        table_name = clean_identifier(
            table_match.group("name")
        )

        lines = content.splitlines()
        table_line_index = content[:table_match.start()].count("\n")
        table_description = get_description_before(
            lines,
            table_line_index,
            "",
        )

        columns = []
        measures = []

        for line_index, line in enumerate(lines):
            column_match = COLUMN_DECLARATION.match(line)

            if column_match is not None:
                block = get_object_block(lines, line_index)
                calculated_expression = extract_column_expression(
                    column_match,
                    block,
                )
                is_calculated = "=" in column_match.group(0)

                columns.append({
                    "name": clean_identifier(
                        column_match.group("name")
                    ),
                    "description": get_description_before(
                        lines,
                        line_index,
                        "\t",
                    ),
                    "dataType": get_property_value(
                        block,
                        "dataType",
                        "calculated" if is_calculated else "unknown",
                    ),
                    "sourceColumn": get_property_value(
                        block,
                        "sourceColumn",
                    ),
                    "formatString": get_property_value(
                        block,
                        "formatString",
                    ),
                    "summarizeBy": get_property_value(
                        block,
                        "summarizeBy",
                    ),
                    "isHidden": has_object_flag(
                        block,
                        "isHidden",
                    ),
                    "isKey": has_object_flag(
                        block,
                        "isKey",
                    ),
                    "expression": calculated_expression,
                    "isCalculated": is_calculated,
                })

            measure_match = MEASURE_DECLARATION.match(line)

            if measure_match is not None:
                block = get_object_block(lines, line_index)

                measures.append({
                    "name": clean_identifier(
                        measure_match.group("name")
                    ),
                    "description": get_description_before(
                        lines,
                        line_index,
                        "\t",
                    ),
                    "expression": extract_measure_expression(
                        measure_match,
                        block,
                    ),
                    "formatString": get_property_value(
                        block,
                        "formatString",
                    ),
                    "displayFolder": get_property_value(
                        block,
                        "displayFolder",
                    ),
                    "isHidden": has_object_flag(
                        block,
                        "isHidden",
                    ),
                })

        table_objects[table_name] = {
            "description": table_description,
            "columns": columns,
            "measures": measures,
        }

    return table_objects


def get_relationships(
    tmdl_files: Dict[str, str]
) -> List[Dict[str, Any]]:
    """Extract relationship endpoints and important behavior flags."""

    relationships = []

    for file_name, content in sorted(tmdl_files.items()):
        if PurePosixPath(file_name).name != "relationships.tmdl":
            continue

        lines = content.splitlines()

        for line_index, line in enumerate(lines):
            match = RELATIONSHIP_DECLARATION.match(line)

            if match is None:
                continue

            block = get_root_object_block(lines, line_index)
            active_value = get_root_property_value(
                block,
                "isActive",
                "true",
            )

            relationships.append({
                "name": clean_identifier(match.group("name")),
                "fromColumn": get_root_property_value(
                    block,
                    "fromColumn",
                ),
                "toColumn": get_root_property_value(
                    block,
                    "toColumn",
                ),
                "isActive": active_value.lower() != "false",
                "crossFilteringBehavior": get_root_property_value(
                    block,
                    "crossFilteringBehavior",
                    "oneDirection",
                ),
                "securityFilteringBehavior": get_root_property_value(
                    block,
                    "securityFilteringBehavior",
                ),
            })

    return relationships


def get_security_roles(
    tmdl_files: Dict[str, str]
) -> List[Dict[str, Any]]:
    """Extract role names, model permission, and table filters."""

    roles = []

    for file_name, content in sorted(tmdl_files.items()):
        file_path = PurePosixPath(file_name)

        if "roles" not in file_path.parts:
            continue

        lines = content.splitlines()
        role_match = next(
            (
                ROLE_DECLARATION.match(line)
                for line in lines
                if ROLE_DECLARATION.match(line) is not None
            ),
            None,
        )

        if role_match is None:
            continue

        role_index = next(
            index
            for index, line in enumerate(lines)
            if ROLE_DECLARATION.match(line) is not None
        )
        role_block = get_root_object_block(lines, role_index)
        table_permissions = []

        for line in role_block:
            permission_match = TABLE_PERMISSION_DECLARATION.match(line)

            if permission_match is None:
                continue

            table_permissions.append({
                "table": clean_identifier(
                    permission_match.group("table")
                ),
                "filterExpression": permission_match.group(
                    "expression"
                ).strip(),
            })

        roles.append({
            "name": clean_identifier(role_match.group("name")),
            "modelPermission": get_root_property_value(
                role_block,
                "modelPermission",
                "read",
            ),
            "tablePermissions": table_permissions,
        })

    return roles


def get_perspectives(
    tmdl_files: Dict[str, str]
) -> List[Dict[str, Any]]:
    """Extract perspective names and the tables included in each one."""

    perspectives = []

    for file_name, content in sorted(tmdl_files.items()):
        file_path = PurePosixPath(file_name)

        if "perspectives" not in file_path.parts:
            continue

        lines = content.splitlines()
        perspective_match = next(
            (
                PERSPECTIVE_DECLARATION.match(line)
                for line in lines
                if PERSPECTIVE_DECLARATION.match(line) is not None
            ),
            None,
        )

        if perspective_match is None:
            continue

        table_names = []

        for line in lines:
            table_match = PERSPECTIVE_TABLE_DECLARATION.match(line)

            if table_match is not None:
                table_names.append(
                    clean_identifier(table_match.group("name"))
                )

        perspectives.append({
            "name": clean_identifier(
                perspective_match.group("name")
            ),
            "tables": table_names,
        })

    return perspectives


def get_cultures(tmdl_files: Dict[str, str]) -> List[str]:
    """Return culture identifiers represented by culture TMDL files."""

    cultures = []

    for file_name in tmdl_files:
        file_path = PurePosixPath(file_name)

        if "cultures" in file_path.parts:
            cultures.append(file_path.stem)

    return sorted(cultures)


def get_shared_expression_names(
    tmdl_files: Dict[str, str]
) -> List[str]:
    """Return shared-expression names without exposing their M source."""

    names = []

    for file_name, content in tmdl_files.items():
        if PurePosixPath(file_name).name != "expressions.tmdl":
            continue

        for line in content.splitlines():
            match = EXPRESSION_DECLARATION.match(line)

            if match is not None:
                names.append(clean_identifier(match.group("name")))

    return sorted(names)


def load_tmdl_files(zip_path: str) -> Dict[str, str]:
    """Safely load TMDL text files from a definition ZIP."""

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
                raise ValueError(
                    "The ZIP contains too many files."
                )

            total_size = sum(
                entry.file_size
                for entry in file_entries
            )

            if total_size > MAX_UNCOMPRESSED_SIZE:
                raise ValueError(
                    "The uncompressed content exceeds 100 MB."
                )

            tmdl_files: Dict[str, str] = {}

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

                if member_path.suffix.lower() != ".tmdl":
                    continue

                try:
                    content = archive.read(entry).decode(
                        "utf-8-sig"
                    )
                except UnicodeDecodeError as error:
                    raise ValueError(
                        f"{raw_name} is not valid UTF-8 text."
                    ) from error

                tmdl_files[str(member_path)] = content

    except BadZipFile as error:
        raise ValueError(
            "The uploaded file is not a valid ZIP."
        ) from error

    has_model = any(
        PurePosixPath(name).name == "model.tmdl"
        for name in tmdl_files
    )

    if not has_model:
        raise ValueError(
            "The ZIP does not contain model.tmdl."
        )

    table_files = [
        name
        for name in tmdl_files
        if (
            "tables" in PurePosixPath(name).parts
            and name.endswith(".tmdl")
        )
    ]

    if not table_files:
        raise ValueError(
            "The ZIP does not contain any table TMDL files."
        )

    return tmdl_files


def main() -> None:
    """Inspect any semantic-model definition ZIP from the command line."""

    argument_parser = argparse.ArgumentParser(
        description="Inspect a Power BI TMDL definition ZIP."
    )
    argument_parser.add_argument(
        "zip_path",
        help="Path to the semantic-model definition ZIP.",
    )
    arguments = argument_parser.parse_args()

    files = load_tmdl_files(arguments.zip_path)

    print(f"Loaded {len(files)} TMDL files:")

    for file_name in sorted(files):
        print(f"- {file_name}")

    tables = get_table_names(files)

    print(f"\nFound {len(tables)} tables:")

    for table_name in tables:
        print(f"- {table_name}")

    table_objects = get_table_objects(files)

    print("\nTable object counts:")

    for table_name, objects in table_objects.items():
        column_count = len(objects["columns"])
        measure_count = len(objects["measures"])

        print(
            f"- {table_name}: "
            f"{column_count} columns, "
            f"{measure_count} measures"
        )


if __name__ == "__main__":
    main()
