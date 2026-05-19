from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class NewsArticle:
    source: str
    title: str
    published_at: datetime
    body: str | None = None
    publisher: str | None = None
    url: str | None = None
    ticker: str | None = None


@dataclass(slots=True)
class Disclosure:
    rcept_no: str
    report_nm: str
    rcept_dt: datetime
    corp_code: str | None = None
    corp_name: str | None = None
    ticker: str | None = None
    submitter: str | None = None
    source_url: str | None = None
    pblntf_ty: str | None = None
    pblntf_detail_ty: str | None = None
