from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_OWNED_EXACT_MODULES = frozenset(
    {
        "aiohttp",
        "pydantic",
        "voluptuous",
        "homeassistant",
        "homeassistant.config_entries",
        "homeassistant.core",
        "homeassistant.helpers",
        "homeassistant.helpers.aiohttp_client",
        "homeassistant.helpers.selector",
        "custom_components.fellow",
    }
)


def _clear_modules() -> None:
    for name in list(sys.modules):
        if name in _OWNED_EXACT_MODULES or name.startswith(
            "custom_components.fellow."
        ):
            sys.modules.pop(name, None)


def _install_aiohttp_stub() -> None:
    aiohttp = types.ModuleType("aiohttp")

    class ClientError(Exception):
        pass

    class ContentTypeError(Exception):
        pass

    class ClientSession:
        pass

    class ClientResponse:
        pass

    aiohttp.ClientError = ClientError
    aiohttp.ContentTypeError = ContentTypeError
    aiohttp.ClientSession = ClientSession
    aiohttp.ClientResponse = ClientResponse
    sys.modules["aiohttp"] = aiohttp


def _install_pydantic_stub() -> None:
    pydantic = types.ModuleType("pydantic")

    class ValidationError(Exception):
        pass

    class BaseModel:
        @classmethod
        def model_validate(cls, data: Any) -> Any:
            return data

    def field_validator(*_args: Any, **_kwargs: Any):
        def decorator(func: Any) -> Any:
            return func

        return decorator

    pydantic.BaseModel = BaseModel
    pydantic.ValidationError = ValidationError
    pydantic.field_validator = field_validator
    sys.modules["pydantic"] = pydantic


def _install_voluptuous_stub() -> None:
    voluptuous = types.ModuleType("voluptuous")

    class Invalid(Exception):
        pass

    def Schema(value: Any) -> Any:
        return value

    def Required(key: Any, default: Any = None) -> Any:
        return key

    def Optional(key: Any, default: Any = None) -> Any:
        return key

    def All(*validators: Any) -> tuple[Any, ...]:
        return validators

    def Coerce(value_type: type[Any]) -> Any:
        return value_type

    def Range(**_kwargs: Any) -> Any:
        return lambda value: value

    voluptuous.All = All
    voluptuous.Coerce = Coerce
    voluptuous.Invalid = Invalid
    voluptuous.Optional = Optional
    voluptuous.Range = Range
    voluptuous.Required = Required
    voluptuous.Schema = Schema
    sys.modules["voluptuous"] = voluptuous


