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
    from fastapi import FastAPI, HTTPException
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

    # BUG FIX 1 + 2: safe_generate wraps .text access so a safety-blocked
    # or empty response never crashes the loop. Returns a fallback string.
    def safe_generate(model, prompt: str) -> str:
        try:
            resp = model.generate_content(prompt)
            # .text raises ValueError if response was blocked or parts are empty
            return resp.text.strip()
        except ValueError:
            # Safety block or empty response — return a structured fallback
            return (
                "I was unable to generate a response for this turn. "
                "The content may have triggered a safety filter. "
                "Please rephrase the input and try again."
            )
        except Exception as e:
            return f"API error on this turn: {str(e)[:200]}"

    # BUG FIX 2: extract the final substantive output correctly.
    # Agents often write "[full answer]\nTERMINATE" in one response.
    # Old code skipped the whole turn. This version strips the TERMINATE
    # suffix and returns whatever precedes it.
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
                # TERMINATE was the only content — continue to previous turn
            else:
                return content
        # All turns had only TERMINATE — return last turn content anyway
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

        # BUG FIX 3: build a persistent format reminder injected into every
        # Agent A prompt so the required structure is never lost after turn 1.
        fmt_reminder = (
            f"\n\nRequired output format (maintain this throughout):\n{fmt}"
            if fmt else ""
        )

        history, turns = [], []
        terminated     = False

        # First message to Agent A: the full task + format
        initial_task = f"{task}{fmt_reminder}"
        current_critique = ""  # Agent B's latest critique (empty on turn 1)

        for n in range(max_turns):

            # ── Agent A ───────────────────────────────────────────
            hist_block = (
                "\n\n".join(f"[{t['agent']}]:\n{t['content']}" for t in history)
                if history else "Opening of session."
            )

            # BUG FIX 3: always include the task + format reminder in Agent A's
            # prompt regardless of turn number.
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

            # ── Agent B ───────────────────────────────────────────
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
            current_critique = content_b  # passed back to Agent A next turn

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

    # BUG FIX 6: wrap entire run_debate call so any unexpected exception
    # returns a readable 500 message instead of a bare crash.
    @web_app.post("/run")
    async def run_session(req: RunRequest):
        try:
            config = load_config(req.config_name)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

        try:
            result = run_debate(config, req.input)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Debate engine error: {str(e)[:300]}"
            )

        try:
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
        except Exception:
            # Supabase failure should not prevent returning the result
            session_id = None

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

    # BUG FIX 4: null guards on input_text and final_output in synthesize.
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

        # BUG FIX 4: safe string slicing with null defaults
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
