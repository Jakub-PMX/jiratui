from datetime import date
from unittest.mock import AsyncMock, Mock, patch

import pytest
from textual.widgets import Button, DataTable

from jiratui.api_controller.controller import APIControllerResponse
from jiratui.app import JiraApp
from jiratui.models import DailyWorklogEntry, DailyWorklogSummary
from jiratui.widgets.work_log_summary import WorkLogSummaryScreen, format_duration


@pytest.mark.parametrize(
    'seconds, expected',
    [
        (0, '0m'),
        (60, '1m'),
        (3600, '1h'),
        (5400, '1h 30m'),
        (7200, '2h'),
        (3661, '1h 1m'),
        (180, '3m'),
    ],
)
def test_format_duration(seconds: int, expected: str):
    assert format_duration(seconds) == expected


@pytest.mark.asyncio
@patch.object(JiraApp, 'api')
async def test_worklog_summary_screen_compose(app):
    async with app.run_test():
        await app.push_screen(WorkLogSummaryScreen())
        screen = app.screen

        assert isinstance(screen.query_one('#worklog-from-date'), type(screen.from_date_input))
        assert isinstance(screen.query_one('#worklog-to-date'), type(screen.to_date_input))
        assert isinstance(screen.query_one('#worklog-search-button'), Button)
        assert isinstance(screen.query_one('#worklog-summary-table'), DataTable)
        assert isinstance(screen.query_one('#worklog-itemised-table'), DataTable)


@pytest.mark.asyncio
@patch.object(JiraApp, 'api')
async def test_worklog_summary_screen_search_success(api_mock: Mock, app):
    api_mock.get_worklogs_by_date_range = AsyncMock(
        return_value=APIControllerResponse(
            result=[
                DailyWorklogSummary(
                    date=date(2025, 10, 15),
                    total_seconds=7200,
                    entries=[
                        DailyWorklogEntry(
                            date=date(2025, 10, 15),
                            issue_key='PROJ-1',
                            issue_summary='Test Issue',
                            time_spent='2h',
                            time_spent_seconds=7200,
                            comment='Some work',
                        )
                    ],
                )
            ]
        )
    )

    async with app.run_test() as pilot:
        await app.push_screen(WorkLogSummaryScreen())
        screen = app.screen

        # Trigger search by clicking the button
        await pilot.click('#worklog-search-button')
        await pilot.pause()

        summary_table = screen.query_one('#worklog-summary-table', DataTable)
        itemised_table = screen.query_one('#worklog-itemised-table', DataTable)

        assert len(summary_table.rows) == 1
        assert len(itemised_table.rows) == 1
        api_mock.get_worklogs_by_date_range.assert_called_once()


@pytest.mark.asyncio
@patch.object(JiraApp, 'api')
async def test_worklog_summary_screen_search_no_results(api_mock: Mock, app):
    api_mock.get_worklogs_by_date_range = AsyncMock(
        return_value=APIControllerResponse(result=[])
    )

    async with app.run_test() as pilot:
        await app.push_screen(WorkLogSummaryScreen())
        screen = app.screen

        await pilot.click('#worklog-search-button')
        await pilot.pause()

        status_label = screen.query_one('#worklog-status-label')
        assert 'No worklogs found' in status_label.renderable.plain


@pytest.mark.asyncio
@patch.object(JiraApp, 'api')
async def test_worklog_summary_screen_search_error(api_mock: Mock, app):
    api_mock.get_worklogs_by_date_range = AsyncMock(
        return_value=APIControllerResponse(success=False, error='API error')
    )

    async with app.run_test() as pilot:
        await app.push_screen(WorkLogSummaryScreen())
        screen = app.screen

        await pilot.click('#worklog-search-button')
        await pilot.pause()

        status_label = screen.query_one('#worklog-status-label')
        assert 'Failed to fetch worklogs' in status_label.renderable.plain


@pytest.mark.asyncio
async def test_worklog_summary_screen_invalid_date(app):
    async with app.run_test() as pilot:
        await app.push_screen(WorkLogSummaryScreen())
        screen = app.screen

        screen.from_date_input.value = 'invalid-date'
        await pilot.click('#worklog-search-button')
        await pilot.pause()

        status_label = screen.query_one('#worklog-status-label')
        assert 'Invalid date format' in status_label.renderable.plain


@pytest.mark.asyncio
async def test_worklog_summary_screen_from_after_to(app):
    async with app.run_test() as pilot:
        await app.push_screen(WorkLogSummaryScreen())
        screen = app.screen

        screen.from_date_input.value = '2025-10-20'
        screen.to_date_input.value = '2025-10-15'
        await pilot.click('#worklog-search-button')
        await pilot.pause()

        status_label = screen.query_one('#worklog-status-label')
        assert 'From' in status_label.renderable.plain