def _install_homeassistant_stubs() -> None:
    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = [str(ROOT / "tests" / "_homeassistant_stub")]
    sys.modules["homeassistant"] = homeassistant

    config_entries = types.ModuleType("homeassistant.config_entries")

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs: Any) -> None:
            kwargs.pop("domain", None)
            super().__init_subclass__()

        def __init__(self) -> None:
            self.hass = None

        async def async_set_unique_id(self, value: str) -> None:
            self._unique_id = value

        def _abort_if_unique_id_configured(self) -> None:
            return None

        def _abort_if_unique_id_mismatch(self, reason: str | None = None) -> None:
            return None

        def _get_reauth_entry(self) -> dict[str, Any]:
            return {"entry_id": "reauth"}

        def _get_reconfigure_entry(self) -> dict[str, Any]:
            return {"entry_id": "reconfigure"}

        def async_show_form(
            self,
            *,
            step_id: str,
            data_schema: Any = None,
            errors: dict[str, str] | None = None,
            last_step: bool = False,
        ) -> dict[str, Any]:
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
                "last_step": last_step,
            }

        def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
            return {"type": "create_entry", "title": title, "data": data}

        def async_abort(self, *, reason: str) -> dict[str, Any]:
            return {"type": "abort", "reason": reason}

        def async_update_reload_and_abort(
            self, entry: Any, *, data_updates: dict[str, Any]
        ) -> dict[str, Any]:
            return {
                "type": "abort",
                "reason": "updated",
                "entry": entry,
                "data_updates": data_updates,
            }

    class OptionsFlow:
        def __init__(self) -> None:
            self.config_entry = types.SimpleNamespace(options={})

        def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
            return {"type": "create_entry", "title": title, "data": data}

        def async_show_form(
            self,
            *,
            step_id: str,
            data_schema: Any = None,
            errors: dict[str, str] | None = None,
            last_step: bool = False,
        ) -> dict[str, Any]:
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
                "last_step": last_step,
            }

    config_entries.ConfigEntry = type("ConfigEntry", (), {})
    config_entries.ConfigFlow = ConfigFlow
    config_entries.ConfigFlowResult = dict
    config_entries.OptionsFlow = OptionsFlow
    sys.modules["homeassistant.config_entries"] = config_entries

    core = types.ModuleType("homeassistant.core")

    class HomeAssistant:
        pass

    def callback(func: Any) -> Any:
        return func

    core.HomeAssistant = HomeAssistant
    core.callback = callback
    sys.modules["homeassistant.core"] = core

    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")

    def async_get_clientsession(hass: Any) -> Any:
        return getattr(hass, "session", None)

    aiohttp_client.async_get_clientsession = async_get_clientsession
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

    selector = types.ModuleType("homeassistant.helpers.selector")

    class TextSelector:
        def __init__(self, config: Any) -> None:
            self.config = config

    class TextSelectorConfig:
        def __init__(self, *, type: str) -> None:
            self.type = type

    class TextSelectorType:
        EMAIL = "email"
        PASSWORD = "password"

    selector.TextSelector = TextSelector
    selector.TextSelectorConfig = TextSelectorConfig
    selector.TextSelectorType = TextSelectorType
    sys.modules["homeassistant.helpers.selector"] = selector

    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = [str(ROOT / "tests" / "_homeassistant_helpers_stub")]
    sys.modules["homeassistant.helpers"] = helpers


def _install_package_placeholders() -> None:
    custom_components = types.ModuleType("custom_components")
    custom_components.__path__ = [str(ROOT / "custom_components")]
    sys.modules["custom_components"] = custom_components

    fellow = types.ModuleType("custom_components.fellow")
    fellow.__path__ = [str(ROOT / "custom_components" / "fellow")]
    sys.modules["custom_components.fellow"] = fellow


def _load_module(
    name: str, path: Path, *, package: bool = False
) -> types.ModuleType:
    kwargs: dict[str, Any] = {}
    if package:
        kwargs["submodule_search_locations"] = [str(path.parent)]
    spec = importlib.util.spec_from_file_location(name, path, **kwargs)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_fellow_aiden_module() -> types.ModuleType:
    _clear_modules()
    _install_aiohttp_stub()
    _install_pydantic_stub()
    _install_package_placeholders()
    _load_module(
        "custom_components.fellow.const",
        ROOT / "custom_components" / "fellow" / "const.py",
    )
    return _load_module(
        "custom_components.fellow.fellow_aiden",
        ROOT / "custom_components" / "fellow" / "fellow_aiden" / "__init__.py",
        package=True,
    )


def load_config_flow_module() -> types.ModuleType:
    _clear_modules()
    _install_aiohttp_stub()
    _install_pydantic_stub()
    _install_voluptuous_stub()
    _install_homeassistant_stubs()
    _install_package_placeholders()
    _load_module(
        "custom_components.fellow.const",
        ROOT / "custom_components" / "fellow" / "const.py",
    )
    _load_module(
        "custom_components.fellow.fellow_aiden",
        ROOT / "custom_components" / "fellow" / "fellow_aiden" / "__init__.py",
        package=True,
    )
    return _load_module(
        "custom_components.fellow.config_flow",
        ROOT / "custom_components" / "fellow" / "config_flow.py",
    )
