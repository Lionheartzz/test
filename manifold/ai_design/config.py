"""Local operator configuration. Secrets never enter analyses, projects or exports."""
import json
import threading
from urllib.parse import urlsplit
from typing import Literal
from pydantic import Field, SecretStr, model_validator, field_validator
from ..schema import Strict
from .. import store

_lock = threading.Lock()


class ReasoningSettings(Strict):
    # Wire dialect is an operator choice, never inferred from endpoint/model names.
    dialect: Literal['provider_default', 'reasoning_effort', 'thinking'] = 'provider_default'
    mode: Literal['provider_default', 'enabled', 'disabled'] = 'provider_default'
    effort: Literal['provider_default', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'] = 'provider_default'


class ProviderSettings(Strict):
    base_url: str = Field(default='', max_length=500)
    model: str = Field(default='', max_length=120)
    label: str = Field(default='', max_length=120)
    transport: str = Field(default='chat-completions', pattern='^chat-completions$')
    api_key: SecretStr = Field(default_factory=lambda: SecretStr(''))
    enabled: bool = False
    anonymous: bool = False
    json_mode: bool = True
    max_tokens: int | None = Field(default=None, ge=1, strict=True)
    max_tokens_parameter: Literal['max_tokens', 'max_completion_tokens'] = 'max_tokens'
    reasoning: ReasoningSettings = Field(default_factory=ReasoningSettings)
    operation_reasoning: dict[Literal['hydraulic_understanding', 'topology_reasoning', 'manifold_optimization'], ReasoningSettings] = Field(default_factory=dict)
    contract_retries: int = Field(default=0, ge=0, le=1)
    stream: bool = False
    stream_usage: bool = True
    timeout_seconds: int = Field(default=120, ge=15, le=300)
    max_pages: int = Field(default=12, ge=1, le=24)
    image_max_side: int = Field(default=2400, ge=1000, le=4000)

    @field_validator('max_tokens', mode='before')
    @classmethod
    def optional_tokens(cls, value):
        # Decimal strings preserve operator integers beyond JavaScript's safe range.
        if value is None or value == '':
            return None
        if isinstance(value, str) and value.isascii() and value.isdecimal():
            return int(value)
        return value

    @model_validator(mode='after')
    def endpoint(self):
        self.base_url = self.base_url.strip().rstrip('/')
        self.model = self.model.strip()
        if self.base_url:
            url = urlsplit(self.base_url)
            local = url.hostname in ('localhost', '127.0.0.1', '::1')
            if not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError('Use an API base URL without credentials, query or fragment')
            if url.scheme != 'https' and not (url.scheme == 'http' and local):
                raise ValueError('HTTPS is required except for a loopback model server')
        if self.enabled and (not self.base_url or not self.model):
            raise ValueError('An enabled provider needs a base URL and model')
        return self


def path():
    return store.ROOT / '.pmc-local' / 'ai-provider.json'


def read():
    if not path().exists():
        return ProviderSettings()
    try:
        return ProviderSettings.model_validate_json(path().read_text(encoding='utf-8'))
    except (ValueError, OSError):
        raise ValueError('Local AI configuration cannot be read; update it from AI settings') from None


def public(settings=None):
    warning = None
    if settings is None:
        try:
            settings = read()
        except ValueError:
            settings = ProviderSettings()
            warning = 'Local configuration is unreadable. Re-enter settings and credentials to replace it.'
    result = settings.model_dump(exclude={'api_key'})
    if settings.max_tokens is not None and settings.max_tokens > 2**53-1:
        result['max_tokens'] = str(settings.max_tokens)
    result['key_present'] = bool(settings.api_key.get_secret_value())
    result['ready'] = bool(settings.enabled and settings.base_url and settings.model and
                           (result['key_present'] or settings.anonymous))
    result['configuration_warning'] = warning
    return result


def save(settings):
    with _lock:
        try:
            old = read()
        except ValueError:
            old = ProviderSettings()
        if not settings.api_key.get_secret_value() and settings.base_url == old.base_url:
            settings.api_key = old.api_key
        if settings.enabled and not settings.anonymous and not settings.api_key.get_secret_value():
            raise ValueError('Enter an API key for this endpoint or explicitly choose anonymous access')
        data = settings.model_dump(exclude={'api_key'})
        data['api_key'] = settings.api_key.get_secret_value()
        store.atomic_json(path(), data)
    return public(settings)


def clear_key():
    with _lock:
        settings = read()
        settings.api_key = SecretStr('')
        settings.enabled = False
        data = settings.model_dump(exclude={'api_key'})
        data['api_key'] = ''
        store.atomic_json(path(), data)
    return public(settings)
