"""API collector — calls public APIs and maps response fields."""

from __future__ import annotations

from typing import Any

from failsafe.collectors.base import BaseCollector, CollectionResult
from failsafe.schema import APIConfig
from failsafe.utils.parse import extract_json_path, map_fields
from failsafe.utils.request import RequestError, fetch_json


class APICollector(BaseCollector):
    def execute(self, config: APIConfig, **kwargs) -> CollectionResult:
        result = CollectionResult()
        rate_limit = kwargs.get("rate_limit", 1.0)
        page = 1

        while page <= config.max_pages:
            params = dict(config.params)
            if config.pagination_param and page > 1:
                params[config.pagination_param] = self._page_value(config, page)

            try:
                data = fetch_json(
                    config.endpoint_url,
                    method=config.method,
                    headers=config.headers,
                    params=params,
                    body=config.body,
                    rate_limit=rate_limit,
                )

                records_data = extract_json_path(data, config.data_path)
                if records_data is None:
                    break

                if isinstance(records_data, dict):
                    records_data = [records_data]
                elif not isinstance(records_data, list):
                    result.errors.append(f"Unexpected data type at path {config.data_path}")
                    break

                if not records_data:
                    break

                for raw_record in records_data:
                    if isinstance(raw_record, dict):
                        mapped = map_fields(raw_record, config.field_mappings)
                        result.records.append(mapped)
                    else:
                        result.records.append({"value": raw_record})

                if not config.pagination_type:
                    break
                page += 1

            except RequestError as e:
                result.errors.append(str(e))
                break

        result.metadata["pages_fetched"] = page
        result.metadata["endpoint"] = config.endpoint_url
        return result

    def _page_value(self, config: APIConfig, page: int) -> Any:
        if config.pagination_type == "offset":
            page_size = config.params.get("limit", config.params.get("page_size", 20))
            return (page - 1) * int(page_size)
        return page
