#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#

from contextlib import nullcontext as does_not_raise
from datetime import datetime
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pendulum
import pytest
from airbyte_cdk.models import (
    AirbyteMessage,
    AirbyteRecordMessage,
    AirbyteStateBlob,
    AirbyteStateMessage,
    AirbyteStateType,
    AirbyteStream,
    AirbyteStreamState,
    ConfiguredAirbyteCatalog,
    ConfiguredAirbyteStream,
    DestinationSyncMode,
    StreamDescriptor,
    SyncMode,
    Type,
)
from source_acceptance_test.config import IncrementalConfig
from source_acceptance_test.tests.test_incremental import TestIncremental as _TestIncremental
from source_acceptance_test.tests.test_incremental import compare_cursor_with_threshold


def build_messages_from_record_data(stream: str, records: list[dict]) -> list[AirbyteMessage]:
    return [build_record_message(stream, data) for data in records]


def build_record_message(stream: str, data: dict) -> AirbyteMessage:
    return AirbyteMessage(type=Type.RECORD, record=AirbyteRecordMessage(stream=stream, data=data, emitted_at=111))


def build_state_message(state: dict) -> AirbyteMessage:
    return AirbyteMessage(type=Type.STATE, state=AirbyteStateMessage(data=state))


def build_per_stream_state_message(
    descriptor: StreamDescriptor, stream_state: Optional[dict[str, Any]], data: Optional[dict[str, Any]] = None
) -> AirbyteMessage:
    if data is None:
        data = stream_state
    stream_state_blob = AirbyteStateBlob.parse_obj(stream_state) if stream_state else None
    return AirbyteMessage(
        type=Type.STATE,
        state=AirbyteStateMessage(
            type=AirbyteStateType.STREAM, stream=AirbyteStreamState(stream_descriptor=descriptor, stream_state=stream_state_blob), data=data
        ),
    )


@pytest.mark.parametrize(
    "record_value, state_value, threshold_days, expected_result",
    [
        (datetime(2020, 10, 10), datetime(2020, 10, 9), 0, True),
        (datetime(2020, 10, 10), datetime(2020, 10, 11), 0, False),
        (datetime(2020, 10, 10), datetime(2020, 10, 11), 1, True),
        (pendulum.parse("2020-10-10"), pendulum.parse("2020-10-09"), 0, True),
        (pendulum.parse("2020-10-10"), pendulum.parse("2020-10-11"), 0, False),
        (pendulum.parse("2020-10-10"), pendulum.parse("2020-10-11"), 1, True),
        ("2020-10-10", "2020-10-09", 0, True),
        ("2020-10-10", "2020-10-11", 0, False),
        ("2020-10-10", "2020-10-11", 1, True),
        (1602288000000, 1602201600000, 0, True),
        (1602288000000, 1602374400000, 0, False),
        (1602288000000, 1602374400000, 1, True),
        (1602288000, 1602201600, 0, True),
        (1602288000, 1602374400, 0, False),
        (1602288000, 1602374400, 1, True),
        ("aaa", "bbb", 0, False),
        ("bbb", "aaa", 0, True),
    ],
)
def test_compare_cursor_with_threshold(record_value, state_value, threshold_days, expected_result):
    assert compare_cursor_with_threshold(record_value, state_value, threshold_days) == expected_result


