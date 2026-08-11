import json
from datetime import date
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from model_doc_agent.documenter import (
    build_documentation_metadata,
    build_documentation_prompt,
    build_model_metadata,
)
from model_doc_agent.report_parser import (
    get_report_metadata,
    load_report_files,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DEFINITION_ZIP = (
    PROJECT_ROOT / "sample_data" / "definition.zip"
)


class ReportParserTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project_zip = (
            Path(self.temporary_directory.name) / "SalesProject.zip"
        )
        self._create_project_zip()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _write_json(self, archive, file_name, value):
        archive.writestr(
            file_name,
            json.dumps(value),
        )

    def _create_project_zip(self):
        with ZipFile(SAMPLE_DEFINITION_ZIP, "r") as source:
            with ZipFile(self.project_zip, "w") as project:
                for entry in source.infolist():
                    if entry.is_dir() or not entry.filename.endswith(
                        ".tmdl"
                    ):
                        continue

                    project.writestr(
                        "Sales.SemanticModel/" + entry.filename,
                        source.read(entry),
                    )

                self._write_json(
                    project,
                    "Sales.Report/definition.pbir",
                    {
                        "version": "4.0",
                        "datasetReference": {
                            "byPath": {
                                "path": "../Sales.SemanticModel"
                            }
                        },
                    },
                )
                self._write_json(
                    project,
                    "Sales.Report/definition/report.json",
                    {
                        "layoutOptimization": "PhonePortrait",
                        "settings": {
                            "exportDataMode": (
                                "AllowSummarizedAndUnderlying"
                            )
                        },
                        "filterConfig": {
                            "filters": [
                                {
                                    "type": "Categorical",
                                    "field": {
                                        "Column": {
                                            "Expression": {
                                                "SourceRef": {
                                                    "Entity": "Store"
                                                }
                                            },
                                            "Property": "Country",
                                        }
                                    },
                                    "filter": {
                                        "Literal": {
                                            "Value": (
                                                "'CONFIDENTIAL_COUNTRY'"
                                            )
                                        }
                                    },
                                }
                            ]
                        },
                    },
                )
                self._write_json(
                    project,
                    "Sales.Report/definition/pages/pages.json",
                    {
                        "pageOrder": ["page1"],
                        "activePageName": "page1",
                    },
                )
                self._write_json(
                    project,
                    "Sales.Report/definition/pages/page1/page.json",
                    {
                        "name": "page1",
                        "displayName": "Sales Overview",
                        "width": 1280,
                        "height": 720,
                        "filterConfig": {
                            "filters": [
                                {
                                    "type": "Categorical",
                                    "field": {
                                        "Column": {
                                            "Expression": {
                                                "SourceRef": {
                                                    "Entity": "Calendar"
                                                }
                                            },
                                            "Property": "Year",
                                        }
                                    },
                                    "filter": {
                                        "Where": [
                                            {
                                                "Literal": {
                                                    "Value": (
                                                        "'CONFIDENTIAL_YEAR'"
                                                    )
                                                }
                                            }
                                        ]
                                    },
                                }
                            ]
                        },
                        "pageBinding": {
                            "type": "Drillthrough",
                            "parameters": [
                                {
                                    "fieldExpr": {
                                        "Column": {
                                            "Expression": {
                                                "SourceRef": {
                                                    "Entity": "Calendar"
                                                }
                                            },
                                            "Property": "Year",
                                        }
                                    }
                                }
                            ],
                        },
                    },
                )
                self._write_json(
                    project,
                    (
                        "Sales.Report/definition/pages/page1/visuals/"
                        "sales-card/visual.json"
                    ),
                    {
                        "name": "sales-card",
                        "visual": {
                            "visualType": "cardVisual",
                            "query": {
                                "queryState": {
                                    "Data": {
                                        "projections": [
                                            {
                                                "field": {
                                                    "Measure": {
                                                        "Expression": {
                                                            "SourceRef": {
                                                                "Entity": (
                                                                    "Sales"
                                                                )
                                                            }
                                                        },
                                                        "Property": (
                                                            "Sales Amount"
                                                        ),
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                }
                            },
                            "visualContainerObjects": {
                                "title": [
                                    {
                                        "properties": {
                                            "show": {
                                                "expr": {
                                                    "Literal": {
                                                        "Value": "true"
                                                    }
                                                }
                                            },
                                            "text": {
                                                "expr": {
                                                    "Literal": {
                                                        "Value": (
                                                            "'Revenue KPI'"
                                                        )
                                                    }
                                                }
                                            },
                                        }
                                    }
                                ]
                            },
                        },
                        "filterConfig": {
                            "filters": [
                                {
                                    "type": "Categorical",
                                    "field": {
                                        "Column": {
                                            "Expression": {
                                                "SourceRef": {
                                                    "Entity": "Customer"
                                                }
                                            },
                                            "Property": "CustomerKey",
                                        }
                                    },
                                    "filter": {
                                        "Literal": {
                                            "Value": (
                                                "'CONFIDENTIAL_CUSTOMER'"
                                            )
                                        }
                                    },
                                }
                            ]
                        },
                    },
                )
                self._write_json(
                    project,
                    (
                        "Sales.Report/definition/bookmarks/"
                        "executive.bookmark.json"
                    ),
                    {
                        "name": "executive",
                        "displayName": "Executive View",
                        "options": {
                            "targetVisualNames": ["sales-card"]
                        },
                        "explorationState": {
                            "secret": "CONFIDENTIAL_BOOKMARK_STATE"
                        },
                    },
                )

    def test_report_metadata_connects_visual_to_model(self):
        model_metadata = build_model_metadata(str(self.project_zip))
        report_files = load_report_files(str(self.project_zip))
        reports = get_report_metadata(
            report_files,
            model_metadata["tables"],
        )

        self.assertEqual(len(reports), 1)
        report = reports[0]
        self.assertEqual(report["name"], "Sales")
        self.assertEqual(
            report["semanticModelReference"],
            "Sales.SemanticModel",
        )
        self.assertEqual(report["statistics"]["pageCount"], 1)
        self.assertEqual(report["statistics"]["visualCount"], 1)
        self.assertEqual(report["filterCount"], 1)
        self.assertEqual(report["filters"][0]["fields"][0]["name"], "Country")
        self.assertTrue(
            report["filters"][0]["fields"][0]["modelMatch"]
        )

        page = report["pages"][0]
        self.assertEqual(page["displayName"], "Sales Overview")
        self.assertTrue(page["isActive"])
        self.assertEqual(
            page["drillthroughFields"][0]["name"],
            "Year",
        )

        visual = page["visuals"][0]
        self.assertEqual(visual["type"], "cardVisual")
        self.assertEqual(visual["title"], "Revenue KPI")
        self.assertEqual(visual["fields"][0]["role"], "Data")
        self.assertEqual(visual["fields"][0]["name"], "Sales Amount")
        self.assertTrue(visual["fields"][0]["modelMatch"])

    def test_sensitive_filter_and_bookmark_values_are_excluded(self):
        metadata = build_documentation_metadata(str(self.project_zip))
        serialized_metadata = json.dumps(metadata)

        self.assertNotIn("CONFIDENTIAL_YEAR", serialized_metadata)
        self.assertNotIn("CONFIDENTIAL_CUSTOMER", serialized_metadata)
        self.assertNotIn("CONFIDENTIAL_COUNTRY", serialized_metadata)
        self.assertNotIn(
            "CONFIDENTIAL_BOOKMARK_STATE",
            serialized_metadata,
        )
        self.assertNotIn("sales-card", serialized_metadata)
        self.assertIn("Calendar", serialized_metadata)
        self.assertIn("CustomerKey", serialized_metadata)
        self.assertIn("Executive View", serialized_metadata)

    def test_complete_project_prompt_is_summary_first(self):
        metadata = build_documentation_metadata(str(self.project_zip))
        prompt = build_documentation_prompt(
            metadata,
            detail_level="summary",
        )

        self.assertEqual(metadata["artifactType"], "powerBiProject")
        self.assertEqual(metadata["sourceFormat"], "PBIP Project")
        self.assertEqual(metadata["generatedOn"], date.today().isoformat())
        self.assertEqual(
            metadata["semanticModel"]["name"],
            "Sales.SemanticModel",
        )
        self.assertEqual(metadata["reportStatistics"]["pageCount"], 1)
        sales_amount_usage = next(
            item
            for item in metadata["semanticModel"]["measureUsage"]
            if item["measure"] == "Sales Amount"
        )
        self.assertEqual(sales_amount_usage["visualCount"], 1)
        self.assertEqual(
            sales_amount_usage["pages"],
            ["Sales / Sales Overview"],
        )
        self.assertIn(
            "Documentation detail level: SUMMARY",
            prompt,
        )
        self.assertIn("Revenue KPI", prompt)


if __name__ == "__main__":
    unittest.main()
