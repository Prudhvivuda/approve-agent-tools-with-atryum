#!/usr/bin/env python3
"""Seed Atryum for the quickstart via its REST API (stdlib only, idempotent).

Reads seed.json (agents + charters extracted from the ValidMind org template,
demo MCP servers, and the rule set) and drives:

    PUT  /api/v1/servers/<name>     — register the demo MCP servers
    POST /api/v1/llm-configs        — the AI-evaluation judge (user's LLM key)
    POST /api/v1/agents             — the six governed agents, charters included
    POST /api/v1/rules              — approve / evaluate / fallback rule tiers

Safe to re-run: servers are upserts, everything else is matched by name (or by
the [quickstart] description marker for rules) and updated in place.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

ATRYUM = os.environ["ATRYUM_URL"].rstrip("/")
DEMO_MCP_BASE = os.environ["DEMO_MCP_BASE"].rstrip("/")
SEED_PATH = os.environ.get("SEED_PATH", "/seed/seed.json")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")


def call(method, path, body=None):
    req = urllib.request.Request(
        f"{ATRYUM}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} -> {e.code}: {detail}") from None


def wait_healthy(timeout=300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{ATRYUM}/healthz", timeout=5) as r:
                if r.status == 200:
                    print(f"Atryum is healthy at {ATRYUM}")
                    return
        except Exception as e:
            print(f"waiting for Atryum ({e})")
        time.sleep(5)
    sys.exit(f"Atryum did not become healthy within {timeout}s")


def seed_servers(seed):
    for s in seed["servers"]:
        body = {
            "mode": s["mode"],
            "base_url": f"{DEMO_MCP_BASE}{s['path']}",
            "enabled": True,
        }
        call("PUT", f"/api/v1/servers/{s['name']}", body)
        print(f"server {s['name']} -> {body['base_url']}")


def seed_llm_config(seed):
    name = seed["llm_config_name"]
    body = {
        "name": name,
        "provider": LLM_PROVIDER,
        "model": LLM_MODEL,
        "api_key": LLM_API_KEY,
        "base_url": LLM_BASE_URL,
        "enabled": True,
    }
    _, existing = call("GET", "/api/v1/llm-configs")
    for cfg in existing.get("items", []):
        if cfg["name"] == name:
            call("PATCH", f"/api/v1/llm-configs/{cfg['id']}", body)
            print(f"llm-config {name} updated ({LLM_PROVIDER}/{LLM_MODEL})")
            return cfg["id"]
    _, created = call("POST", "/api/v1/llm-configs", body)
    print(f"llm-config {name} created ({LLM_PROVIDER}/{LLM_MODEL})")
    return created["id"]


def seed_agents(seed):
    _, existing = call("GET", "/api/v1/agents")
    by_name = {a["name"]: a for a in existing.get("items", [])}
    for a in seed["agents"]:
        body = {
            "name": a["name"],
            "description": a["description"],
            "enabled": True,
            "agent_ids": a["agent_ids"],
            "charter": a["charter"],
            "tags": a["tags"],
        }
        if a["name"] in by_name:
            agent_id = by_name[a["name"]]["cuid"]
            patch = dict(body)
            patch["enabled"] = True
            call("PATCH", f"/api/v1/agents/{agent_id}", patch)
            print(f"agent {a['name']} updated")
        else:
            call("POST", "/api/v1/agents", body)
            print(f"agent {a['name']} created")


def seed_rules(seed, llm_config_id):
    _, existing = call("GET", "/api/v1/rules")
    by_desc = {r.get("description"): r for r in existing.get("items", [])}
    for r in seed["rules"]:
        body = {
            "action": r["action"],
            "server_patterns": r["server_patterns"],
            "tool_patterns": r["tool_patterns"],
            "agent_cuids": r["agent_cuids"],
            "description": r["description"],
            "enabled": True,
        }
        if r["action"] == "ai_evaluation":
            body["atryum_llm_config_id"] = llm_config_id
        if r["description"] in by_desc:
            call("PUT", f"/api/v1/rules/{by_desc[r['description']]['id']}", body)
            print(f"rule updated: {r['description']}")
        else:
            call("POST", "/api/v1/rules", body)
            print(f"rule created: {r['description']}")


def main():
    seed = json.load(open(SEED_PATH))
    wait_healthy()
    seed_servers(seed)
    llm_config_id = seed_llm_config(seed)
    seed_agents(seed)
    seed_rules(seed, llm_config_id)
    print("Atryum is configured.")


if __name__ == "__main__":
    main()