@pytest.mark.parametrize("cursor_type", ["date", "string"])
@pytest.mark.parametrize(
    "records1, records2, latest_state, threshold_days, expected_error",
    [
        ([{"date": "2020-01-01"}, {"date": "2020-01-02"}], [], "2020-01-02", 0, does_not_raise()),
        (
            [{"date": "2020-01-02"}, {"date": "2020-01-03"}],
            [],
            "2020-01-02",
            0,
            pytest.raises(AssertionError, match="First incremental sync should produce records younger"),
        ),
        (
            [{"date": "2020-01-01"}, {"date": "2020-01-02"}],
            [{"date": "2020-01-02"}, {"date": "2020-01-03"}],
            "2020-01-02",
            0,
            does_not_raise(),
        ),
        (
            [{"date": "2020-01-01"}],
            [{"date": "2020-01-01"}],
            "2020-01-02",
            0,
            pytest.raises(AssertionError, match="Second incremental sync should produce records older"),
        ),
        (
            [{"date": "2020-01-01"}, {"date": "2020-01-02"}],
            [{"date": "2020-01-01"}, {"date": "2020-01-02"}],
            "2020-01-03",
            2,
            does_not_raise(),
        ),
        (
            [{"date": "2020-01-02"}, {"date": "2020-01-03"}],
            [],
            "2020-01-02",
            2,
            pytest.raises(AssertionError, match="First incremental sync should produce records younger"),
        ),
        (
            [{"date": "2020-01-01"}],
            [{"date": "2020-01-02"}],
            "2020-01-06",
            3,
            pytest.raises(AssertionError, match="Second incremental sync should produce records older"),
        ),
    ],
)
@pytest.mark.parametrize(
    "run_per_stream_test",
    [
        pytest.param(False, id="test_two_sequential_reads_using_a_mock_connector_emitting_legacy_state"),
        pytest.param(True, id="test_two_sequential_reads_using_a_mock_connector_emitting_per_stream_state"),
    ],
)
def test_incremental_two_sequential_reads(
    records1, records2, latest_state, threshold_days, cursor_type, expected_error, run_per_stream_test
):
    input_config = IncrementalConfig(threshold_days=threshold_days)
    cursor_paths = {"test_stream": ["date"]}
    catalog = ConfiguredAirbyteCatalog(
        streams=[
            ConfiguredAirbyteStream(
                stream=AirbyteStream(
                    name="test_stream",
                    json_schema={"type": "object", "properties": {"date": {"type": cursor_type}}},
                    supported_sync_modes=[SyncMode.full_refresh, SyncMode.incremental],
                ),
                sync_mode=SyncMode.incremental,
                destination_sync_mode=DestinationSyncMode.overwrite,
                cursor_field=["date"],
            )
        ]
    )

    if run_per_stream_test:
        call_read_output_messages = [
            *build_messages_from_record_data("test_stream", records1),
            build_per_stream_state_message(descriptor=StreamDescriptor(name="test_stream"), stream_state={"date": latest_state}),
        ]
        call_read_with_state_output_messages = build_messages_from_record_data("test_stream", records2)
    else:
        call_read_output_messages = [
            *build_messages_from_record_data("test_stream", records1),
            build_state_message({"date": latest_state}),
        ]
        call_read_with_state_output_messages = build_messages_from_record_data("test_stream", records2)

    docker_runner_mock = MagicMock()
    docker_runner_mock.call_read.return_value = call_read_output_messages
    docker_runner_mock.call_read_with_state.return_value = call_read_with_state_output_messages

    t = _TestIncremental()
    with expected_error:
        t.test_two_sequential_reads(
            inputs=input_config,
            connector_config=MagicMock(),
            configured_catalog_for_incremental=catalog,
            cursor_paths=cursor_paths,
            docker_runner=docker_runner_mock,
        )


