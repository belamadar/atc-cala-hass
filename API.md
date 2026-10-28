# ATC Cala / Grupo Ferroli Cloud API

Reverse-engineered from two mitmproxy captures of the **ATC Cala** Android app
(`com.atc.hc`) controlling WiFi electric radiators — `flows` (440 transactions, includes the
login) and `flows(1)` (120 transactions, control actions). This is the working mental model
for the Home Assistant integration — treat it as observed behaviour, not an official spec.

> Everything below was seen against a single account with one installation (`IdInstalacion=12345`,
> "Home") and two radiators. Fields marked _(inferred)_ were not exercised in the
> capture but follow directly from observed patterns.

---

## 1. Transport & Auth

| Property | Value |
|---|---|
| API base URL | `https://gateway.grupoferroli.es/APIGW/api/` |
| Token endpoint | `https://gateway.grupoferroli.es/APIGW/token` (note: **not** under `/api/`) |
| Server | `Microsoft-IIS/10.0`, `ASP.NET` (`X-AspNet-Version: 4.0.30319`) — OWIN OAuth |
| Auth | `Authorization: Bearer <access_token>` on **every** `/api/*` request |
| Content type (responses) | `application/json; charset=utf-8` |
| CORS | `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Headers: authorization` |

### Login — `POST /APIGW/token`
Standard OAuth2 **Resource Owner Password Credentials** grant (ASP.NET/OWIN). No auth header on
this call. Body is `application/x-www-form-urlencoded`:

```
grant_type=password&username=<email>&password=<password>&client_id=AppATC
```

`client_id=AppATC` is a fixed constant for this app. Response (`200`):

```json
{
  "access_token": "<access_token>",               // ~450-char opaque token (NOT a JWT)
  "token_type": "bearer",
  "expires_in": 1199,                                // seconds ≈ 20 minutes
  "refresh_token": "<32-hex-char GUID>", // opaque GUID
  "as:client_id": "AppATC",
  "userName": "<email>",
  "idUser": "10001",
  "company": "1000",
  "role": "U",
  "language": "en",
  "status": "ACT",
  "cssClass": "ferroli",                             // brand theming
  "wifi": "ATC",
  "displayName": "-",
  "SelectedSchedule": "AAAA…",                        // 336 chars (7 days × 48 slots), account-level default schedule
  "AcceptSubscription": "FALSE",
  ".issued": "Tue, 14 Jul 2026 20:44:05 GMT",
  ".expires": "Tue, 14 Jul 2026 21:04:05 GMT"
}
```

- The returned `access_token` is used verbatim as `Bearer` on every `/api/*` call — verified: it
  matches the token used across all 440 subsequent requests in the capture.
- **Lifetime ~20 min** (`expires_in: 1199`). The integration must re-auth or refresh before expiry.
- `idUser` feeds `GET /api/User?IdUsuario=`; `language` and `SelectedSchedule` are account defaults.

### Token refresh — `POST /APIGW/token` _(confirmed)_
The OWIN refresh grant, confirmed in the decompiled app 2.1.7 (`autoLogin` / `getNewRefreshToken`)
and verified live (returns a fresh `access_token`):

```
grant_type=refresh_token&refresh_token=<refresh_token>&client_id=AppATC
```

The refresh response may omit `refresh_token` — keep the previous one if so. Safe fallback: re-run
the password grant when the access token nears expiry (`pyatccala` does exactly this).

> **Secrets:** the captures contain the real account username/password (password grant) and live
> tokens. Keep them out of committed code — store credentials in HA's config entry, not in source.

### Client fingerprint (for reference)
The app is a WebView/hybrid app: requests carry `Origin: http://localhost`,
`X-Requested-With: com.atc.hc`, and an Android WebView `User-Agent`. None of these appear to be
required by the server (CORS is wide open), but replicating `Accept: application/json` is wise.

Every state-changing endpoint is preceded by a CORS `OPTIONS` preflight — the HA integration
(server-side HTTP, not a browser) can skip these entirely.

---

## 2. Endpoint summary

