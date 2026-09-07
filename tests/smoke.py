"""Exercise a disposable HA instance through real HTTP and WebSocket APIs.

Run only against a fresh test container. Creates a local test administrator.
The instance must identify itself as 'Bohu Test'; never target a real HA home.
"""

import argparse
import asyncio
import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp


async def run(
    base_url: str, state_file: Path, payload_file: Path | None, restart: bool
):
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        token = None

        async def request(method, path, *, expected=200, **kwargs):
            headers = kwargs.pop("headers", {})
            if token is not None:
                headers["Authorization"] = f"Bearer {token}"
            async with session.request(
                method, base_url + path, headers=headers, **kwargs
            ) as response:
                body = await response.text()
                assert response.status == expected, (
                    method,
                    path,
                    response.status,
                    body,
                )
                return (
                    json.loads(body)
                    if response.content_type == "application/json"
                    else body
                )

        if state_file.exists():
            state = json.loads(state_file.read_text())
            token = state["token"]
        else:
            # An existing installation must never be modified by this test script.
            onboarding = await request("GET", "/api/onboarding")
            assert not any(item["done"] for item in onboarding), (
                "Use a fresh disposable HA instance"
            )
            password = secrets.token_urlsafe(24)
            created = await request(
                "POST",
                "/api/onboarding/users",
                json={
                    "name": "Bohu Test",
                    "username": "bohu-test",
                    "password": password,
                    "client_id": base_url + "/",
                    "language": "en",
                },
            )
            auth = await request(
                "POST",
                "/auth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": created["auth_code"],
                    "client_id": base_url + "/",
                },
            )
            token = auth["access_token"]
            state = {"token": token, "password": password}
            state_file.write_text(json.dumps(state))
            await request("POST", "/api/onboarding/core_config", json={})
            await request("POST", "/api/onboarding/analytics", json={})
            await request(
                "POST",
                "/api/onboarding/integration",
                json={
                    "client_id": base_url + "/",
                    "redirect_uri": base_url + "/?auth_callback=1",
                },
            )

        config = await request("GET", "/api/config")
        assert config["location_name"] == "Bohu Test", (
            "Refusing to modify a non-test HA instance"
        )
        print(f"Home Assistant {config['version']}", flush=True)

        async with session.ws_connect(base_url + "/api/websocket") as ws:
            assert (await ws.receive_json())["type"] == "auth_required"
            await ws.send_json({"type": "auth", "access_token": token})
            assert (await ws.receive_json())["type"] == "auth_ok"
            message_id = 0

            async def command(kind, **kwargs):
                nonlocal message_id
                message_id += 1
                await ws.send_json({"id": message_id, "type": kind, **kwargs})
                response = await ws.receive_json()
                assert response["id"] == message_id and response["success"], response
                return response["result"]

            async def wait_loaded(entry_id):
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    entries = await command("config_entries/get", domain="bohu")
                    if any(
                        e["entry_id"] == entry_id and e["state"] == "loaded"
                        for e in entries
                    ):
                        return
                    await asyncio.sleep(0.2)
                raise AssertionError("Integration did not load")

            async def create_device(name):
                flow = await request(
                    "POST",
                    "/api/config/config_entries/flow",
                    json={"handler": "bohu", "show_advanced_options": False},
                )
                assert flow["step_id"] == "user", flow
                address_field = next(
                    f for f in flow["data_schema"] if f["name"] == "base_url"
                )
                assert address_field["default"] == config["internal_url"], address_field
                flow_path = "/api/config/config_entries/flow/" + flow["flow_id"]
                invalid = await request(
                    "POST", flow_path, json={"name": name, "base_url": "http://ha/api"}
                )
                assert invalid["errors"] == {"base_url": "invalid_url"}, invalid
                finish = await request(
                    "POST", flow_path, json={"name": name, "base_url": base_url}
                )
                assert finish["step_id"] == "finish", finish
                url = finish["description_placeholders"]["url"]
                result = await request("POST", flow_path, json={})
                assert result["type"] == "create_entry", result
                entry_id = result["result"]["entry_id"]
                await wait_loaded(entry_id)
                return entry_id, urlsplit(url).path

            async def entities_for(entry_id):
                registry = await command("config/entity_registry/list")
                return {
                    e["unique_id"].removeprefix(entry_id + "_"): e["entity_id"]
                    for e in registry
                    if e["config_entry_id"] == entry_id
                }

            async def options(entry_id):
                return await request(
                    "POST",
                    "/api/config/config_entries/options/flow",
                    json={"handler": entry_id},
                )

            payload = (
                json.loads(payload_file.read_bytes())
                if payload_file
                else {
                    "method": "update",
                    "did": "demo0001",
                    "WeatherType": "0",
                    "T": "23",
                    "H": "59",
                    "HCHO": "0.138",
                    "VOC": "0.283",
                    "C6H6": "0.043",
                }
            )
            body = json.dumps(payload).encode()
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            if restart:
                entry_id, path = state["entry_id"], state["path"]
                await wait_loaded(entry_id)
                settings = await options(entry_id)
                assert (
                    urlsplit(settings["description_placeholders"]["url"]).path == path
                )
                assert settings["description_placeholders"]["did"] == payload["did"]
                assert await request("POST", path, data=body, headers=headers) == "OK\n"
                print(
                    "PASS: URL and device ID binding survive container restart",
                    flush=True,
                )
                return

            entry_id, path = await create_device("Living room")
            state.update(entry_id=entry_id, path=path)
            state_file.write_text(json.dumps(state))
            entities = await entities_for(entry_id)
            assert len(entities) == 6, entities
            devices = await command("config/device_registry/list")
            assert len([d for d in devices if entry_id in d["config_entries"]]) == 1
            for entity_id in entities.values():
                assert (await request("GET", "/api/states/" + entity_id))[
                    "state"
                ] == "unavailable"
            print(
                "PASS: UI flow creates a device and six entities before the first report",
                flush=True,
            )

            # A malformed first report must not bind a device ID.
            await request(
                "POST",
                path,
                data=b'{"method":"update","did":"wrong"}',
                headers=headers,
                expected=400,
            )
            assert (await options(entry_id))["description_placeholders"]["did"] == "—"
            assert await request("POST", path, data=body, headers=headers) == "OK\n"
            for key in ("T", "H", "HCHO", "VOC", "C6H6"):
                result = await request("GET", "/api/states/" + entities[key])
                assert float(result["state"]) == float(payload[key]), result
                if key in ("HCHO", "VOC", "C6H6"):
                    assert result["attributes"]["unit_of_measurement"] == "mg/m³", (
                        result
                    )
            assert (await options(entry_id))["description_placeholders"][
                "did"
            ] == payload["did"]
            print(
                "PASS: real-format upload binds ID and updates all five numeric sensors",
                flush=True,
            )

            await request(
                "POST",
                path,
                data=json.dumps({**payload, "did": "different"}),
                headers=headers,
                expected=409,
            )
            for bad in (
                b"{",
                b"[]",
                b"\xff",
                json.dumps({**payload, "HCHO": "NaN"}).encode(),
            ):
                await request("POST", path, data=bad, headers=headers, expected=400)
            await request("POST", path, data=b" " * 4097, headers=headers, expected=413)
            await request("GET", path, expected=405)

            # Check a chunked upload as well as Content-Length requests.
            async def chunks():
                yield body[:15]
                yield body[15:]

            assert await request("POST", path, data=chunks(), headers=headers) == "OK\n"
            print(
                "PASS: malformed, oversized and mismatched reports rejected; chunked upload accepted",
                flush=True,
            )

            other_id, other_path = await create_device("Bedroom")
            assert other_path != path
            await request("POST", other_path, data=body, headers=headers, expected=409)
            await request(
                "POST",
                other_path,
                data=json.dumps({**payload, "did": "demo0002", "T": "18"}),
                headers=headers,
            )
            other_entities = await entities_for(other_id)
            assert (
                float(
                    (await request("GET", "/api/states/" + other_entities["T"]))[
                        "state"
                    ]
                )
                == 18
            )
            assert float(
                (await request("GET", "/api/states/" + entities["T"]))["state"]
            ) == float(payload["T"])
            print(
                "PASS: multiple devices isolated and duplicate hardware ID rejected",
                flush=True,
            )

            flow = await options(entry_id)
            opt_path = "/api/config/config_entries/options/flow/" + flow["flow_id"]
            finish = await request(
                "POST",
                opt_path,
                json={"base_url": base_url, "gas_unit": "µg/m³", "timeout": 10},
            )
            assert urlsplit(finish["description_placeholders"]["url"]).path == path
            await request("POST", opt_path, json={})
            # Explicit reload also exercises registered webhook/expiry cleanup.
            await request(
                "POST", f"/api/config/config_entries/entry/{entry_id}/reload", json={}
            )
            await wait_loaded(entry_id)
            assert await entities_for(entry_id) == entities
            await request("POST", path, data=body, headers=headers)
            gas = await request("GET", "/api/states/" + entities["HCHO"])
            assert gas["attributes"]["unit_of_measurement"] == "µg/m³"
            assert float(gas["state"]) == float(payload["HCHO"])
            await asyncio.sleep(6)
            await request("POST", path, data=b"{}", headers=headers, expected=400)
            await asyncio.sleep(5)
            for key in ("T", "H", "HCHO", "VOC", "C6H6"):
                assert (await request("GET", "/api/states/" + entities[key]))[
                    "state"
                ] == "unavailable"
            assert (await request("GET", "/api/states/" + entities["last_seen"]))[
                "state"
            ] != "unavailable"
            await request("POST", path, data=body, headers=headers)
            assert float(
                (await request("GET", "/api/states/" + entities["T"]))["state"]
            ) == float(payload["T"])
            print(
                "PASS: options, reload, stable entity IDs, timeout and recovery",
                flush=True,
            )

            await request("DELETE", f"/api/config/config_entries/entry/{other_id}")
            # HA returns 200 for an unknown webhook by design, but it has no effect.
            await request("POST", other_path, data=body, headers=headers)
            assert not await entities_for(other_id)
            print(
                "PASS: removing a device cleans up its entities and receiving handler",
                flush=True,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8123")
    parser.add_argument(
        "--state",
        type=Path,
        required=True,
        help="Private test credential file, outside the repository",
    )
    parser.add_argument("--payload-file", type=Path)
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.url, args.state, args.payload_file, args.restart))
