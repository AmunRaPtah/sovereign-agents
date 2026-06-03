# SOVEREIGN AGENTS — SESSION HANDOVER

Use this prompt at the start of any future session to restore full context.

---

## PASTE THIS INTO NEW SESSIONS

```
I have a deployed multi-agent research system called Sovereign Agents.
Here is the full technical context. Help me [describe your task].

SYSTEM OVERVIEW
A two-agent adversarial debate system (Builder + Critic) that validates
mathematics, reviews literature, writes grants, scouts IP, and runs
strategy analysis across 12 pre-built configs. All from a phone browser.

LIVE URLS
UI (Netlify):    [get from Netlify dashboard — bookmark it]
Backend (Modal): https://ennyolutogun--sovereign-agents-api.modal.run
GitHub repo:     https://github.com/AmunRaPtah/sovereign-agents

ARCHITECTURE
  Phone browser → Netlify UI (index.html)
                → Modal backend (app.py, FastAPI + Gemini 2.0 Flash)
                → Supabase (stores all sessions permanently)
  GitHub push to modal_app/ → GitHub Actions auto-deploys to Modal

CREDENTIALS (all stored in Claude memory and Modal secrets)
  Modal workspace:       ennyolutogun
  Modal Token ID:        ak-b6kzvsCo9NxANlZ195kobQ
  Modal Token Secret:    YOUR_MODAL_TOKEN_SECRET
  Modal secret name:     sovereign-agents-secrets (holds Gemini + Supabase keys)
  Gemini API key:        YOUR_GEMINI_KEY
  Mistral API key:       YOUR_MISTRAL_KEY
  Supabase project:      byhryzouspgfrfowatej
  Supabase URL:          https://byhryzouspgfrfowatej.supabase.co
  Supabase service key:  YOUR_SUPABASE_SERVICE_KEY
  GitHub PAT:            YOUR_GITHUB_PAT (AmunRaPtah)

FILE STRUCTURE (GitHub repo)
  modal_app/
    app.py                    core engine — Modal 1.x, FastAPI, all imports inside api()
    requirements.txt
    configs/                  12 YAML files, one per use case
      cct_math_validator      CCT ODEs, propagation math, simulation
      biomath_full            any drug discovery mathematics
      lit_review_deep         novelty audit, gap mapping, research directions
      drug_discovery_full     target → ADMET → CCT → clinical
      grant_architect         proposal structure and narrative
      grant_refiner           hostile reviewer simulation + scoring
      ip_scout                protectable elements + FTO analysis
      competitive_intel       moat, positioning, landscape
      business_strategy       GTM, critical path, first action
      writing_refiner         any draft to publication standard
      amr_interpreter         genomics → clinical → public health
      memory_synthesis        cross-session pattern synthesis
  netlify_ui/
    index.html                single-file frontend, dark theme, marked.js markdown
  supabase/
    schema.sql                agent_sessions table + indexes + views
  .github/workflows/
    deploy.yml                auto-deploys on push to modal_app/**

SUPABASE DATA
  Table: agent_sessions
  Columns: id, created_at, config_name, input_text, agent_turns (JSONB),
           final_output, verification_status, tags, total_turns
  Views: sessions_summary, config_usage_stats
  Access: Supabase dashboard → Table Editor → agent_sessions

HOW DEPLOYMENTS WORK
  Any edit to modal_app/ on GitHub triggers auto-deploy via GitHub Actions.
  Edit a config YAML on GitHub mobile → commit → Modal redeploys in ~60s.
  No terminal, no a-Shell required ever again.
  Watch deploys at: https://github.com/AmunRaPtah/sovereign-agents/actions

HOW TO MAKE CHANGES

  ADD / MODIFY A CONFIG:
  1. Go to github.com/AmunRaPtah/sovereign-agents/tree/main/modal_app/configs
  2. Tap the config file to edit, or tap + to create new one
  3. Follow the YAML structure of any existing config (name, description,
     category, agent_a/b with name+persona, task_template, output_format,
     max_turns, termination_word)
  4. Commit. Deploy runs automatically.

  MODIFY THE DEBATE ENGINE (app.py):
  1. Edit modal_app/app.py on GitHub
  2. Key functions: run_debate(), safe_generate(), extract_final_output()
  3. All third-party imports MUST stay inside api() function — never at
     module level. This is required for Modal 1.x phone-only deploy.
  4. Use scaledown_window=, not container_idle_timeout= (Modal 1.x breaking change)

  UPDATE THE FRONTEND (index.html):
  1. Edit netlify_ui/index.html on GitHub
  2. Netlify auto-redeploys on any push to main (no paths filter on netlify)
  3. MODAL_URL constant at top of script block — already set correctly

  ADD A NEW API KEY TO MODAL SECRETS:
  1. Go to modal.com → Secrets → sovereign-agents-secrets → Edit
  2. Add key-value pair
  3. Redeploy (push any change to modal_app/ or trigger manually)

KNOWN ISSUES RESOLVED
  - Modal 1.x breaking change: container_idle_timeout removed, use scaledown_window
  - All third-party imports inside api() to allow modal deploy from minimal environments
  - Gemini safety blocks: wrapped in safe_generate() with ValueError catch
  - TERMINATE extraction: extract_final_output() strips suffix, preserves content
  - Output format lost after turn 1: fmt_reminder injected into every Agent A prompt
  - Markdown rendering: marked.js CDN in frontend, md-render class on all output panels

NEXT PLANNED FEATURES
  - Multi-model: Agent A on Gemini, Agent B on Mistral (adversarial diversity)
  - Key rotation: fallback chain across multiple API keys
  - project_config Supabase table: needs one SQL create statement run in dashboard
  - Groq integration for faster Agent B turns

MODEL CONTEXT
  Primary LLM: gemini-2.0-flash (free, 1M tokens/day)
  Mistral key available for multi-model upgrade when ready
  Agent debate: max 8 turns, TERMINATE protocol, safe_generate wrapper
```

---

## QUICK REFERENCE FOR COMMON TASKS

**"I want to change how a config behaves"**
Edit the YAML file on GitHub. Change agent personas, task_template, output_format,
or max_turns. Commit. Done.

**"I want a new config for [use case]"**
Ask Claude to write a new YAML following the existing structure, then push to
github.com/AmunRaPtah/sovereign-agents/tree/main/modal_app/configs

**"The deploy failed"**
Check https://github.com/AmunRaPtah/sovereign-agents/actions for the error.
Common causes: syntax error in YAML or app.py, new Modal breaking change.

**"I want to see my past sessions"**
Supabase dashboard → Table Editor → agent_sessions
Or use the History tab in the UI.

**"I want to add Mistral / Groq as Agent B"**
Tell Claude: modify app.py to support per-agent model config from YAML,
add MISTRAL_API_KEY / GROQ_API_KEY to Modal secrets, update affected configs.

**"The UI is broken / not loading configs"**
Check that https://ennyolutogun--sovereign-agents-api.modal.run/health returns
{"status": "online"}. If not, check Modal dashboard for deploy errors.