Paths below are relative to the API base `…/APIGW/api/` except `POST /APIGW/token`, which sits
one level up.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/APIGW/token` | Log in (password grant) → access + refresh token |
| `GET` | `/Instalaciones` | List installations (sites) for the account |
| `GET` | `/Zona?IdInstalacion={id}` | List zones within an installation |
| `GET` | `/Radiador?IdInstalacion={id}&IdZona={z}` | List radiators + full state |
| `PUT` | `/Radiador` | Apply changes to one or more radiators |
| `GET` | `/GetHoraInstalacionExtra?IdInstalacion={id}&minutosAdd={m}` | Server clock (for scheduling / boost expiry) |
| `GET` | `/User?IdUsuario={idUser}` | User profile / account details |
| `GET` | `/Language?ClientId=AppATC` | Supported UI languages |
| `GET` | `/Instalacion/{id}/consumo/{period}` | Energy consumption (`diario`/`semanal`/`mensual`/`anual`) |
| `GET` | `/Zona/{idInstalacion}/{idZona}/consumo/{period}` | Zone energy consumption |
| `GET` | `/Radiador/{idRadiador}/consumo/{period}` | Radiator energy consumption |
| `GET`/`POST`/`PUT`/`DELETE` | `/Instalacion` (`?IdInstalacion=` for GET/DELETE) | Read / create / modify / delete an installation (the GET omits tariff + currency — use `/Instalaciones`) |
| `DELETE` | `/Instalacion/limpiarAsociados?IdInstalacion=` | Clear everything associated with an installation |
| `POST`/`PUT` | `/Zona` | Create (`IdZona:"-1"`) / rename a zone (`{IdZona, IdInstalacion, Nombre}`) |
| `DELETE` | `/Zona/?zonas={id}&zonas={id}` | Delete zones |
| `PUT` | `/Radiador/UnpairRadiador` | Unpair radiators (same body shape as `PUT /Radiador`) |
| `GET` | `/Gateway?IdInstalacion=` | List gateways |
| `POST` | `/Gateway` | Add a gateway / radiator to an installation |
| `DELETE` | `/Gateway?IdGateway=&resetGW=` / `/Gateway/UnlinkGateway?IdGateway=` | Unpair / unlink a gateway |
| `PUT` | `/User` | Update profile |
| `POST` | `/User/AuthChangePassword` | Change password (token payload + `pass` + `newPassword`) |
| `POST` | `/User/Sesiones` / `/User/Logout` | List sessions / log out (body: the token response) |
| `DELETE` | `/User/Session?IdSesion=` | End a session |
| `GET` | `/Moneda`, `/ZonaHoraria`, `/TiposDispositivo`, `/TextoLegal` (`?ClientId=AppATC`) | Catalogs (no auth) |

All responses observed returned `200` (no error cases captured).

---

## 3. `GET /Instalaciones`

No query params. Returns an array of installations.

```json
[{
  "datos": {
    "IdInstalacion": 12345,
    "Nombre": "Home",
    "tipoInstalacion": "WIFI",
    "IdZonaHoraria": 47,
    "offsetZonaHoraria": "1",
    "CurrentDate": "2026-07-14T22:08:50.986",
    "CurrentUTCDate": "2026-07-14T21:08:50.986",
    "IdMoneda": 1, "Moneda": "€",
    "IdZona": 0,
    "HoraValleActiva": true,
    "HoraValleInicio": "0", "HoraValleFin": "9",
    "HoraVallePrecio": 0.100, "HoraPicoPrecio": 0.150,
    "ErrorOperacion": 0, "Error": 0, "Reset": false
  },
  "radiadores": null,
  "zonas": null,
  "nzonas": 0,
  "nradiadores": 2
}]
```

Key fields:
- `IdInstalacion` — the site id used as a query param everywhere else.
- `tipoInstalacion` — `"WIFI"` here (radiators talk to the cloud directly, each is its own
  gateway). Other topologies (a hub/`IdGateway`) likely exist for other product lines.
- `nradiadores` / `nzonas` — counts; the actual arrays come from the dedicated endpoints.
- **Tariff block** (`HoraValle*` = off-peak / "valley hours", `HoraPico*` = peak): off-peak is
  00:00–09:00 at €0.10/kWh, peak at €0.15/kWh. Useful for an energy-cost sensor in HA.
- Timezone: `IdZonaHoraria` + `offsetZonaHoraria` ("1" = UTC+1); `CurrentDate` vs `CurrentUTCDate`
  confirm the server applies the site's local offset.

---

## 4. `GET /Zona?IdInstalacion={id}`

Returns an array of zones. In this capture it was always `[]` (this installation groups radiators
directly with no zones). Zones are an optional grouping layer; `IdZona=0` means "no zone / all".

---

## 5. `GET /Radiador?IdInstalacion={id}&IdZona={z}`

The core polling endpoint. `IdZona=0` returns all radiators in the installation. Returns an array,
one object per radiator:

```json
{
  "IdRadiador": "000C01234567890",
  "IdGateway": "000C01234567890",
  "IdZona": 0, "NombreZona": "",
  "Nombre": "Cs",
  "TempActual": 21.0,
  "IdModoActual": "C",
  "TempComfort": 19.0,
  "TempEco": 3.0,
  "TempAntiFrost": 7.0,
  "TempForzado": 20.0,
  "TemperaturaConsignaCalculada": 21.0,
  "DeltaTemperaturaSonda": 0.0,
  "DiasForzado": 0, "TiempoForzado": "0", "ModoForzado": false,
  "ProgramacionL": "EEEE...CCCC...EEEE",
  "ProgramacionM": "...", "ProgramacionX": "...", "ProgramacionJ": "...",
  "ProgramacionV": "...", "ProgramacionS": "...", "ProgramacionD": "...",
  "Encendido": true,
  "Calentando": false,
  "TecladoBloqueado": false,
  "Brillo": 0, "DuracionBrillo": 10,
  "VentanasAbiertas": false, "VentanasAbiertasStatus": false,
  "ArranqueAdaptativo": false, "ArranqueAdaptativoStatus": false,
  "ProgramaTiempo": 0,
  "Easy": false,
  "Error": 0, "ErrorList": "", "Err_Offline": false,
  "LastOnline": "0001-01-01T00:00:00",
  "HoraActual": "2026-07-14T22:11:14.839233",
  "Software": "V 1.16.25",
  "Tipo": "WIFI",
  "Potencia": 1800,
  "LimitePotencia": 100,
  "CurrentUTCDate": "2026-07-14T21:08:50.986"
}
```

### Field reference

**Identity**
- `IdRadiador` — 15-char device id (`000C01234567890`). This is the handle used in `PUT` bodies.
- `IdGateway` — equals `IdRadiador` for WIFI radiators (each is its own gateway).
- `Nombre` — user label. `NombreZona` / `IdZona` — zone assignment.

**Temperature (all °C)**
- `TempActual` — current measured room temperature (read-only sensor value).
- `TemperaturaConsignaCalculada` — the **currently active setpoint** the device computed from its
  mode. In `P`/schedule mode this is what the schedule resolves to; `0.0` seen when the device is
  effectively off/idle. Use this as the "target temperature" readback.
- `TempComfort` — Comfort setpoint (12–30 °C in the app).
- `TempEco` — **not a temperature**: the number of degrees Eco sits *below* Comfort (0.5–4.5,
  confirmed in the decompiled app: Eco setpoint = `TempComfort - TempEco`).
- `TempAntiFrost` — Anti-frost setpoint, fixed at 7 °C (the app does not let you change it).
- `TempForzado` — setpoint used while boost/forced mode is active.
- `DeltaTemperaturaSonda` — sensor calibration offset.

**Mode** — `IdModoActual` is a single letter:

| Code | Meaning | Active setpoint |
|---|---|---|
| `C` | Comfort | `TempComfort` |
| `E` | Eco | `TempComfort - TempEco` |
| `A` | Anti-frost (Antihielo) | `TempAntiFrost` |
| `P` | Programa (follow weekly schedule) | schedule → Comfort or Eco per slot |

The app's UI also has a virtual mode `M` (manual/boost); it is never sent as `IdModoActual` —
boost is driven by `ModoForzado`/`TiempoForzado` on top of the current mode.

`Encendido` (bool) is the master on/off, independent of mode. `ModoForzado` (bool) is a temporary
boost overlay on top of the mode (see below). Mapping to HA: `Encendido=false` → HVAC `off`;
otherwise `heat`, with the four mode letters exposed as a preset/select.

**Weekly schedule** — `ProgramacionL/M/X/J/V/S/D`, Spanish weekday initials:

| Field | Day |
|---|---|
| `ProgramacionL` | Lunes (Mon) |
| `ProgramacionM` | Martes (Tue) |
| `ProgramacionX` | Miércoles (Wed) |
| `ProgramacionJ` | Jueves (Thu) |
| `ProgramacionV` | Viernes (Fri) |
| `ProgramacionS` | Sábado (Sat) |
| `ProgramacionD` | Domingo (Sun) |

Each is a **48-character string**, one char per 30-minute slot starting at 00:00
(`[0]`=00:00–00:30 … `[47]`=23:30–24:00). Each char is `C` (Comfort slot) or `E` (Eco slot).
When the radiator is in mode `P`, the active setpoint follows this map (Comfort slots →
`TempComfort`, Eco slots → `TempEco`).

**Boost / forced mode**
- `ModoForzado` (bool) — whether a timed boost override is active.
- `TempForzado` — the boost setpoint.
- `TiempoForzado` — **Unix epoch seconds** at which the boost expires (e.g. `1797288174`). `"0"`
  when never used; after a boost ends the server may keep a *past* value (and even
  `ModoForzado=true`), so treat the boost as active only while `TiempoForzado > now`.
  The app caps a boost at ~366 days and ends one early with just `ModoForzado=false`.
- `DiasForzado` — days component (0 in captures).

**Device / status flags**
- `Calentando` (bool) — the element is actively heating right now (drawing power). Good source
  for an HA `hvac_action` of `heating` vs `idle`.
- `TecladoBloqueado` (bool) — physical keypad / child lock.
- `Brillo` (0–100) — display brightness; `DuracionBrillo` — seconds the display stays lit.
- `VentanasAbiertas` (bool) — open-window detection **enabled**; `VentanasAbiertasStatus` —
  window currently detected open.
- `ArranqueAdaptativo` / `ArranqueAdaptativoStatus` — adaptive-start feature enabled / active.
- `Potencia` — rated power in watts (1800). `LimitePotencia` — power cap as a **percent** (100 or
  50 seen). Energy estimate ≈ `Potencia × LimitePotencia/100` while `Calentando`.
- `Software` — firmware (`V 1.16.25`). `Tipo` — `WIFI`.
- `Err_Offline` / `LastOnline` — connectivity. `LastOnline: 0001-01-01T00:00:00` = never/unknown
  (the radiators were online during capture).
- `Error` / `ErrorList` — fault reporting (clean here).
- `Easy`, `ProgramaTiempo` — purpose unconfirmed (both 0/false throughout).

---

## 6. `PUT /Radiador` — control

Single endpoint for **all** mutations. Body:

```json
{
  "Cambios": [ {"Campo": "<FieldName>", "Valor": "<value>"} ],
  "Zones": [],
  "Heaters": ["000C01234567890"]
}
```

- `Cambios` — list of field/value changes to apply (batchable — multiple in one call).
- `Heaters` — target radiator ids (`IdRadiador`). Multiple ids = apply the same changes to all.
- `Zones` — target zones; always `[]` in captures. Presumably an alternative addressing mode
  (apply to every radiator in a zone).

**Value encoding:** the app sends values inconsistently — some as JSON strings (`"29.5"`,
`"true"`), some as raw JSON numbers/bools (`0.5`, `90`, `true`). The server **normalizes every
value to a string** in its echo. Safest for the integration: **always send `Valor` as a string.**

Response echoes the request and adds a Firebase push descriptor:

```json
{
  "Zones": [], "Heaters": ["000C01234567890"],
  "Cambios": [{"Campo":"TempComfort","Valor":"29.5"}],
  "HeatersForFirebase": [
    {"IdRadiador":"000C01234567890","IdGateway":"000C01234567890","PosicionGW":1,"cnt":40}
  ],
  "idCia": 0, "idInstalacion": 0, "traza": "COUNT: 1"
}
```

- `HeatersForFirebase[].cnt` — a per-device command counter that increments on each successful
  change (40→41→42… across the capture). The cloud pushes the change to the device via Firebase;
  `cnt` is that message's sequence. **The PUT does not confirm the device applied the change** —
  it only confirms the cloud queued it. Poll `GET /Radiador` afterwards to verify.
- `traza: "COUNT: 1"` — server-side trace string; ignorable.

### Observed `Campo` values (writable fields)

| Campo | Example `Valor` | Effect |
|---|---|---|
| `Encendido` | `"true"` | Master power on/off |
| `IdModoActual` | `"C"` / `"E"` / `"A"` / `"P"` | Set mode |
| `TempComfort` | `"29.5"`, `"12"` | Comfort setpoint |
| `TempEco` | `"4.5"`, `"0.5"` | Eco offset below Comfort (0.5–4.5) |
| `TempForzado` | `"18"` | Boost setpoint |
| `TiempoForzado` | `"1797288174"` | Boost expiry (Unix epoch s) |
| `ModoForzado` | `"true"` | Enable/disable boost |
| `ProgramacionX` | 48-char `C`/`E` string | Overwrite one day's schedule |
| `TecladoBloqueado` | `"true"` / `"false"` | Keypad lock |
| `Brillo` | `"90"`, `"0"` | Display brightness |
| `LimitePotencia` | `"50"` | Power cap (%) |

_(Confirmed in the decompiled app, not captured:)_ the other schedule days
(`ProgramacionL/M/J/V/S/D`), `DeltaTemperaturaSonda` (°C, −5.0…+5.0, 0.1 steps),
`DuracionBrillo` (1–240 s), `VentanasAbiertas`, `VentanasAbiertasStatus` (`false` dismisses a
detected open window; the app sends it with every mode change), `ArranqueAdaptativo`, `Easy`,
`Nombre` (≤13 chars), `IdZona` + `IdInstalacion` (move radiators; `IdZona=-1` = no zone) and
`ResetGW` (WIFI) / `reset` (reset command). `LimitePotencia` is 20–100 %.

### Common command recipes

Set Comfort mode at 21°C:
```json
{"Cambios":[{"Campo":"Encendido","Valor":"true"},{"Campo":"IdModoActual","Valor":"C"},
            {"Campo":"TempComfort","Valor":"21"}],"Zones":[],"Heaters":["<id>"]}