@pytest.mark.parametrize(
    "records, state_records, threshold_days, expected_error",
    [
        pytest.param(
            [
                {"type": Type.STATE, "name": "test_stream", "stream_state": {}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-07"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-08"}},
                {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-09"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-09"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-10"}},
                {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-11"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-12"}},
                {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-13"}},
            ],
            [
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-07"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-08"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-09"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-09"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-10"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-12"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-13"}},
                ],
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-09"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-09"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-10"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-12"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-13"}},
                ],
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-12"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-13"}},
                ],
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-13"}},
                ],
            ],
            0,
            does_not_raise(),
            id="test_incremental_with_2_states",
        ),
        pytest.param(
            [
                {"type": Type.STATE, "name": "test_stream", "stream_state": {}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-07"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-08"}},
                {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-09"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-12"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-13"}},
                {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
            ],
            [
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-07"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-08"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-09"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-12"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-13"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                ],
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-09"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-12"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-13"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                ],
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                ],
            ],
            0,
            pytest.raises(AssertionError),
            id="test_first_incremental_only_younger_records",
        ),
        pytest.param(
            [
                {"type": Type.STATE, "name": "test_stream", "stream_state": {}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-07"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-08"}},
                {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-09"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-07"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-08"}},
                {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
            ],
            [
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-07"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-08"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-09"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-07"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-08"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                ],
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-09"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-07"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-08"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                ],
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                ],
            ],
            3,
            does_not_raise(),
            id="test_incremental_with_threshold",
        ),
        pytest.param(
            [
                {"type": Type.STATE, "name": "test_stream", "stream_state": {}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-07"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-08"}},
                {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-09"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-04"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-05"}},
                {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-11"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-12"}},
                {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-13"}},
            ],
            [
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-07"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-08"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-09"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-04"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-05"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-12"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-13"}},
                ],
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-09"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-04"}},  # out of order
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-05"}},  # out of order
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-12"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-13"}},
                ],
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-12"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-13"}},
                ],
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-13"}},
                ],
            ],
            0,
            pytest.raises(AssertionError),
            id="test_incremental_with_incorrect_messages",
        ),
        pytest.param(
            [
                {"type": Type.STATE, "name": "test_stream", "stream_state": {}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-07"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-08"}},
                {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-09"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-09"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-10"}},
                {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-11"}},
                {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-12"}},
                {
                    "type": Type.STATE,
                    "name": "test_stream_2",
                    "stream_state": {"date": "2022-05-13"},
                    "data": {"test_stream": {"date": "2022-05-11"}, "test_stream_2": {"date": "2022-05-13"}},
                },
                {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-13"}},
                {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-14"}},
                {
                    "type": Type.STATE,
                    "name": "test_stream_2",
                    "stream_state": {"date": "2022-05-15"},
                    "data": {"test_stream": {"date": "2022-05-11"}, "test_stream_2": {"date": "2022-05-15"}},
                },
            ],
            [
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-07"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-08"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-09"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-09"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-10"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-12"}},
                    {
                        "type": Type.STATE,
                        "name": "test_stream_2",
                        "stream_state": {"date": "2022-05-13"},
                        "data": {"test_stream": {"date": "2022-05-11"}, "test_stream_2": {"date": "2022-05-13"}},
                    },
                    {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-13"}},
                    {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-14"}},
                    {
                        "type": Type.STATE,
                        "name": "test_stream_2",
                        "stream_state": {"date": "2022-05-15"},
                        "data": {"test_stream": {"date": "2022-05-11"}, "test_stream_2": {"date": "2022-05-15"}},
                    },
                ],
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-09"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-09"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-10"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-12"}},
                    {
                        "type": Type.STATE,
                        "name": "test_stream_2",
                        "stream_state": {"date": "2022-05-13"},
                        "data": {"test_stream": {"date": "2022-05-11"}, "test_stream_2": {"date": "2022-05-13"}},
                    },
                    {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-13"}},
                    {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-14"}},
                    {
                        "type": Type.STATE,
                        "name": "test_stream_2",
                        "stream_state": {"date": "2022-05-15"},
                        "data": {"test_stream": {"date": "2022-05-11"}, "test_stream_2": {"date": "2022-05-15"}},
                    },
                ],
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-11"}},
                    {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-12"}},
                    {
                        "type": Type.STATE,
                        "name": "test_stream_2",
                        "stream_state": {"date": "2022-05-13"},
                        "data": {"test_stream": {"date": "2022-05-11"}, "test_stream_2": {"date": "2022-05-13"}},
                    },
                    {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-13"}},
                    {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-14"}},
                    {
                        "type": Type.STATE,
                        "name": "test_stream_2",
                        "stream_state": {"date": "2022-05-15"},
                        "data": {"test_stream": {"date": "2022-05-11"}, "test_stream_2": {"date": "2022-05-15"}},
                    },
                ],
                [
                    {
                        "type": Type.STATE,
                        "name": "test_stream_2",
                        "stream_state": {"date": "2022-05-13"},
                        "data": {"test_stream": {"date": "2022-05-11"}, "test_stream_2": {"date": "2022-05-13"}},
                    },
                    {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-13"}},
                    {"type": Type.RECORD, "name": "test_stream_2", "data": {"date": "2022-05-14"}},
                    {
                        "type": Type.STATE,
                        "name": "test_stream_2",
                        "stream_state": {"date": "2022-05-15"},
                        "data": {"test_stream": {"date": "2022-05-11"}, "test_stream_2": {"date": "2022-05-15"}},
                    },
                ],
                [
                    {
                        "type": Type.STATE,
                        "name": "test_stream_2",
                        "stream_state": {"date": "2022-05-15"},
                        "data": {"test_stream": {"date": "2022-05-11"}, "test_stream_2": {"date": "2022-05-15"}},
                    },
                ],
            ],
            0,
            does_not_raise(),
            id="test_incremental_with_multiple_streams",
        ),
        pytest.param(
            [
                {"type": Type.STATE, "name": "test_stream", "stream_state": None},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-07"}},
                {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-08"}},
                {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-09"}},
            ],
            [
                [
                    {"type": Type.STATE, "name": "test_stream", "stream_state": None},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-07"}},
                    {"type": Type.RECORD, "name": "test_stream", "data": {"date": "2022-05-08"}},
                    {"type": Type.STATE, "name": "test_stream", "stream_state": {"date": "2022-05-09"}},
                ],
                [],
            ],
            0,
            does_not_raise(),
            id="test_incremental_with_none_state",
        ),
    ],
)
@pytest.mark.parametrize(
    "run_per_stream_test",
    [
        pytest.param(False, id="test_read_with_multiple_states_using_a_mock_connector_emitting_legacy_state"),
        pytest.param(True, id="test_read_with_multiple_states_using_a_mock_connector_emitting_per_stream_state"),
    ],
)
def test_per_stream_read_with_multiple_states(records, state_records, threshold_days, expected_error, run_per_stream_test):
    input_config = IncrementalConfig(threshold_days=threshold_days)
    cursor_paths = {"test_stream": ["date"], "test_stream_2": ["date"]}
    catalog = ConfiguredAirbyteCatalog(
        streams=[
            ConfiguredAirbyteStream(
                stream=AirbyteStream(
                    name="test_stream",
                    json_schema={"type": "object", "properties": {"date": {"type": "date"}}},
                    supported_sync_modes=[SyncMode.full_refresh, SyncMode.incremental],
                ),
                sync_mode=SyncMode.incremental,
                destination_sync_mode=DestinationSyncMode.overwrite,
                cursor_field=["date"],
            ),
            ConfiguredAirbyteStream(
                stream=AirbyteStream(
                    name="test_stream_2",
                    json_schema={"type": "object", "properties": {"date": {"type": "date"}}},
                    supported_sync_modes=[SyncMode.full_refresh, SyncMode.incremental],
                ),
                sync_mode=SyncMode.incremental,
                destination_sync_mode=DestinationSyncMode.overwrite,
                cursor_field=["date"],
            ),
        ]
    )

    if run_per_stream_test:
        call_read_output_messages = [
            build_per_stream_state_message(
                descriptor=StreamDescriptor(name=record["name"]), stream_state=record["stream_state"], data=record.get("data", None)
            )
            if record["type"] == Type.STATE
            else build_record_message(record["name"], record["data"])
            for record in list(records)
        ]
        call_read_with_state_output_messages = [
            [
                build_per_stream_state_message(
                    descriptor=StreamDescriptor(name=record["name"]), stream_state=record["stream_state"], data=record.get("data", None)
                )
                if record["type"] == Type.STATE
                else build_record_message(stream=record["name"], data=record["data"])
                for record in state_records_group
            ]
            for state_records_group in list(state_records)
        ]
    else:
        call_read_output_messages = [
            build_state_message(state=record.get("data") or {record["name"]: record["stream_state"]})
            if record["type"] == Type.STATE
            else build_record_message(stream=record["name"], data=record["data"])
            for record in list(records)
        ]
        call_read_with_state_output_messages = [
            [
                build_state_message(state=record.get("data") or {record["name"]: record["stream_state"]})
                if record["type"] == Type.STATE
                else build_record_message(stream=record["name"], data=record["data"])
                for record in state_records_group
            ]
            for state_records_group in list(state_records)
        ]

    docker_runner_mock = MagicMock()
    docker_runner_mock.call_read.return_value = call_read_output_messages
    docker_runner_mock.call_read_with_state.side_effect = call_read_with_state_output_messages

    t = _TestIncremental()
    with expected_error:
        t.test_read_sequential_slices(
            inputs=input_config,
            connector_config=MagicMock(),
            configured_catalog_for_incremental=catalog,
            cursor_paths=cursor_paths,
            docker_runner=docker_runner_mock,
        )


def test_config_skip_test():
    docker_runner_mock = MagicMock()
    docker_runner_mock.call_read.return_value = []
    t = _TestIncremental()
    with patch.object(pytest, "skip", return_value=None):
        t.test_read_sequential_slices(
            inputs=IncrementalConfig(skip_comprehensive_incremental_tests=True),
            connector_config=MagicMock(),
            configured_catalog_for_incremental=ConfiguredAirbyteCatalog(
                streams=[
                    ConfiguredAirbyteStream(
                        stream=AirbyteStream(
                            name="test_stream",
                            json_schema={"type": "object", "properties": {"date": {"type": "date"}}},
                            supported_sync_modes=[SyncMode.full_refresh, SyncMode.incremental],
                        ),
                        sync_mode=SyncMode.incremental,
                        destination_sync_mode=DestinationSyncMode.overwrite,
                        cursor_field=["date"],
                    )
                ]
            ),
            cursor_paths={},
            docker_runner=docker_runner_mock,
        )

    # This is guaranteed to fail when the test gets executed
    docker_runner_mock.call_read.assert_not_called()
