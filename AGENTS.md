# AGENTS.md

## Contributor pull requests

- PRs from contributors other than `kristofferR` must include `AI models used: None`
  if no AI helped create or edit the contribution. Otherwise, list every
  model used to create or edit code, tests, or PR text by its most specific
  available name and version, for example `AI models used: GPT-6 Astra`.
- Include each model's reasoning level or effort when the tool exposes it, for
  example `Reasoning levels: GPT-6 Astra: high`. If unavailable, say
  `Reasoning levels: Unavailable (not exposed by tool)`. Never guess.
  Missing or unavailable reasoning levels do not block a PR.
- Routine automated review bots need not be listed. Put this disclosure in
  the PR description, never in commit authorship or co-author trailers.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration for Fellow Aiden coffee brewers. The integration connects to Fellow's cloud API to provide real-time monitoring, control, and profile management for Fellow Aiden brewing devices.

**Domain**: `fellow`
**Integration Type**: Cloud polling (IoT class)

## Architecture

### Core Components

- **`manifest.json`**: Integration metadata (version, dependencies, domain, IoT class)
- **`__init__.py`**: Main integration entry point, handles setup/teardown and service registration
- **`coordinator.py`**: Data update coordinator that polls Fellow's cloud API every minute
- **`fellow_aiden/`**: Vendored Fellow Aiden Python library for API communication
- **`config_flow.py`**: Configuration flow for user authentication setup
- **`base_entity.py`**: Base entity class that provides device registry info and common attributes

### Platform Files

- **`sensor.py`**: Sensors for water usage, brew counts, timestamps, and calculated metrics
- **`binary_sensor.py`**: Binary sensors for brewing status, lid position, water level, etc.
- **`select.py`**: Select entities for choosing brew profiles

### Key Data Flow

1. **Authentication**: Users provide email/password via config flow
2. **Data Fetching**: Coordinator polls Fellow's API using vendored library
3. **Entity Updates**: Sensors and binary sensors update from coordinator data
4. **Device Registry**: All entities are grouped under a single device per brewer

## Development Notes

### Fellow Aiden Library (Vendored)

The integration includes a vendored copy of the Fellow Aiden library in `fellow_aiden/`:
- **`__init__.py`**: Main `FellowAiden` async class with API methods
- **`profile.py`**: Pydantic models for coffee profiles
- **`schedule.py`**: Pydantic models for brewing schedules

**Key Features**:
- **Fully Async**: Uses `aiohttp` for all HTTP requests — no executor thread wrapping needed
- **Injected Session**: Accepts an `aiohttp.ClientSession` (from HA's `async_get_clientsession`) for proper session management
- **HTTP Retries**: Built-in retry logic for server errors (3 retries for 408/5xx)
- **Lazy Loading**: Profiles and schedules are fetched on-demand via async `get_profiles()`/`get_schedules()` methods
- **Performance**: Profile validation removed from delete operations for speed

**Public API**: Construction is lightweight — call `await api.authenticate()` after creating the instance to perform the initial login and device fetch. `await api.fetch_device()` triggers data refreshes. Token refresh is handled automatically inside `_request_with_reauth()` using the stored refresh token, with fallback to full re-login.

### Services

Two custom services are registered:
- **`fellow.create_profile`**: Create new brew profiles with detailed parameters
- **`fellow.delete_profile`**: Delete profiles by ID

Service definitions are in `services.yaml` with extensive parameter validation.

### Entity Patterns

- All entities inherit from `FellowAidenBaseEntity` for consistent device info
- Sensors handle various data types (numbers, timestamps, calculated values)
- Binary sensors use appropriate device classes (`RUNNING`, `DOOR`, `PROBLEM`)
- Device info includes MAC addresses, firmware version, and elevation as hardware version

### Authentication & Error Handling

- Initial auth happens during config flow setup via `await _try_login(hass, email, password)`
- The library is fully async — the coordinator calls `await self.api.fetch_device()` etc. directly, no executor jobs
- On 401, `_request_with_reauth()` first tries a lightweight token refresh via the stored refresh token, then falls back to full email/password re-login
- Token expiry is expected and logged at DEBUG level; only persistent auth failures log at WARNING
- The coordinator delegates all auth retry logic to the library — no redundant retry wrapping
- Update failures are logged but don't crash the integration

## Testing & Debugging

- Enable debug logging for domain `fellow` to see API calls and data updates
- The integration polls every minute - check logs for update patterns
- Device config data structure varies, so entities handle missing keys gracefully
- Profile and schedule data is cached and only refreshed after modifications

## Common Patterns

When adding new sensors:
1. Add to appropriate sensor list in `sensor.py` or `binary_sensor.py`
2. Follow existing patterns for data extraction from coordinator
3. Use appropriate units and device classes
4. Handle missing/None values gracefully

When modifying services:
1. Update `services.yaml` for UI validation
2. Modify service handlers in `__init__.py`
3. Ensure proper error handling and data validation
