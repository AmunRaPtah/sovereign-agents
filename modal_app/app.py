# ═══════════════════════════════════════════════════════════════════
# SOVEREIGN AGENTS — Modal Engine
# All third-party imports are INSIDE the api() function.
# This means modal deploy works from a-Shell with ONLY modal installed.
# ═══════════════════════════════════════════════════════════════════

import modal
import os
from pathlib import Path

# ─── MODAL APP SETUP ─────────────────────────────────────────────
app = modal.App("sovereign-agents")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install([
        "google-generativeai>=0.8.0",
        "supabase>=2.4.0",
        "pyyaml>=6.0",
        "fastapi>=0.110.0",
        "pydantic>=2.0.0",
        "httpx>=0.27.0",
    ])
    .add_local_dir("./configs", remote_path="/configs")
)

# ─── ENTRYPOINT ───────────────────────────────────────────────────
# ALL third-party imports live here so they only run in the container,
# never in a-Shell where they are not installed.

@app.function(
    image=image,
    secrets=[modal.Secret.from_name("sovereign-agents-secrets")],
    timeout=600,
    container_idle_timeout=300,
)
@modal.asgi_app()
def api():
    import yaml
    import google.generativeai as genai
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    from supabase import create_client

    # ── FastAPI app ────────────────────────────────────────────────
    web_app = FastAPI(title="Sovereign Agents API")
    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Pydantic models ────────────────────────────────────────────
    class RunRequest(BaseModel):
        config_name: str
        input: str
        tags: list[str] = []

    class SynthesisRequest(BaseModel):
        topic: str
        config_filter: str = None
        session_limit: int = 50

    # ── Helpers ────────────────────────────────────────────────────
    def get_supabase():
        return create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
        )

    def load_config(name: str) -> dict:
        p = Path("/configs") / f"{name}.yaml"
        if not p.exists():
            raise FileNotFoundError(f"Config '{name}' not found.")
        with open(p) as f:
            return yaml.safe_load(f)

    def get_model():
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        return genai.GenerativeModel(
            "gemini-2.0-flash",
            generation_config=genai.GenerationConfig(
                temperature=0.7,
                max_output_tokens=2048,
            ),
        )

    # ── Debate engine ──────────────────────────────────────────────
    def run_debate(config: dict, user_input: str) -> dict:
        model     = get_model()
        a_name    = config["agent_a"]["name"]
        b_name    = config["agent_b"]["name"]
        a_role    = config["agent_a"]["persona"]
        b_role    = config["agent_b"]["persona"]
        task      = config["task_template"].replace("{input}", user_input)
        fmt       = config.get("output_format", "")
        max_turns = config.get("max_turns", 8)
        stop      = config.get("termination_word", "TERMINATE")

        history, turns = [], []
        terminated     = False
        current_msg    = f"{task}\n\nRequired output format:\n{fmt}" if fmt else task

        for n in range(max_turns):

            # Agent A
            hist_block = (
                "\n\n".join(f"[{t['agent']}]:\n{t['content']}" for t in history)
                if history else "Opening of session."
            )
            prompt_a = (
                f"You are {a_name}.\n\nROLE:\n{a_role}\n\n"
                f"CONVERSATION SO FAR:\n{hist_block}\n\n"
                f"RESPOND TO:\n{current_msg}\n\n"
                f"If work is fully validated and complete, output the single word "
                f"{stop} on its own line. Otherwise continue."
            )
            content_a = model.generate_content(prompt_a).text.strip()
            history.append({"agent": a_name, "content": content_a})
            turns.append({"agent": a_name, "role": "builder",
                          "content": content_a, "turn": n * 2 + 1})

            if stop.upper() in content_a.upper():
                terminated = True
                break

            # Agent B
            hist_block = "\n\n".join(
                f"[{t['agent']}]:\n{t['content']}" for t in history
            )
            prompt_b = (
                f"You are {b_name}.\n\nROLE:\n{b_role}\n\n"
                f"CONVERSATION SO FAR:\n{hist_block}\n\n"
                f"You are reviewing {a_name}'s latest response. "
                f"Apply maximum critical rigour. Provide numbered critiques.\n\n"
                f"If everything is fully validated with zero remaining issues, "
                f"output the single word {stop} on its own line."
            )
            content_b = model.generate_content(prompt_b).text.strip()
            history.append({"agent": b_name, "content": content_b})
            turns.append({"agent": b_name, "role": "critic",
                          "content": content_b, "turn": n * 2 + 2})
            current_msg = content_b

            if stop.upper() in content_b.upper():
                terminated = True
                break

        # Last substantive turn before TERMINATE
        final = next(
            (t["content"] for t in reversed(turns)
             if stop.upper() not in t["content"].upper()),
            turns[-1]["content"] if turns else "",
        )

        return {
            "turns": turns,
            "final_output": final,
            "terminated": terminated,
            "total_turns": len(turns),
            "verification_status": "VERIFIED" if terminated else "MAX_TURNS_REACHED",
        }

    # ── Routes ─────────────────────────────────────────────────────
    @web_app.get("/health")
    async def health():
        return {"status": "online"}

    @web_app.get("/configs")
    async def list_configs():
        out = []
        for f in sorted(Path("/configs").glob("*.yaml")):
            with open(f) as fh:
                c = yaml.safe_load(fh)
            out.append({
                "name":        c["name"],
                "description": c.get("description", ""),
                "agent_a":     c["agent_a"]["name"],
                "agent_b":     c["agent_b"]["name"],
                "category":    c.get("category", "general"),
                "special":     c.get("special", False),
            })
        return {"configs": out}

    @web_app.post("/run")
    async def run_session(req: RunRequest):
        try:
            config = load_config(req.config_name)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

        result = run_debate(config, req.input)

        sb  = get_supabase()
        row = {
            "config_name":         req.config_name,
            "input_text":          req.input,
            "agent_turns":         result["turns"],
            "final_output":        result["final_output"],
            "verification_status": result["verification_status"],
            "tags":                req.tags,
            "total_turns":         result["total_turns"],
        }
        saved      = sb.table("agent_sessions").insert(row).execute()
        session_id = saved.data[0]["id"] if saved.data else None

        return {
            "session_id":          session_id,
            "config_name":         req.config_name,
            "final_output":        result["final_output"],
            "turns":               result["turns"],
            "verification_status": result["verification_status"],
            "total_turns":         result["total_turns"],
        }

    @web_app.get("/sessions")
    async def get_sessions(config_name: str = None, limit: int = 30):
        sb = get_supabase()
        q  = (
            sb.table("agent_sessions")
            .select("id,created_at,config_name,final_output,verification_status,tags,total_turns")
            .order("created_at", desc=True)
            .limit(limit)
        )
        if config_name:
            q = q.eq("config_name", config_name)
        return {"sessions": q.execute().data}

    @web_app.get("/sessions/{session_id}")
    async def get_session(session_id: str):
        sb = get_supabase()
        return (
            sb.table("agent_sessions")
            .select("*")
            .eq("id", session_id)
            .single()
            .execute()
            .data
        )

    @web_app.post("/synthesize")
    async def synthesize(req: SynthesisRequest):
        sb = get_supabase()
        q  = (
            sb.table("agent_sessions")
            .select("config_name,input_text,final_output,created_at,tags,verification_status")
            .order("created_at", desc=True)
            .limit(req.session_limit)
        )
        if req.config_filter:
            q = q.eq("config_name", req.config_filter)
        sessions = q.execute().data

        if not sessions:
            return {"synthesis": "No sessions yet.", "session_count": 0}

        body = "\n\n---\n\n".join(
            f"Config: {s['config_name']} | {s['created_at'][:10]} | {s['verification_status']}\n"
            f"Input: {s['input_text'][:400]}\n"
            f"Output: {s['final_output'][:800]}"
            for s in sessions
        )
        prompt = (
            f"You are a Pattern Recognition and Knowledge Synthesis engine.\n\n"
            f"TOPIC: {req.topic}\n\n"
            f"SESSIONS ({len(sessions)}):\n{body}\n\n"
            "Output exactly:\n"
            "### Recurring Patterns\n"
            "### Contradictions and Tensions\n"
            "### Emergent Conclusions\n"
            "### Remaining Knowledge Gaps\n"
            "### Recommended Next Directions (5 ranked by leverage)"
        )
        model    = get_model()
        response = model.generate_content(prompt)
        return {"synthesis": response.text, "session_count": len(sessions), "topic": req.topic}

    return web_app
