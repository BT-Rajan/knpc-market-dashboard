from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, EmailStr, field_serializer


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    role: str
    username: str


class SourceBase(BaseModel):
    name: str
    url: str
    source_type: str = "css"
    value_selector: str
    news_selector: Optional[str] = None
    priority: int = 1
    active: bool = True


class SourceCreate(SourceBase):
    item_id: int


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    source_type: Optional[str] = None
    value_selector: Optional[str] = None
    news_selector: Optional[str] = None
    priority: Optional[int] = None
    active: Optional[bool] = None


class SourceOut(SourceBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    item_id: int


class ItemBase(BaseModel):
    code: str
    name: str
    category: str
    unit: str = "USD/bbl"
    active: bool = True


class ItemCreate(ItemBase):
    pass


class ItemOut(ItemBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sources: List[SourceOut] = []


class NavItem(BaseModel):
    code: str
    name: str


class NavCategory(BaseModel):
    category: str
    items: List[NavItem]


class PricePoint(BaseModel):
    price_date: date
    price: float


class TickerEntry(BaseModel):
    code: str
    name: str
    category: str
    unit: str
    current_price: Optional[float] = None
    previous_price: Optional[float] = None
    daily_change: Optional[float] = None
    daily_change_pct: Optional[float] = None
    as_of: Optional[date] = None


class NewsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    headline: str
    url: Optional[str] = None
    source: Optional[str] = None
    collected_at: datetime


class ItemDetail(BaseModel):
    code: str
    name: str
    category: str
    unit: str
    current_price: Optional[float] = None
    previous_price: Optional[float] = None
    daily_change: Optional[float] = None
    daily_change_pct: Optional[float] = None
    as_of: Optional[date] = None
    weekly_series: List[PricePoint] = []
    monthly_series: List[PricePoint] = []
    news: List[NewsOut] = []


class ScrapeLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    run_at: datetime
    item_code: Optional[str] = None
    source_name: Optional[str] = None
    status: str
    message: Optional[str] = None


class ScrapeSettingOut(BaseModel):
    frequency_minutes: int


class ScrapeSettingUpdate(BaseModel):
    frequency_minutes: int


class AIAskRequest(BaseModel):
    provider: str  # "deepseek" | "claude"
    item_code: Optional[str] = None
    question: str


class AIAskResponse(BaseModel):
    provider: str
    answer: str


class AICredentialsOut(BaseModel):
    deepseek_configured: bool
    claude_configured: bool


class AICredentialsUpdate(BaseModel):
    deepseek_api_key: Optional[str] = None
    claude_api_key: Optional[str] = None


# --- Email distribution list ---

class EmailRecipientBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    active: bool = True


class EmailRecipientCreate(EmailRecipientBase):
    pass


class EmailRecipientUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    active: Optional[bool] = None


class EmailRecipientOut(EmailRecipientBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# --- Email templates ---

class EmailTemplateBase(BaseModel):
    name: str
    subject: str
    body_html: str


class EmailTemplateCreate(EmailTemplateBase):
    pass


class EmailTemplateUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None


class EmailTemplateOut(EmailTemplateBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    updated_at: datetime


# --- Gmail sender credentials ---

class EmailCredentialsOut(BaseModel):
    configured: bool
    gmail_address: Optional[str] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    last_failure_message: Optional[str] = None
    consecutive_failures: int = 0


class EmailCredentialsUpdate(BaseModel):
    gmail_address: Optional[str] = None
    gmail_app_password: Optional[str] = None


# --- Sending ---

class EmailSendRequest(BaseModel):
    template_id: int
    recipient_ids: List[int]
    variables: dict[str, str] = {}
    attach_report_filename: Optional[str] = None


class EmailSendResult(BaseModel):
    recipient: str
    status: str  # "success" | "error"
    message: Optional[str] = None


class EmailSendResponse(BaseModel):
    sent: int
    failed: int
    results: List[EmailSendResult]


class EmailLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sent_at: datetime
    template_name: Optional[str] = None
    recipient: str
    status: str
    message: Optional[str] = None


# --- Scheduled sends ---
# scheduled_at/created_at/sent_at are stored naive-but-UTC (matching every
# other timestamp column in this app). The _utc_z serializer appends "Z" on
# the way out so the browser's `new Date(...)` parses them as UTC and
# converts to local time correctly for display -- without it, a naive
# ISO string with no zone gets reinterpreted as local time on the way back,
# silently shifting the displayed time by the browser's UTC offset.

def _utc_z(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat() + "Z" if dt.tzinfo is None else dt.isoformat()


class ScheduledEmailCreate(BaseModel):
    template_id: int
    recipient_ids: List[int]
    variables: dict[str, str] = {}
    attach_report_filename: Optional[str] = None
    scheduled_at: datetime


class ScheduledEmailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    template_id: int
    template_name: str
    recipient_ids: List[int]
    variables: dict
    attach_report_filename: Optional[str] = None
    scheduled_at: datetime
    status: str
    created_at: datetime
    sent_at: Optional[datetime] = None
    result_summary: Optional[str] = None

    @field_serializer("scheduled_at", "created_at", "sent_at")
    def _serialize_utc(self, dt: Optional[datetime], _info):
        return _utc_z(dt)
