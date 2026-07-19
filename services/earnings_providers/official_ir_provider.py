"""Conservative official IR calendar HTML provider."""

from __future__ import annotations

import html
import logging
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from typing import Any, Callable

from services.earnings import japan_today
from services.earnings_providers.base import EarningsFetchResult
from utils.validators import normalize_ticker

logger = logging.getLogger(__name__)
USER_AGENT = "orekabu-ai/local-personal-use"
MAX_HTML_BYTES = 2 * 1024 * 1024
EARNINGS_PHRASES = (
    "決算発表予定",
    "決算発表",
    "四半期決算",
    "中間決算",
    "通期決算",
    "決算説明会",
)
DATE_PATTERNS = (
    re.compile(r"(?P<year>20\d{2})年\s*(?P<month>1[0-2]|0?[1-9])月\s*(?P<day>3[01]|[12]\d|0?[1-9])日"),
    re.compile(r"(?P<year>20\d{2})[./-](?P<month>1[0-2]|0?[1-9])[./-](?P<day>3[01]|[12]\d|0?[1-9])"),
    re.compile(r"(?<!\d)(?P<month>1[0-2]|0?[1-9])月\s*(?P<day>3[01]|[12]\d|0?[1-9])日"),
)


@dataclass(frozen=True)
class ExtractedIRDate:
    """One date and its short evidence context."""

    value: date
    evidence: str
    fiscal_quarter: str
    fiscal_year: int | None


