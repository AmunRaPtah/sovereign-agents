# ═══════════════════════════════════════════════════════════════════
# SOVEREIGN AGENTS — Modal Engine  (QC-verified build)
# All third-party imports live inside api() so modal deploy works
# from a-Shell where only `modal` is installed locally.
# ═══════════════════════════════════════════════════════════════════

import modal
import os
from pathlib import Path

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


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("sovereign-agents-secrets")],
    timeout=600,
    scaledown_window=300,
)
@modal.asgi_app()
def api():
    import yaml
    import google.generativeai as genai
    from fastapi import FastAPI, HTTPException, BackgroundTasks
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    from supabase import create_client

    web_app = FastAPI(title="Sovereign Agents API")
    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
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

    # safe_generate: Gemini primary, Mistral fallback on 429/quota errors.
    def safe_generate_mistral(prompt: str) -> str:
        mistral_key = os.environ.get("MISTRAL_API_KEY", "")
        if not mistral_key:
            return "Mistral fallback unavailable: MISTRAL_API_KEY not set in Modal secrets."
        try:
            import httpx
            resp = httpx.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {mistral_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "mistral-small-latest",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2048,
                    "temperature": 0.7,
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return f"Mistral fallback error: {str(e)[:200]}"

    def safe_generate(model, prompt: str) -> str:
        try:
            resp = model.generate_content(prompt)
            return resp.text.strip()
        except ValueError:
            return (
                "I was unable to generate a response for this turn. "
                "The content may have triggered a safety filter. "
                "Please rephrase the input and try again."
            )
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower() or "ResourceExhausted" in err:
                return safe_generate_mistral(prompt)
            return f"API error on this turn: {err[:200]}"

    def extract_final_output(turns: list, stop: str) -> str:
        if not turns:
            return ""
        for t in reversed(turns):
            content = t["content"]
            upper   = content.upper()
            stop_up = stop.upper()
            if stop_up in upper:
                idx = upper.rfind(stop_up)
                pre = content[:idx].strip()
                if pre:
                    return pre
            else:
                return content
        return turns[-1]["content"]

    # ── Debate engine ──────────────────────────────────────────────
    def run_debate(config: dict, user_input: str) -> dict:
        model    = get_model()
        a_name   = config["agent_a"]["name"]
        b_name   = config["agent_b"]["name"]
        a_role   = config["agent_a"]["persona"]
        b_role   = config["agent_b"]["persona"]
        task     = config["task_template"].replace("{input}", user_input)
        fmt      = config.get("output_format", "")
        max_turns = config.get("max_turns", 8)
        stop     = config.get("termination_word", "TERMINATE")

        fmt_reminder = (
            f"\n\nRequired output format (maintain this throughout):\n{fmt}"
            if fmt else ""
        )

        history, turns = [], []
        terminated     = False

        initial_task = f"{task}{fmt_reminder}"
        current_critique = ""

        for n in range(max_turns):

            hist_block = (
                "\n\n".join(f"[{t['agent']}]:\n{t['content']}" for t in history)
                if history else "Opening of session."
            )

            if n == 0:
                task_section = f"YOUR TASK:\n{initial_task}"
            else:
                task_section = (
                    f"ORIGINAL TASK (maintain this output format):\n{initial_task}"
                    f"\n\nCRITIQUE TO ADDRESS:\n{current_critique}"
                )

            prompt_a = (
                f"You are {a_name}.\n\nROLE:\n{a_role}\n\n"
                f"CONVERSATION SO FAR:\n{hist_block}\n\n"
                f"{task_section}\n\n"
                f"If work is fully validated and complete with all format requirements "
                f"met, output the single word {stop} on its own line at the end. "
                f"Otherwise produce your full response."
            )

            content_a = safe_generate(model, prompt_a)
            history.append({"agent": a_name, "content": content_a})
            turns.append({
                "agent": a_name, "role": "builder",
                "content": content_a, "turn": n * 2 + 1
            })

            if stop.upper() in content_a.upper():
                terminated = True
                break

            hist_block = "\n\n".join(
                f"[{t['agent']}]:\n{t['content']}" for t in history
            )
            prompt_b = (
                f"You are {b_name}.\n\nROLE:\n{b_role}\n\n"
                f"CONVERSATION SO FAR:\n{hist_block}\n\n"
                f"You are reviewing {a_name}'s latest response. "
                f"Apply maximum critical rigour. Provide specific numbered critiques.\n\n"
                f"If everything is fully validated with zero remaining issues, "
                f"output the single word {stop} on its own line."
            )

            content_b = safe_generate(model, prompt_b)
            history.append({"agent": b_name, "content": content_b})
            turns.append({
                "agent": b_name, "role": "critic",
                "content": content_b, "turn": n * 2 + 2
            })
            current_critique = content_b

            if stop.upper() in content_b.upper():
                terminated = True
                break

        final = extract_final_output(turns, stop)

        return {
            "turns": turns,
            "final_output": final,
            "terminated": terminated,
            "total_turns": len(turns),
            "verification_status": "VERIFIED" if terminated else "MAX_TURNS_REACHED",
        }

    # ── Background task: runs debate and updates Supabase row ──────
    def _run_and_save(config: dict, user_input: str, session_id: str, tags: list):
        try:
            result = run_debate(config, user_input)
            get_supabase().table("agent_sessions").update({
                "agent_turns":         result["turns"],
                "final_output":        result["final_output"],
                "verification_status": result["verification_status"],
                "total_turns":         result["total_turns"],
            }).eq("id", session_id).execute()
        except Exception as e:
            try:
                get_supabase().table("agent_sessions").update({
                    "verification_status": "ERROR",
                    "final_output":        f"Engine error: {str(e)[:300]}",
                    "total_turns":         0,
                }).eq("id", session_id).execute()
            except Exception:
                pass

    # ── Routes ─────────────────────────────────────────────────────
    @web_app.get("/")
    async def root():
        return {"status": "online", "service": "Sovereign Agents API"}

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

    # Fire-and-forget: inserts a PENDING row immediately, runs debate
    # in a FastAPI background task so the mobile connection never hangs.
    @web_app.post("/run")
    async def run_session(req: RunRequest, background_tasks: BackgroundTasks):
        try:
            config = load_config(req.config_name)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

        try:
            sb  = get_supabase()
            row = sb.table("agent_sessions").insert({
                "config_name":         req.config_name,
                "input_text":          req.input,
                "tags":                req.tags,
                "verification_status": "PENDING",
                "final_output":        "",
                "agent_turns":         [],
                "total_turns":         0,
            }).execute()
            session_id = row.data[0]["id"]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Session init failed: {str(e)[:200]}")

        background_tasks.add_task(_run_and_save, config, req.input, session_id, req.tags)

        return {"session_id": session_id, "status": "pending"}

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
        try:
            sb = get_supabase()
            return (
                sb.table("agent_sessions")
                .select("*")
                .eq("id", session_id)
                .single()
                .execute()
                .data
            )
        except Exception as e:
            raise HTTPException(status_code=404, detail="Session not found.")

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
            f"Input: {(s.get('input_text') or '')[:400]}\n"
            f"Output: {(s.get('final_output') or '')[:800]}"
            for s in sessions
        )
        prompt = (
            f"You are a Pattern Recognition and Knowledge Synthesis engine.\n\n"
            f"TOPIC: {req.topic}\n\n"
            f"SESSIONS ({len(sessions)} total):\n{body}\n\n"
            "Output exactly this structure:\n"
            "### Recurring Patterns\n"
            "### Contradictions and Tensions\n"
            "### Emergent Conclusions\n"
            "### Remaining Knowledge Gaps\n"
            "### Recommended Next Directions (5 items, ranked by leverage)"
        )
        try:
            model    = get_model()
            response = model.generate_content(prompt)
            synthesis_text = response.text
        except Exception as e:
            synthesis_text = f"Synthesis error: {str(e)[:200]}"

        return {
            "synthesis":     synthesis_text,
            "session_count": len(sessions),
            "topic":         req.topic,
        }

    return web_app
