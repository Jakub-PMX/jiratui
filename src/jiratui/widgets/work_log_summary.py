from datetime import date, datetime, timedelta
from typing import cast

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ItemGrid, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Label, Static

from jiratui.api_controller.controller import APIControllerResponse
from jiratui.models import DailyWorklogSummary
from jiratui.widgets.base import DateInput


def format_duration(seconds: int) -> str:
    """Formats a duration in seconds to a human-readable string.

    Args:
        seconds: the number of seconds.

    Returns:
        A string like "1h 30m", "2h", "45m", etc.
    """
    if seconds <= 0:
        return '0m'
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours and minutes:
        return f'{hours}h {minutes}m'
    elif hours:
        return f'{hours}h'
    else:
        return f'{minutes}m'


class WorklogFromDateInput(DateInput):
    """A date input for the 'from' date in the worklog summary screen."""

    ID = 'worklog-from-date'
    LABEL = 'From'
    TOOLTIP = 'Start date for worklog search (inclusive)'


class WorklogToDateInput(DateInput):
    """A date input for the 'to' date in the worklog summary screen."""

    ID = 'worklog-to-date'
    LABEL = 'To'
    TOOLTIP = 'End date for worklog search (inclusive)'


class WorkLogSummaryScreen(Screen):
    """A screen that displays a summary of worklogs for the current user within a date range."""

    HELP = 'See Worklogs section in the help'
    DEFAULT_CSS = """
    WorkLogSummaryScreen > Vertical {
        height: 100%;
    }
    """
    BINDINGS = [
        ('escape', 'app.pop_screen', 'Close'),
    ]
    TITLE = 'Worklog Summary'

    def __init__(self):
        super().__init__()
        self._daily_summaries: list[DailyWorklogSummary] = []

    @property
    def from_date_input(self) -> WorklogFromDateInput:
        return self.query_one('#worklog-from-date', expect_type=WorklogFromDateInput)

    @property
    def to_date_input(self) -> WorklogToDateInput:
        return self.query_one('#worklog-to-date', expect_type=WorklogToDateInput)

    @property
    def summary_table(self) -> DataTable:
        return self.query_one('#worklog-summary-table', expect_type=DataTable)

    @property
    def itemised_table(self) -> DataTable:
        return self.query_one('#worklog-itemised-table', expect_type=DataTable)

    @property
    def search_button(self) -> Button:
        return self.query_one('#worklog-search-button', expect_type=Button)

    @property
    def results_container(self) -> VerticalScroll:
        return self.query_one('#worklog-results-container', expect_type=VerticalScroll)

    @property
    def status_label(self) -> Static:
        return self.query_one('#worklog-status-label', expect_type=Static)

    def compose(self) -> ComposeResult:
        vertical = Vertical()
        vertical.border_title = self.TITLE
        with vertical:
            with ItemGrid(classes='worklog-summary-search-grid'):
                yield WorklogFromDateInput()
                yield WorklogToDateInput()
                yield Button('Search', id='worklog-search-button', variant='primary', flat=True)
            yield Static('', id='worklog-status-label')
            with VerticalScroll(id='worklog-results-container'):
                yield Label('Daily Summary', classes='worklog-section-title')
                yield DataTable(
                    id='worklog-summary-table',
                    cursor_type='none',
                    show_header=True,
                    show_row_labels=False,
                )
                yield Label('Itemised Entries', classes='worklog-section-title')
                yield DataTable(
                    id='worklog-itemised-table',
                    cursor_type='none',
                    show_header=True,
                    show_row_labels=False,
                )
        yield Footer(show_command_palette=False)

    async def on_mount(self) -> None:
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        self.from_date_input.value = week_ago.isoformat()
        self.to_date_input.value = today.isoformat()
        self.summary_table.add_columns('Date', 'Total Time')
        self.itemised_table.add_columns('Date', 'Work Item', 'Summary', 'Time Spent', 'Comment')
        self.results_container.styles.display = 'none'

    def _parse_date(self, value: str) -> date | None:
        """Parses a date string in ISO format."""
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    @on(Button.Pressed, '#worklog-search-button')
    async def handle_search(self) -> None:
        """Handles the search button press to fetch and display worklogs."""
        from_date = self._parse_date(self.from_date_input.value)
        to_date = self._parse_date(self.to_date_input.value)

        if not from_date or not to_date:
            self.status_label.update('Invalid date format. Use YYYY-MM-DD.')
            self.results_container.styles.display = 'none'
            return

        if from_date > to_date:
            self.status_label.update('The "From" date must be before or equal to the "To" date.')
            self.results_container.styles.display = 'none'
            return

        self.search_button.loading = True
        self.status_label.update('Fetching worklogs...')
        self.results_container.styles.display = 'none'
        self.run_worker(self._fetch_worklogs(from_date, to_date))

    async def _fetch_worklogs(self, from_date: date, to_date: date) -> None:
        """Fetches worklogs from the API and updates the tables."""
        application = cast('JiraApp', self.app)  # type:ignore[name-defined] # noqa: F821
        response: APIControllerResponse = await application.api.get_worklogs_by_date_range(
            from_date=from_date,
            to_date=to_date,
        )

        self.search_button.loading = False

        if not response.success:
            self.status_label.update(f'Failed to fetch worklogs: {response.error}')
            self.results_container.styles.display = 'none'
            return

        summaries: list[DailyWorklogSummary] = response.result or []
        if not summaries:
            self.status_label.update('No worklogs found for the selected date range.')
            self.results_container.styles.display = 'none'
            return

        self._update_tables(summaries)
        self.status_label.update(f'Found worklogs for {len(summaries)} day(s).')
        self.results_container.styles.display = 'block'

    def _update_tables(self, summaries: list[DailyWorklogSummary]) -> None:
        """Updates the summary and itemised data tables with the worklog data.

        Args:
            summaries: a list of daily worklog summaries.
        """
        summary_table = self.summary_table
        itemised_table = self.itemised_table

        summary_table.clear()
        itemised_table.clear()

        for daily in summaries:
            summary_table.add_row(
                daily.date.isoformat(),
                format_duration(daily.total_seconds),
            )

            for entry in daily.entries:
                comment_display = entry.comment.replace('\n', ' ')[:50]
                if len(entry.comment) > 50:
                    comment_display += '...'
                itemised_table.add_row(
                    entry.date.isoformat(),
                    entry.issue_key,
                    entry.issue_summary,
                    entry.time_spent,
                    comment_display,
                )

    def action_close_screen(self) -> None:
        self.dismiss()