```

Start a boost to 18°C until a given time (compute epoch via `GetHoraInstalacionExtra` + duration):
```json
{"Cambios":[{"Campo":"TempForzado","Valor":"18"},{"Campo":"TiempoForzado","Valor":"1797288174"},
            {"Campo":"ModoForzado","Valor":"true"}],"Zones":[],"Heaters":["<id>"]}
```

Turn off:
```json
{"Cambios":[{"Campo":"Encendido","Valor":"false"}],"Zones":[],"Heaters":["<id>"]}
```

---

## 7. `GET /GetHoraInstalacionExtra?IdInstalacion={id}&minutosAdd={m}`

Returns the server's current local time (as a bare JSON string), optionally shifted by
`minutosAdd` minutes:

```
"2026-07-14T22:12:13.6768563"
```

`minutosAdd=0` → now; `minutosAdd=30` seen → now + 30 min. The app uses this to compute
`TiempoForzado` (boost expiry) from the **server's** clock rather than the phone's, avoiding
timezone/drift bugs. The integration should do the same: fetch server time, add the boost
duration, convert to Unix epoch for `TiempoForzado`.

---

## 8. `GET /User?IdUsuario={idUser}`

Account profile. `IdUsuario` comes from the token response's `idUser`.

```json
{
  "id": 10001, "idUser": 10001,
  "email": "<email>",
  "displayName": "-", "surname": null,
  "language": "en",
  "idGatewayRegistro": "000C01234567891",   // gateway used at account registration
  "AcceptSubscription": false,
  "HoraValleActivaRegistro": false, "HoraVallePrecioRegistro": 0.0, "HoraPicoPrecioRegistro": 0.0
}
```

Mostly registration metadata; `access_token`/`refresh_token`/`pass` fields come back `null` here
(they are only issued by `/token`). Low value for the integration beyond confirming identity.

---

## 9. `GET /Language?ClientId=AppATC`

Static list of supported UI languages. Not needed for control; useful only if the integration
localizes labels.

```json
[{"id":"en","Descripcion":"English"},{"id":"es","Descripcion":"Español"},
 {"id":"it","Descripcion":"Italiano"},{"id":"pt","Descripcion":"Português"},
 {"id":"fr","Descripcion":"Français"}]
