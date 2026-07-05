"""File collector — downloads and parses publicly accessible files (PDF, Excel, CSV)."""

from __future__ import annotations

from failsafe.collectors.base import BaseCollector, CollectionResult
from failsafe.schema import FileConfig
from failsafe.utils.parse import map_fields, parse_csv_text, parse_excel, parse_pdf
from failsafe.utils.request import RequestError, fetch_binary, fetch_page


class FileCollector(BaseCollector):
    def execute(self, config: FileConfig, **kwargs) -> CollectionResult:
        result = CollectionResult()
        rate_limit = kwargs.get("rate_limit", 1.0)

        try:
            if config.file_type == "csv":
                text = fetch_page(config.file_url, rate_limit=rate_limit, encoding=config.encoding)
                records = parse_csv_text(text)
            elif config.file_type in ("xlsx", "xls"):
                content = fetch_binary(config.file_url, rate_limit=rate_limit)
                records = parse_excel(
                    content,
                    sheet_name=config.sheet_name,
                    start_row=config.start_row,
                    header_row=config.header_row,
                )
            elif config.file_type == "pdf":
                content = fetch_binary(config.file_url, rate_limit=rate_limit)
                text = parse_pdf(content)
                records = [{"text": text, "source_url": config.file_url}]
            else:
                result.errors.append(f"Unsupported file type: {config.file_type}")
                return result

            for record in records:
                if config.field_mappings:
                    mapped = map_fields(record, {k: str(v) for k, v in config.field_mappings.items()})
                    result.records.append(mapped)
                else:
                    result.records.append(record)

        except RequestError as e:
            result.errors.append(str(e))
        except Exception as e:
            result.errors.append(f"File parsing failed: {e}")

        result.metadata["file_url"] = config.file_url
        result.metadata["file_type"] = config.file_type
        return result