class _TextExtractor(HTMLParser):
    """Extract visible text while ignoring scripts and styles."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style", "noscript"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


class OfficialIREarningsProvider:
    """Fetch one configured official IR page after checking robots.txt."""

    name = "official_ir"

    def __init__(
        self,
        source: dict[str, Any],
        *,
        opener: Callable[..., Any] = urllib.request.urlopen,
        today: date | None = None,
        timeout: int = 20,
    ) -> None:
        self.source = source
        self.opener = opener
        self.today = today or japan_today()
        self.timeout = timeout

    def fetch_next_earnings(self, ticker: str) -> EarningsFetchResult:
        """Return future dates found near earnings-specific language."""
        normalized = normalize_ticker(ticker)
        retrieved_at = datetime.now().astimezone().isoformat(timespec="seconds")
        source_url = str(self.source.get("source_url") or "")
        try:
            if not self._robots_allowed(source_url):
                return self._failure(
                    normalized,
                    retrieved_at,
                    "robots_denied",
                    "robots.txtにより自動取得できません。",
                )
            page = self._fetch_page(source_url)
            extracted = extract_ir_earnings_dates(page, self.today)
            if not extracted:
                return self._failure(
                    normalized,
                    retrieved_at,
                    "empty_data",
                    "公式IRページから将来の決算予定日を抽出できませんでした。",
                )
            dates = tuple(item.value for item in extracted)
            quarters = {item.fiscal_quarter for item in extracted}
            years = {item.fiscal_year for item in extracted if item.fiscal_year}
            evidence = " / ".join(item.evidence for item in extracted[:3])[:1000]
            return EarningsFetchResult(
                ticker=normalized,
                earnings_date=dates[0],
                candidate_dates=dates,
                fiscal_year=next(iter(years)) if len(years) == 1 else None,
                fiscal_quarter=next(iter(quarters)) if len(quarters) == 1 else "未設定",
                source_name=self.name,
                source_reference=source_url,
                retrieved_at=retrieved_at,
                confidence=(
                    "high"
                    if self.source.get("source_type") == "official_ir_calendar"
                    else "medium"
                ),
                raw_payload_summary=evidence,
            )
        except Exception as exc:
            logger.warning(
                "公式IR取得失敗 ticker=%s source_id=%s error=%s",
                normalized,
                self.source.get("id"),
                type(exc).__name__,
            )
            return self._failure(
                normalized,
                retrieved_at,
                _error_code(exc),
                "公式IRページを取得できませんでした。",
                type(exc).__name__,
            )

    def _robots_allowed(self, source_url: str) -> bool:
        parts = urllib.parse.urlsplit(source_url)
        robots_url = urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, "/robots.txt", "", "")
        )
        request = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
        try:
            with self.opener(request, timeout=self.timeout) as response:
                content = response.read(MAX_HTML_BYTES).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return True
            if exc.code in {401, 403}:
                return False
            raise
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(content.splitlines())
        return parser.can_fetch(USER_AGENT, source_url)

    def _fetch_page(self, source_url: str) -> str:
        request = urllib.request.Request(source_url, headers={"User-Agent": USER_AGENT})
        with self.opener(request, timeout=self.timeout) as response:
            raw = response.read(MAX_HTML_BYTES + 1)
            if len(raw) > MAX_HTML_BYTES:
                raise ValueError("IRページがサイズ上限を超えています。")
            content_type = str(response.headers.get("Content-Type") or "")
        match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type)
        encodings = [match.group(1)] if match else []
        encodings.extend(["utf-8", "cp932"])
        for encoding in encodings:
            try:
                return raw.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue
        return raw.decode("utf-8", errors="replace")

    def _failure(
        self,
        ticker: str,
        retrieved_at: str,
        code: str,
        message: str,
        summary: str = "",
    ) -> EarningsFetchResult:
        return EarningsFetchResult(
            ticker=ticker,
            source_name=self.name,
            source_reference=str(self.source.get("source_url") or ""),
            retrieved_at=retrieved_at,
            confidence="unknown",
            error_code=code,
            error_message=message,
            raw_payload_summary=summary,
        )


def html_to_text(value: str) -> str:
    """Convert HTML to normalized visible text without retaining markup."""
    parser = _TextExtractor()
    parser.feed(value)
    text = html.unescape(" ".join(parser.parts))
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_ir_earnings_dates(
    html_value: str,
    today: date | None = None,
) -> list[ExtractedIRDate]:
    """Extract conservative future date candidates near earnings phrases."""
    base_date = today or japan_today()
    text = html_to_text(html_value)
    matches: dict[date, ExtractedIRDate] = {}
    date_matches = _all_date_matches(text)
    for index, date_match in enumerate(date_matches):
        next_start = (
            date_matches[index + 1].start()
            if index + 1 < len(date_matches)
            else len(text)
        )
        after = text[date_match.start() : min(next_start, date_match.end() + 180)]
        context = after if _contains_earnings_phrase(after) else ""
        if not context:
            previous_end = date_matches[index - 1].end() if index else 0
            before = text[max(previous_end, date_match.start() - 180) : date_match.end()]
            context = before if _contains_earnings_phrase(before) else ""
        if not context:
            continue

        parsed = _date_from_match(date_match, base_date, context)
        if parsed is None or parsed < base_date:
            continue
        if parsed > base_date + timedelta(days=730):
            continue

        quarter = infer_quarter(context)
        fiscal_year = infer_fiscal_year(context)
        evidence = re.sub(r"\s+", " ", context).strip()[:240]
        matches.setdefault(
            parsed,
            ExtractedIRDate(parsed, evidence, quarter, fiscal_year),
        )
    return [matches[key] for key in sorted(matches)]


def _all_date_matches(text: str) -> list[re.Match[str]]:
    """Return non-overlapping supported date matches in document order."""
    found: list[re.Match[str]] = []
    occupied: list[tuple[int, int]] = []
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            span = match.span()
            if any(span[0] < end and start < span[1] for start, end in occupied):
                continue
            found.append(match)
            occupied.append(span)
    return sorted(found, key=lambda item: item.start())


def _contains_earnings_phrase(value: str) -> bool:
    return any(phrase in value for phrase in EARNINGS_PHRASES)


def infer_quarter(context: str) -> str:
    """Infer a supported quarter label from a short evidence context."""
    normalized = unicodedata.normalize("NFKC", context)
    if re.search(r"第?1四半期|第1Q|1Q", normalized, re.IGNORECASE):
        return "Q1"
    if re.search(r"第?2四半期|中間決算|第2Q|2Q", normalized, re.IGNORECASE):
        return "Q2"
    if re.search(r"第?3四半期|第3Q|3Q", normalized, re.IGNORECASE):
        return "Q3"
    if re.search(r"通期決算|本決算|期末決算", normalized):
        return "通期"
    return "未設定"


def infer_fiscal_year(context: str) -> int | None:
    """Infer the fiscal year when the context explicitly contains a year ending."""
    match = re.search(r"(20\d{2})年(?:\d{1,2}月)?期", context)
    return int(match.group(1)) if match else None


def _date_from_match(
    match: re.Match[str],
    today: date,
    context: str = "",
) -> date | None:
    year_text = match.groupdict().get("year")
    context_year = re.search(r"(20\d{2})年", context)
    year = (
        int(year_text)
        if year_text
        else int(context_year.group(1))
        if context_year
        else today.year
    )
    month = int(match.group("month"))
    day = int(match.group("day"))
    if not year_text and month <= 2 and today.month >= 11:
        year += 1
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _error_code(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"http_{exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return "network_error"
    if isinstance(exc, TimeoutError):
        return "timeout"
    return "parse_error"