```

---

## 10. `GET /Instalacion/{IdInstalacion}/consumo/diario`

Daily energy consumption for an installation, broken down by hour. Note the path uses singular
`Instalacion` and embeds the id in the path (not a query param).

```json
{
  "ConsumoTotalValle": 0.0,        // total off-peak kWh for the day
  "ConsumoTotalPico": 0.0,         // total peak kWh for the day
  "PrecioValle": 0.10, "PrecioPico": 0.15,   // €/kWh off-peak / peak
  "tmInicio": 1783987200000,       // window start: local 00:00 encoded as if it were UTC, epoch ms
  "tmFin": 1784070900000,          // window end, Unix epoch ms
  "detalleConsumo": [
    {"anno":2026,"mes":7,"dia":14,"hora":20,"Temperatura":20.8,"ConsumoValle":0.0,"ConsumoPico":0.0},
    …  // 24 rows, one per hour
  ]
}
```

- `detalleConsumo` — 24 hourly rows (`hora` 0–23). Each carries `ConsumoValle` / `ConsumoPico`
  (off-peak / peak kWh that hour) and `Temperatura` (avg room temp that hour; `0.0` for hours not
  yet reached / no data).
- **Other periods** (verified live): `semanal`, `mensual` and `anual` return the same shape for
  the *current* week/month/year, with `tmInicio`/`tmFin` = `0` and `hora` = `-1`. Rows are keyed
  by `dia` = weekday (1 = Monday … 7 = Sunday; `mes`/`anno` are unreliable) for `semanal`,
  `dia` = day of month for `mensual`, and `mes` for `anual`. `Temperatura` = `0.0` means no data.
  `tmInicio`/`tmFin` for `diario` do not line up exactly with local midnight; rely on the rows.
- No date query param was observed — the capture only fetched "today". A history/range variant may
  exist but is unconfirmed.
- Good source for HA energy-dashboard sensors (daily kWh split by tariff) and cost estimates using
  `PrecioValle` / `PrecioPico`.

---

## 11. Notes for the Home Assistant integration

- **Config flow / auth:** collect email + password → `POST /APIGW/token` (password grant,
  `client_id=AppATC`). Cache the `access_token` and re-auth when it nears the ~20-min expiry
  (try the refresh grant first, fall back to a fresh password login). Store credentials in the HA
  config entry.
- **Discovery flow:** `GET /Instalaciones` → for each, `GET /Radiador?IdInstalacion=&IdZona=0` to
  enumerate devices. One HA `climate` entity per `IdRadiador`.
- **Polling:** `GET /Radiador` is the single source of truth for state. There's no observed push
  channel for us (Firebase pushes go to the app, not to arbitrary clients), so poll on an interval.
- **Write-then-verify:** `PUT` only queues a change (`cnt`), so re-poll to reflect real state; the
  device may lag or reject.
- **`climate` entity mapping (suggested):**
  - `hvac_mode`: `off` if `Encendido=false`, else `heat`.
  - `hvac_action`: `heating` if `Calentando`, else `idle`.
  - `current_temperature`: `TempActual`; `target_temperature`: `TemperaturaConsignaCalculada`
    (or the mode's stored setpoint when editing).
  - `preset_mode`: Comfort / Eco / Anti-frost / Programa (the four `IdModoActual` letters),
    plus a Boost preset driven by `ModoForzado`.
  - Extra entities: keypad-lock switch (`TecladoBloqueado`), open-window binary sensor
    (`VentanasAbiertasStatus`), brightness number (`Brillo`), power-limit number (`LimitePotencia`),
    firmware/`Software` + connectivity (`Err_Offline`) as diagnostics.
- **Still unknown / TODO:**
  1. ~~Refresh-token grant~~ — **confirmed** (decompiled app + verified live). See §1.
  2. Zone-based control semantics (`Zones` in the PUT body).
  3. Whether non-WIFI (hub/gateway) installations use different fields.
  4. Error/failure response shapes (only `200`s captured) — e.g. what `POST /token` returns on bad
     credentials, and what `/api/*` returns on an expired token (presumably `401`).
  5. ~~History~~ — the app uses `…/consumo/{diario|semanal|mensual|anual}`; no arbitrary
     date range exists.
